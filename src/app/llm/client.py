"""OpenAI 兼容模型的无状态客户端。

职责边界（重要）：
- 只负责一次请求：鉴权、超时、response_format 降级、错误分类、用量返回；
- **不保存会话/消息历史**。上下文由调用方每次显式传入 messages；
- 不做 prompt 组装、JSON 校验、业务重试——这些属于领域编排层。

因此，把它抽成独立文件不会改变任何 session 的上下文；也不会出现
多用户/多标签页串话——客户端本身没有“当前会话”这种状态。
"""

import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LLMResponse:
    content: str
    finish_reason: str | None
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LLMError(Exception):
    """模型接入层错误；status_code 供 API 层透传。"""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


@lru_cache(maxsize=4)
def _build_client(api_key: str, base_url: str, timeout: int) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)


def get_client() -> OpenAI:
    api_key = (settings.LLM_API_KEY or "").strip()
    if not api_key:
        raise LLMError("未配置 LLM_API_KEY，无法调用模型", status_code=503)
    # 缓存键包含配置值：改 .env 并重启后会生成新客户端，不会复用旧 key
    return _build_client(api_key, settings.LLM_BASE_URL, settings.LLM_TIMEOUT_SECONDS)


def _request(
    client: OpenAI,
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    temperature: float,
    json_mode: bool,
) -> Any:
    kwargs: dict[str, Any] = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    return client.chat.completions.create(**kwargs)


def _provider_message(exc: BadRequestError) -> str:
    """尽量取出上游 400 的可读原因；只在日志/映射中使用，不回显 key。"""
    response = getattr(exc, "response", None)
    if response is not None:
        data = None
        try:
            data = response.json()
        except ValueError:
            data = None
        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if isinstance(message, str) and message:
                    return message
        text = getattr(response, "text", "")
        if isinstance(text, str) and text:
            return text[:300]
    return str(exc)[:300]


def chat(
    messages: Sequence[Mapping[str, str]],
    *,
    max_tokens: int = 2000,
    temperature: float = 0.2,
    json_mode: bool = True,
) -> LLMResponse:
    """发起一次无状态对话请求。messages 由调用方负责组装与持久化。"""
    client = get_client()
    payload = [dict(message) for message in messages]
    started = time.perf_counter()

    try:
        try:
            response = _request(
                client,
                payload,
                max_tokens=max_tokens,
                temperature=temperature,
                json_mode=json_mode,
            )
        except BadRequestError as exc:
            # 部分 OpenAI 兼容端点不支持 response_format，降级为提示词约束
            message = str(exc).lower()
            if json_mode and ("response_format" in message or "json" in message):
                logger.warning("provider rejected response_format, retrying without it")
                response = _request(
                    client,
                    payload,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    json_mode=False,
                )
            else:
                raise
    except AuthenticationError as exc:
        raise LLMError("模型鉴权失败，请检查 LLM_API_KEY 是否有效") from exc
    except PermissionDeniedError as exc:
        raise LLMError("当前 key 没有该模型的调用权限") from exc
    except RateLimitError as exc:
        raise LLMError("模型限流或额度不足，请稍后再试") from exc
    except (APITimeoutError, APIConnectionError) as exc:
        raise LLMError("模型服务超时或网络不可达，请稍后再试") from exc
    except BadRequestError as exc:
        provider_message = _provider_message(exc)
        logger.error("model rejected request: %s", provider_message)
        lowered = provider_message.lower()
        if "location is not supported" in lowered:
            raise LLMError(
                "当前网络或账号所在地区不受模型服务支持，请更换可用网络或模型"
            ) from exc
        if "not found" in lowered and "model" in lowered:
            raise LLMError("模型名称不可用，请检查 LLM_MODEL 配置") from exc
        raise LLMError("模型请求被拒绝，请检查模型名称、参数或账号权限") from exc
    except InternalServerError as exc:
        raise LLMError("模型服务暂时不可用，请稍后重试") from exc
    except Exception as exc:
        logger.exception("LLM request failed")
        raise LLMError("模型调用失败，请稍后重试") from exc

    latency = time.perf_counter() - started
    if not response.choices:
        raise LLMError("模型返回为空，请稍后重试")

    choice = response.choices[0]
    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    logger.info(
        "llm call model=%s json_mode=%s max_tokens=%s latency=%.2fs prompt_tokens=%s completion_tokens=%s finish=%s",
        getattr(response, "model", settings.LLM_MODEL),
        json_mode,
        max_tokens,
        latency,
        prompt_tokens,
        completion_tokens,
        choice.finish_reason,
    )

    return LLMResponse(
        content=choice.message.content or "",
        finish_reason=choice.finish_reason,
        model=getattr(response, "model", None) or settings.LLM_MODEL,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
