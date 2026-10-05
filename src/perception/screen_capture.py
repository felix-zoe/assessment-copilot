import base64
import io
from dataclasses import dataclass
from typing import List, Optional, Tuple
import mss
from PIL import Image, ImageGrab
from loguru import logger


@dataclass
class CapturedImage:
    image: Image.Image
    raw_bytes: bytes
    base64_str: str
    offset_x: int  # 截图相对于全屏绝对坐标系的 X 偏移
    offset_y: int  # 截图相对于全屏绝对坐标系的 Y 偏移
    width: int
    height: int


class ScreenCapture:
    """基于 mss 的高性能显存级屏幕捕获器 (带 PIL.ImageGrab 双重保底)"""

    def __init__(self, monitor_index: int = 1, crop_region: Optional[List[int]] = None):
        """
        :param monitor_index: 显示器索引 (1 为主屏)
        :param crop_region: [left, top, right, bottom] 绝对坐标选区，若为 None 则截取整个显示器
        """
        self.monitor_index = monitor_index
        self.crop_region = crop_region
        try:
            self._sct = mss.MSS() if hasattr(mss, "MSS") else mss.mss()
        except Exception:
            self._sct = None

    def capture(self, custom_region: Optional[Tuple[int, int, int, int]] = None) -> CapturedImage:
        """
        执行截屏并返回 CapturedImage 对象
        :param custom_region: 动态传入 (left, top, width, height) 区域，优先于配置
        """
        # 1. 尝试 mss 极速截屏
        if self._sct:
            try:
                monitors = self._sct.monitors
                target_monitor = monitors[1] if self.monitor_index >= len(monitors) else monitors[self.monitor_index]

                if custom_region:
                    left, top, width, height = custom_region
                    bbox = {"left": left, "top": top, "width": width, "height": height}
                    offset_x, offset_y = left, top
                elif self.crop_region and len(self.crop_region) == 4:
                    c_left, c_top, c_right, c_bottom = self.crop_region
                    bbox = {
                        "left": c_left,
                        "top": c_top,
                        "width": max(1, c_right - c_left),
                        "height": max(1, c_bottom - c_top),
                    }
                    offset_x, offset_y = c_left, c_top
                else:
                    bbox = target_monitor
                    offset_x, offset_y = target_monitor["left"], target_monitor["top"]

                sct_img = self._sct.grab(bbox)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                return self._build_result(img, offset_x, offset_y)
            except Exception as e:
                logger.debug(f"mss 截屏遭遇异常 ({e})，自动切换至 PIL.ImageGrab 保底")

        # 2. 回退保底方案：PIL ImageGrab
        if custom_region:
            left, top, width, height = custom_region
            bbox = (left, top, left + width, top + height)
            offset_x, offset_y = left, top
        elif self.crop_region and len(self.crop_region) == 4:
            c_left, c_top, c_right, c_bottom = self.crop_region
            bbox = (c_left, c_top, c_right, c_bottom)
            offset_x, offset_y = c_left, c_top
        else:
            bbox = None
            offset_x, offset_y = 0, 0

        try:
            img = ImageGrab.grab(bbox=bbox)
            if img.mode != "RGB":
                img = img.convert("RGB")
        except Exception as e:
            logger.warning(f"PIL.ImageGrab 截屏失败 ({e})，当前可能处于无桌面/锁屏会话，生成测试画布保底")
            w = (bbox[2] - bbox[0]) if bbox else 1920
            h = (bbox[3] - bbox[1]) if bbox else 1080
            img = Image.new("RGB", (max(100, w), max(100, h)), color=(240, 240, 240))

        return self._build_result(img, offset_x, offset_y)

    def _build_result(self, img: Image.Image, offset_x: int, offset_y: int) -> CapturedImage:
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        raw_bytes = buffer.getvalue()
        base64_str = base64.b64encode(raw_bytes).decode("utf-8")

        return CapturedImage(
            image=img,
            raw_bytes=raw_bytes,
            base64_str=base64_str,
            offset_x=offset_x,
            offset_y=offset_y,
            width=img.width,
            height=img.height,
        )

    def close(self):
        if self._sct:
            try:
                self._sct.close()
            except Exception:
                pass
