from loguru import logger

from ..core.config import Settings
from .base import BaseLLMProvider
from .providers.gemini_provider import GeminiProvider
from .providers.ollama_provider import OllamaProvider
from .providers.openai_compatible import OpenAICompatibleProvider


def create_llm_provider(settings: Settings) -> BaseLLMProvider:
    """根据 settings.llm 配置创建对应供应商实例"""
    active = settings.llm.active_provider
    provider_configs = settings.llm.providers

    if active not in provider_configs:
        logger.warning(
            f"未在 providers 中找到激活的供应商 [{active}] 配置，尝试使用 openai_like 默认配置"
        )
        active = "openai_like"

    cfg = provider_configs.get(active)
    if not cfg:
        from ..core.config import ProviderDetailConfig
        from .provider_registry import get_provider_meta
        meta = get_provider_meta(active)
        default_model = meta.preset_models[0] if meta.preset_models else "qwen2.5-vl-72b-instruct"
        logger.warning(f"未配置供应商 [{active}] 明细，采用默认配置")
        cfg = ProviderDetailConfig(
            base_url=meta.default_base_url or None,
            model=default_model,
        )

    if active == "gemini":
        return GeminiProvider(
            api_key=cfg.api_key or "",
            model=cfg.model,
            temperature=cfg.temperature,
            timeout=cfg.timeout,
        )
    elif active == "ollama":
        return OllamaProvider(
            base_url=cfg.base_url or "http://localhost:11434/v1",
            api_key=cfg.api_key or "ollama",
            model=cfg.model,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
            timeout=cfg.timeout,
        )
    else:
        # 默认使用 OpenAI 兼容协议
        return OpenAICompatibleProvider(
            base_url=cfg.base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=cfg.api_key or "",
            model=cfg.model,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
            timeout=cfg.timeout,
        )
