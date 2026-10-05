from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel, Field


class QuestionAnalysisResult(BaseModel):
    selected_option: str = Field(
        ..., 
        description="推荐的最佳选项字母，例如 'A', 'B', 'C', 'D'；若多选可为 'AB' 等"
    )
    confidence: float = Field(
        default=0.9, 
        ge=0.0, 
        le=1.0, 
        description="模型推导置信度 (0.0 ~ 1.0)"
    )
    reasoning: str = Field(
        default="", 
        description="解题步骤与思维链分析"
    )
    is_last_question: bool = Field(
        default=False, 
        description="是否识别为最后一题或问卷结束页面"
    )
    raw_response: Optional[str] = Field(
        default=None, 
        description="大模型原始返回文本"
    )


class BaseLLMProvider(ABC):
    """大模型供应商抽象基类"""

    @abstractmethod
    async def analyze_question(
        self,
        image_base64: Optional[str],
        text_content: str,
    ) -> QuestionAnalysisResult:
        """
        核心做题分析接口
        :param image_base64: 图片 Base64 编码 (若有多模态题目图像)
        :param text_content: OCR 提取的题目与选项文本
        :return: 结构化做题结果
        """
        pass
