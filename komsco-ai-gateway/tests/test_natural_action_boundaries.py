import asyncio
import ast
from pathlib import Path

from komsco_ai_gateway import main as gateway_main
from komsco_ai_gateway import natural_action_rendering


PUBLIC_SYMBOLS = (
    "execution_mode_allows_actions",
    "execution_mode_allows_immediate_actions",
    "parse_unrestricted_chat_command",
    "is_pod_list_request",
    "pod_list_namespace",
    "is_pod_count_query",
    "pod_count_query_namespace",
    "pod_count_query_target_name",
    "parse_pod_count_query",
    "rollback_revision_from_message",
    "hpa_bounds_from_message",
    "is_followup_execution_request",
    "recent_natural_action_request",
    "parse_natural_action_intent",
    "action_candidate_plan_intent",
    "create_natural_action_plan",
    "create_plan_from_action_candidate",
    "action_plan_result_from_record",
    "plan_has_execution",
    "latest_pending_action_plan_result",
    "execute_natural_action_plan_result",
    "natural_action_plan_response",
    "no_pending_action_plan_response",
    "unresolved_natural_action_response",
    "natural_action_execution_response",
    "natural_action_evidence_check_response",
)


def test_main_keeps_natural_action_public_symbols() -> None:
    assert all(callable(getattr(gateway_main, name, None)) for name in PUBLIC_SYMBOLS)


def test_parsing_facade_uses_current_main_helper_bindings(monkeypatch) -> None:
    request = gateway_main.ChatRequest(message="patched deployment 3개로 올려줘")
    calls: list[str] = []

    monkeypatch.setattr(
        gateway_main,
        "namespace_from_natural_action",
        lambda _req: calls.append("namespace") or "patched-namespace",
    )
    monkeypatch.setattr(
        gateway_main,
        "natural_target_name",
        lambda _req, _match, **_kwargs: calls.append("target") or "patched-target",
    )

    intent = gateway_main.parse_natural_action_intent(request)

    assert calls == ["namespace", "target"]
    assert intent is not None
    assert intent["namespace"] == "patched-namespace"
    assert intent["targetName"] == "patched-target"


def test_recent_request_uses_current_main_intent_parser(monkeypatch) -> None:
    request = gateway_main.ChatRequest(
        message="실행해",
        recentMessages=[
            {"role": "user", "content": "이전 요청"},
            {"role": "assistant", "content": "확인했습니다"},
        ],
    )
    seen: list[str] = []

    monkeypatch.setattr(
        gateway_main,
        "parse_natural_action_intent",
        lambda candidate: seen.append(candidate.message) or {"toolName": "patched"},
    )

    contextual = gateway_main.recent_natural_action_request(request)

    assert contextual is not None
    assert contextual.message == "이전 요청"
    assert seen == ["이전 요청"]


def test_orchestration_dependencies_are_dynamic_and_keep_store_identity(monkeypatch) -> None:
    first_store: dict[str, dict] = {}
    second_store: dict[str, dict] = {}
    first_parser = lambda _req: {"source": "first"}
    second_parser = lambda _req: {"source": "second"}

    monkeypatch.setattr(gateway_main, "SEALED_ACTION_PLANS", first_store)
    monkeypatch.setattr(gateway_main, "parse_natural_action_intent", first_parser)
    first = gateway_main._natural_action_orchestration_dependencies()

    monkeypatch.setattr(gateway_main, "SEALED_ACTION_PLANS", second_store)
    monkeypatch.setattr(gateway_main, "parse_natural_action_intent", second_parser)
    second = gateway_main._natural_action_orchestration_dependencies()

    assert first.sealed_action_plans is first_store
    assert first.parse_natural_action_intent is first_parser
    assert second.sealed_action_plans is second_store
    assert second.parse_natural_action_intent is second_parser


def test_create_and_execute_facades_pass_current_dependencies(monkeypatch) -> None:
    current_store: dict[str, dict] = {}
    captured: list[object] = []

    async def fake_create(*_args, dependencies, **_kwargs):
        captured.append(dependencies.sealed_action_plans)
        return {"status": "planned"}

    async def fake_execute(*_args, dependencies, **_kwargs):
        captured.append(dependencies.sealed_action_plans)
        return {"status": "execution_disabled"}

    monkeypatch.setattr(gateway_main, "SEALED_ACTION_PLANS", current_store)
    monkeypatch.setattr(
        gateway_main.natural_action_orchestration,
        "create_natural_action_plan",
        fake_create,
    )
    monkeypatch.setattr(
        gateway_main.natural_action_orchestration,
        "execute_natural_action_plan_result",
        fake_execute,
    )

    created = asyncio.run(
        gateway_main.create_natural_action_plan(
            gateway_main.ChatRequest(message="demo:web 재시작해줘"),
            "Bearer token",
            {"username": "operator"},
            incident_id="incident-1",
            run_id="run-1",
        )
    )
    executed = asyncio.run(
        gateway_main.execute_natural_action_plan_result(
            {"status": "planned", "planId": "plan-1"},
            "Bearer token",
            {"username": "operator"},
        )
    )

    assert created == {"status": "planned"}
    assert executed == {"status": "execution_disabled"}
    assert captured == [current_store, current_store]


def test_latest_pending_plan_uses_current_main_callbacks(monkeypatch) -> None:
    record = {"metadata": {"name": "plan-1", "createdAt": "2026-07-11T00:00:00Z"}}
    monkeypatch.setattr(gateway_main, "SEALED_ACTION_PLANS", {"plan-1": record})
    monkeypatch.setattr(gateway_main, "plan_has_execution", lambda plan_id: plan_id != "plan-1")
    monkeypatch.setattr(gateway_main, "can_subject_read_record", lambda *_args: True)
    monkeypatch.setattr(
        gateway_main,
        "action_plan_result_from_record",
        lambda current: {"status": "planned", "record": current},
    )

    result = gateway_main.latest_pending_action_plan_result({"username": "operator"})

    assert result == {"status": "planned", "record": record}


def test_rendering_facade_preserves_exact_plan_and_pending_strings() -> None:
    result = {
        "status": "planned",
        "target": {"namespace": "demo", "name": "web", "kind": "Deployment"},
        "intent": {"toolName": "rollout_restart_deployment"},
        "parameters": {"restartedAt": "2026-07-11T00:00:00Z"},
        "risk": "low",
    }
    expected_plan = "\n".join(
        [
            "자연어 조치 요청을 승인 가능한 Action Plan으로 정리했습니다.",
            "",
            "### Action Plan",
            "- 대상: `demo/web` (Deployment)",
            "- 조치: `rollout_restart_deployment`",
            '- 입력값: `{"restartedAt": "2026-07-11T00:00:00Z"}`',
            "- 위험도: `low`",
            "- 상태: 승인 전에는 변경 작업을 실행하지 않습니다.",
            "",
            "### 다음 단계",
            "- 오른쪽 `AIOps 실행 상태 > 승인·실행`에서 `승인` 후 `실행`을 누르면 실제 변경됩니다.",
        ]
    )
    expected_pending = "\n".join(
        [
            "실행할 Gateway AIOps Action Plan이 없습니다.",
            "",
            "`승인`/`실행` 같은 후속 명령은 Gateway가 생성한 미실행 Action Plan이 있을 때만 처리합니다.",
            "대상과 namespace를 포함해서 다시 요청하세요.",
            "",
            "예: `komsco-ai-dev 네임스페이스의 aiops-two-pod-exec 파드 3개로 올려줘`",
            "예: `6:cis 파드 3개로 올려줘`",
        ]
    )

    assert gateway_main.natural_action_plan_response(result) == expected_plan
    assert gateway_main.no_pending_action_plan_response() == expected_pending
    assert gateway_main.natural_action_plan_response(result) == (
        natural_action_rendering.natural_action_plan_response(
            result, redact_sensitive=gateway_main.redact_sensitive
        )
    )


def test_rendering_facade_preserves_exact_ambiguous_string() -> None:
    result = {
        "status": "ambiguous",
        "intent": {"kind": "Deployment"},
        "candidates": [
            {"namespace": "demo-a", "name": "web", "kind": "Deployment"},
            {"namespace": "demo-b", "name": "web", "kind": "Deployment"},
        ],
    }

    assert gateway_main.natural_action_plan_response(result) == "\n".join(
        [
            "자연어 조치 요청을 해석했지만 대상 후보가 여러 개라 실행하지 않았습니다.",
            "",
            "### 대상 후보",
            "- `demo-a/web` (Deployment)",
            "- `demo-b/web` (Deployment)",
            "",
            "namespace와 대상 이름을 함께 지정해 다시 요청하세요.",
        ]
    )


def test_rendering_facade_preserves_exact_execution_disabled_string() -> None:
    result = {
        "status": "execution_disabled",
        "plan": {
            "planId": "plan-1",
            "target": {"namespace": "demo", "name": "web", "kind": "Deployment"},
            "intent": {"toolName": "rollout_restart_deployment"},
            "parameters": {"restartedAt": "2026-07-11T00:00:00Z"},
        },
        "approvalId": "approval-1",
        "executionId": "execution-1",
        "mutationOutcome": {
            "status": "mutation_disabled",
            "reason": "KOMSCO_AI_ENABLE_MUTATIONS is false.",
        },
        "remediationOutcome": {"status": "not_remediated"},
    }

    assert gateway_main.natural_action_execution_response(result) == "\n".join(
        [
            "자연어 조치 요청을 해석했지만 mutation 실행은 비활성화되어 있습니다.",
            "",
            "### 실행 요약",
            "- 대상: `demo/web` (Deployment)",
            "- Action: `rollout_restart_deployment`",
            '- Parameters: `{"restartedAt": "2026-07-11T00:00:00Z"}`',
            "- Plan: `plan-1`",
            "- Approval: `approval-1`",
            "- Execution: `execution-1`",
            "- Mutation: `mutation_disabled` / `KOMSCO_AI_ENABLE_MUTATIONS is false.`",
            "- Verification: `not_remediated` / `None`",
        ]
    )


def test_natural_action_modules_do_not_import_main() -> None:
    package_dir = Path(gateway_main.__file__).parent
    for module_name in (
        "natural_action_parsing.py",
        "natural_action_orchestration.py",
        "natural_action_rendering.py",
    ):
        tree = ast.parse((package_dir / module_name).read_text(encoding="utf-8"))
        imported_modules = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported_names = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert "main" not in imported_modules
        assert "komsco_ai_gateway.main" not in imported_modules
        assert "main" not in imported_names
        assert "komsco_ai_gateway.main" not in imported_names
