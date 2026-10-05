import asyncio
import threading
from typing import Optional
from loguru import logger

from .config import Settings
from .safety_guard import SafetyGuard
from .state import AppState, RuntimeStatus, WorkMode, global_state
from ..llm.base import BaseLLMProvider, QuestionAnalysisResult
from ..llm.factory import create_llm_provider
from ..perception.ocr_engine import OCREngine
from ..perception.screen_capture import ScreenCapture
from ..perception.ui_locator import UILocator
from ..ui.overlay_hud import OverlayHUD


class TaskCoordinator:
    """系统核心任务调度协同器 (纯安全辅助模式)"""

    def __init__(self, settings: Settings, hud: Optional[OverlayHUD] = None):
        self.settings = settings
        self.hud = hud
        self.state: AppState = global_state
        self.state.mode = WorkMode.COPILOT

        # 初始化感知与推理子系统
        self.capture = ScreenCapture(
            monitor_index=settings.app.capture.monitor_index,
            crop_region=settings.app.capture.crop_region,
        )
        self.ocr = OCREngine()
        self.llm_provider: BaseLLMProvider = create_llm_provider(settings)
        self.safety = SafetyGuard()

        self._async_loop = asyncio.new_event_loop()
        self._analyze_lock = threading.Lock()

    def set_hud(self, hud: OverlayHUD):
        self.hud = hud
        if self.hud:
            self.hud.update_mode_signal.emit(self.state.mode.value)

    @staticmethod
    def _extract_stem_fingerprint(ocr_blocks, screen_height: int = 1080) -> str:
        """题干特征提取辅助方法"""
        return UILocator.extract_stem_fingerprint(ocr_blocks, screen_height=screen_height)

    def trigger_step(self):
        """外部触发入口 (如按下 Alt+C)"""
        if self.state.is_analyzing:
            logger.info("当前正在分析题目中，忽略重复触发")
            self._update_hud_status("正在分析中，请稍候...", "#FBBF24")
            return

        threading.Thread(target=self._run_single_copilot_step, daemon=True).start()

    def _update_hud_status(self, text: str, color: str = "#94A3B8"):
        if self.hud:
            self.hud.update_status_signal.emit(text, color)

    def _run_single_copilot_step(self) -> Optional[QuestionAnalysisResult]:
        """执行单次安全辅助分析流程"""
        if not self._analyze_lock.acquire(blocking=False):
            return None

        self.state.is_analyzing = True
        try:
            self.state.status = RuntimeStatus.CAPTURING
            self._update_hud_status("正在截屏与读取视觉...", "#FBBF24")
            captured = self.capture.capture()

            self.state.status = RuntimeStatus.OCR_PROCESSING
            self._update_hud_status("正在本地提取文字排版...", "#FBBF24")
            ocr_blocks = self.ocr.recognize(
                captured.image,
                offset_x=captured.offset_x,
                offset_y=captured.offset_y
            )
            full_text = self.ocr.get_full_text(ocr_blocks)

            # 检测是否包含完卷特征
            is_submit_detected = UILocator.detect_submit_page(ocr_blocks)

            self.state.status = RuntimeStatus.LLM_INFERRING
            self._update_hud_status("大模型推导思维链中...", "#60A5FA")
            result: QuestionAnalysisResult = self._async_loop.run_until_complete(
                self.llm_provider.analyze_question(captured.base64_str, full_text)
            )

            # 综合研判是否为最后一题
            is_last = result.is_last_question or is_submit_detected

            # 更新 HUD 展示结果
            if self.hud:
                self.hud.update_result_signal.emit(
                    result.selected_option,
                    result.confidence,
                    result.reasoning,
                    is_last,
                )
                if is_last:
                    self._update_hud_status("⚠️ 疑似最后一题或交卷页，请人工核验！", "#F59E0B")
                else:
                    self._update_hud_status("分析完成 (等待用户手动选择)", "#10B981")

            self.state.status = RuntimeStatus.COMPLETED
            return result

        except Exception as e:
            logger.error(f"辅助模式分析执行出错: {e}")
            self.state.status = RuntimeStatus.ERROR
            self.state.last_error = str(e)
            self._update_hud_status(f"分析异常: {str(e)[:25]}", "#EF4444")
            return None

        finally:
            self.state.is_analyzing = False
            self._analyze_lock.release()
