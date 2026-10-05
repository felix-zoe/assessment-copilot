"""Perception layer for screen capturing, OCR, and element locating."""
from .screen_capture import ScreenCapture, CapturedImage
from .ocr_engine import OCREngine, OCRResultBlock

__all__ = ["ScreenCapture", "CapturedImage", "OCREngine", "OCRResultBlock"]
