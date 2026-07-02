from __future__ import annotations

import time

from backend.story_analysis.platforms import StoryNotesRuntime


class StoryNotesClient:
    def __init__(self, runtime: StoryNotesRuntime) -> None:
        try:
            from openai import OpenAI
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("缺少 openai 依赖，请先安装 requirements.txt 中的 openai。") from exc

        self.runtime = runtime
        self.client = OpenAI(api_key=runtime.api_key, base_url=runtime.base_url)

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self.runtime.max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.runtime.model_name,
                    temperature=self.runtime.temperature,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                content = response.choices[0].message.content
                return content or "[]"
            except Exception as exc:
                last_error = exc
                if attempt < self.runtime.max_retries:
                    time.sleep(self.runtime.retry_delay * attempt)
        raise RuntimeError(f"模型调用失败：{last_error}")
