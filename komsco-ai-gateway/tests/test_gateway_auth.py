import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException

import komsco_ai_gateway.main as gateway_main
from komsco_ai_gateway.main import app


def test_verify_bearer_header_rejects_empty_bearer_token() -> None:
    with pytest.raises(HTTPException) as caught:
        gateway_main.verify_bearer_header("Bearer ")

    assert caught.value.status_code == 401


def test_self_subject_review_timeout_raises_structured_504(monkeypatch) -> None:
    class TimeoutClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, *args, **kwargs):
            raise httpx.ConnectTimeout("connect timed out")

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.example:6443")
    monkeypatch.setattr(gateway_main.httpx, "AsyncClient", TimeoutClient)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(gateway_main.fetch_self_subject_review("Bearer test-token"))

    assert exc.value.status_code == 504
    assert exc.value.detail["code"] == "openshift_api_unavailable"
    assert exc.value.detail["operation"] == "self_subject_review"


def test_chat_stream_handles_openshift_user_auth_401_without_raw_status(monkeypatch) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        raise HTTPException(
            status_code=401,
            detail=gateway_main.build_openshift_user_auth_failure_detail(
                401,
                '{"kind":"Status","apiVersion":"v1","status":"Failure","message":"Unauthorized","reason":"Unauthorized","code":401}',
            ),
        )

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)

    def parse_sse_events(body: str) -> list[dict | str]:
        events: list[dict | str] = []
        for frame in body.split("\n\n"):
            data_lines = [
                line[len("data:") :].strip()
                for line in frame.splitlines()
                if line.startswith("data:")
            ]
            if not data_lines:
                continue
            raw = "\n".join(data_lines)
            events.append("[DONE]" if raw == "[DONE]" else json.loads(raw))
        return events

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer expired-token"},
                json={"message": "aiops-scenario-1-crashloop 이거 왜 재시작해?"},
            )

        assert response.status_code == 200
        body = response.text
        events = parse_sse_events(body)
        text_events = [event for event in events if isinstance(event, dict) and event.get("type") == "text"]
        subject_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "subject_review"
        ]

        assert subject_results[-1]["status"] == "error"
        assert "사용자 인증이 만료" in text_events[-1]["content"]
        assert "새로고침" in text_events[-1]["content"]
        assert "OpenShift subject review failed" not in body
        assert '"kind":"Status"' not in body
        assert events[-1] == "[DONE]"

    asyncio.run(run())
