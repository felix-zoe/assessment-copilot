import sys
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
from loguru import logger

from src.core.config import load_settings
from src.core.coordinator import TaskCoordinator
from src.llm.factory import create_llm_provider
from src.ui.hotkey_manager import HotkeyManager
from src.ui.overlay_hud import OverlayHUD
from src.ui.settings_dialog import SettingsDialog


def main():
    logger.add("logs/copilot_{time}.log", rotation="10 MB", retention="7 days", level="INFO")
    logger.info("正在启动 Assessment Copilot...")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 1. 加载配置
    settings = load_settings()

    # 2. 创建置顶悬浮 HUD
    hud = OverlayHUD()
    hud.show()

    # 3. 核心调度协同器
    coordinator = TaskCoordinator(settings, hud=hud)
    coordinator.set_hud(hud)

    # 4. 注册并启动全局热键监听
    hotkey_mgr = HotkeyManager()
    hotkey_mgr.register(settings.app.hotkey_trigger, coordinator.trigger_step)
    # 增加快捷隐藏/显示悬浮窗热键 Alt+H
    hotkey_mgr.register("<alt>+h", lambda: hud.setVisible(not hud.isVisible()))
    hotkey_mgr.start()

    # 5. 系统托盘图标
    tray_icon = QSystemTrayIcon(app)
    # 使用标准应用图标或默认图标
    tray_icon.setIcon(app.style().standardIcon(app.style().StandardPixmap.SP_ComputerIcon))
    tray_icon.setToolTip("Assessment Copilot - 安全辅助答题")

    tray_menu = QMenu()

    action_toggle_hud = QAction("显示/隐藏 悬浮窗 (Alt+H)", tray_menu)
    action_toggle_hud.triggered.connect(lambda: hud.setVisible(not hud.isVisible()))

    action_settings = QAction("大模型设置...", tray_menu)
    def open_settings():
        dialog = SettingsDialog(settings)
        if dialog.exec():
            # 重新实例化大模型网关
            coordinator.llm_provider = create_llm_provider(settings)
            logger.info("设置已更新并生效")

    action_settings.triggered.connect(open_settings)

    action_quit = QAction("退出程序", tray_menu)
    action_quit.triggered.connect(app.quit)

    tray_menu.addAction(action_toggle_hud)
    tray_menu.addSeparator()
    tray_menu.addAction(action_settings)
    tray_menu.addSeparator()
    tray_menu.addAction(action_quit)

    tray_icon.setContextMenu(tray_menu)
    tray_icon.show()

    # 清理钩子
    def on_exit():
        logger.info("程序正在退出，清理热键监听器...")
        hotkey_mgr.stop()

    app.aboutToQuit.connect(on_exit)

    logger.info("Assessment Copilot 启动就绪！悬浮窗已置顶。")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
