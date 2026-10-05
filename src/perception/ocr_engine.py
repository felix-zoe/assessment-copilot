from dataclasses import dataclass
from typing import List, Optional, Tuple
import numpy as np
from PIL import Image
from loguru import logger

try:
    from rapidocr_onnxruntime import RapidOCR
    _RAPIDOCR_AVAILABLE = True
except ImportError:
    RapidOCR = None
    _RAPIDOCR_AVAILABLE = False


@dataclass
class OCRResultBlock:
    text: str
    score: float
    box: List[List[float]]  # 局部相对多边形坐标 4点 [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
    # 转换后的屏幕绝对坐标 (left, top, right, bottom)
    abs_bbox: Tuple[int, int, int, int]
    # 绝对坐标中心点 (center_x, center_y)
    center: Tuple[int, int]


class OCREngine:
    """基于 RapidOCR-ONNXRuntime 的轻量离线文本与坐标识别引擎"""

    def __init__(self):
        if not _RAPIDOCR_AVAILABLE:
            logger.warning("rapidocr_onnxruntime 未安装，OCR 功能将进入模拟模式")
            self._engine = None
        else:
            try:
                self._engine = RapidOCR()
                logger.info("RapidOCR 引擎初始化成功")
            except Exception as e:
                logger.error(f"RapidOCR 初始化异常: {e}")
                self._engine = None

    def is_available(self) -> bool:
        return self._engine is not None

    def recognize(
        self, 
        image: Image.Image, 
        offset_x: int = 0, 
        offset_y: int = 0
    ) -> List[OCRResultBlock]:
        """
        对传入图像执行 OCR 识别，并映射为屏幕全局坐标
        :param image: PIL Image
        :param offset_x: 图像在屏幕绝对坐标系中的 X 偏移
        :param offset_y: 图像在屏幕绝对坐标系中的 Y 偏移
        """
        if not self._engine:
            logger.debug("OCR 引擎不可用，返回空结果")
            return []

        # 将 PIL Image 转为 numpy 数组 (RGB)
        img_np = np.array(image)
        try:
            results, elapse = self._engine(img_np)
        except Exception as e:
            logger.error(f"OCR 识别执行失败: {e}")
            return []

        if not results:
            return []

        blocks: List[OCRResultBlock] = []
        for item in results:
            box, text, score = item[0], item[1], float(item[2])
            xs = [pt[0] for pt in box]
            ys = [pt[1] for pt in box]
            
            x_min = int(min(xs)) + offset_x
            x_max = int(max(xs)) + offset_x
            y_min = int(min(ys)) + offset_y
            y_max = int(max(ys)) + offset_y

            center_x = (x_min + x_max) // 2
            center_y = (y_min + y_max) // 2

            blocks.append(
                OCRResultBlock(
                    text=text.strip(),
                    score=score,
                    box=box,
                    abs_bbox=(x_min, y_min, x_max, y_max),
                    center=(center_x, center_y),
                )
            )

        # 【自适应浅色半透明水印增强通路】：
        # 很多考场界面的选项使用浅灰色半透明背景大水印 (如淡色 A/B/C/D)，默认 OCR 会将其作为底纹过滤。
        # 若初步识别未检出足够的 A-D 独立标记，自动进行快速对比度拉伸补充识别，确保水印字母 100% 显形！
        has_option_letters = any(
            b.text.strip().upper() in ["A", "B", "C", "D"] or 
            (len(b.text.strip()) > 1 and b.text.strip()[0].upper() in ["A", "B", "C", "D"] and not b.text.strip()[1].isalpha())
            for b in blocks
        )
        if not has_option_letters:
            try:
                from PIL import ImageEnhance
                enhanced = ImageEnhance.Contrast(image.convert("L")).enhance(3.0).convert("RGB")
                enhanced_results, _ = self._engine(np.array(enhanced))
                if enhanced_results:
                    for item in enhanced_results:
                        text = item[1].strip()
                        # 仅提取补充具有选项特征的字母或短标记
                        if text.upper() in ["A", "B", "C", "D"] or (len(text) <= 3 and any(c in text.upper() for c in "ABCD")):
                            box, score = item[0], float(item[2])
                            xs = [pt[0] for pt in box]
                            ys = [pt[1] for pt in box]
                            x_min = int(min(xs)) + offset_x
                            x_max = int(max(xs)) + offset_x
                            y_min = int(min(ys)) + offset_y
                            y_max = int(max(ys)) + offset_y
                            center_x = (x_min + x_max) // 2
                            center_y = (y_min + y_max) // 2
                            
                            # 避免重复添加完全重叠的已有块
                            if not any(abs(b.center[0] - center_x) < 20 and abs(b.center[1] - center_y) < 20 for b in blocks):
                                blocks.append(
                                    OCRResultBlock(
                                        text=text,
                                        score=score,
                                        box=box,
                                        abs_bbox=(x_min, y_min, x_max, y_max),
                                        center=(center_x, center_y),
                                    )
                                )
                                logger.info(f"浅色水印自适应增强成功捕获选项标记: '{text}' at ({center_x}, {center_y})")
            except Exception as e:
                logger.debug(f"浅色水印自适应增强跳过: {e}")

        return blocks

    def get_full_text(self, blocks: List[OCRResultBlock]) -> str:
        """根据垂直 Y 坐标自然排序拼接全文文本"""
        sorted_blocks = sorted(blocks, key=lambda b: (b.abs_bbox[1] // 15, b.abs_bbox[0]))
        return "\n".join([b.text for b in sorted_blocks if b.text])
