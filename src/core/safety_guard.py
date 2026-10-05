from typing import List, Optional, Tuple
from loguru import logger
from ..perception.ocr_engine import OCRResultBlock
from ..perception.ui_locator import UILocator


class SafetyGuard:
    """自动化运行安全守卫：完题熔断、提交拦截与紧急保护"""

    def __init__(self, max_questions: int = 100):
        self.max_questions = max_questions
        self.answered_count = 0

    def reset(self):
        self.answered_count = 0

    def increment(self):
        self.answered_count += 1

    def check_pre_condition(self, ocr_blocks: List[OCRResultBlock]) -> Tuple[bool, str]:
        """
        前置安全检查（在单题分析与选择前执行）
        仅检查是否超选题上限或已在交卷完成页面，绝不提前拦截正常做题！
        """
        if self.answered_count >= self.max_questions:
            return True, f"已达到单次自动化最大题目上限 ({self.max_questions})，自动暂停"

        if UILocator.detect_submit_page(ocr_blocks) and self.answered_count > 0:
            return True, "页面已显示「提交试卷/答题完成」，已为您拦截自动提交，请人工确认！"

        return False, ""

    def check_post_condition(
        self, 
        ocr_blocks: List[OCRResultBlock], 
        is_last_from_llm: bool = False
    ) -> Tuple[bool, str]:
        """
        后置完题检查（在选项选定后、推进下一题前执行）
        研判当前是否已是整份试卷的最后一道题
        """
        # 1. 达到预设防死循环上限
        if self.answered_count >= self.max_questions:
            return True, f"已达到单次自动化最大题目上限 ({self.max_questions})，自动暂停"

        # 2. 页面中检测到交卷/完卷特征词
        if UILocator.detect_submit_page(ocr_blocks):
            return True, "页面检测到「提交试卷/答题完成」特征词，已为您拦截自动提交，请人工交卷！"

        # 3. 大模型明确判定为最后一题
        if is_last_from_llm:
            return True, "大模型分析判断当前为最后一题，已停止推进，请人工交卷！"

        # 4. 无法找到「下一题」推进按钮
        next_btn = UILocator.locate_next_button(ocr_blocks)
        if not next_btn:
            return True, "已完成本题作答。页面未检索到「下一题」按钮，疑似为最后一题，请人工确认交卷！"

        return False, ""

    def should_terminate(
        self, 
        ocr_blocks: List[OCRResultBlock], 
        is_last_from_llm: bool = False
    ) -> Tuple[bool, str]:
        """兼容旧接口，调用后置检查"""
        return self.check_post_condition(ocr_blocks, is_last_from_llm)
