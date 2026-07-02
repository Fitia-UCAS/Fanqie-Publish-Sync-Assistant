from __future__ import annotations

import json
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from backend.crawling.rate_limit import AdaptiveRateLimiter
from backend.crawling.records import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_REQUEST_DELAY_MAX,
    DEFAULT_REQUEST_DELAY_MIN,
    DEFAULT_TIMEOUT,
)


@dataclass(slots=True)
class HttpPolicy:

    timeout: int = DEFAULT_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES
    delay_min: float = DEFAULT_REQUEST_DELAY_MIN
    delay_max: float = DEFAULT_REQUEST_DELAY_MAX
    headers: dict[str, str] = field(default_factory=dict)
    should_stop: Callable[[], bool] | None = None
    rate_limiter: AdaptiveRateLimiter | None = None


class HttpClient:

    BLOCK_STATUS_CODES = {403, 429, 444}

    def __init__(self, options: HttpPolicy) -> None:
        self.options = options
        self._local = threading.local()
        self._limiter = options.rate_limiter or AdaptiveRateLimiter(
            delay_min=options.delay_min,
            delay_max=options.delay_max,
        )
        self._limiter.configure(delay_min=options.delay_min, delay_max=options.delay_max)

    def get_text(self, url: str, headers: dict[str, str] | None = None) -> str:
        response = self._get(url, headers=headers)
        return self._decode(response)

    def get_json(self, url: str, headers: dict[str, str] | None = None) -> Any:
        return json.loads(self.get_text(url, headers=headers))

    def _get(self, url: str, headers: dict[str, str] | None = None) -> requests.Response:
        self._limiter.wait_before_request(self.options.should_stop)
        try:
            response = self._session().get(url, timeout=self.options.timeout, headers=headers or None)
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout) as exc:
            decision = self._limiter.record_block("连接超时")
            raise TimeoutError(
                f"连接超时，站点限速器退避 {int(decision.seconds)} 秒后继续请求；"
                "这通常表示站点限流、线路阻断或网络不稳定。"
            ) from exc

        if response.status_code in self.BLOCK_STATUS_CODES:
            decision = self._limiter.record_block(f"HTTP {response.status_code}")
            raise requests.HTTPError(
                f"站点拒绝访问（HTTP {response.status_code}），"
                f"已进入冷却 {int(decision.seconds)} 秒后再请求。",
                response=response,
            )

        response.raise_for_status()
        self._limiter.record_success()
        return response

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is not None:
            return session

        session = requests.Session()
        session.headers.update(self.options.headers)
        retry = Retry(
            total=self.options.max_retries,
            connect=self.options.max_retries,
            read=self.options.max_retries,
            status=self.options.max_retries,
            backoff_factor=0.6,
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=("GET",),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=32, pool_maxsize=32)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        self._local.session = session
        return session

    def _sleep(self) -> None:
        if self.options.delay_max <= 0:
            return
        time.sleep(random.uniform(self.options.delay_min, self.options.delay_max))

    @staticmethod
    def _decode(response: requests.Response) -> str:
        raw = response.content
        for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        response.encoding = response.apparent_encoding or "utf-8"
        return response.text
