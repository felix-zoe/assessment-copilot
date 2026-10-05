from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class WorkMode(str, Enum):
    COPILOT = "copilot"


class RuntimeStatus(str, Enum):
    IDLE = "idle"
    CAPTURING = "capturing"
    OCR_PROCESSING = "ocr_processing"
    LLM_INFERRING = "llm_inferring"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class AppState:
    mode: WorkMode = WorkMode.COPILOT
    status: RuntimeStatus = RuntimeStatus.IDLE
    is_analyzing: bool = False
    status_message: str = "就绪"
    last_error: Optional[str] = None


# 全局单例
global_state = AppState()

