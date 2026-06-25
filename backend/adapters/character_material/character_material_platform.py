from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class CharacterMaterialPlatformRuntime:
    platform: str
    api_key: str
    base_url: str
    model_name: str
    description: str
    temperature: float
    max_retries: int
    retry_delay: float


class CharacterMaterialPlatform:
    PLATFORMS: dict[str, dict[str, str]] = {
        "deepseek": {
            "api_key_env": "DEEPSEEK_API",
            "base_url_env": "DEEPSEEK_BASE_URL",
            "model_env": "DEEPSEEK_MODEL_NAME",
            "default_base_url": "https://api.deepseek.com",
            "default_model": "deepseek-chat",
            "description": "DeepSeek AI 平台",
        },
        "openai": {
            "api_key_env": "OPENAI_API_KEY",
            "base_url_env": "OPENAI_BASE_URL",
            "model_env": "OPENAI_MODEL_NAME",
            "default_base_url": "https://api.openai.com/v1",
            "default_model": "gpt-4o-mini",
            "description": "OpenAI 官方平台",
        },
        "siliconflow": {
            "api_key_env": "SILICONFLOW_API_KEY",
            "base_url_env": "SILICONFLOW_BASE_URL",
            "model_env": "SILICONFLOW_MODEL_NAME",
            "default_base_url": "https://api.siliconflow.cn/v1",
            "default_model": "Qwen/Qwen3-30B-A3B-Instruct-2507",
            "description": "SiliconFlow AI 平台",
        },
        "moonshot": {
            "api_key_env": "MOONSHOT_API_KEY",
            "base_url_env": "MOONSHOT_BASE_URL",
            "model_env": "MOONSHOT_MODEL_NAME",
            "default_base_url": "https://api.moonshot.cn/v1",
            "default_model": "kimi-k2-0905-preview",
            "description": "月之暗面 Kimi 平台",
        },
        "custom": {
            "api_key_env": "CUSTOM_API_KEY",
            "base_url_env": "CUSTOM_BASE_URL",
            "model_env": "CUSTOM_MODEL_NAME",
            "default_base_url": "https://your-custom-endpoint.com/v1",
            "default_model": "custom-model",
            "description": "自定义 OpenAI 兼容接口",
        },
    }

    @classmethod
    def list_platforms(cls) -> dict[str, str]:
        return {name: item["description"] for name, item in cls.PLATFORMS.items()}

    @classmethod
    def default_runtime_values(cls, platform: str) -> dict[str, str]:
        cfg = cls._platform_config(platform)
        return {
            "baseUrl": os.getenv(cfg["base_url_env"], cfg["default_base_url"]),
            "modelName": os.getenv(cfg["model_env"], cfg["default_model"]),
        }

    @classmethod
    def runtime_from_payload(cls, payload: dict) -> CharacterMaterialPlatformRuntime:
        platform = str(payload.get("platform") or os.getenv("LLM_PLATFORM") or "deepseek").strip()
        cfg = cls._platform_config(platform)
        api_key = str(payload.get("apiKey") or os.getenv(cfg["api_key_env"]) or "").strip()
        if not api_key:
            configured = [name for name, item in cls.PLATFORMS.items() if os.getenv(item["api_key_env"])]
            if configured:
                raise ValueError(f"平台 {platform} 的 API Key 未配置，可切换到已配置平台：{', '.join(configured)}。")
            env_names = "、".join(item["api_key_env"] for item in cls.PLATFORMS.values())
            raise ValueError(f"没有找到 API Key，请在页面填写 API Key，或至少配置一个环境变量：{env_names}")
        temperature = _float(payload.get("temperature"), _float(os.getenv("TEMPERATURE"), 0.2))
        max_retries = _int(payload.get("maxRetries"), _int(os.getenv("MAX_RETRIES"), 3))
        retry_delay = _float(payload.get("retryDelay"), _float(os.getenv("RETRY_DELAY"), 2.0))
        return CharacterMaterialPlatformRuntime(
            platform=platform,
            api_key=api_key,
            base_url=str(payload.get("baseUrl") or os.getenv(cfg["base_url_env"], cfg["default_base_url"])).strip(),
            model_name=str(payload.get("modelName") or os.getenv(cfg["model_env"], cfg["default_model"])).strip(),
            description=cfg["description"],
            temperature=temperature,
            max_retries=max(1, max_retries),
            retry_delay=max(0.0, retry_delay),
        )

    @classmethod
    def _platform_config(cls, platform: str) -> dict[str, str]:
        if platform not in cls.PLATFORMS:
            supported = "、".join(cls.PLATFORMS)
            raise ValueError(f"不支持的平台：{platform}。支持的平台：{supported}")
        return cls.PLATFORMS[platform]


def _int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except Exception:
        return default


def _float(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except Exception:
        return default
