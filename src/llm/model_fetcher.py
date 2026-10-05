import time
from typing import List, Optional, Tuple
import httpx
from loguru import logger


class ModelFetcher:
    """大模型列表探针与连通性测试器"""

    VISION_KEYWORDS = [
        "vl", "vision", "4o", "4v", "gemini", "minicpm", "glm-4v", 
        "omni", "kimi", "k2", "claude", "sonnet", "internvl", "pixtral"
    ]

    @classmethod
    def _clean_base_url(cls, base_url: str) -> str:
        """规范化 Base URL，清除末尾多余斜杠与聊天路径"""
        url = base_url.strip().rstrip("/")
        if url.endswith("/chat/completions"):
            url = url[:-len("/chat/completions")].rstrip("/")
        return url

    @classmethod
    def _is_vision_model(cls, model_id: str) -> bool:
        """启发式研判是否为具备视觉多模态能力的大模型"""
        m_lower = model_id.lower()
        return any(kw in m_lower for kw in cls.VISION_KEYWORDS)

    @classmethod
    async def fetch_models(
        cls, 
        base_url: str, 
        api_key: str, 
        provider_id: str = "",
        timeout: float = 12.0
    ) -> List[str]:
        """
        从目标供应商 API 端点动态拉取可用模型列表
        :param base_url: API 基础地址
        :param api_key: 访问凭据
        :param provider_id: 供应商标识 (如 siliconflow, ollama 等)
        :param timeout: 请求超时秒数
        :return: 排序后的模型 ID 列表
        """
        clean_url = cls._clean_base_url(base_url)
        if not clean_url:
            raise ValueError("Base URL 不能为空")

        headers = {
            "Authorization": f"Bearer {api_key.strip()}" if api_key.strip() else "",
            "Content-Type": "application/json",
        }

        # 候选的 models 请求端点
        endpoints = [f"{clean_url}/models"]
        if not clean_url.endswith("/v1"):
            endpoints.append(f"{clean_url}/v1/models")

        # 若是本地 Ollama，追加 /api/tags 端点
        if provider_id == "ollama" or "11434" in clean_url:
            endpoints.append(f"{clean_url}/api/tags")

        raw_models: List[str] = []
        last_error = None

        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            for ep in endpoints:
                try:
                    logger.info(f"正在尝试拉取模型列表: {ep}")
                    resp = await client.get(ep, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        # 标准 OpenAI 格式: {"data": [{"id": "..."}, ...]}
                        if "data" in data and isinstance(data["data"], list):
                            for item in data["data"]:
                                if isinstance(item, dict) and "id" in item:
                                    raw_models.append(str(item["id"]))
                                elif isinstance(item, str):
                                    raw_models.append(item)
                            if raw_models:
                                break

                        # Ollama 原生格式: {"models": [{"name": "..."}, ...]}
                        if "models" in data and isinstance(data["models"], list):
                            for item in data["models"]:
                                if isinstance(item, dict) and "name" in item:
                                    raw_models.append(str(item["name"]))
                            if raw_models:
                                break
                    elif resp.status_code in [401, 403]:
                        raise PermissionError(f"身份认证失败 ({resp.status_code})，请检查 API Key 是否正确有效")
                    else:
                        last_error = f"HTTP {resp.status_code}: {resp.text[:100]}"
                except PermissionError:
                    raise
                except Exception as e:
                    last_error = str(e)
                    continue

        if not raw_models:
            err_msg = f"未能从端点拉取到模型列表 ({last_error or '端点未返回有效数据'})"
            logger.warning(err_msg)
            raise RuntimeError(err_msg)

        # 排序：具备视觉多模态能力的模型优先置顶，其余字母升序排序
        vision_models = sorted([m for m in raw_models if cls._is_vision_model(m)])
        text_models = sorted([m for m in raw_models if not cls._is_vision_model(m)])

        return vision_models + text_models

    @classmethod
    async def test_connectivity(
        cls, 
        base_url: str, 
        api_key: str, 
        model: str, 
        timeout: float = 12.0
    ) -> Tuple[bool, str, float]:
        """
        测试端点连通性、Key 与指定 Model 的可用性
        :return: (is_success, detail_message, latency_ms)
        """
        clean_url = cls._clean_base_url(base_url)
        if not clean_url:
            return False, "Base URL 为空", 0.0

        headers = {
            "Authorization": f"Bearer {api_key.strip()}" if api_key.strip() else "",
            "Content-Type": "application/json",
        }

        # 端点补全
        endpoint = clean_url if clean_url.endswith("/chat/completions") else f"{clean_url}/chat/completions"
        if not clean_url.endswith("/v1") and not clean_url.endswith("/chat/completions") and "/v" not in clean_url:
            endpoint = f"{clean_url}/v1/chat/completions"

        payload = {
            "model": model.strip() if model.strip() else "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
            "temperature": 0.1,
        }

        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
                resp = await client.post(endpoint, json=payload, headers=headers)
                latency_ms = (time.perf_counter() - start_time) * 1000

                if resp.status_code == 200:
                    return True, "连接成功，模型响应正常", latency_ms
                elif resp.status_code in [401, 403]:
                    return False, f"鉴权失败 (HTTP {resp.status_code})，请检查 API Key", latency_ms
                elif resp.status_code == 404:
                    return False, f"端点未找到 (HTTP 404)，请检查 Base URL 是否正确", latency_ms
                else:
                    err_txt = resp.text[:120]
                    return False, f"服务返回异常 (HTTP {resp.status_code}): {err_txt}", latency_ms
        except httpx.ConnectError:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return False, "无法连接到服务器，请检查网络或 Base URL", latency_ms
        except httpx.TimeoutException:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return False, f"请求超时 (超过 {timeout} 秒)", latency_ms
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return False, f"连接异常: {str(e)[:80]}", latency_ms
