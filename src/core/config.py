import os
from pathlib import Path
from typing import Dict, List, Literal, Optional
import yaml
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "configs" / "config.yaml"
EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "configs" / "config.example.yaml"


class CaptureConfig(BaseModel):
    monitor_index: int = Field(default=1, description="显示器序号")
    crop_region: Optional[List[int]] = Field(default=None, description="[left, top, right, bottom]")


class AppConfig(BaseModel):
    mode: str = Field(default="copilot", description="运行模式 (安全辅助)")
    hotkey_trigger: str = Field(default="<alt>+c", description="触发分析热键")
    capture: CaptureConfig = Field(default_factory=CaptureConfig)


class ProviderDetailConfig(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: str
    temperature: float = 0.1
    max_tokens: int = 1024
    timeout: float = 20.0


class LLMConfig(BaseModel):
    active_provider: str = Field(default="openai_like", description="当前激活的供应商标识")
    providers: Dict[str, ProviderDetailConfig] = Field(default_factory=dict)


class RPAConfig(BaseModel):
    human_delay_min: float = 3.5
    human_delay_max: float = 6.5
    next_question_delay: float = 2.0
    bezier_jitter: float = 1.5
    max_auto_questions: int = 100


class Settings(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    rpa: RPAConfig = Field(default_factory=RPAConfig)


def load_settings(custom_path: Optional[Path] = None) -> Settings:
    """加载配置：优先读取 configs/config.yaml，不存在则回退至 config.example.yaml"""
    target = custom_path or (CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_CONFIG_PATH)
    if not target.exists():
        # 如果均不存在，返回默认配置
        return Settings()

    with open(target, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return Settings.model_validate(data)
