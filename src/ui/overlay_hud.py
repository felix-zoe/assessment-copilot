import sys
from typing import Optional
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from loguru import logger

try:
    import win32con
    import win32gui
    _WIN32_AVAILABLE = True
except ImportError:
    _WIN32_AVAILABLE = False


class OverlayHUD(QWidget):
    """
    非侵入式置顶无焦点悬浮窗 (No-Focus Floating HUD)
    针对校招平台防切屏优化：配置 WS_EX_NOACTIVATE，绝不抢占输入焦点
    """
    # 线程安全 UI 更新信号
    update_result_signal = Signal(str, float, str, bool)  # option, confidence, reasoning, is_last
    update_status_signal = Signal(str, str)              # status_text, color_code
    update_mode_signal = Signal(str)                     # mode_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.old_pos: Optional[QPoint] = None
        self._init_window_flags()
        self._init_ui()
        self._apply_no_activate_style()
        self._connect_signals()

    def _init_window_flags(self):
        # 无边框 + 强行置顶 + 工具栏小窗口 (不占任务栏)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.resize(360, 260)
        # 默认停靠屏幕右上角
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 390, 60)

    def _init_ui(self):
        # 主卡片容器
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame(self)
        card.setObjectName("cardFrame")
        card.setStyleSheet("""
            #cardFrame {
                background-color: rgba(26, 29, 36, 0.94);
                border: 1px solid rgba(80, 90, 110, 0.6);
                border-radius: 12px;
            }
            QLabel {
                color: #E2E8F0;
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(8)

        # 1. 顶部标题与状态栏 (支持拖动)
        header_layout = QHBoxLayout()
        self.title_label = QLabel("⚡ 答题 Copilot")
        self.title_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #60A5FA;")

        self.mode_badge = QLabel("安全辅助")
        self.mode_badge.setStyleSheet("""
            background-color: #1E3A8A;
            color: #93C5FD;
            padding: 2px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: bold;
        """)

        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #94A3B8;
                border: none;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #EF4444;
            }
        """)
        self.close_btn.clicked.connect(self.hide)

        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.mode_badge)
        header_layout.addWidget(self.close_btn)
        card_layout.addLayout(header_layout)

        # 2. 状态提示条
        self.status_label = QLabel("就绪 (按 Alt+C 立即分析)")
        self.status_label.setStyleSheet("color: #94A3B8; font-size: 11px;")
        card_layout.addWidget(self.status_label)

        # 3. 核心答案高亮展示区
        result_box = QFrame()
        result_box.setStyleSheet("""
            background-color: rgba(15, 23, 42, 0.7);
            border-radius: 8px;
            border: 1px solid rgba(59, 130, 246, 0.3);
            padding: 4px;
        """)
        result_layout = QHBoxLayout(result_box)
        result_layout.setContentsMargins(10, 6, 10, 6)

        opt_title = QLabel("推荐选项:")
        opt_title.setStyleSheet("font-size: 13px; color: #CBD5E1;")

        self.option_val = QLabel("--")
        self.option_val.setFont(QFont("Consolas", 22, QFont.Weight.Bold))
        self.option_val.setStyleSheet("color: #10B981; padding-left: 6px;")

        self.conf_badge = QLabel("置信度: --")
        self.conf_badge.setStyleSheet("color: #64748B; font-size: 11px;")

        result_layout.addWidget(opt_title)
        result_layout.addWidget(self.option_val)
        result_layout.addStretch()
        result_layout.addWidget(self.conf_badge)
        card_layout.addWidget(result_box)

        # 4. 解题思路 (滚动区)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { width: 4px; background: transparent; }
            QScrollBar::handle:vertical { background: #475569; border-radius: 2px; }
        """)
        self.reasoning_label = QLabel("按下快捷键触发分析后，解题思维链与推导将在此呈现。")
        self.reasoning_label.setWordWrap(True)
        self.reasoning_label.setStyleSheet("color: #94A3B8; font-size: 11px; line-height: 1.4;")
        scroll.setWidget(self.reasoning_label)
        card_layout.addWidget(scroll)

        # 5. 底部快捷键提示
        footer = QLabel("Alt+C 立即分析 | 右上角 × 隐藏")
        footer.setStyleSheet("color: #475569; font-size: 10px;")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(footer)

        main_layout.addWidget(card)

    def _apply_no_activate_style(self):
        """应用 Windows 底层 WS_EX_NOACTIVATE 扩展样式，避免夺取活动窗口焦点"""
        if not _WIN32_AVAILABLE:
            return

        try:
            hwnd = int(self.winId())
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            win32gui.SetWindowLong(
                hwnd,
                win32con.GWL_EXSTYLE,
                style | win32con.WS_EX_NOACTIVATE | win32con.WS_EX_TOPMOST
            )
            logger.info("已成功启用 WS_EX_NOACTIVATE 防失焦窗口特性")
        except Exception as e:
            logger.warning(f"应用 WS_EX_NOACTIVATE 失败: {e}")

    def _connect_signals(self):
        self.update_result_signal.connect(self._on_update_result)
        self.update_status_signal.connect(self._on_update_status)
        self.update_mode_signal.connect(self._on_update_mode)

    def _on_update_result(self, option: str, confidence: float, reasoning: str, is_last: bool):
        self.option_val.setText(option or "--")
        conf_pct = int(confidence * 100)
        self.conf_badge.setText(f"置信度: {conf_pct}%")
        self.reasoning_label.setText(reasoning or "无具体解析")
        if is_last:
            self.status_label.setText("⚠️ 检测到试卷结束或最后一题，请人工交卷！")
            self.status_label.setStyleSheet("color: #F59E0B; font-size: 11px; font-weight: bold;")

    def _on_update_status(self, text: str, color_code: str):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color_code}; font-size: 11px;")

    def _on_update_mode(self, mode_name: str = "copilot"):
        self.mode_badge.setText("安全辅助")
        self.mode_badge.setStyleSheet("""
            background-color: #1E3A8A;
            color: #93C5FD;
            padding: 2px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: bold;
        """)

    # 鼠标拖拽移动窗口支持
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos is not None:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.pos() + delta)
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None
