import json
import re
from typing import Any, Dict, List, Optional
import httpx
from loguru import logger

from ..base import BaseLLMProvider, QuestionAnalysisResult
from ..prompt_templates import SYSTEM_ASSESSMENT_PROMPT, USER_QUESTION_PROMPT_TEMPLATE


class GeminiProvider(BaseLLMProvider):
    """Google Gemini 原生 REST API 适配器 (零额外 SDK 依赖)"""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-1.5-flash",
        temperature: float = 0.1,
        timeout: float = 25.0,
    ):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

    async def analyze_question(
        self,
        image_base64: Optional[str],
        text_content: str,
    ) -> QuestionAnalysisResult:
        parts: List[Dict[str, Any]] = []

        # 组合提示词
        full_text = f"{SYSTEM_ASSESSMENT_PROMPT}\n\n" + USER_QUESTION_PROMPT_TEMPLATE.format(
            extracted_text=text_content or "(未提取到文本)"
        )
        parts.append({"text": full_text})

        if image_base64:
            parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": image_base64
                }
            })

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": self.temperature,
                "response_mime_type": "application/json",
            }
        }

        params = {"key": self.api_key}

        logger.info(f"正在调用 Google Gemini API [{self.model}]...")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.url, json=payload, params=params)
            response.raise_for_status()
            data = response.json()

        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini 未返回有效候选结果")

        raw_text = candidates[0]["content"]["parts"][0]["text"].strip()
        logger.debug(f"Gemini 原始返回:\n{raw_text}")

        return self._parse_json(raw_text)

    def _parse_json(self, raw_text: str) -> QuestionAnalysisResult:
        cleaned = raw_text.strip()
        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
            if match:
                cleaned = match.group(1).strip()

        try:
            val = json.loads(cleaned)
            return QuestionAnalysisResult(
                selected_option=str(val.get("selected_option", "")).upper().strip(),
                confidence=float(val.get("confidence", 0.9)),
                reasoning=str(val.get("reasoning", "")),
                is_last_question=bool(val.get("is_last_question", False)),
                raw_response=raw_text,
            )
        except Exception as e:
            logger.warning(f"Gemini JSON 解析异常 ({e})")
            opt_match = re.search(r"\b([A-D])\b", raw_text)
            return QuestionAnalysisResult(
                selected_option=opt_match.group(1) if opt_match else "A",
                confidence=0.5,
                reasoning=raw_text[:200],
                is_last_question=False,
                raw_response=raw_text,
            )
