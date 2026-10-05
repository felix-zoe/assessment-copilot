# Assessment Copilot (校招测评智能辅助系统)

> ⚠️ **声明**：本项目仅用于多模态大语言模型 (VLM)、计算机视觉 (OCR) 与桌面 RPA 自动化技术的学习与工程实践探索，不得用于商业牟利或违规作弊。

---

## 📌 项目特性

1. **非侵入式黑盒架构**：
   - 不修改网页 DOM，不依赖考试客户端内部协议；
   - 完全基于屏幕截屏、本地 RapidOCR 与 OS 级输入控制。
2. **纯安全辅助模式 (Copilot Mode)**：
   - 🛡️ **人工主权与零风险**：按快捷键触发分析，悬浮窗半透明置顶呈现推荐选项、置信度与完整思维链 (CoT)，由用户手工点击，绝不注入模拟鼠标动作，彻底杜绝作弊与切屏封禁风险。
   - 🔒 **交卷与最后一题智能预警**：当检测到试卷结束或无“下一题”时，悬浮窗醒目提醒人工复核并交卷。
3. **Windows 防失焦优化**：
   - PySide6 悬浮 HUD 启用 `WS_EX_NOACTIVATE` 特性，在呼出与刷新时**绝不抢占前台输入焦点**，彻底规避平台切屏检测 (`blur` 事件)。
4. **全厂商模型热插拔 (LLM Switch)**：
   - **预设主流厂商**：内置 DeepSeek 官方、硅基流动 (SiliconFlow)、阿里通义千问 (DashScope)、商汤日日新 (SenseNova)、智谱 AI (GLM)、月之暗面 (Kimi)、MiniMax、火山引擎豆包、OpenAI、Google Gemini、本地 Ollama 以及自定义 OpenAI-Compatible 代理；
   - **一键拉取模型**：输入 Key 后点击「🔍 获取模型列表」自动探针探测并下拉选择，优先推荐视觉 Vision 多模态模型；
   - **连通性测速**：点击「⚡ 测试连接」发送即时探测，实时反馈毫秒级往返延迟。

---

## 🚀 快速上手

### 1. 安装依赖

推荐使用 Python 3.10+：
```bash
pip install -r requirements.txt
```

### 2. 配置大模型 API (两种方式任选)

- **方式 A (推荐)：在客户端界面直接配置**
  启动程序后，右键任务栏托盘图标 $\rightarrow$ **「大模型设置...」**，选择厂商，填入 API Key，点击「获取模型列表」并保存，立即热生效且自动持久化！
- **方式 B：手动编辑配置文件**
  复制模板文件 `copy configs\config.example.yaml configs\config.yaml`，填入你的供应商 Key。例如使用 **商汤日日新 (SenseNova) DeepSeek-Flash** 或 **硅基流动 (SiliconFlow)**：
```yaml
llm:
  active_provider: "siliconflow"
  providers:
    siliconflow:
      base_url: "https://api.siliconflow.cn/v1"
      api_key: "sk-your-siliconflow-api-key"
      model: "Qwen/Qwen2.5-VL-72B-Instruct"
```

### 3. 启动程序

```bash
python -m src.main
```
启动后，桌面右上角将出现半透明的悬浮 HUD 卡片，任务栏托盘也会显示常驻图标。

---

## ⌨️ 快捷键指南

| 快捷键 | 功能说明 | 适用场景 |
| :--- | :--- | :--- |
| `Alt + C` | **立即分析当前题目** | 随时触发屏幕捕获与思维链解析 |
| `Alt + H` | **快捷显示 / 隐藏悬浮窗** | 考试过程中随时防遮挡 |

---

## 🧪 运行单元测试

```bash
python -m unittest discover tests
```

---

## 📁 项目目录结构

```
assessment-copilot/
├── configs/
│   ├── config.example.yaml         # 配置文件模板
│   └── config.yaml                 # 本地运行时配置
├── docs/
│   └── architecture_solution.md    # 核心技术方案规范
├── src/
│   ├── main.py                     # 程序主入口 (GUI & 生命周期管理)
│   ├── core/                       # 核心业务协同
│   │   ├── config.py               # Pydantic 配置模型
│   │   ├── coordinator.py          # 任务调度与工作流引擎
│   │   ├── safety_guard.py         # 安全守卫 (完题熔断/交卷保护)
│   │   └── state.py                # 全局运行时状态
│   ├── perception/                 # 视觉感知与定位
│   │   ├── screen_capture.py       # mss + ImageGrab 高可用截屏
│   │   ├── ocr_engine.py           # RapidOCR 引擎封装与版面提取
│   │   └── ui_locator.py           # 选项 A/B/C/D 与下一题按钮绝对坐标定位
│   ├── llm/                        # 大模型推理层
│   │   ├── base.py                 # 抽象基类与 Pydantic 规范
│   │   ├── factory.py              # 适配器动态工厂
│   │   ├── prompt_templates.py     # 行测系统 Prompt 与 JSON 约束
│   │   └── providers/
│   │       ├── openai_compatible.py# 通用 OpenAI-compatible 适配器
│   │       ├── gemini_provider.py  # Google Gemini 原生适配器
│   │       └── ollama_provider.py  # 本地 Ollama 适配器
│   ├── rpa/                        # 拟人化执行器
│   │   ├── mouse_driver.py         # 三阶贝塞尔曲线平滑鼠标轨迹生成
│   │   └── scheduler.py            # 正态分布随机思考延迟
│   └── ui/                         # 界面交互 (PySide6)
│       ├── overlay_hud.py          # 无焦点透明置顶悬浮窗
│       ├── settings_dialog.py      # 参数设置对话框
│       └── hotkey_manager.py       # pynput 全局热键拦截分发
├── tests/                          # 单元测试集
├── requirements.txt                # 依赖清单
└── README.md                       # 说明文档
```
