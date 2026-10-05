import unittest
from src.core.safety_guard import SafetyGuard
from src.llm.base import QuestionAnalysisResult
from src.llm.providers.openai_compatible import OpenAICompatibleProvider
from src.perception.ocr_engine import OCRResultBlock


class TestLLMAndSafety(unittest.TestCase):

    def test_json_parsing_regular(self):
        """测试正常格式 JSON 响应解析"""
        provider = OpenAICompatibleProvider(
            base_url="https://api.test.com",
            api_key="test",
            model="test-model"
        )
        sample_json = """
        {
            "selected_option": "C",
            "confidence": 0.96,
            "reasoning": "这是一道经典的言语理解题，根据语境语义选择 C 最优。",
            "is_last_question": false
        }
        """
        res = provider._parse_json_result(sample_json)
        self.assertEqual(res.selected_option, "C")
        self.assertAlmostEqual(res.confidence, 0.96)
        self.assertFalse(res.is_last_question)

    def test_json_parsing_markdown_wrapped(self):
        """测试包含 Markdown 代码块标记的响应解析"""
        provider = OpenAICompatibleProvider(
            base_url="https://api.test.com",
            api_key="test",
            model="test-model"
        )
        sample_md = """
        分析完毕，结果如下：
        ```json
        {
            "selected_option": "A",
            "confidence": 0.88,
            "reasoning": "图形黑块移动规律",
            "is_last_question": true
        }
        ```
        """
        res = provider._parse_json_result(sample_md)
        self.assertEqual(res.selected_option, "A")
        self.assertTrue(res.is_last_question)

    def test_reasoning_content_extraction(self):
        """测试 kimi/deepseek-r1 等长思维模型在非严格 JSON 时的容错与提取"""
        provider = OpenAICompatibleProvider(
            base_url="https://api.test.com",
            api_key="test",
            model="kimi-k2.6"
        )
        sample_reasoning = "经过逻辑分析，我们首先排除A和C，最终选择答案是 B。"
        res = provider._parse_json_result(sample_reasoning)
        self.assertEqual(res.selected_option, "B")
        self.assertIn("答案是 B", res.reasoning)

    def test_safety_guard_termination(self):
        """测试安全守卫的完题熔断保护"""
        guard = SafetyGuard(max_questions=3)
        mock_blocks = [
            OCRResultBlock(
                text="提交试卷",
                score=0.99,
                box=[],
                abs_bbox=(100, 100, 200, 150),
                center=(150, 125)
            )
        ]

        # 1. 命中交卷关键词
        should_stop, reason = guard.should_terminate(mock_blocks, is_last_from_llm=False)
        self.assertTrue(should_stop)
        self.assertIn("提交试卷", reason)

        # 2. 模拟达到题数上限
        guard.answered_count = 3
        should_stop_max, reason_max = guard.should_terminate([], is_last_from_llm=False)
        self.assertTrue(should_stop_max)
        self.assertIn("最大题目上限", reason_max)

    def test_sensenova_provider_creation(self):
        """测试商汤 SenseNova deepseek-flash 供应商加载"""
        from src.core.config import Settings, LLMConfig, ProviderDetailConfig
        from src.llm.factory import create_llm_provider
        from src.llm.providers.openai_compatible import OpenAICompatibleProvider

        test_settings = Settings(
            llm=LLMConfig(
                active_provider="sensenova",
                providers={
                    "sensenova": ProviderDetailConfig(
                        base_url="https://token.sensenova.cn/v1",
                        api_key="sensenova-test-key",
                        model="deepseek-v4-flash",
                    )
                }
            )
        )
        provider = create_llm_provider(test_settings)
        self.assertIsInstance(provider, OpenAICompatibleProvider)
        self.assertEqual(provider.base_url, "https://token.sensenova.cn/v1")
        self.assertEqual(provider.endpoint, "https://token.sensenova.cn/v1/chat/completions")
        self.assertEqual(provider.model, "deepseek-v4-flash")

    def test_copilot_single_step_execution(self):
        """测试纯安全辅助模式下的单题分析流"""
        from unittest.mock import MagicMock, AsyncMock
        from PIL import Image
        from src.core.config import Settings
        from src.core.coordinator import TaskCoordinator
        from src.core.state import RuntimeStatus
        from src.perception.screen_capture import CapturedImage

        test_settings = Settings()
        coordinator = TaskCoordinator(test_settings)

        # Mock 截屏
        dummy_img = Image.new("RGB", (300, 200), (255, 255, 255))
        coordinator.capture.capture = MagicMock(return_value=CapturedImage(
            image=dummy_img,
            raw_bytes=b"dummy",
            base64_str="dummy_base64",
            offset_x=0,
            offset_y=0,
            width=300,
            height=200
        ))

        # Mock LLM 返回
        mock_result = QuestionAnalysisResult(
            selected_option="B",
            confidence=0.98,
            reasoning="测试推理思维链",
            is_last_question=False
        )
        coordinator.llm_provider.analyze_question = AsyncMock(return_value=mock_result)

        # 执行单题辅助分析
        result = coordinator._run_single_copilot_step()

        self.assertIsNotNone(result)
        self.assertEqual(result.selected_option, "B")
        self.assertAlmostEqual(result.confidence, 0.98)
        self.assertEqual(coordinator.state.status, RuntimeStatus.COMPLETED)
        self.assertFalse(coordinator.state.is_analyzing)

    def test_provider_registry(self):
        """测试大模型厂商预设中心与自定义回退"""
        from src.llm.provider_registry import get_all_providers, get_provider_meta

        providers = get_all_providers()
        self.assertGreater(len(providers), 5)

        # 检查主流厂商
        deepseek = get_provider_meta("deepseek")
        self.assertEqual(deepseek.name, "DeepSeek 官方")
        self.assertEqual(deepseek.default_base_url, "https://api.deepseek.com/v1")
        self.assertIn("deepseek-chat", deepseek.preset_models)

        siliconflow = get_provider_meta("siliconflow")
        self.assertEqual(siliconflow.name, "硅基流动 (SiliconFlow)")
        self.assertIsNotNone(siliconflow.api_key_url)

        # 检查未注册的自定义厂商自动回退
        custom = get_provider_meta("my_custom_proxy")
        self.assertTrue(custom.is_custom)
        self.assertIn("my_custom_proxy", custom.name)

    def test_model_fetcher_url_clean_and_vision_filter(self):
        """测试 ModelFetcher 的 URL 清洗与 Vision 模型识别排序"""
        from src.llm.model_fetcher import ModelFetcher

        # URL 清洗
        self.assertEqual(
            ModelFetcher._clean_base_url("https://api.test.com/v1/"),
            "https://api.test.com/v1"
        )
        self.assertEqual(
            ModelFetcher._clean_base_url("https://api.test.com/v1/chat/completions"),
            "https://api.test.com/v1"
        )

        # Vision 模型识别
        self.assertTrue(ModelFetcher._is_vision_model("qwen2.5-vl-72b-instruct"))
        self.assertTrue(ModelFetcher._is_vision_model("gpt-4o"))
        self.assertTrue(ModelFetcher._is_vision_model("gemini-1.5-flash"))
        self.assertFalse(ModelFetcher._is_vision_model("deepseek-chat"))


if __name__ == "__main__":
    unittest.main()
