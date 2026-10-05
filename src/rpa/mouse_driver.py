import math
import random
import time
from typing import List, Optional, Tuple
from loguru import logger

try:
    import win32api
    import win32con
    _WIN32_AVAILABLE = True
except ImportError:
    _WIN32_AVAILABLE = False

from pynput.mouse import Button, Controller as PynputMouse


class MouseDriver:
    """具备三阶贝塞尔曲线拟人化移动与点击的鼠标驱动器"""

    def __init__(self, jitter_strength: float = 1.5):
        self.jitter_strength = jitter_strength
        self._pynput_mouse = PynputMouse()

    def get_position(self) -> Tuple[int, int]:
        """获取当前鼠标全局绝对坐标"""
        if _WIN32_AVAILABLE:
            return win32api.GetCursorPos()
        x, y = self._pynput_mouse.position
        return (int(x), int(y))

    def set_position(self, x: int, y: int):
        """设置当前鼠标全局绝对坐标"""
        if _WIN32_AVAILABLE:
            win32api.SetCursorPos((x, y))
        else:
            self._pynput_mouse.position = (x, y)

    def generate_bezier_points(
        self, 
        start: Tuple[int, int], 
        end: Tuple[int, int], 
        steps: int = 40
    ) -> List[Tuple[int, int]]:
        """
        生成自然的三阶贝塞尔曲线平滑轨迹点序列
        """
        x0, y0 = start
        x3, y3 = end
        dist = math.hypot(x3 - x0, y3 - y0)

        # 随机偏置控制点
        offset = dist * random.uniform(0.15, 0.35)
        angle = math.atan2(y3 - y0, x3 - x0) + random.uniform(-0.5, 0.5)

        x1 = x0 + offset * math.cos(angle)
        y1 = y0 + offset * math.sin(angle)

        x2 = x3 - offset * math.cos(angle)
        y2 = y3 - offset * math.sin(angle)

        points = []
        for i in range(steps + 1):
            t = i / steps
            # 引入缓动函数 (Ease In-Out: S型曲线加速与减速)
            t_smooth = 0.5 * (1 - math.cos(t * math.pi))

            # 三阶贝塞尔方程
            bx = (
                (1 - t_smooth) ** 3 * x0
                + 3 * (1 - t_smooth) ** 2 * t_smooth * x1
                + 3 * (1 - t_smooth) * (t_smooth ** 2) * x2
                + (t_smooth ** 3) * x3
            )
            by = (
                (1 - t_smooth) ** 3 * y0
                + 3 * (1 - t_smooth) ** 2 * t_smooth * y1
                + 3 * (1 - t_smooth) * (t_smooth ** 2) * y2
                + (t_smooth ** 3) * y3
            )

            # 注入手部微抖动
            if 0 < i < steps:
                bx += random.uniform(-self.jitter_strength, self.jitter_strength)
                by += random.uniform(-self.jitter_strength, self.jitter_strength)

            points.append((int(bx), int(by)))

        return points

    def move_to(self, target_x: int, target_y: int, duration_sec: float = 0.4):
        """
        拟人化平滑移动鼠标到指定目标
        """
        start = self.get_position()
        if start == (target_x, target_y):
            return

        dist = math.hypot(target_x - start[0], target_y - start[1])
        steps = max(20, min(80, int(dist / 8)))
        points = self.generate_bezier_points(start, (target_x, target_y), steps=steps)

        delay_per_step = max(0.003, duration_sec / steps)
        for pt in points:
            self.set_position(pt[0], pt[1])
            time.sleep(delay_per_step)

        # 确保精准到达终点
        self.set_position(target_x, target_y)

    def click(self, target_x: Optional[int] = None, target_y: Optional[int] = None):
        """
        在指定位置（或当前位置）模拟人类单击
        包含屏幕物理安全视口硬约束：严禁点击 Y < 120 区域 (避开浏览器标签栏、地址栏)
        """
        if target_x is not None and target_y is not None:
            safe_y = max(120, target_y)
            if safe_y != target_y:
                logger.warning(f"坐标 Y={target_y} 过靠近浏览器顶部标签栏，已被安全拦截并钳制至 Y={safe_y}")
            self.move_to(target_x, safe_y)
            # 到达目标后短暂停顿 35ms 确保光标物理稳定，彻底杜绝误触发鼠标拖拽事件
            time.sleep(0.035)

        # 人类左键按压延迟 (70ms ~ 140ms)
        press_duration = random.uniform(0.07, 0.14)

        if _WIN32_AVAILABLE:
            # 关键修复：无 MOUSEEVENTF_ABSOLUTE 标志时，dx/dy 必须为 0，否则会基于当前光标再次叠加位移导致点偏！
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(press_duration)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        else:
            self._pynput_mouse.press(Button.left)
            time.sleep(press_duration)
            self._pynput_mouse.release(Button.left)

        logger.debug(f"模拟人类单击完成，按压耗时 {press_duration*1000:.1f}ms")
