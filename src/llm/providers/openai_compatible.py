import json
import re
from typing import Any, Dict, List, Optional
import httpx
from loguru import logger

from ..base import BaseLLMProvider, QuestionAnalysisResult
from ..model_fetcher import ModelFetcher
from ..prompt_templates import SYSTEM_ASSESSMENT_PROMPT, USER_QUESTION_PROMPT_TEMPLATE


class OpenAICompatibleProvider(BaseLLMProvider):
    """
    通用 OpenAI 兼容接口适配器
    支持视觉多模态 (Vision)、纯文本模型自适应降级、以及思考模型 (Reasoning Content) 自动提取
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        timeout: float = 30.0,
    ):
        # 规避末尾多余斜杠
        self.base_url = base_url.rstrip("/")
        # 若未包含完整版本路径，补全 /v1
        if not self.base_url.endswith("/v1") and not self.base_url.endswith("/chat/completions") and "/v" not in self.base_url:
            self.endpoint = f"{self.base_url}/v1/chat/completions"
        elif self.base_url.endswith("/chat/completions"):
            self.endpoint = self.base_url
        else:
            self.endpoint = f"{self.base_url}/chat/completions"

        self.api_key = api_key or "sk-dummy"
        self.model = model
        self.temperature = temperature
        self.max_tokens = max(max_tokens, 2048)  # 至少 2048 为推理模型预留思考空间
        self.timeout = timeout

    async def analyze_question(
        self,
        image_base64: Optional[str],
        text_content: str,
    ) -> QuestionAnalysisResult:
        # 默认优先以多模态模式发起请求 (包含屏幕截图与 OCR 文本)
        try:
            return await self._call_api(image_base64, text_content)
        except httpx.HTTPStatusError as e:
            # 若携带图像报错 400/422 (如纯文本模型不支持 image_url 节点)，自动降级为纯文本重试一次
            if e.response.status_code in [400, 422] and image_base64:
                logger.warning(
                    f"模型 [{self.model}] 传入图像返回 HTTP {e.response.status_code}，服务端可能不支持图像输入，自动降级为纯文本重试..."
                )
                return await self._call_api(None, text_content)
            raise

    async def _call_api(
        self,
        image_base64: Optional[str],
        text_content: str,
    ) -> QuestionAnalysisResult:
        user_content: List[Dict[str, Any]] = []

        # 构造提示词文本
        text_prompt = USER_QUESTION_PROMPT_TEMPLATE.format(
            extracted_text=text_content or "(未提取到清晰文字，请依据图像作答)"
        )
        user_content.append({"type": "text", "text": text_prompt})

        # 若允许并存在图片，追加多模态 image_url 节点
        if image_base64:
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image_base64}"
                }
            })

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_ASSESSMENT_PROMPT},
                {"role": "user", "content": user_content if image_base64 else text_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        logger.info(f"正在调用大模型 API [{self.model}] (图像模式: {bool(image_base64)})...")
        async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
            response = await client.post(self.endpoint, json=payload, headers=headers)
            response.raise_for_status()
            resp_data = response.json()

        choices = resp_data.get("choices", [])
        if not choices:
            raise RuntimeError(f"大模型响应缺少 choices 数据: {resp_data}")

        message = choices[0].get("message", {})
        content = message.get("content")
        reasoning_content = message.get("reasoning_content") or message.get("reasoning")

        # 健壮提取有效文本 (兼容 kimi-k2.6, deepseek-r1 等长思维模型)
        raw_text = ""
        if content is not None and str(content).strip():
            raw_text = str(content).strip()
            # 若有独立思考过程，拼接入思维链
            if reasoning_content and str(reasoning_content).strip():
                raw_text = f"【思考过程】:\n{str(reasoning_content).strip()}\n\n【回答】:\n{raw_text}"
        elif reasoning_content is not None and str(reasoning_content).strip():
            logger.info("模型未输出 content 正文，已自动提取 reasoning_content 思考链")
            raw_text = str(reasoning_content).strip()
        else:
            finish_reason = choices[0].get("finish_reason")
            if finish_reason == "length":
                raise RuntimeError(
                    f"模型输出超过最大 Token 限制 ({self.max_tokens}) 被强行截断，未能生成有效回答！"
                )
            raise RuntimeError(f"大模型返回内容为空 (choices[0].message.content 为 null)")

        logger.debug(f"大模型原始返回:\n{raw_text[:200]}...")

        # 解析清洗结构化结果
        return self._parse_json_result(raw_text)

    def _parse_json_result(self, raw_text: str) -> QuestionAnalysisResult:
        """从模型回复中提取并反序列化结构化结果"""
        cleaned = raw_text.strip()
        # 清除常见的 ```json ... ``` 包裹
        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
            if match:
                cleaned = match.group(1).strip()

        # 尝试直接解析 JSON
        try:
            data = json.loads(cleaned)
            return QuestionAnalysisResult(
                selected_option=str(data.get("selected_option", "")).upper().strip(),
                confidence=float(data.get("confidence", 0.90)),
                reasoning=str(data.get("reasoning", "")),
                is_last_question=bool(data.get("is_last_question", False)),
                raw_response=raw_text,
            )
        except Exception:
            pass

        # 尝试提取文本中内嵌的第一个 JSON 块: {...}
        json_obj_match = re.search(r"(\{[\s\S]*\"selected_option\"[\s\S]*\})", raw_text)
        if json_obj_match:
            try:
                data = json.loads(json_obj_match.group(1))
                return QuestionAnalysisResult(
                    selected_option=str(data.get("selected_option", "")).upper().strip(),
                    confidence=float(data.get("confidence", 0.90)),
                    reasoning=str(data.get("reasoning", "")),
                    is_last_question=bool(data.get("is_last_question", False)),
                    raw_response=raw_text,
                )
            except Exception:
                pass

        # 强健壮保底策略：正则智能提取选项与答案
        logger.warning("未能解析为严格 JSON，启用启发式保底提取推荐选项")
        opt_patterns = [
            r"\"selected_option\"\s*:\s*\"([A-D]+)\"",
            r"推荐[选答]?项\s*[:：]?\s*([A-D]+)",
            r"答案[选为是]?\s*[:：]?\s*([A-D]+)",
            r"选择\s*[:：]?\s*([A-D]+)",
            r"\b([A-D])\b",
        ]
        option = "A"
        for p in opt_patterns:
            m = re.search(p, raw_text, re.IGNORECASE)
            if m:
                option = m.group(1).upper()
                break

        return QuestionAnalysisResult(
            selected_option=option,
            confidence=0.75,
            reasoning=raw_text[:300],
            is_last_question=False,
            raw_response=raw_text,
        )
