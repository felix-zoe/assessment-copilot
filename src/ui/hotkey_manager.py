from typing import Callable, Dict, Optional
from loguru import logger
from pynput import keyboard


class HotkeyManager:
    """基于 pynput 的跨平台全局热键管理器"""

    def __init__(self):
        self._listener: Optional[keyboard.GlobalHotKeys] = None
        self._hotkey_map: Dict[str, Callable[[], None]] = {}

    def register(self, hotkey_str: str, callback: Callable[[], None]):
        """
        注册热键
        :param hotkey_str: 如 "<alt>+c", "<esc>", "<alt>+m"
        :param callback: 无参回调函数
        """
        self._hotkey_map[hotkey_str] = callback
        logger.info(f"已注册全局热键: {hotkey_str}")

    def start(self):
        """在后台线程启动全局热键监听"""
        if not self._hotkey_map:
            logger.warning("未注册任何热键，跳过启动监听")
            return

        try:
            self._listener = keyboard.GlobalHotKeys(self._hotkey_map)
            self._listener.start()
            logger.info("全局热键监听器已在后台启动")
        except Exception as e:
            logger.error(f"全局热键启动失败: {e}")

    def stop(self):
        """停止热键监听"""
        if self._listener:
            try:
                self._listener.stop()
                logger.info("全局热键监听器已停止")
            except Exception as e:
                logger.debug(f"停止监听器异常: {e}")
            self._listener = None
