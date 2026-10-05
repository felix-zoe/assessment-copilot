from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ProviderMeta:
    """大模型供应商元数据规范"""
    id: str                                    # 内部唯一标识
    name: str                                  # UI 展示名称
    default_base_url: str                      # 官方默认 Base URL
    api_key_url: Optional[str] = None         # 官网申请/查看 API Key 的直达链接
    preset_models: List[str] = field(default_factory=list) # 预设/推荐模型列表 (Vision模型优先)
    is_custom: bool = False                    # 是否为用户自定义供应商


# 内置主流大模型厂商注册表
PROVIDER_REGISTRY: Dict[str, ProviderMeta] = {
    "deepseek": ProviderMeta(
        id="deepseek",
        name="DeepSeek 官方",
        default_base_url="https://api.deepseek.com/v1",
        api_key_url="https://platform.deepseek.com/api_keys",
        preset_models=[
            "deepseek-chat",
            "deepseek-reasoner",
        ],
    ),
    "siliconflow": ProviderMeta(
        id="siliconflow",
        name="硅基流动 (SiliconFlow)",
        default_base_url="https://api.siliconflow.cn/v1",
        api_key_url="https://cloud.siliconflow.cn/account/ak",
        preset_models=[
            "Qwen/Qwen2.5-VL-72B-Instruct",
            "deepseek-ai/DeepSeek-V3",
            "deepseek-ai/DeepSeek-R1",
            "Pro/deepseek-ai/DeepSeek-V3",
            "Qwen/Qwen2-VL-72B-Instruct",
            "THUDM/glm-4-9b-chat",
        ],
    ),
    "dashscope": ProviderMeta(
        id="dashscope",
        name="阿里通义千问 (DashScope / 百炼)",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_url="https://bailian.console.aliyun.com/?apiKey=1",
        preset_models=[
            "qwen2.5-vl-72b-instruct",
            "qwen2.5-vl-7b-instruct",
            "qwen-vl-max",
            "qwen-plus",
            "qwen-max",
        ],
    ),
    "sensenova": ProviderMeta(
        id="sensenova",
        name="商汤日日新 (SenseNova)",
        default_base_url="https://token.sensenova.cn/v1",
        api_key_url="https://console.sensecore.cn/iam/secret-manage",
        preset_models=[
            "deepseek-v4-flash",
            "deepseek-flash",
            "SenseChat-Vision",
        ],
    ),
    "zhipu": ProviderMeta(
        id="zhipu",
        name="智谱 AI (GLM)",
        default_base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key_url="https://open.bigmodel.cn/usercenter/apikeys",
        preset_models=[
            "glm-4v-plus",
            "glm-4v",
            "glm-4-flash",
            "glm-4-plus",
        ],
    ),
    "moonshot": ProviderMeta(
        id="moonshot",
        name="月之暗面 (Moonshot / Kimi)",
        default_base_url="https://api.moonshot.cn/v1",
        api_key_url="https://platform.moonshot.cn/console/api-keys",
        preset_models=[
            "moonshot-v1-8k",
            "moonshot-v1-32k",
            "moonshot-v1-128k",
        ],
    ),
    "minimax": ProviderMeta(
        id="minimax",
        name="MiniMax (海螺)",
        default_base_url="https://api.minimax.chat/v1",
        api_key_url="https://platform.minimaxi.com/user-center/basic-information/interface-key",
        preset_models=[
            "MiniMax-Text-01",
            "abab6.5s-chat",
        ],
    ),
    "doubao": ProviderMeta(
        id="doubao",
        name="火山引擎 (豆包 / Ark)",
        default_base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_key_url="https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey",
        preset_models=[
            "ep-xxxxxxxx (填入接入点 Endpoint ID)",
        ],
    ),
    "openai": ProviderMeta(
        id="openai",
        name="OpenAI 官方",
        default_base_url="https://api.openai.com/v1",
        api_key_url="https://platform.openai.com/api-keys",
        preset_models=[
            "gpt-4o",
            "gpt-4o-mini",
            "o1",
            "o1-mini",
        ],
    ),
    "gemini": ProviderMeta(
        id="gemini",
        name="Google Gemini",
        default_base_url="https://generativelanguage.googleapis.com",
        api_key_url="https://aistudio.google.com/app/apikey",
        preset_models=[
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-2.0-flash-exp",
        ],
    ),
    "ollama": ProviderMeta(
        id="ollama",
        name="本地 Ollama",
        default_base_url="http://localhost:11434/v1",
        api_key_url=None,
        preset_models=[
            "qwen2.5-vl:7b",
            "llama3.2-vision",
            "minicpm-v",
            "qwen2.5:7b",
        ],
    ),
    "custom": ProviderMeta(
        id="custom",
        name="⚙️ 自定义 (OpenAI-Compatible)",
        default_base_url="",
        api_key_url=None,
        preset_models=[],
        is_custom=True,
    ),
}


def get_all_providers() -> List[ProviderMeta]:
    """获取所有预设与自定义供应商列表"""
    return list(PROVIDER_REGISTRY.values())


def get_provider_meta(provider_id: str) -> ProviderMeta:
    """根据 ID 获取供应商元数据，若不存在则回退至自定义"""
    if provider_id in PROVIDER_REGISTRY:
        return PROVIDER_REGISTRY[provider_id]
    # 如果是未注册的自定义厂商 ID
    return ProviderMeta(
        id=provider_id,
        name=f"自定义 ({provider_id})",
        default_base_url="",
        is_custom=True,
    )
