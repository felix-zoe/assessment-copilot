from .openai_compatible import OpenAICompatibleProvider


class OllamaProvider(OpenAICompatibleProvider):
    """本地 Ollama 离线部署适配器 (复用 OpenAI 兼容协议)"""

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        api_key: str = "ollama",
        model: str = "qwen2.5-vl:7b",
        temperature: float = 0.1,
        max_tokens: int = 1024,
        timeout: float = 30.0,
    ):
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
