import asyncio
import json
from collections.abc import Mapping

import httpx
import pytest

import komsco_ai_gateway.main as gateway_main
from komsco_ai_gateway.main import (
    ACTION_PROPOSALS,
    APPROVAL_DECISIONS,
    EXECUTION_RECORDS,
    SEALED_ACTION_PLANS,
    app,
    parse_natural_action_intent,
)
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


def assert_post_answer_rca_before_done(events: list[dict | str]) -> dict:
    assert events[-1] == "[DONE]"
    rca_events = [
        (index, event)
        for index, event in enumerate(events)
        if isinstance(event, dict) and event.get("type") == "rca_context"
    ]
    assert rca_events
    latest_index, latest_event = rca_events[-1]
    assert latest_index == len(events) - 2
    context = latest_event["context"]
    assert context["metadata"]["phase"] == "post_answer"
    assert (
        context["evidence"]["summary"]["collectedCount"] > 0
        or context["evidence"]["summary"]["missingCount"] > 0
        or context["confidence"]["level"] == "insufficient_evidence"
    )
    return context


def test_chat_stream_unrestricted_executes_natural_scale_action(monkeypatch) -> None:
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()
    APPROVAL_DECISIONS.clear()
    EXECUTION_RECORDS.clear()

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return {"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]}

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_action_access_review(_user_auth_header: str, plan: dict) -> dict:
        target = plan["target"]
        return {
            "allowed": True,
            "enabled": True,
            "resourceAttributes": {
                "group": "apps",
                "name": target["name"],
                "namespace": target["namespace"],
                "resource": "deployments",
                "subresource": "scale",
                "verb": "update",
            },
        }

    async def fake_fetch_ocp_json(_client, path: str, _authorization: str, *_, **__) -> dict:
        assert "/apis/apps/v1/namespaces/team-a/deployments/web-api" in path
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "web-api",
                "namespace": "team-a",
                "uid": "deployment-uid-a",
            },
        }

    async def fake_execute_action_with_executor(
        sealed_plan: dict,
        _grant_reference: dict,
        *,
        fallback_authorization: str | None = None,
    ) -> dict:
        assert sealed_plan["action"]["toolName"] == "set_replicas_within_bounds"
        assert sealed_plan["action"]["normalizedParameters"]["replicas"] == 3
        assert fallback_authorization == "Bearer token"
        return {
            "mutationOutcome": {
                "status": "mutation_succeeded",
                "reason": "typed_action_executed",
                "httpStatus": 200,
            },
            "remediationOutcome": {
                "status": "verified",
                "reason": "scale_spec_matches",
                "observedReplicas": 3,
            },
            "executorTrace": {
                "mutationSubmitted": True,
                "toolName": "set_replicas_within_bounds",
            },
        }

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.test:6443")
    monkeypatch.setattr(gateway_main, "MUTATIONS_ENABLED", True)
    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMANDS_ENABLED", True)
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "fetch_action_access_review", fake_action_access_review)
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fake_fetch_ocp_json)
    monkeypatch.setattr(gateway_main, "execute_action_with_executor", fake_execute_action_with_executor)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "team-a 네임스페이스의 web-api 파드 3개로 올려줘",
                    "pageContext": {"aiopsExecutionMode": "unrestricted"},
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        execute_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "natural_action_execute"
        ]
        text_events = [
            event
            for event in events
            if isinstance(event, dict) and event.get("type") == "text"
        ]
        assert execute_results
        assert execute_results[0]["status"] == "success"
        assert execute_results[0]["result"]["status"] == "executed"
        assert execute_results[0]["result"]["mutationOutcome"]["status"] == "mutation_succeeded"
        assert len(ACTION_PROPOSALS) == 1
        assert len(SEALED_ACTION_PLANS) == 1
        assert len(APPROVAL_DECISIONS) == 1
        assert len(EXECUTION_RECORDS) == 1
        answer_text = "\n".join(event.get("content", "") for event in text_events)
        plan_id = next(iter(SEALED_ACTION_PLANS))
        approval_id = next(iter(APPROVAL_DECISIONS))
        execution_id = next(iter(EXECUTION_RECORDS))
        assert "실행까지 완료" in answer_text
        assert "- Parameters: `" in answer_text
        assert '"replicas": 3' in answer_text
        assert '"hpaReviewed": false' in answer_text
        assert f"- Plan: `{plan_id}`" in answer_text
        assert f"- Approval: `{approval_id}`" in answer_text
        assert f"- Execution: `{execution_id}`" in answer_text
        assert "- Mutation: `mutation_succeeded` / `typed_action_executed`" in answer_text
        assert "- Verification: `verified` / `scale_spec_matches`" in answer_text
        context = assert_post_answer_rca_before_done(events)
        assert context["confidence"]["level"] == "insufficient_evidence"

    asyncio.run(run())


def test_chat_stream_unrestricted_context_does_not_execute_when_server_flag_disabled(
    monkeypatch,
) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_create_natural_action_plan(req, *_args, **_kwargs):
        assert req.message == "team-a 네임스페이스의 web-api 파드 3개로 올려줘"
        return {
            "intent": {
                "kind": "Deployment",
                "namespace": "team-a",
                "parameters": {"replicas": 3},
                "targetName": "web-api",
                "toolName": "set_replicas_within_bounds",
            },
            "planId": "plan-unrestricted-disabled",
            "status": "planned",
            "target": {"kind": "Deployment", "namespace": "team-a", "name": "web-api"},
        }

    async def fail_execute_natural_action_plan_result(*_args, **_kwargs):
        raise AssertionError("unrestricted page context must not execute while server flag is disabled")

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError("OLS must not be called for action plan responses")

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMANDS_ENABLED", False)
    monkeypatch.setattr(gateway_main, "create_natural_action_plan", fake_create_natural_action_plan)
    monkeypatch.setattr(
        gateway_main,
        "execute_natural_action_plan_result",
        fail_execute_natural_action_plan_result,
    )
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "team-a 네임스페이스의 web-api 파드 3개로 올려줘",
                    "pageContext": {"aiopsExecutionMode": "unrestricted"},
                },
            )

        assert response.status_code == 200
        assert "plan-unrestricted-disabled" in response.text
        assert "natural_action_execute" not in response.text
        assert "실행까지 완료" not in response.text

    asyncio.run(run())


def test_chat_stream_unrestricted_followup_without_plan_stays_in_gateway(monkeypatch) -> None:
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()
    APPROVAL_DECISIONS.clear()
    EXECUTION_RECORDS.clear()

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
                json={
                    "message": "진행해",
                    "pageContext": {"aiopsExecutionMode": "unrestricted"},
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        followup_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "natural_action_followup"
        ]
        assert followup_results
        assert followup_results[0]["status"] == "skipped"
        assert "실행할 Gateway AIOps Action Plan이 없습니다" in response.text
        assert "lightspeed_stream" not in response.text

    asyncio.run(run())


def test_chat_stream_unrestricted_followup_uses_recent_user_action_context(monkeypatch) -> None:
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()
    APPROVAL_DECISIONS.clear()
    EXECUTION_RECORDS.clear()

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_create_natural_action_plan(req, *_args, **_kwargs):
        assert req.message == "team-a 네임스페이스의 web-api 파드 4개로 올려줘"
        return {
            "intent": {
                "toolName": "set_replicas_within_bounds",
                "targetName": "web-api",
                "namespace": "team-a",
                "parameters": {"replicas": 4},
            },
            "parameters": {"replicas": 4},
            "planDigest": "sha256:test-plan",
            "planId": "plan-contextual",
            "proposalId": "proposal-contextual",
            "risk": "medium",
            "status": "planned",
            "target": {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "namespace": "team-a",
                "name": "web-api",
                "uid": "uid-web-api",
            },
        }

    async def fake_execute_natural_action_plan_result(plan_result, *_args, **_kwargs):
        return {
            "approvalId": "approval-contextual",
            "executionId": "execution-contextual",
            "mutationOutcome": {"status": "mutation_succeeded", "reason": "typed_action_executed"},
            "plan": dict(plan_result),
            "remediationOutcome": {
                "status": "verified",
                "reason": "scale_spec_matches",
                "observedReplicas": 4,
            },
            "status": "executed",
        }

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError("OLS must not be called for contextual followup execution")

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMANDS_ENABLED", True)
    monkeypatch.setattr(gateway_main, "create_natural_action_plan", fake_create_natural_action_plan)
    monkeypatch.setattr(
        gateway_main,
        "execute_natural_action_plan_result",
        fake_execute_natural_action_plan_result,
    )
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "진행해",
                    "pageContext": {"aiopsExecutionMode": "unrestricted"},
                    "recentMessages": [
                        {
                            "role": "user",
                            "content": "team-a 네임스페이스의 web-api 파드 4개로 올려줘",
                        },
                        {
                            "role": "assistant",
                            "content": "조치 계획을 생성했습니다. 승인하시겠습니까?",
                        },
                    ],
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        followup_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "natural_action_followup"
        ]
        assert followup_results
        assert followup_results[0]["status"] == "success"
        assert "team-a/web-api" in response.text
        assert "scale_spec_matches" in response.text
        assert "lightspeed_stream" not in response.text
        context = assert_post_answer_rca_before_done(events)
        assert context["confidence"]["level"] == "insufficient_evidence"

    asyncio.run(run())


def test_chat_stream_unrestricted_followup_executes_pending_action_with_post_answer_rca(
    monkeypatch,
) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    def fake_latest_pending_action_plan_result(_subject: Mapping[str, object]) -> dict:
        return {
            "intent": {
                "kind": "Deployment",
                "namespace": "team-a",
                "parameters": {"replicas": 4},
                "targetName": "web-api",
                "toolName": "set_replicas_within_bounds",
            },
            "planId": "plan-pending",
            "status": "planned",
            "target": {"kind": "Deployment", "namespace": "team-a", "name": "web-api"},
        }

    async def fake_execute_natural_action_plan_result(plan_result, *_args, **_kwargs):
        return {
            "approvalId": "approval-pending",
            "executionId": "execution-pending",
            "mutationOutcome": {"status": "mutation_succeeded", "reason": "typed_action_executed"},
            "plan": dict(plan_result),
            "remediationOutcome": {"status": "verified", "reason": "pending_plan_verified"},
            "status": "executed",
        }

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError("OLS must not be called for pending followup execution")

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(
        gateway_main,
        "latest_pending_action_plan_result",
        fake_latest_pending_action_plan_result,
    )
    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMANDS_ENABLED", True)
    monkeypatch.setattr(
        gateway_main,
        "execute_natural_action_plan_result",
        fake_execute_natural_action_plan_result,
    )
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "진행해",
                    "pageContext": {"aiopsExecutionMode": "unrestricted"},
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        followup_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "natural_action_followup"
        ]
        assert followup_results
        assert followup_results[0]["status"] == "success"
        assert "pending_plan_verified" in response.text
        assert "lightspeed_stream" not in response.text
        context = assert_post_answer_rca_before_done(events)
        assert context["confidence"]["level"] == "insufficient_evidence"

    asyncio.run(run())


def test_chat_stream_execute_mode_action_plan_response_has_post_answer_rca(
    monkeypatch,
) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_create_natural_action_plan(req, *_args, **_kwargs):
        assert req.message == "team-a 네임스페이스의 web-api 파드 4개로 올려줘"
        return {
            "intent": {
                "kind": "Deployment",
                "namespace": "team-a",
                "parameters": {"replicas": 4},
                "targetName": "web-api",
                "toolName": "set_replicas_within_bounds",
            },
            "planDigest": "sha256:execute-mode-plan",
            "planId": "plan-execute-mode",
            "status": "planned",
            "target": {"kind": "Deployment", "namespace": "team-a", "name": "web-api"},
        }

    async def fail_execute_natural_action_plan_result(*_args, **_kwargs):
        raise AssertionError("execute mode should stop at plan response unless unrestricted")

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError("OLS must not be called for action plan responses")

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMANDS_ENABLED", True)
    monkeypatch.setattr(gateway_main, "create_natural_action_plan", fake_create_natural_action_plan)
    monkeypatch.setattr(
        gateway_main,
        "execute_natural_action_plan_result",
        fail_execute_natural_action_plan_result,
    )
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "team-a 네임스페이스의 web-api 파드 4개로 올려줘",
                    "pageContext": {"aiopsExecutionMode": "execute"},
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        tool_plan_index = next(
            index
            for index, event in enumerate(events)
            if isinstance(event, dict) and event.get("type") == "tool_plan"
        )
        plan_result_index = next(
            index
            for index, event in enumerate(events)
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "natural_action_plan"
        )
        plan_results = [events[plan_result_index]]
        answer_index = next(
            index
            for index, event in enumerate(events)
            if isinstance(event, dict)
            and event.get("type") == "text"
            and "자연어 조치 요청을 승인 가능한 Action Plan으로 정리했습니다." in event.get("content", "")
        )
        post_answer_index = next(
            index
            for index, event in enumerate(events)
            if isinstance(event, dict)
            and event.get("type") == "rca_context"
            and event.get("context", {}).get("metadata", {}).get("phase") == "post_answer"
        )
        run_completed_index = next(
            index
            for index, event in enumerate(events)
            if isinstance(event, dict)
            and event.get("type") == "run_status"
            and event.get("stage") == "completed"
            and "조치 계획 생성 완료" in event.get("message", "")
        )
        assert [
            tool_plan_index,
            plan_result_index,
            answer_index,
            run_completed_index,
            post_answer_index,
            len(events) - 1,
        ] == sorted(
            [
                tool_plan_index,
                plan_result_index,
                answer_index,
                run_completed_index,
                post_answer_index,
                len(events) - 1,
            ]
        )
        assert events[-1] == "[DONE]"
        assert plan_results[0]["result"]["planDigest"] == "sha256:execute-mode-plan"
        assert plan_results
        assert plan_results[0]["status"] == "success"
        answer_text = events[answer_index]["content"]
        assert "자연어 조치 요청을 승인 가능한 Action Plan으로 정리했습니다." in answer_text
        assert "plan-execute-mode" not in answer_text
        assert "sha256:execute-mode-plan" not in answer_text
        assert "ActionProposal -> SealedActionPlan -> ApprovalDecision -> ExecutionRecord" not in answer_text
        assert "natural_action_execute" not in answer_text
        assert "lightspeed_stream" not in answer_text
        context = assert_post_answer_rca_before_done(events)
        assert context["confidence"]["level"] == "insufficient_evidence"

    asyncio.run(run())


def test_chat_action_plan_can_continue_through_standard_approval_api(monkeypatch) -> None:
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()
    APPROVAL_DECISIONS.clear()
    EXECUTION_RECORDS.clear()

    requester = safe_subject({"username": "requester@example.com", "uid": "uid-requester", "groups": ["ops"]})
    approver = safe_subject({"username": "approver@example.com", "uid": "uid-approver", "groups": ["ops"]})

    async def fake_subject_review(user_auth_header: str) -> dict:
        return requester if user_auth_header == "Bearer requester-token" else approver

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_action_access_review(_user_auth_header: str, plan: dict) -> dict:
        target = plan["target"]
        return {
            "allowed": True,
            "enabled": True,
            "resourceAttributes": {
                "group": "apps",
                "name": target["name"],
                "namespace": target["namespace"],
                "resource": "deployments",
                "subresource": "scale",
                "verb": "update",
            },
        }

    async def fake_fetch_ocp_json(_client, path: str, _authorization: str, *_, **__) -> dict:
        assert "/apis/apps/v1/namespaces/team-a/deployments/web-api" in path
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "web-api",
                "namespace": "team-a",
                "uid": "deployment-uid-a",
            },
        }

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError("OLS must not be called for action plan responses")

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.test:6443")
    monkeypatch.setattr(gateway_main, "MUTATIONS_ENABLED", False)
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "fetch_action_access_review", fake_action_access_review)
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fake_fetch_ocp_json)
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            chat_response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer requester-token"},
                json={
                    "message": "team-a 네임스페이스의 web-api 파드 4개로 올려줘",
                    "pageContext": {"aiopsExecutionMode": "execute"},
                },
            )
            events = parse_sse_events(chat_response.text)
            plan_result = next(
                event["result"]
                for event in events
                if isinstance(event, dict)
                and event.get("type") == "tool_result"
                and event.get("name") == "natural_action_plan"
            )
            approval_response = await client.post(
                "/v1/actions/approvals",
                headers={"Authorization": "Bearer approver-token"},
                json={
                    "planId": plan_result["planId"],
                    "expectedPlanDigest": plan_result["planDigest"],
                },
            )
            approval_id = approval_response.json()["metadata"]["name"]
            execution_response = await client.post(
                "/v1/actions/execute",
                headers={"Authorization": "Bearer approver-token"},
                json={
                    "approvalId": approval_id,
                    "planId": plan_result["planId"],
                    "expectedPlanDigest": plan_result["planDigest"],
                },
            )

        assert chat_response.status_code == 200
        assert approval_response.status_code == 200
        assert execution_response.status_code == 403
        assert execution_response.json()["detail"]["mutationOutcome"]["status"] == "mutation_disabled"
        assert len(ACTION_PROPOSALS) == 1
        assert len(SEALED_ACTION_PLANS) == 1
        assert len(APPROVAL_DECISIONS) == 1
        assert len(EXECUTION_RECORDS) == 1
        execution_record = next(iter(EXECUTION_RECORDS.values()))
        assert execution_record["spec"]["planId"] == plan_result["planId"]
        assert execution_record["spec"]["planDigest"] == plan_result["planDigest"]
        visible_text = "\n".join(
            event.get("content", "")
            for event in events
            if isinstance(event, dict) and event.get("type") == "text"
        )
        assert "Action Plan" in visible_text
        assert "ActionProposal -> SealedActionPlan -> ApprovalDecision -> ExecutionRecord" not in visible_text
        context = assert_post_answer_rca_before_done(events)
        assert context["metadata"]["phase"] == "post_answer"

    asyncio.run(run())


def test_chat_stream_action_candidate_pod_prompt_prefers_action_plan_over_pod_count(
    monkeypatch,
) -> None:
    prompt = (
        "Pod `komsco-ai-dev/aiops-scenario-1-crashloop-7448bf8897-57pjz` evict 실행 계획을 생성해줘.\n\n"
        "조치 후보: CrashLoopBackOff: komsco-ai-dev/aiops-scenario-1-crashloop-7448bf8897-57pjz 조치 후보\n"
        "대상: komsco-ai-dev/Pod/aiops-scenario-1-crashloop-7448bf8897-57pjz\n"
        "위험도: 높음\n"
        "근거: container=crashloop, waiting.reason=CrashLoopBackOff, restartCount=2321, "
        "message=back-off 5m0s restarting failed container=crashloop "
        "pod=aiops-scenario-1-crashloop-7448bf8897-57pjz_komsco-ai-dev(f0119e12-b8d1-4fc4-82df-a6516de8e800)\n"
        "선행 확인: oc describe pod aiops-scenario-1-crashloop-7448bf8897-57pjz -n komsco-ai-dev\n"
        "예상 영향: komsco-ai-dev/Pod/aiops-scenario-1-crashloop-7448bf8897-57pjz 회복 가능성이 있지만 "
        "잘못된 변경은 재시작 또는 서비스 영향으로 이어질 수 있습니다.\n\n"
        "실행은 바로 하지 말고, 먼저 Action Plan을 만들고 승인 버튼을 기다려."
    )

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_create_natural_action_plan(req, *_args, **_kwargs):
        assert req.message == prompt
        return {
            "intent": {
                "kind": "Pod",
                "namespace": "komsco-ai-dev",
                "parameters": {"reason": "natural_language_unhealthy_pod_eviction"},
                "targetName": "aiops-scenario-1-crashloop-7448bf8897-57pjz",
                "toolName": "evict_one_unhealthy_controller_owned_pod",
            },
            "parameters": {"reason": "natural_language_unhealthy_pod_eviction"},
            "planId": "plan-action-candidate-pod",
            "proposalId": "proposal-action-candidate-pod",
            "risk": "medium",
            "status": "planned",
            "target": {
                "kind": "Pod",
                "namespace": "komsco-ai-dev",
                "name": "aiops-scenario-1-crashloop-7448bf8897-57pjz",
            },
        }

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError("OLS must not be called for action candidate plan responses")

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "create_natural_action_plan", fake_create_natural_action_plan)
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": prompt,
                    "pageContext": {"aiopsExecutionMode": "execute"},
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        plan_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "natural_action_plan"
        ]
        assert plan_results
        assert "plan-action-candidate-pod" in response.text
        assert "pod_count_investigation" not in response.text
        assert "lightspeed_stream" not in response.text

    asyncio.run(run())


@pytest.mark.parametrize(
    ("scenario_id", "recent_messages", "expected_action_message"),
    [
        (
            "3-user-turn",
            [
                {
                    "role": "user",
                    "content": "team-a 네임스페이스의 web-api 파드 4개로 올려줘",
                },
                {
                    "role": "assistant",
                    "content": "조치 계획을 생성했습니다. 승인하시겠습니까?",
                },
                {"role": "user", "content": "위험도도 같이 봐줘"},
                {"role": "assistant", "content": "중간 위험도이며 승인 후 실행 가능합니다."},
            ],
            "team-a 네임스페이스의 web-api 파드 4개로 올려줘",
        ),
        (
            "4-user-turn",
            [
                {
                    "role": "user",
                    "content": "team-a 네임스페이스의 deployment/web-api revision 2로 롤백해줘",
                },
                {
                    "role": "assistant",
                    "content": "rollback_deployment_to_revision 계획을 만들 수 있습니다.",
                },
                {"role": "user", "content": "리비전 2 대상이 맞는지 다시 설명해줘"},
                {"role": "assistant", "content": "대상은 team-a/web-api revision 2입니다."},
                {"role": "user", "content": "서비스 영향은?"},
                {"role": "assistant", "content": "rollout 과정에서 일시적인 replacement가 발생할 수 있습니다."},
            ],
            "team-a 네임스페이스의 deployment/web-api revision 2로 롤백해줘",
        ),
        (
            "5-user-turn",
            [
                {
                    "role": "user",
                    "content": "team-a 네임스페이스의 hpa/web-hpa 최소 2 최대 8로 변경해줘",
                },
                {
                    "role": "assistant",
                    "content": "set_hpa_bounds 계획을 만들 수 있습니다.",
                },
                {"role": "user", "content": "대상 HPA 이름 다시 말해줘"},
                {"role": "assistant", "content": "대상은 team-a/web-hpa입니다."},
                {"role": "user", "content": "최소 최대 값도 다시 확인해줘"},
                {"role": "assistant", "content": "minReplicas 2, maxReplicas 8입니다."},
                {"role": "user", "content": "운영 영향은?"},
                {"role": "assistant", "content": "autoscaling bounds 변경으로 scale range가 달라집니다."},
            ],
            "team-a 네임스페이스의 hpa/web-hpa 최소 2 최대 8로 변경해줘",
        ),
    ],
)
def test_chat_stream_unrestricted_followup_uses_3_4_5_turn_contexts(
    monkeypatch,
    scenario_id: str,
    recent_messages: list[dict[str, str]],
    expected_action_message: str,
) -> None:
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()
    APPROVAL_DECISIONS.clear()
    EXECUTION_RECORDS.clear()
    created_from_messages: list[str] = []

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_create_natural_action_plan(req, *_args, **_kwargs):
        created_from_messages.append(req.message)
        intent = parse_natural_action_intent(req)
        assert intent, scenario_id
        return {
            "intent": dict(intent),
            "parameters": dict(intent["parameters"]),
            "planDigest": f"sha256:{scenario_id}",
            "planId": f"plan-{scenario_id}",
            "proposalId": f"proposal-{scenario_id}",
            "risk": "medium",
            "status": "planned",
            "target": {
                "apiVersion": intent.get("apiVersion"),
                "kind": intent.get("kind"),
                "namespace": intent.get("namespace"),
                "name": intent.get("targetName"),
                "uid": f"uid-{scenario_id}",
            },
        }

    async def fake_execute_natural_action_plan_result(plan_result, *_args, **_kwargs):
        return {
            "approvalId": f"approval-{scenario_id}",
            "executionId": f"execution-{scenario_id}",
            "mutationOutcome": {"status": "mutation_succeeded", "reason": "typed_action_executed"},
            "plan": dict(plan_result),
            "remediationOutcome": {"status": "verified", "reason": "scenario_verified"},
            "status": "executed",
        }

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError(f"OLS must not be called for {scenario_id} contextual followup execution")

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMANDS_ENABLED", True)
    monkeypatch.setattr(gateway_main, "create_natural_action_plan", fake_create_natural_action_plan)
    monkeypatch.setattr(
        gateway_main,
        "execute_natural_action_plan_result",
        fake_execute_natural_action_plan_result,
    )
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "진행해",
                    "pageContext": {"aiopsExecutionMode": "unrestricted"},
                    "recentMessages": recent_messages,
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        followup_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "natural_action_followup"
        ]
        assert followup_results, scenario_id
        assert followup_results[0]["status"] == "success"
        assert "scenario_verified" in response.text
        assert "lightspeed_stream" not in response.text
        assert created_from_messages == [expected_action_message]
        context = assert_post_answer_rca_before_done(events)
        assert context["confidence"]["level"] == "insufficient_evidence"

    asyncio.run(run())


def test_chat_stream_pod_count_question_directly_investigates_cluster(monkeypatch) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_fetch_ocp_json(_client, path: str, _authorization: str, **_kwargs):
        if path == "/apis/apps/v1/deployments":
            return {
                "items": [
                    {
                        "metadata": {"name": "aiops-two-pod-exec", "namespace": "komsco-ai-dev"},
                        "spec": {
                            "replicas": 3,
                            "selector": {"matchLabels": {"app": "aiops-two-pod-exec"}},
                        },
                        "status": {
                            "availableReplicas": 3,
                            "readyReplicas": 3,
                            "updatedReplicas": 3,
                        },
                    }
                ]
            }
        if path == "/api/v1/pods":
            return {
                "items": [
                    {
                        "metadata": {
                            "labels": {"app": "aiops-two-pod-exec"},
                            "name": f"aiops-two-pod-exec-69c85d74cc-{suffix}",
                            "namespace": "komsco-ai-dev",
                        },
                        "status": {
                            "containerStatuses": [{"ready": True, "restartCount": 0}],
                            "phase": "Running",
                        },
                    }
                    for suffix in ["aaa", "bbb", "ccc"]
                ]
            }
        raise AssertionError(f"unexpected OpenShift path: {path}")

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError("OLS must not be called for direct pod count questions")

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.test:6443")
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fake_fetch_ocp_json)
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "aiops-two-pod-exec 파드 몇개 띄었어?",
                    "pageContext": {"aiopsExecutionMode": "unrestricted"},
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        event_names = [
            event.get("name")
            for event in events
            if isinstance(event, dict) and event.get("type") in {"tool_call", "tool_result"}
        ]
        pod_count_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "pod_count_investigation"
        ]
        for expected_name in [
            "pod_count_scope_resolve",
            "pod_count_deployment_lookup",
            "pod_count_pod_lookup",
            "pod_count_selector_match",
            "pod_count_investigation",
        ]:
            assert expected_name in event_names
        assert pod_count_results
        assert pod_count_results[0]["status"] == "success"
        assert pod_count_results[0]["result"]["rows"][0]["totalPods"] == 3
        evidence_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "evidence_ref"
            and event.get("result", {}).get("sourceType") == "gateway-direct-evidence"
        ]
        rca_events = [
            event
            for event in events
            if isinstance(event, dict) and event.get("type") == "rca_context"
        ]
        assert evidence_results
        assert rca_events
        latest_context = rca_events[-1]["context"]
        assert latest_context["metadata"]["phase"] == "post_answer"
        assert latest_context["evidence"]["summary"]["collectedCount"] >= 1
        assert latest_context["evidence"]["collectedRefs"][0]["evidenceId"] == evidence_results[-1]["result"]["evidenceId"]
        assert (
            latest_context["evidence"]["collectedRefs"][0]["contentDigest"]
            == evidence_results[-1]["result"]["contentDigest"]
        )
        assert "`komsco-ai-dev/aiops-two-pod-exec` 기준 현재 Pod는 총 3개" in response.text
        assert "natural_action_unresolved" not in response.text
        assert "lightspeed_stream" not in response.text

    asyncio.run(run())


def test_chat_stream_top_pod_namespace_question_stays_brief_and_skips_ols(monkeypatch) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    def pod_item(namespace: str, index: int) -> dict:
        return {
            "metadata": {"name": f"{namespace}-pod-{index}", "namespace": namespace},
            "status": {"phase": "Running"},
        }

    async def fake_fetch_ocp_json(_client, path: str, _authorization: str, **_kwargs):
        if path == "/api/v1/pods":
            return {
                "items": [
                    *[pod_item("openshift-marketplace", index) for index in range(24)],
                    *[pod_item("cywell-aiops", index) for index in range(16)],
                    *[pod_item("cyntra", index) for index in range(15)],
                    *[pod_item("komsco-ai-dev", index) for index in range(14)],
                    *[pod_item("openshift-monitoring", index) for index in range(13)],
                    *[pod_item("nginx-gateway", index) for index in range(1)],
                ]
            }
        raise AssertionError(f"unexpected OpenShift path: {path}")

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError("OLS must not be called for top pod namespace count questions")

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.test:6443")
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fake_fetch_ocp_json)
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "파드 수가 제일 많은 네임스페이스는 뭐야",
                    "pageContext": {"aiopsExecutionMode": "execute"},
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        lookup_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "top_pod_namespace_count_lookup"
        ]
        text = "".join(
            event.get("content", "")
            for event in events
            if isinstance(event, dict) and event.get("type") == "text"
        )

        assert lookup_results
        assert lookup_results[0]["status"] == "success"
        assert "`openshift-marketplace`입니다." in text
        assert "| 1 | `openshift-marketplace` | 24 |" in text
        assert "| 5 | `openshift-monitoring` | 13 |" in text
        assert "nginx-gateway" not in text
        assert "Gathering data about your cluster" not in text
        assert not any(
            event.get("name") == "lightspeed_stream"
            for event in events
            if isinstance(event, dict)
        )

    asyncio.run(run())


def test_chat_stream_unparsed_mutation_request_does_not_fall_through_to_ols(monkeypatch) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError("OLS must not be called for unresolved mutation requests")

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "파드 하나 재시작해줘",
                    "pageContext": {"aiopsExecutionMode": "unrestricted"},
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        unresolved_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "natural_action_unresolved"
        ]
        assert unresolved_results
        assert unresolved_results[0]["status"] == "skipped"
        rca_events = [
            event
            for event in events
            if isinstance(event, dict) and event.get("type") == "rca_context"
        ]
        assert rca_events
        assert rca_events[-1]["context"]["metadata"]["phase"] == "post_answer"
        assert rca_events[-1]["context"]["confidence"]["level"] == "insufficient_evidence"
        assert "대상 리소스 이름이 명확하지 않습니다" in response.text
        assert "lightspeed_stream" not in response.text

    asyncio.run(run())


def test_chat_stream_execute_action_request_emits_plan_and_post_answer_rca_context(monkeypatch) -> None:
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()
    APPROVAL_DECISIONS.clear()
    EXECUTION_RECORDS.clear()

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_fetch_ocp_json(_client, path: str, _authorization: str, *_, **__) -> dict:
        assert "/apis/apps/v1/namespaces/team-a/deployments/web-api" in path
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "web-api",
                "namespace": "team-a",
                "uid": "deployment-uid-a",
            },
        }

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError("OLS must not be called for action plan responses")

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.test:6443")
    monkeypatch.setattr(gateway_main, "MUTATIONS_ENABLED", True)
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fake_fetch_ocp_json)
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "team-a 네임스페이스의 web-api 파드 3개로 올려줘",
                    "pageContext": {"aiopsExecutionMode": "execute"},
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        action_plan_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "natural_action_plan"
        ]
        rca_events = [
            event
            for event in events
            if isinstance(event, dict) and event.get("type") == "rca_context"
        ]
        text_events = [
            event
            for event in events
            if isinstance(event, dict) and event.get("type") == "text"
        ]
        assert action_plan_results
        assert action_plan_results[0]["status"] == "success"
        assert action_plan_results[0]["result"]["status"] == "planned"
        assert rca_events
        assert rca_events[-1]["context"]["metadata"]["phase"] == "post_answer"
        assert rca_events[-1]["context"]["safety"]["mode"] == "controlled_execution"
        assert rca_events[-1]["context"]["evidence"]["summary"]["collectedCount"] == 0
        assert any(
            event.get("answerContract") == "natural-action-plan-v0.2.1"
            for event in text_events
        )
        visible_text = "\n".join(event.get("content", "") for event in text_events)
        assert "자연어 조치 요청을 승인 가능한 Action Plan으로 정리했습니다." in visible_text
        assert "ActionProposal -> SealedActionPlan -> ApprovalDecision -> ExecutionRecord" not in visible_text
        assert "natural_action_execute" not in visible_text
        assert "lightspeed_stream" not in visible_text
        assert len(ACTION_PROPOSALS) == 1
        assert len(SEALED_ACTION_PLANS) == 1
        assert len(APPROVAL_DECISIONS) == 0
        assert len(EXECUTION_RECORDS) == 0

    asyncio.run(run())


def test_chat_stream_read_only_action_request_skips_plan_and_emits_post_answer_rca_context(monkeypatch) -> None:
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()
    APPROVAL_DECISIONS.clear()
    EXECUTION_RECORDS.clear()

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError("OLS must not be called for read-only action gate responses")

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "team-a 네임스페이스의 web-api 파드 3개로 올려줘",
                    "pageContext": {"aiopsExecutionMode": "read-only"},
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        read_only_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "natural_action_plan"
        ]
        rca_events = [
            event
            for event in events
            if isinstance(event, dict) and event.get("type") == "rca_context"
        ]
        assert read_only_results
        assert read_only_results[0]["status"] == "skipped"
        assert read_only_results[0]["result"]["executionMode"] == "evidence-check"
        assert rca_events
        assert rca_events[-1]["context"]["metadata"]["phase"] == "post_answer"
        assert rca_events[-1]["context"]["safety"]["mode"] == "evidence_check"
        assert "읽기 전용" in response.text
        assert "조치 후보만 정리" in response.text
        assert "natural_action_execute" not in response.text
        assert "lightspeed_stream" not in response.text
        assert len(ACTION_PROPOSALS) == 0
        assert len(SEALED_ACTION_PLANS) == 0
        assert len(APPROVAL_DECISIONS) == 0
        assert len(EXECUTION_RECORDS) == 0

    asyncio.run(run())
