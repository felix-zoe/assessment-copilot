import random
import time
from typing import Callable, Optional
from loguru import logger


class HumanScheduler:
    """模拟人类审题、计算思考时间的时序调度器"""

    @staticmethod
    def wait_thinking_delay(
        min_sec: float = 3.5, 
        max_sec: float = 6.5,
        stop_check_callback: Optional[Callable[[], bool]] = None
    ) -> bool:
        """
        带中断检测的正态随机等待
        :return: True 表示正常完成等待，False 表示被中途打断
        """
        # 正态分布随机时长
        mean = (min_sec + max_sec) / 2
        sigma = (max_sec - min_sec) / 4
        target_sec = max(min_sec, min(max_sec, random.gauss(mean, sigma)))

        logger.info(f"正在模拟人类审题与推导思考延迟: {target_sec:.2f} 秒...")

        # 切片等待，每 100ms 检查一次是否触发紧急终止
        start_time = time.time()
        while time.time() - start_time < target_sec:
            if stop_check_callback and stop_check_callback():
                logger.warning("思考等待被紧急停止信号打断")
                return False
            time.sleep(0.1)

        return True
