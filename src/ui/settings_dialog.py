import asyncio
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
import yaml
from loguru import logger

from ..core.config import CONFIG_PATH, ProviderDetailConfig, Settings
from ..llm.model_fetcher import ModelFetcher
from ..llm.provider_registry import PROVIDER_REGISTRY, get_all_providers, get_provider_meta


class FetchModelsWorker(QThread):
    """异步拉取模型列表后台工作线程"""
    success_signal = Signal(list)
    error_signal = Signal(str)

    def __init__(self, base_url: str, api_key: str, provider_id: str):
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key
        self.provider_id = provider_id

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            models = loop.run_until_complete(
                ModelFetcher.fetch_models(
                    base_url=self.base_url,
                    api_key=self.api_key,
                    provider_id=self.provider_id,
                )
            )
            loop.close()
            self.success_signal.emit(models)
        except Exception as e:
            self.error_signal.emit(str(e))


class TestConnectionWorker(QThread):
    """异步测试连接连通性工作线程"""
    result_signal = Signal(bool, str, float)

    def __init__(self, base_url: str, api_key: str, model: str):
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            is_ok, msg, latency = loop.run_until_complete(
                ModelFetcher.test_connectivity(
                    base_url=self.base_url,
                    api_key=self.api_key,
                    model=self.model,
                )
            )
            loop.close()
            self.result_signal.emit(is_ok, msg, latency)
        except Exception as e:
            self.result_signal.emit(False, str(e), 0.0)


class SettingsDialog(QDialog):
    """大模型厂商接入与参数配置面板 (参考 CC Switch 交互架构)"""

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("大模型厂商接入与配置 (LLM Switch)")
        self.resize(520, 480)
        self.fetch_worker: Optional[FetchModelsWorker] = None
        self.test_worker: Optional[TestConnectionWorker] = None
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(14)
        main_layout.setContentsMargins(18, 18, 18, 18)

        # 1. 厂商选择区
        provider_group = QGroupBox("选择模型供应商")
        provider_layout = QHBoxLayout(provider_group)
        provider_layout.setSpacing(10)

        self.provider_combo = QComboBox()
        self.provider_combo.setMinimumHeight(32)

        # 填充内置与自定义供应商
        all_providers = get_all_providers()
        for p in all_providers:
            self.provider_combo.addItem(p.name, userData=p.id)

        # 快速直达官网申请 Key 按钮
        self.link_key_btn = QPushButton("🔗 申请 Key")
        self.link_key_btn.setMinimumHeight(32)
        self.link_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.link_key_btn.setToolTip("点击在浏览器打开当前厂商的 API 密钥管理页")
        self.link_key_btn.clicked.connect(self._open_key_url)

        provider_layout.addWidget(self.provider_combo, stretch=4)
        provider_layout.addWidget(self.link_key_btn, stretch=1)
        main_layout.addWidget(provider_group)

        # 2. 接口参数配置区
        param_group = QGroupBox("接入凭据与模型")
        param_form = QFormLayout(param_group)
        param_form.setSpacing(10)
        param_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Base URL
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setMinimumHeight(30)
        self.base_url_edit.setPlaceholderText("https://api.example.com/v1")
        param_form.addRow("接口地址 (Base URL):", self.base_url_edit)

        # API Key (带显隐切换)
        key_layout = QHBoxLayout()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setMinimumHeight(30)
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("sk-...")

        self.toggle_key_btn = QPushButton("👁️")
        self.toggle_key_btn.setFixedSize(30, 30)
        self.toggle_key_btn.setToolTip("显示/隐藏 API Key")
        self.toggle_key_btn.clicked.connect(self._toggle_key_visibility)

        key_layout.addWidget(self.api_key_edit)
        key_layout.addWidget(self.toggle_key_btn)
        param_form.addRow("API 密钥 (API Key):", key_layout)

        # Model 选择 (可选择、可编辑、可动态拉取)
        model_layout = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setMinimumHeight(30)
        self.model_combo.setPlaceholderText("选择或输入模型标识 (如 qwen2.5-vl-72b-instruct)")

        self.fetch_btn = QPushButton("🔍 获取模型列表")
        self.fetch_btn.setMinimumHeight(30)
        self.fetch_btn.setToolTip("向端点发起探测，自动拉取当前 Key 可调用的全部模型")
        self.fetch_btn.clicked.connect(self._on_fetch_models_clicked)

        model_layout.addWidget(self.model_combo, stretch=3)
        model_layout.addWidget(self.fetch_btn, stretch=1)
        param_form.addRow("选择模型 (Model):", model_layout)

        # 连通性测试与状态栏
        test_layout = QHBoxLayout()
        self.test_btn = QPushButton("⚡ 测试连接")
        self.test_btn.setMinimumHeight(28)
        self.test_btn.clicked.connect(self._on_test_connection_clicked)

        self.status_label = QLabel("就绪 (可测试连通性或拉取可用模型)")
        self.status_label.setStyleSheet("color: #64748B; font-size: 11px;")

        test_layout.addWidget(self.test_btn)
        test_layout.addWidget(self.status_label, stretch=1)
        param_form.addRow("", test_layout)

        main_layout.addWidget(param_group)

        # 3. 高级参数 (可选)
        adv_group = QGroupBox("高级参数 (可选)")
        adv_layout = QHBoxLayout(adv_group)

        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 2.0)
        self.temp_spin.setSingleStep(0.1)
        self.temp_spin.setValue(0.1)

        self.timeout_spin = QDoubleSpinBox()
        self.timeout_spin.setRange(5.0, 120.0)
        self.timeout_spin.setSingleStep(5.0)
        self.timeout_spin.setValue(25.0)
        self.timeout_spin.setSuffix(" 秒")

        adv_layout.addWidget(QLabel("温度 (Temperature):"))
        adv_layout.addWidget(self.temp_spin)
        adv_layout.addSpacing(16)
        adv_layout.addWidget(QLabel("超时时间 (Timeout):"))
        adv_layout.addWidget(self.timeout_spin)
        main_layout.addWidget(adv_group)

        # 4. 底部保存与取消按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setMinimumHeight(32)
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("保存并生效")
        save_btn.setMinimumHeight(32)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                padding: 0 16px;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
        """)
        save_btn.clicked.connect(self._save_settings)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        main_layout.addLayout(btn_layout)

        # 绑定切换信号并初始化回显
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        self._select_current_active_provider()

    def _select_current_active_provider(self):
        """初始化选中当前配置中的 active_provider"""
        active = self.settings.llm.active_provider
        found = False
        for i in range(self.provider_combo.count()):
            if self.provider_combo.itemData(i) == active:
                self.provider_combo.setCurrentIndex(i)
                found = True
                break
        if not found:
            self.provider_combo.setCurrentIndex(0)
        self._on_provider_changed(self.provider_combo.currentIndex())

    def _open_key_url(self):
        """跳转打开当前厂商官方 Key 管理控制台"""
        provider_id = self.provider_combo.currentData()
        meta = get_provider_meta(provider_id)
        if meta and meta.api_key_url:
            QDesktopServices.openUrl(QUrl(meta.api_key_url))
        else:
            QMessageBox.information(self, "提示", "当前厂商暂无预设控制台链接，请自行在官网查看。")

    def _toggle_key_visibility(self):
        """显隐 API Key 文本"""
        if self.api_key_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.toggle_key_btn.setText("🔒")
        else:
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.toggle_key_btn.setText("👁️")

    def _on_provider_changed(self, index: int):
        """当用户在下拉框切换供应商时，联动回显或填入默认地址"""
        provider_id = self.provider_combo.itemData(index)
        meta = get_provider_meta(provider_id)

        # 控制申请 Key 按钮
        self.link_key_btn.setEnabled(bool(meta.api_key_url))

        # 读取该厂商保存的配置
        saved_cfg = self.settings.llm.providers.get(provider_id)

        # Base URL
        if saved_cfg and saved_cfg.base_url:
            self.base_url_edit.setText(saved_cfg.base_url)
        else:
            self.base_url_edit.setText(meta.default_base_url)

        # API Key
        if saved_cfg and saved_cfg.api_key:
            self.api_key_edit.setText(saved_cfg.api_key)
        else:
            self.api_key_edit.setText("")

        # 高级参数
        if saved_cfg:
            self.temp_spin.setValue(saved_cfg.temperature)
            self.timeout_spin.setValue(saved_cfg.timeout)
        else:
            self.temp_spin.setValue(0.1)
            self.timeout_spin.setValue(25.0)

        # Model 下拉框填充
        self.model_combo.clear()
        target_model = saved_cfg.model if saved_cfg else (meta.preset_models[0] if meta.preset_models else "")

        # 载入预设模型列表
        for m in meta.preset_models:
            self.model_combo.addItem(m)

        if target_model:
            idx = self.model_combo.findText(target_model)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
            else:
                self.model_combo.insertItem(0, target_model)
                self.model_combo.setCurrentIndex(0)

        self.status_label.setText("就绪")
        self.status_label.setStyleSheet("color: #64748B; font-size: 11px;")

    def _on_fetch_models_clicked(self):
        """点击【获取模型列表】按钮"""
        base_url = self.base_url_edit.text().strip()
        api_key = self.api_key_edit.text().strip()
        provider_id = self.provider_combo.currentData()

        if not base_url:
            QMessageBox.warning(self, "提示", "请先填写 Base URL 接口地址！")
            return

        self.fetch_btn.setEnabled(False)
        self.fetch_btn.setText("⏳ 获取中...")
        self.status_label.setText("正在拉取可用模型列表...")
        self.status_label.setStyleSheet("color: #3B82F6; font-size: 11px;")

        self.fetch_worker = FetchModelsWorker(base_url, api_key, provider_id)
        self.fetch_worker.success_signal.connect(self._on_fetch_models_success)
        self.fetch_worker.error_signal.connect(self._on_fetch_models_error)
        self.fetch_worker.start()

    def _on_fetch_models_success(self, models: List[str]):
        """成功拉取到模型列表"""
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("🔍 获取模型列表")

        if not models:
            self.status_label.setText("未获取到任何模型")
            self.status_label.setStyleSheet("color: #F59E0B; font-size: 11px;")
            return

        current_val = self.model_combo.currentText().strip()
        self.model_combo.clear()

        # 填充新模型列表
        for m in models:
            self.model_combo.addItem(m)

        # 尽量恢复之前的选中模型
        if current_val:
            idx = self.model_combo.findText(current_val)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
            else:
                self.model_combo.insertItem(0, current_val)
                self.model_combo.setCurrentIndex(0)
        else:
            self.model_combo.setCurrentIndex(0)

        self.status_label.setText(f"✅ 成功加载 {len(models)} 个可用模型！")
        self.status_label.setStyleSheet("color: #10B981; font-size: 11px; font-weight: bold;")

    def _on_fetch_models_error(self, err_msg: str):
        """拉取模型列表失败"""
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("🔍 获取模型列表")
        self.status_label.setText(f"❌ 获取失败: {err_msg[:40]}")
        self.status_label.setStyleSheet("color: #EF4444; font-size: 11px;")
        QMessageBox.warning(self, "获取模型列表失败", f"无法拉取模型列表，详细原因：\n{err_msg}\n\n您仍可在输入框手动输入模型标识。")

    def _on_test_connection_clicked(self):
        """点击【测试连接】按钮"""
        base_url = self.base_url_edit.text().strip()
        api_key = self.api_key_edit.text().strip()
        model = self.model_combo.currentText().strip()

        if not base_url:
            QMessageBox.warning(self, "提示", "请先填写 Base URL 接口地址！")
            return

        self.test_btn.setEnabled(False)
        self.test_btn.setText("⏳ 测试中...")
        self.status_label.setText("正在发送探针测试连接...")
        self.status_label.setStyleSheet("color: #3B82F6; font-size: 11px;")

        self.test_worker = TestConnectionWorker(base_url, api_key, model)
        self.test_worker.result_signal.connect(self._on_test_connection_result)
        self.test_worker.start()

    def _on_test_connection_result(self, is_ok: bool, msg: str, latency: float):
        """测试连接结果回调"""
        self.test_btn.setEnabled(True)
        self.test_btn.setText("⚡ 测试连接")

        if is_ok:
            self.status_label.setText(f"🟢 连接正常 (耗时 {int(latency)}ms)")
            self.status_label.setStyleSheet("color: #10B981; font-size: 11px; font-weight: bold;")
        else:
            self.status_label.setText(f"🔴 {msg[:35]}")
            self.status_label.setStyleSheet("color: #EF4444; font-size: 11px;")
            QMessageBox.critical(self, "连接测试失败", f"接口测试未能通过：\n{msg}")

    def _save_settings(self):
        """保存配置并持久化写入 configs/config.yaml"""
        provider_id = self.provider_combo.currentData()
        base_url = self.base_url_edit.text().strip() or None
        api_key = self.api_key_edit.text().strip() or None
        model = self.model_combo.currentText().strip()

        if not model:
            QMessageBox.warning(self, "提示", "请选择或输入模型名称 (Model)！")
            return

        # 更新全局 settings
        self.settings.app.mode = "copilot"
        self.settings.llm.active_provider = provider_id

        if provider_id not in self.settings.llm.providers:
            self.settings.llm.providers[provider_id] = ProviderDetailConfig(model=model)

        target_cfg = self.settings.llm.providers[provider_id]
        target_cfg.base_url = base_url
        target_cfg.api_key = api_key
        target_cfg.model = model
        target_cfg.temperature = self.temp_spin.value()
        target_cfg.timeout = self.timeout_spin.value()

        # 持久化覆盖写入 configs/config.yaml
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(self.settings.model_dump(), f, allow_unicode=True, indent=2)

        logger.info(f"大模型配置已更新并成功持久化至 configs/config.yaml (激活厂商: {provider_id}, 模型: {model})")
        QMessageBox.information(
            self, 
            "保存成功", 
            f"大模型配置已成功保存至 configs/config.yaml！\n\n已激活厂商: {self.provider_combo.currentText()}\n生效模型: {model}"
        )
        self.accept()
