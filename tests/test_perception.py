import unittest
from PIL import Image, ImageDraw, ImageFont
from src.perception.screen_capture import ScreenCapture
from src.perception.ocr_engine import OCREngine
from src.perception.ui_locator import UILocator


class TestPerception(unittest.TestCase):

    def test_screen_capture(self):
        """测试屏幕捕获模块"""
        cap = ScreenCapture(monitor_index=1)
        captured = cap.capture()
        self.assertIsNotNone(captured.image)
        self.assertGreater(captured.width, 100)
        self.assertGreater(captured.height, 100)
        self.assertGreater(len(captured.raw_bytes), 0)
        self.assertGreater(len(captured.base64_str), 0)
        cap.close()

    def test_ocr_and_locator(self):
        """测试本地 RapidOCR 识别与 UI 元素定位"""
        ocr = OCREngine()
        if not ocr.is_available():
            self.skipTest("RapidOCR 引擎不可用，跳过测试")

        # 生成一张包含题目与选项的高清模拟图像
        img = Image.new("RGB", (600, 300), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        # 加载支持中文字符的系统字体
        font = None
        for font_path in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simsun.ttc"]:
            try:
                font = ImageFont.truetype(font_path, 18)
                break
            except Exception:
                pass

        draw.text((20, 20), "1. 依次填入横线处最恰当的词语是：", fill=(0, 0, 0), font=font)
        draw.text((30, 70), "A. 标新立异", fill=(0, 0, 0), font=font)
        draw.text((30, 110), "B. 独树一帜", fill=(0, 0, 0), font=font)
        draw.text((30, 150), "C. 循规蹈矩", fill=(0, 0, 0), font=font)
        draw.text((30, 190), "D. 墨守成规", fill=(0, 0, 0), font=font)
        draw.text((450, 240), "下一题", fill=(0, 0, 0), font=font)

        # 执行识别
        blocks = ocr.recognize(img)
        self.assertGreater(len(blocks), 0, "未能识别出任何文本块")

        full_text = ocr.get_full_text(blocks)
        self.assertIn("A", full_text)
        self.assertIn("B", full_text)

        # 测试选项定位
        opt_b_pos = UILocator.locate_option("B", blocks)
        self.assertIsNotNone(opt_b_pos, "定位选项 B 失败")
        self.assertGreater(opt_b_pos[0], 0)
        self.assertGreater(opt_b_pos[1], 0)

        # 测试下一题定位
        next_pos = UILocator.locate_next_button(blocks)
        self.assertIsNotNone(next_pos, "定位「下一题」按钮失败")
        self.assertGreater(next_pos[0], 400)

    def test_locate_option_excludes_navigation_buttons(self):
        """测试选项定位必须严格过滤带快捷键的导航按钮 (如 '下一题(D)')"""
        from src.perception.ocr_engine import OCRResultBlock

        fake_blocks = [
            OCRResultBlock(
                text="下一题(D)",
                score=0.95,
                box=[],
                abs_bbox=(700, 800, 820, 840),
                center=(760, 820)
            ),
            OCRResultBlock(
                text="保存并下一题 [A]",
                score=0.95,
                box=[],
                abs_bbox=(500, 800, 650, 840),
                center=(575, 820)
            ),
            OCRResultBlock(
                text="D. 墨守成规",
                score=0.98,
                box=[],
                abs_bbox=(100, 300, 300, 330),
                center=(200, 315)
            )
        ]

        # 查找 D：必须命中选项 "D. 墨守成规"，绝对不能命中 "下一题(D)"
        pos_d = UILocator.locate_option("D", fake_blocks, screen_height=1080)
        self.assertIsNotNone(pos_d)
        # Y 坐标应在 300~330 附近，绝不是 800~840 的底部按钮
        self.assertLess(pos_d[1], 400, "定位选项 D 错误地命中了底部的下一题(D)按钮！")

        # 查找 A：只有 "保存并下一题 [A]" 时，应直接返回 None（避免误点导航）
        pos_a = UILocator.locate_option("A", fake_blocks, screen_height=1080)
        self.assertIsNone(pos_a, "定位选项 A 时误触了导航按钮！")

    def test_stem_fingerprint_extraction(self):
        """测试题干特征提取与杂项过滤"""
        from src.core.coordinator import TaskCoordinator
        from src.perception.ocr_engine import OCRResultBlock

        fake_blocks = [
            OCRResultBlock(text="倒计时 45 秒", score=0.9, box=[], abs_bbox=(800, 110, 950, 130), center=(875, 120)),
            OCRResultBlock(text="2. 下列选项中成语使用正确的是：", score=0.95, box=[], abs_bbox=(100, 200, 450, 230), center=(275, 215)),
            OCRResultBlock(text="A. 差强人意", score=0.95, box=[], abs_bbox=(100, 260, 250, 280), center=(175, 270)),
        ]

        fingerprint = TaskCoordinator._extract_stem_fingerprint(fake_blocks, screen_height=1080)
        self.assertIn("下列选项中成语使用正确的是", fingerprint)
        self.assertNotIn("倒计时", fingerprint)

    def test_page_readiness_state_machine(self):
        """测试新题目完整渲染与三态就绪判定"""
        from src.perception.ocr_engine import OCRResultBlock

        # 场景 1：过渡空白/Loading帧（无有效题干）
        blank_blocks = [
            OCRResultBlock(text="...", score=0.9, box=[], abs_bbox=(500, 400, 600, 430), center=(550, 415))
        ]
        is_ready, stem, reason = UILocator.is_page_ready_for_question(blank_blocks, "旧题干", 1080)
        self.assertFalse(is_ready)
        self.assertIn("白屏", reason)

        # 场景 2：页面尚未切走（题干与上一题相同）
        same_stem_blocks = [
            OCRResultBlock(text="1. 依次填入横线处最恰当的词语是：", score=0.9, box=[], abs_bbox=(100, 200, 450, 230), center=(275, 215)),
            OCRResultBlock(text="A. 标新立异", score=0.9, box=[], abs_bbox=(100, 260, 250, 280), center=(175, 270)),
            OCRResultBlock(text="B. 独树一帜", score=0.9, box=[], abs_bbox=(100, 300, 250, 320), center=(175, 310)),
        ]
        is_ready, stem, reason = UILocator.is_page_ready_for_question(same_stem_blocks, "依次填入横线处最恰当的词语是", 1080)
        self.assertFalse(is_ready)
        self.assertIn("尚未切走", reason)

        # 场景 3：题干出来了，但选项还没挂载（选项少于 2 个且文本块单薄）
        half_baked_blocks = [
            OCRResultBlock(text="2. 下列选项中成语使用正确的是：", score=0.9, box=[], abs_bbox=(100, 200, 450, 230), center=(275, 215)),
        ]
        is_ready, stem, reason = UILocator.is_page_ready_for_question(half_baked_blocks, "旧题干", 1080)
        self.assertFalse(is_ready)
        self.assertIn("尚未完全挂载", reason)

        # 场景 4：完整就绪的新题（新题干 + 两个以上选项）
        ready_blocks = [
            OCRResultBlock(text="2. 下列选项中成语使用正确的是：", score=0.9, box=[], abs_bbox=(100, 200, 450, 230), center=(275, 215)),
            OCRResultBlock(text="A. 差强人意", score=0.9, box=[], abs_bbox=(100, 260, 250, 280), center=(175, 270)),
            OCRResultBlock(text="B. 叹为观止", score=0.9, box=[], abs_bbox=(100, 300, 250, 320), center=(175, 310)),
        ]
        is_ready, stem, reason = UILocator.is_page_ready_for_question(ready_blocks, "旧题干", 1080)
        self.assertTrue(is_ready)
        self.assertIn("完整渲染就绪", reason)

        # 场景 5：紧凑无标点无空格排版 (如 'A独树一帜')
        compact_blocks = [
            OCRResultBlock(text="3. 下列词语释义不正确的是：", score=0.9, box=[], abs_bbox=(100, 200, 450, 230), center=(275, 215)),
            OCRResultBlock(text="A独树一帜", score=0.9, box=[], abs_bbox=(100, 260, 250, 280), center=(175, 270)),
            OCRResultBlock(text="B标新立异", score=0.9, box=[], abs_bbox=(100, 300, 250, 320), center=(175, 310)),
        ]
        is_ready_compact, stem_compact, _ = UILocator.is_page_ready_for_question(compact_blocks, "旧题干", 1080)
        self.assertTrue(is_ready_compact, "紧凑排版 A独树一帜 应成功判定为就绪")

        # 场景 6：纯中文无字母前缀选项 (如性格测试/量表题)
        chinese_blocks = [
            OCRResultBlock(text="4. 我善于在压力下保持冷静：", score=0.9, box=[], abs_bbox=(100, 200, 450, 230), center=(275, 215)),
            OCRResultBlock(text="非常符合", score=0.9, box=[], abs_bbox=(100, 260, 250, 280), center=(175, 270)),
            OCRResultBlock(text="比较符合", score=0.9, box=[], abs_bbox=(100, 300, 250, 320), center=(175, 310)),
            OCRResultBlock(text="不符合", score=0.9, box=[], abs_bbox=(100, 340, 250, 360), center=(175, 350)),
        ]
        is_ready_chinese, stem_chinese, _ = UILocator.is_page_ready_for_question(chinese_blocks, "旧题干", 1080)
        self.assertTrue(is_ready_chinese, "纯中文选项应基于内容充实度判定为就绪")

    def test_locate_option_detail_coordinates(self):
        """测试选项详细定位的正文热区、单选圆钮与字母头部梯级坐标"""
        from src.perception.ocr_engine import OCRResultBlock

        blocks = [
            OCRResultBlock(text="B. 独树一帜", score=0.95, box=[], abs_bbox=(100, 300, 250, 340), center=(175, 320))
        ]
        detail = UILocator.locate_option_detail("B", blocks, 1080)
        self.assertIsNotNone(detail)
        # 梯级 1：正文黄金热区 (100 + 28 ~ 60，即 128 ~ 160)
        self.assertGreaterEqual(detail["body_coord"][0], 125)
        self.assertLessEqual(detail["body_coord"][0], 165)
        # 梯级 2：外部单选圆钮区落在 100 偏左 (< 100)
        self.assertLess(detail["radio_coord"][0], 100)
        # 梯级 3：字母头部锚定区 (100 + 12 ~ 22，即 110 ~ 125)
        self.assertGreaterEqual(detail["head_coord"][0], 110)
        self.assertLessEqual(detail["head_coord"][0], 125)


if __name__ == "__main__":
    unittest.main()
