from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException


@dataclass(frozen=True, slots=True)
class LlmStreamConfig:
    api_style: str
    base_url: str
    model: str
    timeout_seconds: float
    heartbeat_seconds: float
    ols_base_url: str
    ols_ca_file: str | bool
    ols_connect_timeout_seconds: float
    dev_echo: bool
    require_final_answer: bool


@dataclass(frozen=True, slots=True)
class LlmStreamDependencies:
    build_ols_payload: Callable[..., Mapping[str, Any]]
    forward_image_attachments: Callable[[], bool]
    parse_tool_text_line: Callable[[str], Mapping[str, Any] | None]
    safe_error_text: Callable[..., str]
    safe_exception_text: Callable[[BaseException], str]
    split_plain_text_events: Callable[[AsyncIterator[str]], AsyncIterator[dict[str, Any]]]
    update_status: Callable[..., None]
    status_snapshot: Callable[[], Mapping[str, Any]]


def should_use_ollama(config: LlmStreamConfig) -> bool:
    return config.api_style == "ollama" and bool(config.base_url)


def active_stage(config: LlmStreamConfig) -> str:
    return "ollama" if should_use_ollama(config) else "lightspeed"


def active_label(config: LlmStreamConfig) -> str:
    return "Ollama LLM" if should_use_ollama(config) else "OpenShift Lightspeed"


def build_ollama_chat_url(base_url: str) -> str:
    url = base_url.rstrip("/")
    if url.endswith("/api/chat"):
        return url
    if url.endswith("/api"):
        return f"{url}/chat"
    return f"{url}/api/chat"


def extract_ollama_chat_content(data: Mapping[str, Any]) -> str:
    message = data.get("message")
    if isinstance(message, Mapping):
        content = message.get("content")
        if isinstance(content, str):
            return content
    response = data.get("response")
    if isinstance(response, str):
        return response
    return ""


def context_digest(gateway_context: Mapping[str, Any] | None) -> str:
    if not isinstance(gateway_context, Mapping):
        return ""
    metadata = gateway_context.get("metadata")
    if not isinstance(metadata, Mapping):
        return ""
    return str(metadata.get("digest") or "")


async def stream_with_heartbeats(
    events: AsyncIterator[dict[str, Any]],
    run_id: str,
    *,
    config: LlmStreamConfig,
) -> AsyncIterator[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any] | BaseException | None] = asyncio.Queue()
    started_at = time.monotonic()

    async def produce() -> None:
        try:
            async for event in events:
                await queue.put(event)
        except BaseException as exc:
            await queue.put(exc)
        finally:
            await queue.put(None)

    producer = asyncio.create_task(produce())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=config.heartbeat_seconds)
            except TimeoutError:
                yield {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": "waiting",
                    "message": f"{active_label(config)} 응답 대기 중",
                    "elapsedMs": int((time.monotonic() - started_at) * 1000),
                }
                continue

            if item is None:
                break
            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        if not producer.done():
            producer.cancel()


async def call_ollama_chat(
    query: str,
    conversation_id: str | None,
    gateway_context: Mapping[str, Any] | None,
    *,
    config: LlmStreamConfig,
    dependencies: LlmStreamDependencies,
) -> AsyncIterator[dict[str, Any]]:
    digest = context_digest(gateway_context)
    if not config.base_url or not config.model:
        reason = "KOMSCO_AI_LLM_BASE_URL or KOMSCO_AI_LLM_MODEL is not configured"
        dependencies.update_status(
            "not_configured",
            context_digest=digest,
            fallback_active=not config.require_final_answer,
            reason=reason,
        )
        if config.require_final_answer:
            raise RuntimeError(reason)
        yield {
            "type": "text",
            "content": "DEV_ECHO: Gateway is running. Configure KOMSCO_AI_LLM_BASE_URL and KOMSCO_AI_LLM_MODEL.\n\n",
            "source": "gateway_fallback",
            "fallbackAnswer": True,
            "gatewayContextDigest": digest,
            "streamProbe": "not_configured",
        }
        yield {"type": "end", "conversationId": conversation_id}
        return

    payload = {
        "model": config.model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "너는 KOMSCO AIOps 운영 분석가다. 확인 결과와 추정을 분리하고, "
                    "위험한 조치는 승인 전 실행 지시로 쓰지 않는다. "
                    "답변은 `현재 판단`, `원인 후보`, `확인 결과`, `조치 방법`, `추가 확인` 순서를 우선한다. "
                    "코드블록 안에는 실행 가능한 명령만 넣고, "
                    "`Tip`, 주의사항, 확인 항목, 제목, 목록 문장은 코드블록 밖에 둔다. "
                    "공용 웹 URL은 기본 답변에 출력하지 마세요."
                ),
            },
            {"role": "user", "content": query},
        ],
        "stream": False,
        "think": False,
    }
    dependencies.update_status("started", context_digest=digest)

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout_seconds, connect=10.0),
        ) as client:
            response = await client.post(
                build_ollama_chat_url(config.base_url),
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            if response.status_code >= 400:
                detail = dependencies.safe_error_text(response.text[:1000], limit=1000)
                dependencies.update_status(
                    "failed",
                    context_digest=digest,
                    fallback_active=not config.require_final_answer,
                    reason=f"HTTP {response.status_code}: {detail}",
                )
                raise HTTPException(status_code=response.status_code, detail=detail)
            data = response.json()

        if not isinstance(data, Mapping):
            raise ValueError("Ollama chat response is not a JSON object")
        content = extract_ollama_chat_content(data)
        if not content.strip():
            raise ValueError("Ollama chat response did not include message.content")

        dependencies.update_status("succeeded", context_digest=digest)
        yield {
            "type": "text",
            "content": content,
            "source": "ollama_chat",
            "gatewayContextDigest": digest,
            "streamProbe": "succeeded",
        }
        yield {"type": "end", "conversationId": conversation_id}
    except Exception as exc:
        if dependencies.status_snapshot().get("lastStatus") != "failed":
            dependencies.update_status(
                "failed",
                context_digest=digest,
                fallback_active=not config.require_final_answer,
                reason=dependencies.safe_exception_text(exc),
            )
        raise


async def call_ols_stream(
    user_auth_header: str,
    query: str,
    conversation_id: str | None,
    attachments: list[Any],
    gateway_context: Mapping[str, Any] | None,
    *,
    config: LlmStreamConfig,
    dependencies: LlmStreamDependencies,
) -> AsyncIterator[dict[str, Any]]:
    digest = context_digest(gateway_context)
    if should_use_ollama(config):
        async for event in call_ollama_chat(
            query,
            conversation_id,
            gateway_context,
            config=config,
            dependencies=dependencies,
        ):
            yield event
        return

    if config.dev_echo or not config.ols_base_url:
        fallback_status = "dev_echo" if config.dev_echo else "not_configured"
        fallback_reason = "DEV_ECHO enabled" if config.dev_echo else "OLS_BASE_URL is not configured"
        dependencies.update_status(
            fallback_status,
            context_digest=digest,
            fallback_active=not config.require_final_answer,
            reason=fallback_reason,
        )
        if config.require_final_answer:
            raise RuntimeError(fallback_reason)
        yield {
            "type": "text",
            "content": "DEV_ECHO: Gateway is running. Configure OLS_BASE_URL for Lightspeed streaming.\n\n",
            "source": "gateway_fallback",
            "fallbackAnswer": True,
            "gatewayContextDigest": digest,
            "streamProbe": fallback_status,
        }
        yield {
            "type": "text",
            "content": query[:1200],
            "source": "gateway_fallback",
            "fallbackAnswer": True,
            "gatewayContextDigest": digest,
            "streamProbe": fallback_status,
        }
        yield {"type": "end", "conversationId": conversation_id}
        return

    payload = dependencies.build_ols_payload(
        query,
        conversation_id,
        attachments,
        forward_image_attachments=dependencies.forward_image_attachments(),
        gateway_context=gateway_context,
    )
    dependencies.update_status("started", context_digest=digest)

    try:
        async with httpx.AsyncClient(
            verify=config.ols_ca_file,
            timeout=httpx.Timeout(
                config.timeout_seconds,
                connect=config.ols_connect_timeout_seconds,
            ),
        ) as client:
            async with client.stream(
                "POST",
                f"{config.ols_base_url}/v1/streaming_query",
                headers={
                    "Accept": "text/event-stream",
                    "Authorization": user_auth_header,
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    detail = body.decode("utf-8", errors="replace")
                    safe_detail = dependencies.safe_error_text(detail, limit=1000)
                    dependencies.update_status(
                        "failed",
                        context_digest=digest,
                        fallback_active=not config.require_final_answer,
                        reason=f"HTTP {response.status_code}: {safe_detail}",
                    )
                    raise HTTPException(status_code=response.status_code, detail=safe_detail)

                content_type = response.headers.get("content-type", "")
                if "text/event-stream" not in content_type:
                    async for event in dependencies.split_plain_text_events(response.aiter_text()):
                        yield event
                    dependencies.update_status("succeeded", context_digest=digest)
                    return

                buffer = ""
                async for chunk in response.aiter_text():
                    if not chunk:
                        continue
                    buffer += chunk
                    frames = buffer.split("\n\n")
                    buffer = frames.pop() or ""

                    for frame in frames:
                        data_lines = [
                            line[len("data:") :].strip()
                            for line in frame.splitlines()
                            if line.startswith("data:")
                        ]
                        if not data_lines:
                            async def iter_frame() -> AsyncIterator[str]:
                                yield frame + "\n"

                            async for event in dependencies.split_plain_text_events(iter_frame()):
                                yield event
                            continue

                        raw = "\n".join(data_lines)
                        if not raw or raw == "[DONE]":
                            continue
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            tool_event = dependencies.parse_tool_text_line(raw)
                            yield tool_event or {"type": "text", "content": raw}
                            continue
                        yield event

                if buffer.strip() and not buffer.lstrip().startswith("data:"):
                    async def iter_buffer() -> AsyncIterator[str]:
                        yield buffer

                    async for event in dependencies.split_plain_text_events(iter_buffer()):
                        yield event
                dependencies.update_status("succeeded", context_digest=digest)
    except Exception as exc:
        if dependencies.status_snapshot().get("lastStatus") != "failed":
            dependencies.update_status(
                "failed",
                context_digest=digest,
                fallback_active=not config.require_final_answer,
                reason=dependencies.safe_exception_text(exc),
            )
        raise
