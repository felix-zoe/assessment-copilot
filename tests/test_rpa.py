import unittest
from src.rpa.mouse_driver import MouseDriver
from src.rpa.scheduler import HumanScheduler


class TestRPA(unittest.TestCase):

    def test_bezier_points_generation(self):
        """测试三阶贝塞尔曲线轨迹生成"""
        driver = MouseDriver(jitter_strength=1.0)
        start = (100, 100)
        end = (500, 500)
        points = driver.generate_bezier_points(start, end, steps=30)

        self.assertEqual(len(points), 31)
        self.assertEqual(points[0], start)
        # 终点允许微小抖动偏移
        self.assertAlmostEqual(points[-1][0], end[0], delta=5)
        self.assertAlmostEqual(points[-1][1], end[1], delta=5)

    def test_human_scheduler_interrupt(self):
        """测试拟人化时序调度的紧急中断"""
        interrupted = False

        def mock_stop_check():
            nonlocal interrupted
            interrupted = True
            return True

        # 测试正常中断
        result = HumanScheduler.wait_thinking_delay(
            min_sec=2.0, 
            max_sec=4.0, 
            stop_check_callback=mock_stop_check
        )
        self.assertFalse(result, "中断信号未生效")
        self.assertTrue(interrupted)


if __name__ == "__main__":
    unittest.main()
