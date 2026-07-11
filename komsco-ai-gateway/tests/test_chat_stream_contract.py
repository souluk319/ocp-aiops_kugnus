import asyncio
import json

import httpx

import komsco_ai_gateway.main as gateway_main
from komsco_ai_gateway.main import EVIDENCE_RECORDS, app
from komsco_ai_gateway.security import safe_subject


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


def test_chat_stream_emits_rca_context_event(monkeypatch) -> None:
    EVIDENCE_RECORDS.clear()
    gateway_main.LAST_RCA_CONTEXT = None

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMANDS_ENABLED", True)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={"message": "OpenShift 상태 간단히 확인해줘", "runId": "run-rca-test"},
            )

        assert response.status_code == 200
        assert "test-token" not in response.text
        events = parse_sse_events(response.text)
        rca_events = [
            event
            for event in events
            if isinstance(event, dict) and event.get("type") == "rca_context"
        ]
        answer_contracts = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "text"
            and event.get("answerContract") == "aiops-action-v0.1.9"
        ]
        assert len(rca_events) >= 2
        latest_context = rca_events[-1]["context"]
        assert latest_context["kind"] == "RcaContext"
        assert latest_context["metadata"]["runId"] == "run-rca-test"
        assert latest_context["metadata"]["phase"] == "post_answer"
        assert latest_context["metadata"]["digest"].startswith("sha256:")
        assert latest_context["evidence"]["summary"]["missingCount"] >= 1
        assert answer_contracts == []
        assert "ActionProposal -> SealedActionPlan" not in response.text
        assert gateway_main.LAST_RCA_CONTEXT["metadata"]["digest"] == latest_context["metadata"]["digest"]

    asyncio.run(run())


def test_chat_stream_ops_question_connects_plan_evidence_final_text_and_action_contract(monkeypatch) -> None:
    EVIDENCE_RECORDS.clear()
    gateway_main.LAST_RCA_CONTEXT = None

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_call_ols_stream(*_args, **_kwargs):
        yield {
            "type": "tool_result",
            "name": "openshift_event_lookup",
            "status": "success",
            "summary": "default namespace restart event evidence collected",
        }
        yield {
            "type": "text",
            "content": (
                "원인: OOMKilled 가능성이 가장 큽니다.\n"
                "조치: resource limit과 최근 배포 변경을 확인한 뒤 승인 계획으로 복구합니다.\n"
            ),
        }
        yield {"type": "end"}

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "call_ols_stream", fake_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "어제 새벽에 default namespace Pod가 왜 재시작됐어?",
                    "runId": "run-full-aiops-contract",
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        assert events[-1] == "[DONE]"
        tool_plan_index = next(
            index
            for index, event in enumerate(events)
            if isinstance(event, dict) and event.get("type") == "tool_plan"
        )
        evidence_ref_index = next(
            index
            for index, event in enumerate(events)
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "evidence_ref"
        )
        pre_answer_index = next(
            index
            for index, event in enumerate(events)
            if isinstance(event, dict)
            and event.get("type") == "rca_context"
            and event.get("context", {}).get("metadata", {}).get("phase") == "pre_answer"
        )
        final_text_index = next(
            index
            for index, event in enumerate(events)
            if isinstance(event, dict)
            and event.get("type") == "text"
            and "원인: OOMKilled" in event.get("content", "")
        )
        action_contract_index = next(
            index
            for index, event in enumerate(events)
            if isinstance(event, dict)
            and event.get("type") == "text"
            and event.get("answerContract") == "aiops-action-v0.1.9"
        )
        post_answer_events = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "rca_context"
            and event.get("context", {}).get("metadata", {}).get("phase") == "post_answer"
        ]

        assert tool_plan_index < evidence_ref_index < pre_answer_index < final_text_index
        assert final_text_index < action_contract_index
        assert post_answer_events
        action_candidates = post_answer_events[-1]["context"]["rcaResult"]["action_candidates"]
        assert any("resource limit" in candidate for candidate in action_candidates)
        assert "Action Plan" in events[
            action_contract_index
        ]["content"]
        assert "ActionProposal -> SealedActionPlan -> ApprovalDecision -> ExecutionRecord" not in events[
            action_contract_index
        ]["content"]

    asyncio.run(run())


def test_chat_stream_unexpected_exception_emits_failed_rca_context_before_done(monkeypatch) -> None:
    EVIDENCE_RECORDS.clear()
    gateway_main.LAST_RCA_CONTEXT = None

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        raise RuntimeError(
            "synthetic product access failure Authorization: Bearer super-secret-token token=raw-secret"
        )

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMANDS_ENABLED", True)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={"message": "OpenShift 상태 확인", "runId": "run-rca-failed-test"},
            )

        assert response.status_code == 200
        assert "super-secret-token" not in response.text
        assert "raw-secret" not in response.text
        assert "Authorization: [REDACTED]" in response.text
        assert "token=[REDACTED]" in response.text
        events = parse_sse_events(response.text)
        assert events[-1] == "[DONE]"
        rca_events = [
            (index, event)
            for index, event in enumerate(events)
            if isinstance(event, dict) and event.get("type") == "rca_context"
        ]
        assert rca_events
        failed_index, failed_event = rca_events[-1]
        done_index = len(events) - 1
        assert failed_index < done_index
        context = failed_event["context"]
        assert context["kind"] == "RcaContext"
        assert context["metadata"]["phase"] == "failed"
        assert context["metadata"]["runId"] == "run-rca-failed-test"
        assert context["confidence"]["level"] == "insufficient_evidence"
        assert context["evidence"]["summary"]["missingCount"] >= 1
        assert gateway_main.LAST_RCA_CONTEXT["metadata"]["digest"] == context["metadata"]["digest"]

    asyncio.run(run())
