from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_MAX_WORKERS = 16
DEFAULT_REQUEST_DELAY_MIN = 0.12
DEFAULT_REQUEST_DELAY_MAX = 0.35
DEFAULT_TIMEOUT = 25
DEFAULT_MAX_RETRIES = 3
MAX_WORKERS_LIMIT = 24


class CrawlErrorType:

    RATE_LIMITED = "RATE_LIMITED"
    HTTP_ERROR = "HTTP_ERROR"
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    CONNECTION_ERROR = "CONNECTION_ERROR"
    CATALOG_PARSE_ERROR = "CATALOG_PARSE_ERROR"
    API_EMPTY_CONTENT = "API_EMPTY_CONTENT"
    API_PARSE_ERROR = "API_PARSE_ERROR"
    HTML_FALLBACK_FAILED = "HTML_FALLBACK_FAILED"
    FILE_WRITE_ERROR = "FILE_WRITE_ERROR"
    USER_STOPPED = "USER_STOPPED"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


@dataclass(slots=True)
class SiteAdapterPolicy:

    html_fallback: bool = True
    detailed_log: bool = False


@dataclass(slots=True)
class ChapterLink:

    index: int
    title: str
    chapter_id: str
    url: str
    source: str = "api"


@dataclass(slots=True)
class ChapterContent:

    index: int
    title: str
    content: str
    url: str = ""
    source: str = ""
    ok: bool = True
    error: str = ""
    error_type: str = ""


@dataclass(slots=True)
class NovelCatalog:

    title: str
    novel_id: str
    url: str
    chapters: list[ChapterLink]


@dataclass(slots=True, frozen=True)
class RetryProfile:

    name: str
    worker_ratio: float
    delay_ratio: float
    delay_min_floor: float
    delay_max_floor: float
    timeout_floor: int
    retry_bonus: int
    cooldown: float


@dataclass(slots=True, frozen=True)
class RateLimitState:

    cooldown_until: float
    consecutive_blocks: int
    next_request_at: float
    delay_min: float
    delay_max: float
    cooldown_base: float
    cooldown_max: float

    def to_payload(self) -> dict[str, float | int]:
        return {
            "cooldownUntil": self.cooldown_until,
            "consecutiveBlocks": self.consecutive_blocks,
            "nextRequestAt": self.next_request_at,
            "delayMin": self.delay_min,
            "delayMax": self.delay_max,
            "cooldownBase": self.cooldown_base,
            "cooldownMax": self.cooldown_max,
        }


@dataclass(slots=True, frozen=True)
class ProgressSnapshot:

    done: int
    total: int
    fetched: int
    failed: int
    limited: int
    written: int = 0

    @property
    def percent(self) -> int:
        if self.total <= 0:
            return 0
        return max(0, min(100, round(self.done * 100 / self.total)))


@dataclass(slots=True, frozen=True)
class LogEvent:

    label: str
    message: str
    level: str = "info"

    def format(self) -> str:
        return f"{self.label}：{self.message}"


@dataclass(slots=True)
class NovelCrawlerRequest:

    novel_url: str
    output_file: Path | None
    start: int = 1
    end: int | None = None
    max_workers: int = DEFAULT_MAX_WORKERS
    request_delay_min: float = DEFAULT_REQUEST_DELAY_MIN
    request_delay_max: float = DEFAULT_REQUEST_DELAY_MAX
    timeout: int = DEFAULT_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES
    html_fallback: bool = True
    detailed_log: bool = False

    def normalized(self) -> "NovelCrawlerRequest":
        return NovelCrawlerRequest(
            novel_url=self.novel_url.strip(),
            output_file=self.output_file,
            start=max(1, int(self.start or 1)),
            end=int(self.end) if self.end else None,
            max_workers=max(1, min(int(self.max_workers or DEFAULT_MAX_WORKERS), MAX_WORKERS_LIMIT)),
            request_delay_min=max(0.0, float(self.request_delay_min)),
            request_delay_max=max(0.0, max(float(self.request_delay_max), float(self.request_delay_min))),
            timeout=max(3, int(self.timeout or DEFAULT_TIMEOUT)),
            max_retries=max(0, int(self.max_retries or 0)),
            html_fallback=bool(self.html_fallback),
            detailed_log=bool(self.detailed_log),
        )


@dataclass(slots=True)
class CrawlReport:

    ok: bool
    message: str
    path: Path | None = None
    title: str = ""
    novel_id: str = ""
    total: int = 0
    selected: int = 0
    success: int = 0
    failed: int = 0
    existing: int = 0
    missing: int = 0
    downloaded: int = 0
    failed_chapters: list[dict[str, str | int]] = field(default_factory=list)
