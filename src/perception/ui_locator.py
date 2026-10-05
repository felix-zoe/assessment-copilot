import random
import re
from typing import Dict, List, Optional, Tuple
from loguru import logger
from .ocr_engine import OCRResultBlock


class UILocator:
    """高精度、强容错的 UI 元素与坐标定位引擎"""

    # 下一题/推进按钮的正则模式（涵盖各类错字、特殊符号、空格与变体）
    NEXT_BUTTON_REGEX = re.compile(
        r"(下[\s一\-—_1~]?\s*[题步项页道]|保存.*[下继续]|提交.*[下继续]|确认.*[下继续]|进入下一?题|继续作?答?|下一步|下页|Next\s*>?|NEXT)",
        re.IGNORECASE
    )

    # 显式关键词兜底匹配
    NEXT_KEYWORDS = [
        "下一题", "下 一 题", "下一项", "下一道", "下一步", "下一页", "下页",
        "保存并下一题", "提交并下一题", "确认并下一题", "保存并继续", "继续", "继续答题",
        "进入下一题", "确定", "确认", "next", "next question"
    ]

    # 提交/完卷特征词
    SUBMIT_KEYWORDS = ["提交试卷", "确认交卷", "结束测评", "提交答卷", "完成答题", "交卷", "确认提交", "测试结束"]

    # 选项匹配中必须严格排除的系统/导航/操作按钮关键词（彻底杜绝将包含(D)或快捷键的下一题/保存按钮误当选项）
    EXCLUDE_OPTION_WORDS = [
        "下一", "上一", "提交", "交卷", "保存", "确定", "确认", 
        "标记", "跳过", "答题卡", "next", "submit", "previous", "continue"
    ]

    @classmethod
    def locate_option_detail(
        cls, 
        target_option: str, 
        ocr_blocks: List[OCRResultBlock],
        screen_height: int = 1080
    ) -> Optional[Dict]:
        """
        高精度定位目标选项并返回包含主点击坐标、单选圆钮补偿坐标与局部 Bounding Box 的详细数据
        """
        if not target_option:
            return None

        # 提取首个有效选项字母
        clean_match = re.search(r"[A-D]", target_option.upper())
        if not clean_match:
            logger.warning(f"目标选项 [{target_option}] 中未包含合法的 A-D 字符")
            return None
        opt_char = clean_match.group(0)

        # 匹配多种常见选项格式
        patterns = [
            re.compile(rf"^[\(\[\（【]?\s*{opt_char}\s*[\)\]\）】\.\、\:\-\s]", re.IGNORECASE),
            re.compile(rf"^{opt_char}$", re.IGNORECASE),
        ]

        candidates: List[Tuple[OCRResultBlock, int]] = []
        safe_top = 120 if screen_height > 600 else 0
        safe_bottom = screen_height - 40 if screen_height > 600 else screen_height

        # 自适应主答题区右边界过滤：严禁匹配到屏幕右侧 78% 以外的非答题盲区 (如 X > 2000 的侧边栏/滚动条)
        max_canvas_x = max([b.abs_bbox[2] for b in ocr_blocks], default=1920)
        safe_right = int(max_canvas_x * 0.78) if max_canvas_x > 1200 else max_canvas_x

        for block in ocr_blocks:
            x_center = (block.abs_bbox[0] + block.abs_bbox[2]) // 2
            y_center = (block.abs_bbox[1] + block.abs_bbox[3]) // 2
            if y_center < safe_top or y_center > safe_bottom:
                continue
            if x_center > safe_right:
                continue

            text = block.text.strip()
            clean_text_lower = text.replace(" ", "").lower()

            # 【核心安全过滤】：严禁将导航按钮（如“下一题(D)”、“保存并下一题”、“确定(A)”）误当成选项！
            if any(kw in clean_text_lower for kw in cls.EXCLUDE_OPTION_WORDS):
                continue

            # 权重打分
            priority = 0
            for pat in patterns:
                if pat.search(text):
                    priority = 10
                    break

            if priority == 0:
                if text.upper().startswith(opt_char) and len(text) > 1 and not text[1].isalpha():
                    priority = 5
                elif text.upper() == opt_char:
                    priority = 10

            if priority > 0:
                candidates.append((block, priority))

        if not candidates:
            # 保底检索 (A) 或 [A]
            for block in ocr_blocks:
                x_center = (block.abs_bbox[0] + block.abs_bbox[2]) // 2
                if x_center > safe_right:
                    continue
                clean_text_lower = block.text.replace(" ", "").lower()
                if any(kw in clean_text_lower for kw in cls.EXCLUDE_OPTION_WORDS):
                    continue
                if f"({opt_char})" in block.text.upper() or f"[{opt_char}]" in block.text.upper():
                    candidates.append((block, 8))

        if not candidates:
            # 【终极兜底：几何等间距推导与卡片行自适应映射】
            opt_idx = {"A": 0, "B": 1, "C": 2, "D": 3}.get(opt_char, 0)

            # 策略 1：如果已识别出部分选项字母 (如已捕获 A/B/C)，利用等间距几何插值推导缺失选项 (如 D)
            known_letter_blocks: List[Tuple[int, OCRResultBlock]] = []
            for char_k, idx_k in [("A", 0), ("B", 1), ("C", 2), ("D", 3)]:
                for b in ocr_blocks:
                    if b.text.strip().upper() == char_k and b.abs_bbox[1] > safe_top and (b.abs_bbox[0] + b.abs_bbox[2]) // 2 < safe_right:
                        known_letter_blocks.append((idx_k, b))
                        break

            if len(known_letter_blocks) >= 2:
                known_letter_blocks.sort(key=lambda x: x[0])
                first_idx, first_b = known_letter_blocks[0]
                last_idx, last_b = known_letter_blocks[-1]
                step_y = (last_b.abs_bbox[1] - first_b.abs_bbox[1]) / max(1, (last_idx - first_idx))
                target_y_approx = int(first_b.abs_bbox[1] + (opt_idx - first_idx) * step_y)

                # 寻找在 target_y_approx (±40px) 附近属于主答题区的文本块 (如 'n!')
                near_blocks = [
                    b for b in ocr_blocks 
                    if abs(b.abs_bbox[1] - target_y_approx) < 40 
                    and (b.abs_bbox[0] + b.abs_bbox[2]) // 2 < safe_right
                    and not any(kw in b.text.replace(" ", "").lower() for kw in cls.EXCLUDE_OPTION_WORDS)
                ]
                if near_blocks:
                    matched_inferred_block = near_blocks[0]
                    candidates.append((matched_inferred_block, 7))
                    logger.info(
                        f"几何等间距推导成功: 选项 [{opt_char}] 成功映射至 Y={target_y_approx} 附近的目标块 "
                        f"'{matched_inferred_block.text}' at {matched_inferred_block.center}"
                    )

            # 策略 2：纯内容行自适应聚类
            if not candidates:
                content_blocks = [
                    b for b in ocr_blocks 
                    if b.abs_bbox[1] > safe_top 
                    and (b.abs_bbox[0] + b.abs_bbox[2]) // 2 < safe_right
                    and not any(kw in b.text.replace(" ", "").lower() for kw in cls.EXCLUDE_OPTION_WORDS)
                    and not any(kw in b.text for kw in ["单选", "多选", "分", "第", "倒计时", "剩余时间"])
                    and b.text.strip().upper() not in ["A", "B", "C", "D"]
                ]
                content_blocks.sort(key=lambda b: b.abs_bbox[1])
                card_rows = []
                for b in content_blocks:
                    if not card_rows or abs(b.abs_bbox[1] - card_rows[-1][0].abs_bbox[1]) > 25:
                        card_rows.append([b])
                    else:
                        card_rows[-1].append(b)

                if len(card_rows) >= 2 and opt_idx < len(card_rows):
                    matched_row_block = card_rows[opt_idx][0]
                    candidates.append((matched_row_block, 6))
                    logger.info(f"启用卡片垂直顺序兜底: 选项 [{opt_char}] 成功映射至第 {opt_idx + 1} 行卡片 '{matched_row_block.text}'")

        if not candidates:
            logger.warning(f"OCR 结果中未能检索到选项 [{opt_char}] 的对应位置")
            return None

        candidates.sort(key=lambda x: (x[1], x[0].abs_bbox[1]), reverse=True)
        matched_block = candidates[0][0]

        x_min, y_min, x_max, y_max = matched_block.abs_bbox
        width = x_max - x_min
        height = y_max - y_min
        y_center = y_min + height // 2

        # 梯级 1：正文黄金热区 (最符合现代网页长条卡片的最优触发区，绝不卡在字母缝隙)
        body_offset_x = min(60, max(28, int(width * 0.25)))
        body_x = x_min + body_offset_x + random.randint(-2, 2)
        body_y = y_center + random.randint(-2, 2)

        # 梯级 2：独立单选圆钮区 (针对圆圈独立在文字左侧外部 16~28px 的传统表单)
        radio_offset_x = min(28, max(16, int(height * 0.8)))
        radio_x = max(10, x_min - radio_offset_x)
        radio_y = y_center

        # 梯级 3：字母头部锚定区 (字母 A-D 本身所在区域)
        head_offset_x = min(22, max(12, int(height * 0.5)))
        head_x = x_min + head_offset_x + random.randint(-1, 1)
        head_y = y_center + random.randint(-1, 1)

        detail = {
            "opt_char": opt_char,
            "body_coord": (body_x, body_y),
            "radio_coord": (radio_x, radio_y),
            "head_coord": (head_x, head_y),
            "click_coord": (body_x, body_y),  # 默认首选正文黄金热区
            "bbox": (x_min, y_min, x_max, y_max),
            "matched_text": matched_block.text
        }

        logger.info(
            f"成功定位选项 [{opt_char}]: 正文热区 {detail['body_coord']}, "
            f"独立圆钮区 {detail['radio_coord']}, 字母头部区 {detail['head_coord']} "
            f"[匹配文本: '{matched_block.text}']"
        )
        return detail

    @classmethod
    def locate_option(
        cls, 
        target_option: str, 
        ocr_blocks: List[OCRResultBlock],
        screen_height: int = 1080
    ) -> Optional[Tuple[int, int]]:
        """高精度定位目标选项点击坐标（轻量便捷入口）"""
        detail = cls.locate_option_detail(target_option, ocr_blocks, screen_height)
        if detail:
            return detail["click_coord"]
        return None

    @classmethod
    def extract_stem_fingerprint(cls, ocr_blocks: List[OCRResultBlock], screen_height: int = 1080) -> str:
        """提取题干指纹特征（屏幕上方 10%~55% 核心区域的题干文字）"""
        stem_parts = []
        for b in ocr_blocks:
            y_center = (b.abs_bbox[1] + b.abs_bbox[3]) // 2
            if 100 < y_center < screen_height * 0.55:
                clean = b.text.strip()
                if len(clean) >= 2 and not any(kw in clean for kw in ["倒计时", "剩余时间", "得分", "分数"]):
                    stem_parts.append(clean)
        raw_stem = "".join(stem_parts)
        clean_stem = re.sub(r"[^\w\u4e00-\u9fa5]", "", raw_stem)
        return clean_stem[:60]

    @classmethod
    def is_page_ready_for_question(
        cls,
        ocr_blocks: List[OCRResultBlock],
        last_stem_fingerprint: str = "",
        screen_height: int = 1080
    ) -> Tuple[bool, str, str]:
        """
        新题目渲染完整度与三态就绪判定引擎：
        兼具高容错与严谨性，杜绝在骨架屏、Loading菊花图、过渡白屏中误触发，同时杜绝误杀无字母/紧凑排版选项！
        返回: (is_ready, current_stem, reason_desc)
        """
        stem_parts = []
        option_detected_count = 0
        answer_area_block_count = 0
        safe_top = 100 if screen_height > 600 else 0

        # 选项前缀模式：涵盖 A-D、全角 Ａ-Ｄ、数字 1-4，支持无标点紧贴汉字（如 "A标新立异"）
        opt_pattern = re.compile(r"^[\(\[\（【]?\s*([A-DＡ-Ｄ1-4])", re.IGNORECASE)

        for b in ocr_blocks:
            y_center = (b.abs_bbox[1] + b.abs_bbox[3]) // 2
            text = b.text.strip()
            clean_lower = text.replace(" ", "").lower()

            if y_center < safe_top or any(kw in clean_lower for kw in cls.EXCLUDE_OPTION_WORDS):
                continue

            # 统计页面答题核心区域有效文本块（排除倒计时与交卷等杂质）
            if not any(kw in clean_lower for kw in ["倒计时", "剩余时间", "得分", "分数", "交卷"]):
                answer_area_block_count += 1

            # 1. 题干采集（屏幕上中部 10% ~ 55% 区域）
            if safe_top < y_center < screen_height * 0.55:
                if len(text) >= 2 and not any(kw in clean_lower for kw in ["倒计时", "剩余时间", "得分", "分数"]):
                    stem_parts.append(text)

            # 2. 选项数量统计 (只要以 A-D、1-4 开头，无论后面是否有标点)
            if opt_pattern.search(text) or (len(text) == 1 and text.upper() in ["A", "B", "C", "D"]):
                option_detected_count += 1

        raw_stem = "".join(stem_parts)
        clean_stem = re.sub(r"[^\w\u4e00-\u9fa5]", "", raw_stem)[:60]

        # 规则 1：题干必须非空且有实体内容（过滤白屏/骨架屏过渡）
        if len(clean_stem) < 4:
            return (False, clean_stem, "页面题干内容过短或正处于白屏/加载过渡态")

        # 规则 2：新题干不能与上一题一致（过滤尚未切走）
        # 采用精准相等与长子串互包含判定，杜绝由于题号或标点偶发漏识导致的互锁穿透
        if last_stem_fingerprint:
            if clean_stem == last_stem_fingerprint or \
               (len(clean_stem) >= 6 and clean_stem in last_stem_fingerprint) or \
               (len(last_stem_fingerprint) >= 6 and last_stem_fingerprint in clean_stem):
                return (False, clean_stem, "页面仍停留在上一题，尚未切走")

        # 规则 3：选项挂载充实度核验（双重放行标准，彻底杜绝误杀）
        # 标准 A: 检测到 2 个或以上显式选项标记（A-D / 1-4）
        # 标准 B: 即使无显式字母前缀，但答题区域有效文本块 >= 3（如纯中文选项、性格测评、量表题）
        if option_detected_count >= 2 or answer_area_block_count >= 3:
            return (True, clean_stem, "新题目已完整渲染就绪")

        return (False, clean_stem, f"页面内容过于单薄 (仅 {answer_area_block_count} 个文本块)，选项列表可能尚未完全挂载")

    @classmethod
    def locate_next_button(
        cls, 
        ocr_blocks: List[OCRResultBlock],
        screen_height: int = 1080
    ) -> Optional[Tuple[int, int]]:
        """
        高精度定位「下一题」或推进按钮坐标
        包含正则容错、空格过滤、相邻文本块融合和位置加权
        """
        # 自适应高度计算：若传入默认 1080 但当前识别块分布在小选区/小画布中，自动适配参考高度
        max_y = max([b.abs_bbox[3] for b in ocr_blocks], default=screen_height)
        eff_height = max_y if (screen_height == 1080 and max_y < 700) else screen_height
        candidates: List[Tuple[OCRResultBlock, float]] = []

        safe_top = 120 if eff_height > 600 else 0
        for block in ocr_blocks:
            y_center = (block.abs_bbox[1] + block.abs_bbox[3]) // 2
            # 严格过滤顶部浏览器标签栏 (Y < 120) 与底部 Windows 任务栏
            if (y_center < safe_top) or (y_center < eff_height * 0.35 and eff_height > 600):
                continue
            if eff_height > 600 and y_center > eff_height - 30:
                continue

            raw_text = block.text
            clean_text = raw_text.replace(" ", "").replace("\u3000", "").replace("\t", "")

            matched = False
            weight = 0.0

            # 1. 正则强匹配
            if cls.NEXT_BUTTON_REGEX.search(clean_text):
                matched = True
                weight += 10.0
            else:
                # 2. 关键词包含匹配
                for kw in cls.NEXT_KEYWORDS:
                    if kw.replace(" ", "") in clean_text:
                        matched = True
                        weight += 8.0
                        break

            if matched:
                # 启发式权重过滤：
                # a. 按钮通常文本较短 (<= 8个字)，字数越少越可能是按钮
                if len(clean_text) <= 8:
                    weight += 5.0
                elif len(clean_text) > 15:
                    weight -= 6.0  # 可能是长段落中提到了“接下来的问题...”

                # b. 按钮通常在屏幕下方 (Y 坐标 > 屏幕高度的 30%)
                y_center = (block.abs_bbox[1] + block.abs_bbox[3]) / 2
                if y_center > screen_height * 0.4:
                    weight += 5.0
                if y_center > screen_height * 0.7:
                    weight += 3.0  # 在底部更大概率是下一题

                if weight > 5.0:
                    candidates.append((block, weight))

        # 3. 相邻文本块拼接检测 (如果 OCR 把 "下" 和 "一题" 拆分成两个相邻块)
        if not candidates and len(ocr_blocks) >= 2:
            for i in range(len(ocr_blocks) - 1):
                b1, b2 = ocr_blocks[i], ocr_blocks[i+1]
                # 检查两个文本块是否在同一水平线上且距离很近
                y_diff = abs(b1.center[1] - b2.center[1])
                x_gap = b2.abs_bbox[0] - b1.abs_bbox[2]
                if y_diff < 15 and 0 <= x_gap < 30:
                    combined = (b1.text + b2.text).replace(" ", "")
                    if cls.NEXT_BUTTON_REGEX.search(combined):
                        # 合并为一个伪候选块
                        merged_bbox = (b1.abs_bbox[0], min(b1.abs_bbox[1], b2.abs_bbox[1]),
                                       b2.abs_bbox[2], max(b1.abs_bbox[3], b2.abs_bbox[3]))
                        merged_center = ((merged_bbox[0] + merged_bbox[2]) // 2,
                                         (merged_bbox[1] + merged_bbox[3]) // 2)
                        dummy_block = OCRResultBlock(
                            text=combined,
                            score=0.9,
                            box=[],
                            abs_bbox=merged_bbox,
                            center=merged_center
                        )
                        candidates.append((dummy_block, 12.0))
                        break

        if not candidates:
            logger.debug("页面中未检索到「下一题」推进按钮")
            return None

        # 选取权重最高的一项
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_block = candidates[0][0]

        x_min, y_min, x_max, y_max = best_block.abs_bbox
        target_x = (x_min + x_max) // 2 + random.randint(-4, 4)
        target_y = (y_min + y_max) // 2 + random.randint(-2, 2)

        logger.info(
            f"成功定位「下一题」按钮坐标: ({target_x}, {target_y}) "
            f"[命中词: '{best_block.text}']"
        )
        return (target_x, target_y)

    @classmethod
    def detect_submit_page(cls, ocr_blocks: List[OCRResultBlock]) -> bool:
        """检测页面是否包含交卷、答题卡完成等结束标志"""
        for block in ocr_blocks:
            clean = block.text.replace(" ", "").replace("\u3000", "")
            for kw in cls.SUBMIT_KEYWORDS:
                if kw in clean:
                    logger.info(f"检测到完卷特征词: '{kw}'，判定为最后一题或问卷结束！")
                    return True
        return False
