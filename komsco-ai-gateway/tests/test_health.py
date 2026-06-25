import asyncio
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import HTTPException

import komsco_ai_gateway.main as gateway_main
import komsco_ai_gateway.olm_operator as olm_operator
from komsco_ai_gateway.host_diagnostics_collector import collect_host_diagnostics
from komsco_ai_gateway.host_diagnostics_controller import build_diagnostic_job_manifest
from komsco_ai_gateway.main import (
    ACTION_PROPOSALS,
    ACTION_REGISTRY_DIGEST,
    ACTION_REGISTRY_ENTRIES,
    APPROVAL_DECISIONS,
    AUDIT_RECORDS,
    BREAK_GLASS_PROFILE_DIGEST,
    BREAK_GLASS_PROFILES,
    BREAK_GLASS_REQUESTS,
    EXECUTION_RECORDS,
    PREAPPROVED_PATCH_REQUESTS,
    RUNBOOK_PLANS,
    RUNBOOK_REGISTRY_DIGEST,
    RUNBOOK_REGISTRY_ENTRIES,
    SEALED_ACTION_PLANS,
    ActionProposalCreate,
    ActionTarget,
    BreakGlassRequestCreate,
    BreakGlassTargetNode,
    ChatRequest,
    DIAGNOSTIC_REQUESTS,
    EVIDENCE_RECORDS,
    HOST_DIAGNOSTIC_COLLECTOR_DIGEST,
    HOST_DIAGNOSTIC_COLLECTORS,
    ImageAttachment,
    RagDocumentUploadCreate,
    METRICS,
    TextReferenceFilter,
    WORKFLOW_RECORDS,
    app,
    build_attachment_context,
    build_action_proposal_record,
    build_action_proposal_fallback,
    build_action_access_review_request,
    build_aiops_action_candidates,
    build_aiops_anomaly_summary,
    build_aiops_overview,
    build_active_alerts_rca_evidence,
    build_cluster_summary,
    build_cluster_operator_status_evidence,
    build_cronjob_activity_evidence,
    build_deployment_rollout_evidence,
    build_diagnostic_request_candidate,
    build_diagnostic_request_record,
    build_empty_answer_fallback,
    build_evidence_reference_events,
    build_ols_gateway_context,
    build_ols_payload,
    build_ols_query,
    build_node_status_rca_evidence,
    build_product_access_review_request,
    build_pod_count_investigation,
    build_break_glass_request_record,
    build_preapproved_patch_record,
    build_rag_answer_citation_text,
    build_rag_context_detail,
    build_runbook_plan_record,
    build_rag_upload_document,
    build_sealed_action_plan_record,
    build_restart_metric_rca_evidence,
    candidate_action_request_digest,
    can_subject_read_record,
    compact_controller_submission,
    build_pod_status_evidence,
    DiagnosticEvidencePolicy,
    DiagnosticLimits,
    DiagnosticRequestCreate,
    DiagnosticTargetNode,
    DiagnosticTimeRange,
    PatchPreapprovedFieldCreate,
    RunbookPlanCreate,
    diagnostic_request_digest,
    is_followup_execution_request,
    is_pod_count_query,
    is_pod_list_request,
    page_context_aiops_execution_mode,
    parse_bool,
    parse_natural_action_intent,
    parse_pod_count_query,
    recent_natural_action_request,
    parse_ols_verify,
    parse_unrestricted_chat_command,
    policy_check_summary,
    normalize_console_page_context,
    normalize_controller_phase,
    product_access_review_status,
    sealed_action_plan_digest,
    summarize_product_access_review,
    summarize_policy_detail,
    unresolved_natural_action_response,
    validate_execution_evidence_freshness,
    should_collect_cronjob_activity_evidence,
    should_collect_pod_status_evidence,
    should_collect_rca_signal_evidence,
    should_filter_gateway_api_references,
    should_filter_low_signal_references,
    split_plain_text_events,
    validate_image_attachments,
)
from komsco_ai_gateway.aiops_core import (
    AiopsCoreError,
    build_hpa_bounds_request,
    build_mutation_request,
    build_rollback_request,
    matching_hpas_for_deployment,
)
from komsco_ai_gateway.aiops_contracts import (
    assert_read_only_tool_plan,
    build_adapter_registry,
    build_rca_context,
    build_runtime_safety_contract,
    build_runtime_tool_plan,
    create_evidence_status,
    resolve_tool_plan_adapters,
)
from komsco_ai_gateway.security import (
    build_evidence_reference,
    classify_request_policy,
    redact_sensitive,
    safe_subject,
)


def test_healthz() -> None:
    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/healthz")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    asyncio.run(run())


def test_rag_pdf_upload_parser_extracts_page_marked_text(monkeypatch) -> None:
    class FakePage:
        def __init__(self, text: str) -> None:
            self.text = text

        def extract_text(self) -> str:
            return self.text

    class FakeReader:
        is_encrypted = False
        pages = [FakePage("Cluster upgrade runbook"), FakePage("Check oc get co")]

        def __init__(self, _stream) -> None:
            pass

    monkeypatch.setattr(gateway_main, "PdfReader", FakeReader)

    content, report = gateway_main.extract_rag_upload_file_content(
        "운영가이드.pdf",
        "application/pdf",
        b"%PDF-1.7 fake",
    )

    assert "<!-- page: 1 -->" in content
    assert "Cluster upgrade runbook" in content
    assert report["parser"] == "pypdf"
    assert report["documentFormat"] == "pdf"
    assert report["pageCount"] == 2


def test_rag_upload_file_endpoint_uses_multipart_parser_and_existing_rag_contract(monkeypatch) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        return {"username": "admin", "uid": "uid-admin", "groups": ["cluster-admins"]}

    def fake_extract(name: str, mime_type: str, raw: bytes) -> tuple[str, dict]:
        assert name == "runbook.pdf"
        assert mime_type == "application/pdf"
        assert raw.startswith(b"%PDF")
        return (
            "# Runbook\n\n조치 전 oc get co로 Operator 상태를 확인한다.",
            {
                "parser": "pypdf",
                "documentFormat": "pdf",
                "originalFileName": name,
                "originalMimeType": mime_type,
                "originalBytes": len(raw),
                "extractedChars": 42,
                "truncated": False,
            },
        )

    def fake_persist(record: dict) -> tuple[str, str, dict]:
        return "persisted", "stored by test", record["document"]

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "extract_rag_upload_file_content", fake_extract)
    monkeypatch.setattr(gateway_main, "persist_rag_upload_document", fake_persist)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/rag/uploads/file",
                headers={"Authorization": "Bearer test-token"},
                data={
                    "labels": json.dumps({"source": "chat-attachment", "version": "v0.1.5"}),
                    "namespace": "komsco-ai-kugnus",
                    "version": "v0.1.5",
                },
                files={"file": ("runbook.pdf", b"%PDF-1.7 fake", "application/pdf")},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["kind"] == "RagUploadIngestionResult"
        assert payload["spec"]["status"] == "persisted"
        assert payload["spec"]["document"]["mimeType"] == "application/pdf"
        assert payload["spec"]["document"]["labels"]["parser"] == "pypdf"
        assert payload["spec"]["document"]["labels"]["version"] == "v0.1.5"
        assert payload["spec"]["chunks"]
        assert payload["spec"]["ingestionReport"]["documentFormat"] == "pdf"

    asyncio.run(run())


def test_parse_bool() -> None:
    assert parse_bool("true")
    assert parse_bool("1")
    assert parse_bool("on")
    assert not parse_bool("false")
    assert not parse_bool(None)
    assert parse_bool(None, default=True)


def test_parse_ols_verify() -> None:
    assert parse_ols_verify(None) is True
    assert parse_ols_verify("true") is True
    assert parse_ols_verify("false") is False
    assert parse_ols_verify("/var/run/configmaps/service-ca/service-ca.crt") == (
        "/var/run/configmaps/service-ca/service-ca.crt"
    )


def test_aiops_contract_rejects_mutating_tool_plan() -> None:
    result = assert_read_only_tool_plan(
        {
            "execution_policy": {"mode": "read_only"},
            "tool_plan": [
                {"step": 1, "tool": "get_pod", "verb": "get"},
                {"step": 2, "tool": "rollout_restart_deployment", "verb": "patch"},
            ],
        }
    )

    assert not result["ok"]
    assert any("patch" in violation for violation in result["violations"])
    assert any("forbidden tool" in violation for violation in result["violations"])


def test_official_evidence_rca_question_scopes_default_namespace_without_page_context() -> None:
    plan = build_runtime_tool_plan("어제 새벽에 default namespace Pod가 왜 재시작됐어?")

    assert plan["target"]["namespace"] == "default"
    assert {step.get("official_tool") for step in plan["tool_plan"]} >= {
        "event_tool",
        "grep_tool",
        "metric_tool",
        "snapshot_tool",
    }
    assert plan["validation"]["ok"]


def test_aiops_contract_summarizes_missing_evidence() -> None:
    status = create_evidence_status(
        {
            "evidence": [{"type": "event", "summary": "OOMKilled"}],
            "missing": [{"type": "metric", "reason": "Prometheus unavailable"}],
        }
    )

    by_type = {item["type"]: item for item in status}
    assert by_type["openshift"]["status"] == "collected"
    assert by_type["metric"]["status"] == "missing"
    assert by_type["metric"]["reason"] == "Prometheus unavailable"


def test_runtime_safety_contract_defaults_to_read_only() -> None:
    contract = build_runtime_safety_contract(
        mutations_enabled=False,
        unrestricted_commands_enabled=False,
        diagnostics_enabled=False,
        record_store_enabled=False,
    )

    assert contract["mode"] == "read_only"
    assert "patch" in contract["forbiddenActions"]
    assert contract["capabilityGates"]["mutationsEnabled"] is False
    assert contract["toolPlanStatus"]["status"] == "waiting_for_first_question"
    assert contract["lightspeedStatus"]["streamProbe"] == "not_started"
    assert {adapter["name"]: adapter["status"] for adapter in contract["adapterStatus"]} == {
        "AI Gateway": "available",
        "Linux": "disabled",
        "OpenShift": "available",
        "Windows": "planned",
    }
    linux = next(adapter for adapter in contract["adapterStatus"] if adapter["name"] == "Linux")
    windows = next(adapter for adapter in contract["adapterStatus"] if adapter["name"] == "Windows")
    openshift = next(adapter for adapter in contract["adapterStatus"] if adapter["name"] == "OpenShift")
    gateway = next(adapter for adapter in contract["adapterStatus"] if adapter["name"] == "AI Gateway")
    assert len(openshift["supportedTools"]) >= 3
    assert len(gateway["supportedTools"]) >= 1
    assert "KOMSCO_AI_DIAGNOSTICS_ENABLED" in linux["disabledReason"]
    assert "runtime collector" in windows["disabledReason"]


def test_adapter_registry_resolves_openshift_tool_plan_steps_and_marks_disabled_adapters() -> None:
    plan = build_runtime_tool_plan("default 네임스페이스 pod가 왜 재시작됐어?")
    registry = build_adapter_registry(
        diagnostics_enabled=False,
        diagnostics_controller_configured=False,
    )
    resolutions = resolve_tool_plan_adapters(plan, adapter_registry=registry)

    assert len(resolutions) >= 3
    assert {item["tool"] for item in resolutions} >= {
        "openshift_event_lookup",
        "openshift_pod_status_lookup",
        "openshift_pod_log_pattern_probe",
        "openshift_node_status_lookup",
        "openshift_alert_lookup",
        "openshift_metric_query",
    }
    resolution_by_tool = {item["tool"]: item for item in resolutions}
    assert resolution_by_tool["openshift_event_lookup"]["status"] == "resolved"
    assert resolution_by_tool["openshift_pod_status_lookup"]["resolved"] is True
    assert resolution_by_tool["openshift_pod_log_pattern_probe"]["resolved"] is True
    assert resolution_by_tool["openshift_node_status_lookup"]["status"] == "resolved"
    assert resolution_by_tool["openshift_alert_lookup"]["status"] == "resolved"
    assert resolution_by_tool["openshift_metric_query"]["status"] == "resolved"
    assert all(item["adapter"] == "OpenShift" for item in resolutions)
    linux = next(adapter for adapter in registry if adapter["name"] == "Linux")
    windows = next(adapter for adapter in registry if adapter["name"] == "Windows")
    assert linux["status"] == "disabled"
    assert linux["nextAction"].startswith("Enable diagnostics")
    assert windows["status"] == "planned"
    assert "Windows node agent" in windows["requirements"]


def test_adapter_registry_resolves_cronjob_event_lookup() -> None:
    plan = build_runtime_tool_plan("batch 네임스페이스의 CronJob report-cleaner가 15분마다 실행되는지 확인해줘")
    resolutions = resolve_tool_plan_adapters(plan)

    assert plan["task_type"] == "cronjob_activity"
    assert {item["tool"] for item in resolutions} >= {
        "openshift_cronjob_lookup",
        "openshift_job_event_lookup",
    }
    assert all(item["status"] == "resolved" for item in resolutions)
    assert all(item["adapter"] == "OpenShift" for item in resolutions)


def test_runtime_tool_plan_generates_read_only_pod_restart_rca() -> None:
    plan = build_runtime_tool_plan(
        "어제 새벽 default 네임스페이스 pod가 왜 재시작됐어?",
        execution_mode="read-only",
    )

    assert plan["kind"] == "ToolPlan"
    assert plan["task_type"] == "pod_restart_rca"
    assert plan["target"]["namespace"] == "default"
    assert plan["execution_policy"]["mode"] == "read_only"
    assert plan["validation"]["ok"] is True
    assert len(plan["adapter_resolution"]) >= 3
    resolution_by_tool = {item["tool"]: item for item in plan["adapter_resolution"]}
    assert resolution_by_tool["openshift_pod_status_lookup"]["resolved"] is True
    assert resolution_by_tool["openshift_event_lookup"]["resolved"] is True
    assert resolution_by_tool["openshift_node_status_lookup"]["status"] == "resolved"
    assert resolution_by_tool["openshift_alert_lookup"]["status"] == "resolved"
    assert resolution_by_tool["openshift_metric_query"]["status"] == "resolved"
    assert {step["adapter"] for step in plan["tool_plan"]} == {"OpenShift"}
    assert {step["verb"] for step in plan["tool_plan"]} <= {"get", "list", "watch"}
    missing_types = {item["type"] for item in plan["missing_evidence"]}
    assert {"clusteroperator", "runbook"} <= missing_types
    assert {"event", "pod_log", "snapshot"}.isdisjoint(missing_types)
    assert {"node", "alert", "metric"}.isdisjoint(missing_types)


def test_runtime_safety_contract_exposes_latest_tool_plan() -> None:
    plan = build_runtime_tool_plan("clusteroperator 상태 확인해줘")
    contract = build_runtime_safety_contract(
        mutations_enabled=False,
        unrestricted_commands_enabled=False,
        diagnostics_enabled=False,
        record_store_enabled=False,
        latest_runtime_tool_plan=plan,
    )

    assert contract["toolPlanStatus"]["status"] == "runtime_ready"
    assert contract["toolPlanStatus"]["latestRuntimePlan"]["task_type"] == "cluster_operator_status"
    assert contract["toolPlanStatus"]["adapterResolution"]
    assert all(
        item["status"] == "resolved"
        for item in contract["toolPlanStatus"]["adapterResolution"]
    )


def test_rca_context_tracks_evidence_refs_and_missing_evidence() -> None:
    plan = build_runtime_tool_plan("어제 새벽 default 네임스페이스 pod가 왜 재시작됐어?")
    context = build_rca_context(
        message="어제 새벽 default 네임스페이스 pod가 왜 재시작됐어?",
        tool_plan=plan,
        evidence_refs=[
            {
                "collectedAt": "2026-06-24T00:00:00Z",
                "contentDigest": "sha256:abc",
                "evidenceId": "ev-abc",
                "eventName": "pod_status_evidence",
                "eventStatus": "success",
                "sourceType": "gateway-preflight-evidence",
                "summary": "Pod 상태/재시작 증거 수집 완료",
            }
        ],
        page_context={"namespace": "default", "resourceKind": "Pod"},
        run_id="run-test",
        incident_id="inc-test",
    )

    assert context["kind"] == "RcaContext"
    assert context["metadata"]["contextId"].startswith("rca-")
    assert context["metadata"]["digest"].startswith("sha256:")
    assert context["metadata"]["runId"] == "run-test"
    assert context["question"]["digest"].startswith("sha256:")
    assert context["question"]["taskType"] == "pod_restart_rca"
    assert context["question"]["pageContext"] == {"namespace": "default", "resourceKind": "Pod"}
    assert context["evidence"]["summary"]["collectedCount"] == 1
    assert context["evidence"]["collectedRefs"][0]["type"] == "pod_status"
    assert any(item["type"] == "runbook" for item in context["evidence"]["missing"])
    assert context["confidence"]["level"] == "evidence_based"
    assert context["analysisPlan"]["mode"] == "evidence_first"
    assert context["analysisPlan"]["answerContract"]["format"] == "operations_rca_report"
    assert context["analysisPlan"]["answerContract"]["mustNotInventEvidence"] is True
    assert "확인 불가" in context["analysisPlan"]["answerContract"]["requiredSections"]
    step_status = {
        item["evidenceType"]: item
        for item in context["analysisPlan"]["evidenceCollectionSteps"]
    }
    assert step_status["pod_status"]["status"] == "collected"
    assert step_status["pod_status"]["evidenceId"] == "ev-abc"
    assert step_status["event"]["status"] == "not_attempted"
    assert step_status["pod_log"]["status"] == "not_attempted"
    assert step_status["node"]["status"] == "not_attempted"
    assert step_status["alert"]["status"] == "not_attempted"
    assert step_status["metric"]["status"] == "not_attempted"


def test_rca_context_without_evidence_marks_uncertainty() -> None:
    plan = build_runtime_tool_plan("clusteroperator 상태 확인해줘")
    context = build_rca_context(
        message="clusteroperator 상태 확인해줘",
        tool_plan=plan,
        evidence_refs=[],
        run_id="run-test",
        incident_id="inc-test",
    )

    assert context["evidence"]["summary"]["collectedCount"] == 0
    assert context["confidence"]["level"] == "insufficient_evidence"
    assert any(item["type"] == "openshift" for item in context["evidence"]["missing"])


def test_rca_context_treats_skipped_or_failed_refs_as_missing_not_collected() -> None:
    plan = build_runtime_tool_plan("backend-api pod count 알려줘")
    context = build_rca_context(
        message="backend-api pod count 알려줘",
        tool_plan=plan,
        evidence_refs=[
            {
                "collectedAt": "2026-06-24T00:00:00Z",
                "contentDigest": "sha256:skipped",
                "evidenceId": "ev-skipped",
                "eventName": "pod_count_investigation",
                "eventStatus": "skipped",
                "sourceType": "gateway-direct-evidence",
                "summary": "Pod 개수 직접 조회 완료",
            }
        ],
        run_id="run-test",
        incident_id="inc-test",
    )

    assert context["evidence"]["summary"]["collectedCount"] == 0
    assert context["evidence"]["summary"]["failedCount"] == 1
    assert context["evidence"]["failedRefs"][0]["evidenceId"] == "ev-skipped"
    assert any(item.get("evidenceId") == "ev-skipped" for item in context["evidence"]["missing"])
    assert context["confidence"]["level"] == "insufficient_evidence"


def test_rca_context_tracks_node_alert_metric_status_without_stale_missing() -> None:
    plan = build_runtime_tool_plan("default 네임스페이스 pod가 왜 재시작됐어?")
    context = build_rca_context(
        message="default 네임스페이스 pod가 왜 재시작됐어?",
        tool_plan=plan,
        evidence_refs=[
            {
                "collectedAt": "2026-06-24T00:00:00Z",
                "contentDigest": "sha256:node",
                "evidenceId": "ev-node",
                "evidenceType": "node",
                "eventName": "node_status_evidence",
                "eventStatus": "success",
                "sourcePath": "/api/v1/nodes",
                "sourceType": "gateway-preflight-evidence",
                "summary": "Node 상태 RCA 증거 수집 완료",
            },
            {
                "collectedAt": "2026-06-24T00:00:01Z",
                "contentDigest": "sha256:alert",
                "evidenceId": "ev-alert",
                "evidenceType": "alert",
                "eventName": "active_alerts_evidence",
                "eventStatus": "partial",
                "missingReason": "Thanos vector result was capped",
                "sourcePath": "/api/v1/query?query=ALERTS",
                "sourceType": "gateway-preflight-evidence",
                "summary": "Active Alert RCA 증거 부분 수집",
            },
            {
                "collectedAt": "2026-06-24T00:00:02Z",
                "contentDigest": "sha256:metric",
                "evidenceId": "ev-metric",
                "evidenceType": "metric",
                "eventName": "restart_metric_evidence",
                "eventStatus": "error",
                "missingReason": "Prometheus query failed",
                "sourcePath": "/api/v1/query?query=increase",
                "sourceType": "gateway-preflight-evidence",
                "summary": "Restart metric RCA 증거 수집 불가",
            },
        ],
        run_id="run-rca-status",
        incident_id="inc-rca-status",
    )

    step_status = {
        item["evidenceType"]: item
        for item in context["analysisPlan"]["evidenceCollectionSteps"]
    }
    missing_types = {item["type"] for item in context["evidence"]["missing"]}

    assert context["evidence"]["summary"]["collectedCount"] == 1
    assert context["evidence"]["summary"]["partialCount"] == 1
    assert context["evidence"]["summary"]["failedCount"] == 1
    assert step_status["node"]["status"] == "collected"
    assert step_status["alert"]["status"] == "partial"
    assert step_status["metric"]["status"] == "failed"
    assert "node" not in missing_types
    assert "alert" not in missing_types
    assert "metric" in missing_types
    assert context["evidence"]["partialRefs"][0]["evidenceId"] == "ev-alert"


def test_rca_context_classifies_clusteroperator_detail_before_pod_status_name() -> None:
    plan = build_runtime_tool_plan("clusteroperator 상태 확인해줘")
    context = build_rca_context(
        message="clusteroperator 상태 확인해줘",
        tool_plan=plan,
        evidence_refs=[
            {
                "collectedAt": "2026-06-24T00:00:00Z",
                "contentDigest": "sha256:co",
                "detail": "Gateway-collected ClusterOperator evidence from Kubernetes API.",
                "evidenceId": "ev-co",
                "eventName": "pod_status_evidence",
                "eventStatus": "success",
                "sourceType": "gateway-preflight-evidence",
                "summary": "Pod 상태/재시작 증거 수집 완료",
            }
        ],
        run_id="run-test",
        incident_id="inc-test",
    )

    assert context["evidence"]["collectedRefs"][0]["type"] == "clusteroperator"


def test_runtime_safety_contract_exposes_latest_rca_context() -> None:
    plan = build_runtime_tool_plan("clusteroperator 상태 확인해줘")
    context = build_rca_context(
        message="clusteroperator 상태 확인해줘",
        tool_plan=plan,
        evidence_refs=[],
        run_id="run-test",
        incident_id="inc-test",
    )
    contract = build_runtime_safety_contract(
        mutations_enabled=False,
        unrestricted_commands_enabled=False,
        diagnostics_enabled=False,
        record_store_enabled=False,
        latest_runtime_tool_plan=plan,
        latest_rca_context=context,
    )

    assert contract["rcaContextStatus"]["status"] == "available"
    assert contract["rcaContextStatus"]["digest"] == context["metadata"]["digest"]
    assert contract["rcaContextStatus"]["latestContext"]["kind"] == "RcaContext"
    assert any(item["type"] == "openshift" for item in contract["evidenceStatus"])


def test_runtime_safety_contract_counts_rca_collected_refs_as_evidence() -> None:
    plan = build_runtime_tool_plan("clusteroperator 상태 확인해줘")
    context = build_rca_context(
        message="clusteroperator 상태 확인해줘",
        tool_plan=plan,
        evidence_refs=[
            {
                "collectedAt": "2026-06-24T00:00:00Z",
                "contentDigest": "sha256:clusteroperator",
                "eventStatus": "success",
                "sourceType": "gateway-preflight-evidence",
                "summary": "clusteroperator 상태 증거 수집 완료",
            }
        ],
        run_id="run-test",
        incident_id="inc-test",
    )
    contract = build_runtime_safety_contract(
        mutations_enabled=False,
        unrestricted_commands_enabled=False,
        diagnostics_enabled=False,
        record_store_enabled=False,
        latest_runtime_tool_plan=plan,
        latest_rca_context=context,
    )

    openshift_status = next(
        item for item in contract["evidenceStatus"] if item["type"] == "openshift"
    )
    assert context["evidence"]["summary"]["collectedCount"] == 1
    assert openshift_status["status"] == "collected"
    assert openshift_status["count"] == 1


def test_runtime_safety_contract_counts_pod_count_direct_evidence_as_openshift_collected() -> None:
    plan = build_runtime_tool_plan("aiops-two-pod-exec 파드 몇개 띄었어?")
    context = build_rca_context(
        message="aiops-two-pod-exec 파드 몇개 띄었어?",
        tool_plan=plan,
        evidence_refs=[
            {
                "collectedAt": "2026-06-24T00:00:00Z",
                "contentDigest": "sha256:pod-count",
                "evidenceId": "ev-pod-count",
                "eventName": "pod_count_investigation",
                "eventStatus": "success",
                "sourceType": "gateway-direct-evidence",
                "summary": "Pod 개수 직접 조회 완료",
            }
        ],
        run_id="run-pod-count",
        incident_id="inc-pod-count",
    )
    contract = build_runtime_safety_contract(
        mutations_enabled=False,
        unrestricted_commands_enabled=False,
        diagnostics_enabled=False,
        record_store_enabled=False,
        latest_runtime_tool_plan=plan,
        latest_rca_context=context,
    )

    openshift_status = next(
        item for item in contract["evidenceStatus"] if item["type"] == "openshift"
    )
    assert context["evidence"]["summary"]["collectedCount"] == 1
    assert context["evidence"]["collectedRefs"][0]["type"] == "pod_status"
    assert openshift_status["status"] == "collected"
    assert openshift_status["count"] == 1


def test_olm_operator_read_only_installation_skips_mutating_operands() -> None:
    config = olm_operator.installation_config(
        {
            "metadata": {"namespace": "komsco-ai-kugnus"},
            "spec": {
                "targetNamespace": "komsco-ai-kugnus",
                "consolePluginName": "komsco-ai-console-plugin-kugnus",
                "capabilities": {
                    "diagnostics": False,
                    "mutations": False,
                    "unrestrictedCommands": False,
                },
            },
        }
    )
    resources = olm_operator.resources_for(config)
    names = {(resource["kind"], resource["metadata"]["name"]) for resource in resources}

    assert ("Deployment", "komsco-ai-gateway") in names
    assert ("Deployment", "komsco-ai-console-plugin") in names
    assert ("ConsolePlugin", "komsco-ai-console-plugin-kugnus") in names
    assert ("Deployment", "komsco-ai-action-executor") not in names
    assert ("Deployment", "komsco-ai-host-diagnostics-controller") not in names
    assert ("ServiceAccount", "komsco-ai-action-executor") not in names
    assert ("ServiceAccount", "komsco-ai-host-diagnostics-controller") not in names


def test_olm_operator_can_wire_rag_backend_url_from_secret() -> None:
    config = olm_operator.installation_config(
        {
            "metadata": {"namespace": "komsco-ai-kugnus"},
            "spec": {
                "targetNamespace": "komsco-ai-kugnus",
                "consolePluginName": "komsco-ai-console-plugin-kugnus",
                "rag": {
                    "backendUrlSecret": "komsco-ai-rag-pgvector",
                    "backendUrlKey": "database-url",
                    "embeddingModel": "hashing-local-dev",
                    "vectorDimensions": 64,
                },
            },
        }
    )
    gateway = next(
        resource
        for resource in olm_operator.resources_for(config)
        if resource["kind"] == "Deployment" and resource["metadata"]["name"] == "komsco-ai-gateway"
    )
    env = {item["name"]: item for item in gateway["spec"]["template"]["spec"]["containers"][0]["env"]}

    assert env["KOMSCO_AI_RAG_BACKEND_URL"]["valueFrom"]["secretKeyRef"] == {
        "name": "komsco-ai-rag-pgvector",
        "key": "database-url",
    }
    assert env["KOMSCO_AI_RAG_EMBEDDING_MODEL"]["value"] == "hashing-local-dev"
    assert env["KOMSCO_AI_RAG_VECTOR_DIMENSIONS"]["value"] == "64"


def _ready_olm_resource(
    api_version: str,
    kind: str,
    name: str,
    resource_namespace: str | None = None,
) -> dict:
    if kind == "Deployment":
        return {
            "metadata": {"name": name, "namespace": resource_namespace},
            "spec": {"replicas": 1},
            "status": {"availableReplicas": 1, "readyReplicas": 1, "updatedReplicas": 1},
        }
    if kind == "ConfigMap" and name == "komsco-ai-service-ca":
        return {
            "metadata": {"name": name, "namespace": resource_namespace},
            "data": {"service-ca.crt": "test-ca"},
        }
    if kind == "ConsolePlugin":
        return {
            "metadata": {"name": name},
            "spec": {
                "backend": {
                    "service": {
                        "name": "komsco-ai-console-plugin",
                        "namespace": "komsco-ai-kugnus",
                    }
                },
                "proxy": [
                    {
                        "alias": "ai-gateway",
                        "endpoint": {
                            "service": {
                                "name": "komsco-ai-gateway",
                                "namespace": "komsco-ai-kugnus",
                            }
                        },
                    }
                ],
            },
        }
    return {"apiVersion": api_version, "kind": kind, "metadata": {"name": name, "namespace": resource_namespace}}


def test_olm_operator_status_payload_exposes_v011_readiness_conditions(monkeypatch) -> None:
    monkeypatch.setattr(olm_operator, "get_resource", _ready_olm_resource)
    config = olm_operator.installation_config(
        {
            "metadata": {"namespace": "komsco-ai-kugnus", "generation": 7},
            "spec": {
                "targetNamespace": "komsco-ai-kugnus",
                "pluginReplicas": 1,
                "gatewayReplicas": 1,
                "consolePluginName": "komsco-ai-console-plugin-kugnus",
                "capabilities": {
                    "diagnostics": False,
                    "mutations": False,
                    "unrestrictedCommands": False,
                },
            },
        }
    )

    payload = olm_operator.build_status_payload(
        {"metadata": {"name": "komsco-aiops-kugnus", "namespace": "komsco-ai-kugnus", "generation": 7}},
        "Ready",
        "KOMSCO AIOps runtime reconciled",
        config,
    )
    by_type = {item["type"]: item for item in payload["conditions"]}

    assert payload["phase"] == "Ready"
    assert payload["versionScope"] == "Ver.0.1.1"
    assert set(olm_operator.DEFAULT_READINESS_CONDITION_TYPES) <= set(by_type)
    assert by_type["ActionExecutorReady"]["reason"] == "DisabledByReadOnly"
    assert by_type["HostDiagnosticsReady"]["reason"] == "DisabledByPolicy"
    assert payload["components"]["gateway"]["ready"] is True
    assert payload["components"]["consolePlugin"]["ready"] is True
    assert payload["components"]["serviceCA"]["ready"] is True
    assert payload["components"]["rbac"]["ready"] is True
    assert payload["components"]["safetyMode"]["reason"] == "ReadOnlyLocked"


def test_olm_operator_status_payload_reports_progressing_when_gateway_unavailable(monkeypatch) -> None:
    def fake_resource(
        api_version: str,
        kind: str,
        name: str,
        resource_namespace: str | None = None,
    ) -> dict:
        resource = _ready_olm_resource(api_version, kind, name, resource_namespace)
        if kind == "Deployment" and name == "komsco-ai-gateway":
            resource["status"] = {"availableReplicas": 0, "readyReplicas": 0, "updatedReplicas": 1}
        return resource

    monkeypatch.setattr(olm_operator, "get_resource", fake_resource)
    config = olm_operator.installation_config(
        {
            "metadata": {"namespace": "komsco-ai-kugnus", "generation": 8},
            "spec": {
                "targetNamespace": "komsco-ai-kugnus",
                "pluginReplicas": 1,
                "gatewayReplicas": 1,
                "consolePluginName": "komsco-ai-console-plugin-kugnus",
                "capabilities": {
                    "diagnostics": False,
                    "mutations": False,
                    "unrestrictedCommands": False,
                },
            },
        }
    )

    payload = olm_operator.build_status_payload(
        {"metadata": {"name": "komsco-aiops-kugnus", "namespace": "komsco-ai-kugnus", "generation": 8}},
        "Ready",
        "KOMSCO AIOps runtime reconciled",
        config,
    )
    by_type = {item["type"]: item for item in payload["conditions"]}

    assert payload["phase"] == "Progressing"
    assert "GatewayReady" in payload["message"]
    assert by_type["GatewayReady"]["status"] == "False"
    assert by_type["GatewayReady"]["reason"] == "WaitingForRollout"
    assert payload["components"]["gateway"]["ready"] is False


def test_olm_operator_status_rejects_execute_mode_without_mutations(monkeypatch) -> None:
    monkeypatch.setattr(olm_operator, "get_resource", _ready_olm_resource)
    config = olm_operator.installation_config(
        {
            "metadata": {"namespace": "komsco-ai-kugnus", "generation": 9},
            "spec": {
                "targetNamespace": "komsco-ai-kugnus",
                "mode": "execute",
                "pluginReplicas": 1,
                "gatewayReplicas": 1,
                "consolePluginName": "komsco-ai-console-plugin-kugnus",
                "capabilities": {
                    "diagnostics": False,
                    "mutations": False,
                    "unrestrictedCommands": False,
                },
            },
        }
    )

    payload = olm_operator.build_status_payload(
        {"metadata": {"name": "komsco-aiops-kugnus", "namespace": "komsco-ai-kugnus", "generation": 9}},
        "Ready",
        "KOMSCO AIOps runtime reconciled",
        config,
    )
    by_type = {item["type"]: item for item in payload["conditions"]}

    assert payload["phase"] == "Progressing"
    assert by_type["ActionExecutorReady"]["status"] == "False"
    assert by_type["ActionExecutorReady"]["reason"] == "MutationCapabilityMismatch"
    assert by_type["SafetyModeReady"]["status"] == "False"
    assert by_type["SafetyModeReady"]["reason"] == "ExecuteCapabilityMismatch"


def test_olm_operator_status_rejects_read_only_mode_with_mutations(monkeypatch) -> None:
    monkeypatch.setattr(olm_operator, "get_resource", _ready_olm_resource)
    config = olm_operator.installation_config(
        {
            "metadata": {"namespace": "komsco-ai-kugnus", "generation": 10},
            "spec": {
                "targetNamespace": "komsco-ai-kugnus",
                "mode": "read-only",
                "pluginReplicas": 1,
                "gatewayReplicas": 1,
                "consolePluginName": "komsco-ai-console-plugin-kugnus",
                "capabilities": {
                    "diagnostics": False,
                    "mutations": True,
                    "unrestrictedCommands": False,
                },
            },
        }
    )

    payload = olm_operator.build_status_payload(
        {"metadata": {"name": "komsco-aiops-kugnus", "namespace": "komsco-ai-kugnus", "generation": 10}},
        "Ready",
        "KOMSCO AIOps runtime reconciled",
        config,
    )
    by_type = {item["type"]: item for item in payload["conditions"]}

    assert payload["phase"] == "Progressing"
    assert by_type["SafetyModeReady"]["status"] == "False"
    assert by_type["SafetyModeReady"]["reason"] == "ReadOnlyCapabilityMismatch"


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


def test_page_context_aiops_execution_mode_accepts_unrestricted_aliases() -> None:
    assert (
        page_context_aiops_execution_mode(
            ChatRequest(
                message="명령 실행",
                pageContext={"aiopsExecutionMode": "unrestricted"},
            )
        )
        == "unrestricted"
    )
    assert (
        page_context_aiops_execution_mode(
            ChatRequest(
                message="명령 실행",
                pageContext={"aiopsExecutionMode": "실험"},
            )
        )
        == "unrestricted"
    )


def test_parse_unrestricted_chat_command_requires_explicit_prefix() -> None:
    assert parse_unrestricted_chat_command("/exec printf ok") == "printf ok"
    assert parse_unrestricted_chat_command("실행: ```bash\nprintf ok\n```") == "printf ok"
    assert parse_unrestricted_chat_command("파드 목록 조회해줘") == ""


def test_followup_execution_request_accepts_korean_variants() -> None:
    assert is_followup_execution_request("진행해")
    assert is_followup_execution_request("승인해")
    assert is_followup_execution_request("실행해")
    assert is_followup_execution_request("적용")
    assert not is_followup_execution_request("진행 상황 분석해줘")


def test_recent_natural_action_request_uses_previous_user_message() -> None:
    request = ChatRequest(
        message="진행해",
        pageContext={"namespace": "team-a", "aiopsExecutionMode": "unrestricted"},
        recentMessages=[
            {"role": "user", "content": "team-a 네임스페이스의 web-api 파드 4개로 올려줘"},
            {"role": "assistant", "content": "조치 계획을 생성했습니다. 승인하시겠습니까?"},
        ],
    )

    contextual_request = recent_natural_action_request(request)

    assert contextual_request
    assert contextual_request.message == "team-a 네임스페이스의 web-api 파드 4개로 올려줘"
    intent = parse_natural_action_intent(contextual_request)
    assert intent
    assert intent["namespace"] == "team-a"
    assert intent["targetName"] == "web-api"
    assert intent["parameters"]["replicas"] == 4


def test_unrestricted_command_endpoint_requires_feature_flag(monkeypatch) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        return {"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]}

    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMANDS_ENABLED", False)
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/dev/commands/execute",
                headers={"Authorization": "Bearer test-token"},
                json={"command": "printf should-not-run"},
            )

        assert response.status_code == 403

    asyncio.run(run())


def test_unrestricted_command_endpoint_executes_when_enabled(monkeypatch, tmp_path) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        return {"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]}

    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMANDS_ENABLED", True)
    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMAND_CWD", str(tmp_path))
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/dev/commands/execute",
                headers={"Authorization": "Bearer test-token"},
                json={"command": "printf aiops-unrestricted-ok", "timeoutSeconds": 5},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["kind"] == "UnrestrictedCommandExecution"
        assert payload["spec"]["exitCode"] == 0
        assert payload["spec"]["stdout"] == "aiops-unrestricted-ok"
        assert payload["spec"]["timedOut"] is False

    asyncio.run(run())


def test_chat_stream_exec_prefix_runs_unrestricted_command(monkeypatch, tmp_path) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        return {"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]}

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMANDS_ENABLED", True)
    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMAND_CWD", str(tmp_path))
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "/exec printf chat-unrestricted-ok",
                    "pageContext": {"aiopsExecutionMode": "unrestricted"},
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        command_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "unrestricted_command"
        ]
        text_events = [
            event
            for event in events
            if isinstance(event, dict) and event.get("type") == "text"
        ]
        assert command_results
        assert command_results[0]["status"] == "success"
        assert "chat-unrestricted-ok" in command_results[0]["detail"]
        assert any("chat-unrestricted-ok" in event.get("content", "") for event in text_events)

    asyncio.run(run())


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
        assert len(rca_events) >= 2
        latest_context = rca_events[-1]["context"]
        assert latest_context["kind"] == "RcaContext"
        assert latest_context["metadata"]["runId"] == "run-rca-test"
        assert latest_context["metadata"]["phase"] == "post_answer"
        assert latest_context["metadata"]["digest"].startswith("sha256:")
        assert latest_context["evidence"]["summary"]["missingCount"] >= 1
        assert gateway_main.LAST_RCA_CONTEXT["metadata"]["digest"] == latest_context["metadata"]["digest"]

    asyncio.run(run())


def test_chat_stream_collects_stage3_node_alert_metric_evidence_before_answer(monkeypatch) -> None:
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

    async def fake_pod_evidence(*_args, **_kwargs) -> str:
        return "Gateway-collected Pod status evidence from Kubernetes API `/api/v1/pods`."

    async def fake_node_evidence(_authorization: str) -> dict:
        return {
            "detail": "Gateway-collected Node status evidence from Kubernetes API `/api/v1/nodes`.",
            "evidenceType": "node",
            "sourcePath": "/api/v1/nodes",
            "status": "success",
            "summary": "Node 상태 RCA 증거 수집 완료",
        }

    async def fake_alert_evidence(_authorization: str) -> dict:
        return {
            "detail": 'Gateway-collected Active alert evidence from Thanos query `ALERTS{alertstate="firing"}`.',
            "evidenceType": "alert",
            "missingReason": "Thanos vector result was capped",
            "sourcePath": "/api/v1/query?query=ALERTS",
            "status": "partial",
            "summary": "Active Alert RCA 증거 부분 수집",
        }

    async def fake_metric_evidence(_authorization: str) -> dict:
        return {
            "detail": "Metric RCA evidence unavailable: status=error, reason=Prometheus query failed",
            "evidenceType": "metric",
            "missingReason": "Prometheus query failed",
            "sourcePath": "/api/v1/query?query=increase",
            "status": "error",
            "summary": "Restart metric RCA 증거 수집 불가",
        }

    async def fake_official_restart_evidence(
        _authorization: str,
        namespace: str,
        request_id: str,
    ) -> list[dict]:
        assert namespace == "default"
        return [
            {
                "type": "tool_result",
                "detail": '{"eventCount": 2, "rawEventMessages": "omitted"}',
                "evidenceType": "event",
                "id": f"{request_id}-official-namespace-restart-events",
                "name": "official_namespace_restart_event_evidence",
                "sourcePath": "/api/v1/namespaces/default/events?limit=200",
                "status": "success",
                "summary": "공식 Pod 재시작 namespace Event 증거 수집 완료",
            },
            {
                "type": "tool_result",
                "detail": '{"candidatePods": [{"name": "sample", "restartCount": 3}]}',
                "evidenceType": "snapshot",
                "id": f"{request_id}-official-namespace-restart-snapshot",
                "name": "official_namespace_restart_snapshot",
                "sourcePath": "/api/v1/namespaces/default/pods?limit=200",
                "status": "success",
                "summary": "공식 Pod 재시작 namespace snapshot 증거 수집 완료",
            },
            {
                "type": "tool_result",
                "detail": '{"rawLogDisclosure": false, "patternCounts": {"OOMKilled": 1}}',
                "evidenceType": "pod_log",
                "id": f"{request_id}-official-namespace-restart-log-patterns",
                "matchedPatternIds": ["OOMKilled"],
                "name": "official_namespace_restart_log_pattern_probe",
                "patternCounts": {"OOMKilled": 1},
                "rawLogDisclosure": False,
                "sourcePath": "/api/v1/namespaces/default/pods/sample/log?previous=true",
                "status": "partial",
                "summary": "공식 Pod 재시작 log pattern 증거 부분 수집",
            },
        ]

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "collect_pod_status_evidence", fake_pod_evidence)
    monkeypatch.setattr(
        gateway_main,
        "collect_official_namespace_restart_evidence_events",
        fake_official_restart_evidence,
    )
    monkeypatch.setattr(gateway_main, "collect_node_status_rca_evidence", fake_node_evidence)
    monkeypatch.setattr(gateway_main, "collect_active_alerts_rca_evidence", fake_alert_evidence)
    monkeypatch.setattr(gateway_main, "collect_restart_metric_rca_evidence", fake_metric_evidence)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "어제 새벽에 default namespace Pod가 왜 재시작됐어?",
                    "runId": "run-stage3-preflight",
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        tool_results = [
            event
            for event in events
            if isinstance(event, dict) and event.get("type") == "tool_result"
        ]
        result_by_name = {event.get("name"): event for event in tool_results}
        rca_events = [
            event
            for event in events
            if isinstance(event, dict) and event.get("type") == "rca_context"
        ]
        pre_answer = next(
            event["context"]
            for event in rca_events
            if event.get("phase") == "pre_answer"
        )
        step_status = {
            item["evidenceType"]: item
            for item in pre_answer["analysisPlan"]["evidenceCollectionSteps"]
        }
        evidence_ref_results = [
            event["result"]
            for event in tool_results
            if event.get("name") == "evidence_ref"
        ]
        evidence_ref_types = {item.get("evidenceType") for item in evidence_ref_results}

        assert result_by_name["node_status_evidence"]["status"] == "success"
        assert result_by_name["official_namespace_restart_event_evidence"]["status"] == "success"
        assert result_by_name["official_namespace_restart_snapshot"]["status"] == "success"
        assert result_by_name["official_namespace_restart_log_pattern_probe"]["status"] == "partial"
        assert result_by_name["active_alerts_evidence"]["status"] == "partial"
        assert result_by_name["restart_metric_evidence"]["status"] == "error"
        assert {"node", "alert", "event", "metric", "pod_log", "snapshot"} <= evidence_ref_types
        assert step_status["node"]["status"] == "collected"
        assert step_status["alert"]["status"] == "partial"
        assert step_status["event"]["status"] == "collected"
        assert step_status["pod_log"]["status"] == "partial"
        assert step_status["snapshot"]["status"] == "collected"
        assert step_status["metric"]["status"] == "failed"
        assert pre_answer["evidence"]["summary"]["partialCount"] >= 2
        assert "test-token" not in response.text

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

    async def fake_execute_action_with_executor(sealed_plan: dict, _grant_reference: dict) -> dict:
        assert sealed_plan["action"]["toolName"] == "set_replicas_within_bounds"
        assert sealed_plan["action"]["normalizedParameters"]["replicas"] == 3
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
        assert any("실행까지 완료" in event.get("content", "") for event in text_events)
        context = assert_post_answer_rca_before_done(events)
        assert context["confidence"]["level"] == "insufficient_evidence"

    asyncio.run(run())


def test_normalize_console_page_context_extracts_namespaced_resource() -> None:
    context = normalize_console_page_context(
        {
            "href": "http://localhost:9000/k8s/ns/team-a/deployments/web",
            "pathname": "/k8s/ns/team-a/deployments/web",
            "title": "ignored browser title",
        }
    )

    assert context["route"] == "k8s"
    assert context["namespace"] == "team-a"
    assert context["resourceList"] == "deployments"
    assert context["resourceKind"] == "Deployment"
    assert context["resourceName"] == "web"
    assert "title" not in context


def test_normalize_console_page_context_extracts_catalog_namespace() -> None:
    context = normalize_console_page_context(
        {
            "href": "http://localhost:9000/catalog/ns/team-a",
            "pathname": "/catalog/ns/team-a",
        }
    )

    assert context["route"] == "catalog"
    assert context["namespace"] == "team-a"
    assert context["resourceKind"] == "Catalog"
    assert context["perspective"] == "developer"


def test_product_access_review_request_is_config_driven_ssar() -> None:
    request = build_product_access_review_request()

    assert request["apiVersion"] == "authorization.k8s.io/v1"
    assert request["kind"] == "SelfSubjectAccessReview"
    attributes = request["spec"]["resourceAttributes"]
    assert attributes["verb"]
    assert attributes["resource"]
    assert "token" not in str(request).lower()


def test_product_access_review_statuses_are_nonblocking_by_default() -> None:
    review = {
        "allowed": False,
        "enabled": True,
        "reason": "not allowed in this namespace",
        "required": False,
        "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
    }

    assert product_access_review_status(review) == "warning"
    assert "required: False" in summarize_product_access_review(review)


def test_redact_sensitive_removes_tokens_and_secret_values() -> None:
    raw = {
        "authorization": "Bearer abcdefghijklmnopqrstuvwxyz",
        "message": "password=supersecret token: sha256~abcdef Bearer abcdefghijklmnopqrstuvwxyz",
        "nested": {"clientSecret": "should-not-leak"},
    }

    redacted = redact_sensitive(raw)

    assert redacted["authorization"] == "[REDACTED]"
    assert "supersecret" not in redacted["message"]
    assert "abcdefghijklmnopqrstuvwxyz" not in redacted["message"]
    assert redacted["nested"]["clientSecret"] == "[REDACTED]"


def test_classify_request_policy_blocks_direct_mutation_intent() -> None:
    policy = classify_request_policy("openshift-monitoring pod 재시작해줘")

    assert policy["decision"] == "action_proposal_only"
    assert policy["mutationAllowed"] is False
    assert policy["risk"] == "approval_required"


def test_classify_request_policy_routes_natural_scale_to_action_proposal() -> None:
    policy = classify_request_policy("web-api 파드 3개로 올려줘")

    assert policy["decision"] == "action_proposal_only"
    assert policy["mutationAllowed"] is False
    assert policy["risk"] == "approval_required"


def test_classify_request_policy_blocks_mutation_action_plan_intent() -> None:
    policy = classify_request_policy("deployment 재시작 계획을 세워줘")

    assert policy["decision"] == "action_proposal_only"
    assert policy["mutationAllowed"] is False
    assert policy["risk"] == "approval_required"


def test_classify_request_policy_blocks_rollback_action_plan_intent() -> None:
    policy = classify_request_policy("deployment rollout 문제가 있을 때 롤백 계획을 세워줘")

    assert policy["decision"] == "action_proposal_only"
    assert policy["mutationAllowed"] is False
    assert policy["risk"] == "approval_required"


def test_classify_request_policy_allows_restart_count_analysis() -> None:
    policy = classify_request_policy("현재 클러스터에서 재시작이 많은 Pod를 분석해줘")

    assert policy["decision"] == "allow_read_only_evidence"
    assert policy["mutationAllowed"] is False
    assert policy["risk"] == "low"


def test_classify_request_policy_allows_pod_count_question() -> None:
    policy = classify_request_policy("aiops-two-pod-exec 파드 몇개 띄었어?")

    assert policy["decision"] == "allow_read_only_evidence"
    assert policy["mutationAllowed"] is False
    assert policy["risk"] == "low"


def test_parse_pod_count_query_extracts_target_without_hardcoded_name() -> None:
    query = parse_pod_count_query(
        ChatRequest(message="team-a 네임스페이스의 web-api 파드 몇개 떠있어?")
    )

    assert query == {"namespace": "team-a", "targetName": "web-api"}
    assert is_pod_count_query("backend-api pod count 알려줘")
    assert parse_pod_count_query(ChatRequest(message="pod count 알려줘")) == {
        "namespace": "",
        "targetName": "",
    }


def test_pod_status_evidence_trigger_only_for_read_only_status_analysis() -> None:
    assert should_collect_pod_status_evidence("현재 클러스터의 Pod 상태와 재시작이 많은 Pod를 분석해줘")
    assert should_collect_pod_status_evidence("파드리스트 조회해줘")
    assert should_collect_pod_status_evidence("aiops-two-pod-exec 파드 몇개 띄었어?")
    assert should_collect_pod_status_evidence("ClusterOperator authentication 상태를 확인해줘")
    assert not should_collect_pod_status_evidence("openshift-monitoring pod 재시작해줘")
    assert should_collect_rca_signal_evidence("최근 경고와 원인을 근거 기준으로 정리해줘")
    assert should_collect_rca_signal_evidence("노드 pressure와 CPU metric도 같이 봐줘")


def test_classify_request_policy_allows_read_only_investigation() -> None:
    policy = classify_request_policy("최근 경고와 원인을 근거 기준으로 정리해줘")

    assert policy["decision"] == "allow_read_only_evidence"
    assert policy["mutationAllowed"] is False


def test_policy_check_progress_copy_uses_operator_language() -> None:
    read_only_policy = classify_request_policy("최근 에러로그 20건 가져와봐")
    action_policy = classify_request_policy("web-api 파드 3개로 올려줘")

    assert policy_check_summary(read_only_policy) == "조회/증거 수집 허용"
    assert "Read-only evidence allowed" not in policy_check_summary(read_only_policy)
    assert "정책 결정: 조회/증거 수집 허용" in summarize_policy_detail(read_only_policy)
    assert "내부 결정값: allow_read_only_evidence" in summarize_policy_detail(read_only_policy)
    assert policy_check_summary(action_policy) == "조치 요청은 Action Plan 경로로 처리"
    assert "Action proposal only" not in policy_check_summary(action_policy)


def test_build_pod_count_investigation_uses_deployment_selector() -> None:
    result = build_pod_count_investigation(
        {"namespace": "team-a", "targetName": "web-api"},
        {
            "items": [
                {
                    "metadata": {"name": "web-api", "namespace": "team-a"},
                    "spec": {
                        "replicas": 3,
                        "selector": {"matchLabels": {"app": "web-api"}},
                    },
                    "status": {"readyReplicas": 3, "availableReplicas": 3},
                }
            ]
        },
        {
            "items": [
                {
                    "metadata": {
                        "labels": {"app": "web-api"},
                        "name": "web-api-7d9c4f4d5f-a",
                        "namespace": "team-a",
                    },
                    "status": {
                        "containerStatuses": [{"ready": True, "restartCount": 0}],
                        "phase": "Running",
                    },
                },
                {
                    "metadata": {
                        "labels": {"app": "web-api"},
                        "name": "web-api-7d9c4f4d5f-b",
                        "namespace": "team-a",
                    },
                    "status": {
                        "containerStatuses": [{"ready": True, "restartCount": 0}],
                        "phase": "Running",
                    },
                },
                {
                    "metadata": {
                        "labels": {"app": "web-api"},
                        "name": "web-api-7d9c4f4d5f-c",
                        "namespace": "team-a",
                    },
                    "status": {
                        "containerStatuses": [{"ready": True, "restartCount": 1}],
                        "phase": "Running",
                    },
                },
                {
                    "metadata": {
                        "labels": {"app": "other"},
                        "name": "other-7d9c4f4d5f-a",
                        "namespace": "team-a",
                    },
                    "status": {
                        "containerStatuses": [{"ready": True, "restartCount": 0}],
                        "phase": "Running",
                    },
                },
            ]
        },
    )

    assert result["status"] == "found"
    assert result["matchStrategy"] == "deployment_selector"
    assert result["rows"][0]["desiredReplicas"] == 3
    assert result["rows"][0]["totalPods"] == 3
    assert result["rows"][0]["runningPods"] == 3
    assert result["rows"][0]["readyPods"] == 3


def test_rag_upload_document_redacts_sensitive_content_before_chunking() -> None:
    request = RagDocumentUploadCreate(
        name="ops-runbook.md",
        content="""
        # 운영 절차

        oc get pods -n openshift-marketplace
        Authorization: Bearer secret-token-value-1234567890
        token: sha256~secret-token-value
        client-key-data: UHJpdmF0ZUtleUJvZHk=
        client-certificate-data: Q2VydGlmaWNhdGVCb2R5
        certificate-authority-data: Q0FCb2R5
        -----BEGIN PRIVATE KEY-----
        PrivateKeyBody
        -----END PRIVATE KEY-----
        """,
        labels={"scenario": "upload_rag"},
    )

    record = build_rag_upload_document(request, {"username": "admin"})
    rendered = json.dumps(record, ensure_ascii=False)

    assert record["document"]["sourceType"] == "user-upload"
    assert record["document"]["chunkCount"] >= 1
    assert record["document"]["checksum"].startswith("sha256:")
    assert "secret-token-value" not in rendered
    assert "PrivateKeyBody" not in rendered
    assert "UHJpdmF0ZUtleUJvZHk" not in rendered
    assert "Q2VydGlmaWNhdGVCb2R5" not in rendered
    assert "Q0FCb2R5" not in rendered
    assert "[REDACTED" in rendered


def test_rag_upload_acl_is_derived_from_current_subject() -> None:
    subject = safe_subject(
        {
            "username": "admin",
            "uid": "uid-admin",
            "groups": ["cluster-admins", "system:authenticated"],
        }
    )

    default_acl_record = build_rag_upload_document(
        RagDocumentUploadCreate(name="ops-runbook.md", content="RAG ACL smoke content."),
        subject,
    )
    restricted_acl_record = build_rag_upload_document(
        RagDocumentUploadCreate(
            name="ops-runbook.md",
            content="RAG ACL smoke content.",
            aclGroups=["cluster-admins"],
        ),
        subject,
    )

    assert set(default_acl_record["document"]["aclGroups"]) == {
        "cluster-admins",
        "uid:uid-admin",
        "user:admin",
    }
    assert "system:authenticated" not in default_acl_record["document"]["aclGroups"]
    assert restricted_acl_record["document"]["aclGroups"] == ["cluster-admins"]

    with pytest.raises(HTTPException) as exc:
        build_rag_upload_document(
            RagDocumentUploadCreate(
                name="ops-runbook.md",
                content="RAG ACL smoke content.",
                aclGroups=["other-team"],
            ),
            subject,
        )
    assert exc.value.status_code == 403


def test_rag_search_acl_filter_hides_other_subject_documents() -> None:
    filters = gateway_main.RagSearchFilters()
    admin_principals = {"cluster-admins", "user:admin", "uid:uid-admin"}
    admin_row = {
        "acl_groups": ["cluster-admins", "user:admin"],
        "customer": "KOMSCO",
        "document_id": "user-upload:admin",
        "namespace": "openshift-marketplace",
        "source_type": "user-upload",
        "version": "v0.1.4",
        "labels": {"freshness": "fresh", "safetyClass": "read-only"},
    }
    other_row = {
        "acl_groups": ["other-team", "user:other"],
        "customer": "KOMSCO",
        "document_id": "user-upload:other",
        "namespace": "openshift-marketplace",
        "source_type": "user-upload",
        "version": "v0.1.4",
        "labels": {"freshness": "fresh", "safetyClass": "read-only"},
    }

    assert gateway_main.row_matches_rag_filters(admin_row, filters, admin_principals) is True
    assert gateway_main.row_matches_rag_filters(other_row, filters, admin_principals) is False


def test_rag_search_acl_filter_rejects_requested_group_not_owned_by_subject() -> None:
    subject_principals = {"cluster-admins", "user:admin"}
    row = {
        "acl_groups": ["cluster-admins", "user:admin"],
        "customer": "KOMSCO",
        "document_id": "user-upload:admin",
        "namespace": "openshift-marketplace",
        "source_type": "user-upload",
        "version": "v0.1.4",
        "labels": {"freshness": "fresh", "safetyClass": "read-only"},
    }

    assert (
        gateway_main.row_matches_rag_filters(
            row,
            gateway_main.RagSearchFilters(aclGroups=["cluster-admins"]),
            subject_principals,
        )
        is True
    )
    assert (
        gateway_main.row_matches_rag_filters(
            row,
            gateway_main.RagSearchFilters(aclGroups=["other-team"]),
            subject_principals,
        )
        is False
    )


def test_rag_search_filter_excludes_stale_and_dangerous_documents_by_default() -> None:
    subject_principals = {"cluster-admins", "user:admin"}
    base_row = {
        "acl_groups": ["cluster-admins", "user:admin"],
        "customer": "KOMSCO",
        "document_id": "user-upload:admin",
        "namespace": "openshift-marketplace",
        "source_type": "user-upload",
        "version": "v0.1.4",
    }

    assert (
        gateway_main.row_matches_rag_filters(
            {**base_row, "labels": {"freshness": "fresh", "safetyClass": "read-only"}},
            gateway_main.RagSearchFilters(),
            subject_principals,
        )
        is True
    )
    assert (
        gateway_main.row_matches_rag_filters(
            {**base_row, "labels": {"freshness": "stale", "safetyClass": "read-only"}},
            gateway_main.RagSearchFilters(),
            subject_principals,
        )
        is False
    )
    assert (
        gateway_main.row_matches_rag_filters(
            {**base_row, "labels": {"freshness": "fresh", "safetyClass": "dangerous"}},
            gateway_main.RagSearchFilters(),
            subject_principals,
        )
        is False
    )
    assert (
        gateway_main.row_matches_rag_filters(
            {**base_row, "labels": {"freshness": "stale", "safetyClass": "read-only"}},
            gateway_main.RagSearchFilters(labels={"freshness": "stale"}),
            subject_principals,
        )
        is True
    )

def test_rag_upload_safety_and_freshness_metadata_are_classified() -> None:
    subject = safe_subject(
        {
            "username": "admin",
            "uid": "uid-admin",
            "groups": ["cluster-admins"],
        }
    )

    stale_read_only = build_rag_upload_document(
        RagDocumentUploadCreate(
            name="ops-runbook.md",
            content="Read-only runbook. First inspect events and logs.",
            labels={"freshness": "stale", "safetyClass": "read-only"},
        ),
        subject,
    )
    dangerous = build_rag_upload_document(
        RagDocumentUploadCreate(
            name="dangerous-runbook.md",
            content="운영자가 승인 없이 oc delete pod bad -n default 를 실행하라고 적은 문서",
            labels={"safetyClass": "read-only"},
        ),
        subject,
    )

    assert stale_read_only["document"]["labels"]["freshness"] == "stale"
    assert stale_read_only["document"]["labels"]["safetyClass"] == "read-only"
    assert dangerous["document"]["labels"]["safetyClass"] == "dangerous"
    assert dangerous["chunks"][0]["labels"]["safetyClass"] == "dangerous"


def test_rag_upload_endpoints_validate_contract_without_configured_backend(monkeypatch) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        return {"username": "admin", "uid": "uid-admin", "groups": ["cluster-admins"]}

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "RAG_BACKEND_URL", "")

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            upload_response = await client.post(
                "/v1/rag/uploads",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "name": "uploaded-runbook.md",
                    "content": "Pod restart RCA uploaded runbook. Check events, previous logs, and restart metrics.",
                    "labels": {"scenario": "pod_restart_rca"},
                },
            )
            list_response = await client.get(
                "/v1/rag/uploads",
                headers={"Authorization": "Bearer test-token"},
            )

        assert upload_response.status_code == 200
        upload_payload = upload_response.json()
        assert upload_payload["kind"] == "RagUploadIngestionResult"
        assert upload_payload["spec"]["status"] == "not_configured"
        assert upload_payload["spec"]["document"]["sourceType"] == "user-upload"
        assert upload_payload["spec"]["chunks"]
        assert upload_payload["spec"]["safety"]["rawContentReturned"] is False

        assert list_response.status_code == 200
        list_payload = list_response.json()
        assert list_payload["kind"] == "RagUploadedDocumentList"
        assert list_payload["spec"]["status"] == "not_configured"
        assert list_payload["spec"]["documents"] == []

    asyncio.run(run())


def test_validate_image_attachments_accepts_supported_base64_image() -> None:
    attachment = ImageAttachment(
        data="iVBORw0KGgo=",
        id="image-1",
        mimeType="image/png",
        name="cluster.png",
        size=8,
    )

    validate_image_attachments([attachment])
    context = build_attachment_context([attachment])

    assert "cluster.png" in context
    assert "image/png" in context


def test_build_attachment_context_without_vision_uses_metadata_only_language() -> None:
    attachment = ImageAttachment(
        data="iVBORw0KGgo=",
        id="image-1",
        mimeType="image/png",
        name="catalog-screen.png",
        size=8,
    )

    context = build_attachment_context([attachment])

    assert "비활성화" in context
    assert "첨부 파일 메타데이터" in context
    assert "사용자 설명" in context
    assert "도구 조회 결과" in context
    assert "이미지 원본 판독은 수행하지 않았습니다" not in context


def test_build_ols_payload_does_not_forward_image_attachments_by_default() -> None:
    attachment = ImageAttachment(
        data="iVBORw0KGgo=",
        id="image-1",
        mimeType="image/png",
        name="cluster.png",
        size=8,
    )

    payload = build_ols_payload("이미지 분석해줘", "conversation-1", [attachment])

    assert payload == {
        "query": "이미지 분석해줘",
        "conversation_id": "conversation-1",
    }


def test_build_ols_payload_forwards_image_attachments_when_enabled() -> None:
    attachment = ImageAttachment(
        data="iVBORw0KGgo=",
        id="image-1",
        mimeType="image/png",
        name="cluster.png",
        size=8,
    )

    payload = build_ols_payload(
        "이미지 분석해줘",
        "conversation-1",
        [attachment],
        forward_image_attachments=True,
    )

    assert payload == {
        "query": "이미지 분석해줘",
        "conversation_id": "conversation-1",
        "attachments": [
            {
                "attachment_type": "image",
                "content_type": "image/png",
                "content": "iVBORw0KGgo=",
            }
        ],
    }


def test_build_ols_payload_includes_schema_gateway_context_without_secrets() -> None:
    plan = build_runtime_tool_plan("default 네임스페이스 pod가 왜 재시작됐어?")
    rca_context = build_rca_context(
        message="default 네임스페이스 pod가 왜 재시작됐어?",
        tool_plan=plan,
        evidence_refs=[],
        run_id="run-ols-context",
        incident_id="inc-ols-context",
    )
    safety_contract = build_runtime_safety_contract(
        mutations_enabled=False,
        unrestricted_commands_enabled=False,
        diagnostics_enabled=False,
        record_store_enabled=False,
        latest_runtime_tool_plan=plan,
        latest_rca_context=rca_context,
    )
    gateway_context = build_ols_gateway_context(
        tool_plan=plan,
        rca_context=rca_context,
        safety_contract=safety_contract,
        policy={"decision": "allow_read_only_evidence", "token": "secret-token-value-1234567890"},
        gateway_evidence="safe line\nAuthorization: Bearer secret-token-value-1234567890",
    )

    payload = build_ols_payload(
        "질문",
        "conversation-1",
        [],
        gateway_context=gateway_context,
    )
    rendered = json.dumps(payload, ensure_ascii=False)

    assert payload["gateway_context"]["kind"] == "GatewayContext"
    assert payload["gateway_context"]["toolPlan"]["kind"] == "ToolPlan"
    assert payload["gateway_context"]["rcaContext"]["kind"] == "RcaContext"
    assert payload["gateway_context"]["safetyContract"]["mode"] == "read_only"
    assert payload["gateway_context"]["missingEvidence"]
    assert payload["gateway_context"]["metadata"]["digest"].startswith("sha256:")
    assert payload["gateway_context"]["metadata"]["rcaContextDigest"] == rca_context["metadata"]["digest"]
    assert "secret-token-value" not in rendered
    assert "Bearer secret" not in rendered


def test_validate_image_attachments_rejects_unsupported_type() -> None:
    attachment = ImageAttachment(
        data="aGVsbG8=",
        id="image-1",
        mimeType="text/plain",
        name="note.txt",
        size=5,
    )

    with pytest.raises(HTTPException):
        validate_image_attachments([attachment])


def test_build_ols_query_keeps_page_context_thin_and_requires_live_tools() -> None:
    query = build_ols_query(
        ChatRequest(
            message="최근 OpenShift 경고와 우선 확인할 항목을 정리해줘.",
            pageContext={
                "href": "http://localhost:9000/k8s/cluster/projects",
                "pathname": "/k8s/cluster/projects",
                "title": "개요 · 클러스터 · OKD",
            },
        )
    )

    assert "최근 OpenShift 경고" in query
    assert "스크린샷이나 이미지가 전달된 것이 아닙니다" in query
    assert '답변에 "이미지를 직접 판독할 수 없다"' in query
    assert "경로 기준으로는 Catalog 페이지로 보입니다" in query
    assert "OpenShift MCP 도구를 먼저 사용하세요" in query
    assert "도구 결과에 없는 alert" in query
    assert "OpenShift 경고 분석 프로토콜" in query
    assert "resources_get" in query
    assert '"상세 확인됨"' in query
    assert '"Alert 근거 확인"' in query
    assert '"추가 확인 필요"' in query
    assert "상세 조회를 실제로 호출하지 않은 리소스" in query
    assert "alert 이름이나 summary만으로 원인을 단정하지 마세요" in query
    assert "status.containerStatuses와 events" in query
    assert "정확한 Pod 이름 또는 Pod 목록 evidence에 있는 Pod" in query
    assert "Gateway 선조회 Pod 요약만으로 원인/조치 계획을 끝내지 말고" in query
    assert "Pod 상세의 owner가 ReplicaSet이면 해당 ReplicaSet 상세" in query
    assert "Pod 상태/재시작 분석 프로토콜" in query
    assert "CronJob/Activity 분석 프로토콜" in query
    assert "설정상 의도된 <N>분 주기" in query
    assert "lifecycle/retention 관련 env" in query
    assert "로그나 소스 근거 없이 생성 후" in query
    assert "`restartCount`만 보고 현재 `CrashLoopBackOff`" in query
    assert "`restartCount`는 Pod 단위가 아니라 container 단위" in query
    assert "`restartCount`는 누적 카운터" in query
    assert "containerStatuses[*]" in query
    assert "`Running` 및 `Ready=True`" in query
    assert "과거 실패 Pod 이력, 현재 Operator 상태는 정상" in query
    assert "CatalogSource" in query
    assert "--previous" in query
    assert "Pod 조치/복구 계획 프로토콜" in query
    assert "`Pod -> ReplicaSet -> Deployment`" in query
    assert "placeholder를 남기지 마세요" in query
    assert "selector/label 기반 검증 명령도 placeholder로 남기지 마세요" in query
    assert "Pod spec의 command/args를 조회하지 못했다면" in query
    assert "ReplicaSet 직접 수정은 권장하지 마세요" in query
    assert "컨테이너 실행 명령/애플리케이션 프로세스가 즉시 종료됨" in query
    assert "단순 `oc delete pod` 또는 `oc rollout restart`" in query
    assert "Deployment rollout/Pod 교체 판정 프로토콜" in query
    assert "`replicas=2`, `Ready 2/2`, Pod 2개 존재" in query
    assert "아직 실행 전 또는 교체 증거 없음" in query
    assert "서비스 복구" in query
    assert "테스트 리소스 정리" in query
    assert "Extension APIs" in query
    assert "Admission plugins" in query
    assert "oc logs를 우선 명령으로 제시하지 말고" in query
    assert "ClusterVersion conditions" in query
    assert "apiVersion: config.openshift.io/v1" in query
    assert "kind: ClusterVersion" in query
    assert "alert 결과만으로 ConfigMap 또는 Secret 이름을 만들어 조회하지 마세요" in query
    assert "권한상 직접 확인이 제한될 수 있음" in query
    assert "조회 실패/권한 제한" in query
    assert "즉시 수행" in query
    assert "삼중 백틱" in query
    assert "catalog Pod" in query
    assert "gateway.networking.k8s.io" in query
    assert "GatewayClass 문서" in query
    assert "대상 미지정" in query
    assert "oc get pods -A" in query
    assert "기본 제안하지 마세요" in query
    assert "oc delete pod" in query
    assert "기본 재시작 방법으로 제시하지 마세요" in query
    assert "title" not in query
    assert "OKD" not in query


def test_build_ols_query_treats_console_path_as_context_not_image() -> None:
    query = build_ols_query(
        ChatRequest(
            message="현재 보고 있는 콘솔 화면이 무엇인지 설명해줘.",
            pageContext={
                "href": "http://localhost:9000/catalog/ns/team-a",
                "pathname": "/catalog/ns/team-a",
                "namespace": "team-a",
            },
        )
    )

    assert "첨부 이미지 없음" in query
    assert "/catalog/ns/team-a" in query
    assert '"namespace": "team-a"' in query
    assert '"route": "catalog"' in query
    assert '"resourceKind": "Catalog"' in query
    assert "현재 콘솔 페이지의 스크린샷이나 이미지가 전달된 것이 아닙니다" in query
    assert "화면의 시각적 내용 자체라고 단정하지 말고" in query


def test_build_ols_query_includes_security_guardrail_and_redacts_user_secrets() -> None:
    policy = classify_request_policy("deployment restart 해줘 token=my-secret-token-value")
    query = build_ols_query(
        ChatRequest(message="deployment restart 해줘 token=my-secret-token-value"),
        policy=policy,
        subject=safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["a"]}),
    )

    assert "Gateway Phase 5 Action Execution Envelope" in query
    assert "action_proposal_only" in query
    assert "승인 없이 즉시 mutation을 실행했다고 말하지 마세요" in query
    assert "user@example.com" in query
    assert "my-secret-token-value" not in query
    assert "[REDACTED]" in query


def test_build_ols_query_includes_gateway_evidence() -> None:
    query = build_ols_query(
        ChatRequest(message="현재 클러스터의 Pod 상태를 분석해줘"),
        gateway_evidence="Top container restart counts:\nopenshift-lightspeed exporter restartCount=44",
    )

    assert "[Gateway 선조회 증거]" in query
    assert "openshift-lightspeed exporter restartCount=44" in query
    assert "## RCA 보고서" in query
    assert "### 우선 판단" in query
    assert "### 수집 근거" in query
    assert "### 확인 불가" in query


def test_action_proposal_fallback_is_non_empty_and_requests_target() -> None:
    policy = classify_request_policy("Pod 하나 재시작해줘")
    fallback = build_action_proposal_fallback(ChatRequest(message="Pod 하나 재시작해줘"), policy)

    assert "Phase 5 Action Execution" in fallback
    assert "Approval API와 Action Executor" in fallback
    assert "namespace" in fallback
    assert "Pod 또는 관리 객체" in fallback


def test_empty_answer_fallback_includes_question_and_tool_summary() -> None:
    policy = classify_request_policy("ClusterOperator authentication 상태를 확인해줘")
    fallback = build_empty_answer_fallback(
        ChatRequest(message="ClusterOperator authentication 상태를 확인해줘"),
        policy,
        [
            {
                "name": "resources_list",
                "status": "success",
                "summary": "ClusterOperator authentication 조회 완료",
            }
        ],
    )

    assert "## RCA 보고서" in fallback
    assert "### 우선 판단" in fallback
    assert "### 수집 근거" in fallback
    assert "### 원인 후보" in fallback
    assert "### 확인 불가" in fallback
    assert "### 다음 확인 명령" in fallback
    assert "authentication" in fallback
    assert "resources_list" in fallback
    assert "조회 완료" in fallback


def test_empty_answer_fallback_includes_gateway_evidence_when_ols_fails() -> None:
    policy = classify_request_policy("Failed Pod를 현재 장애로 봐도 되는지 판단해줘")
    fallback = build_empty_answer_fallback(
        ChatRequest(message="Failed Pod를 현재 장애로 봐도 되는지 판단해줘"),
        policy,
        [
            {
                "name": "lightspeed_stream",
                "status": "error",
                "summary": "OpenShift Lightspeed stream failed",
            }
        ],
        (
            "Pod phase/startTime indicate the current Pod object state.\n"
            "ClusterOperator status evidence from Kubernetes API."
        ),
    )

    assert "lightspeed_stream" in fallback
    assert "startTime" in fallback
    assert "ClusterOperator" in fallback
    assert "## RCA 보고서" in fallback
    assert "### 원인 후보" in fallback
    assert "### 확인 불가" in fallback
    assert "Gateway가 수집한 증거 기준" in fallback
    assert "모델의 최종 요약" not in fallback
    assert "Live 조회" not in fallback


def test_chat_stream_marks_lightspeed_context_digest_on_gateway_fallback(monkeypatch) -> None:
    gateway_main.OLS_STREAM_STATUS = {
        "streamProbe": "not_started",
        "lastStatus": "not_started",
        "lastContextDigest": "",
        "lastStartedAt": "",
        "lastCompletedAt": "",
        "lastError": "",
        "fallbackActive": False,
    }

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    captured_context: dict[str, object] = {}

    async def fail_call_ols_stream(
        _user_auth_header: str,
        _query: str,
        _conversation_id: str | None,
        _attachments: list[ImageAttachment],
        gateway_context: Mapping[str, object] | None = None,
    ):
        assert gateway_context is not None
        assert gateway_context["kind"] == "GatewayContext"
        metadata = gateway_context["metadata"]
        assert isinstance(metadata, Mapping)
        context_digest = str(metadata.get("digest") or "")
        assert context_digest.startswith("sha256:")
        captured_context["digest"] = context_digest
        if False:
            yield {}
        raise RuntimeError("synthetic OLS outage")

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={"message": "최근 OpenShift 경고와 우선 확인할 항목을 정리해줘."},
            )
            status_response = await client.get(
                "/v1/aiops/status",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        assert status_response.status_code == 200
        events = parse_sse_events(response.text)
        context_digest = str(captured_context["digest"])
        lightspeed_run_events = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "run_status"
            and event.get("stage") == "lightspeed"
        ]
        fallback_error_events = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "lightspeed_stream"
        ]
        fallback_text_events = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "text"
            and event.get("fallbackAnswer") is True
        ]

        assert lightspeed_run_events[-1]["gatewayContextDigest"] == context_digest
        assert fallback_error_events[-1]["gatewayContextDigest"] == context_digest
        assert fallback_error_events[-1]["fallbackAnswer"] is True
        assert fallback_text_events[-1]["gatewayContextDigest"] == context_digest
        assert fallback_text_events[-1]["source"] == "gateway_fallback"
        assert gateway_main.OLS_STREAM_STATUS["streamProbe"] == "failed"
        assert gateway_main.OLS_STREAM_STATUS["fallbackActive"] is True
        assert gateway_main.OLS_STREAM_STATUS["lastContextDigest"] == context_digest

        lightspeed_status = status_response.json()["spec"]["safetyContract"]["lightspeedStatus"]
        assert lightspeed_status["streamProbe"] == "failed"
        assert lightspeed_status["fallbackActive"] is True
        assert lightspeed_status["lastContextDigest"] == context_digest

    asyncio.run(run())


def test_chat_stream_redacts_secret_bearing_ols_errors(monkeypatch) -> None:
    gateway_main.OLS_STREAM_STATUS = {
        "streamProbe": "not_started",
        "lastStatus": "not_started",
        "lastContextDigest": "",
        "lastStartedAt": "",
        "lastCompletedAt": "",
        "lastError": "",
        "fallbackActive": False,
    }

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
        if False:
            yield {}
        raise HTTPException(
            status_code=502,
            detail="OLS upstream failed Authorization: Bearer abcdefghijklmnopqrstuvwxyz token=supersecret",
        )

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={"message": "최근 OpenShift 경고와 우선 확인할 항목을 정리해줘."},
            )
            status_response = await client.get(
                "/v1/aiops/status",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        assert status_response.status_code == 200
        assert "supersecret" not in response.text
        assert "abcdefghijklmnopqrstuvwxyz" not in response.text
        assert "Bearer abc" not in response.text
        assert "supersecret" not in json.dumps(status_response.json(), ensure_ascii=False)
        assert "[REDACTED]" in response.text
        lightspeed_status = status_response.json()["spec"]["safetyContract"]["lightspeedStatus"]
        assert lightspeed_status["fallbackActive"] is True
        assert "supersecret" not in lightspeed_status["lastError"]

    asyncio.run(run())


def test_chat_stream_marks_empty_ols_success_as_fallback_status(monkeypatch) -> None:
    gateway_main.OLS_STREAM_STATUS = {
        "streamProbe": "not_started",
        "lastStatus": "not_started",
        "lastContextDigest": "",
        "lastStartedAt": "",
        "lastCompletedAt": "",
        "lastError": "",
        "fallbackActive": False,
    }

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def empty_call_ols_stream(*_args, **_kwargs):
        yield {"type": "end", "conversationId": "conversation-empty"}

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "call_ols_stream", empty_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={"message": "최근 OpenShift 경고와 우선 확인할 항목을 정리해줘."},
            )
            status_response = await client.get(
                "/v1/aiops/status",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        assert status_response.status_code == 200
        events = parse_sse_events(response.text)
        fallback_text_events = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "text"
            and event.get("fallbackAnswer") is True
        ]
        assert fallback_text_events
        lightspeed_status = status_response.json()["spec"]["safetyContract"]["lightspeedStatus"]
        assert lightspeed_status["streamProbe"] == "failed"
        assert lightspeed_status["fallbackActive"] is True
        assert lightspeed_status["lastContextDigest"] == fallback_text_events[-1]["gatewayContextDigest"]

    asyncio.run(run())


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


def test_empty_answer_fallback_summarizes_pod_evidence_without_truncating_raw_table() -> None:
    policy = classify_request_policy(
        "team-a 네임스페이스의 sample-crashy 파드가 왜 장애인지 분석하고 조치 계획을 제안해줘"
    )
    gateway_evidence = "\n".join(
        [
            "Gateway-collected Pod status evidence from Kubernetes API `/api/v1/pods`.",
            "x" * 2500,
            "Currently non-healthy or waiting container evidence:",
            "| Namespace | Pod | Container | Current State | Pod Start | Ready | Restarts | Last State/Exit | Owner |",
            "| :--- | :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- |",
            "| team-a | `sample-crashy-6fd7d7cfd7-r4nd0` | `app` | Running (CrashLoopBackOff) / waiting:CrashLoopBackOff | 2026-06-22T00:54:32Z | 0/1 | 9 | Error/1 | ReplicaSet/sample-crashy-6fd7d7cfd7 |",
            "Spec evidence for currently non-healthy or waiting containers:",
            "Use command/args/image/labels below as concrete evidence for root-cause and remediation planning.",
            "| Namespace | Pod | Container | Image | Command | Args | Pod Labels | Owner Chain |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
            "| team-a | `sample-crashy-6fd7d7cfd7-r4nd0` | `app` | registry.example.com/team-a/sample-crashy:v2 | [\"python\", \"-c\", \"raise SystemExit('boom')\"] | - | app=sample-crashy, aiops.komsco/scenario=sample, pod-template-hash=6fd7d7cfd7 | ReplicaSet/sample-crashy-6fd7d7cfd7 -> Deployment/sample-crashy |",
        ]
    )

    fallback = build_empty_answer_fallback(
        ChatRequest(message="team-a 네임스페이스의 sample-crashy 파드가 왜 장애인지 분석하고 조치 계획을 제안해줘"),
        policy,
        [],
        gateway_evidence,
    )

    assert "Gateway가 수집한 Kubernetes 증거 기준" in fallback
    assert "모델의 최종 요약" not in fallback
    assert "Live 조회" not in fallback
    assert "... truncated ..." not in fallback
    assert "Gateway 사전 수집 증거" not in fallback
    assert "sample-crashy-6fd7d7cfd7-r4nd0" in fallback
    assert "raise SystemExit('boom')" in fallback
    assert "즉시 종료" in fallback
    assert "`deployment/sample-crashy`" in fallback
    assert "oc rollout status deployment/sample-crashy -n team-a" in fallback
    assert "oc get pod -n team-a -l app=sample-crashy" in fallback
    assert "<app-label>" not in fallback


def test_pod_list_request_fallback_returns_list_instead_of_single_pod_analysis() -> None:
    gateway_evidence = "\n".join(
        [
            "Gateway-collected Pod status evidence from Kubernetes API `/api/v1/pods`.",
            "Top container restart counts:",
            "| Namespace | Pod | Container | Current State | Pod Start | Ready | Restarts | Last State/Exit | Last Finished | Owner |",
            "| :--- | :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- | :--- |",
            "| team-a | `sample-crashy-6fd7d7cfd7-r4nd0` | `app` | Running (CrashLoopBackOff) / waiting:CrashLoopBackOff | 2026-06-22T00:54:32Z | 0/1 | 158 | Error/1 | 2026-06-22T13:58:35Z | ReplicaSet/sample-crashy-6fd7d7cfd7 |",
            "Current Pod list evidence:",
            "Namespace filter: `team-a`",
            "Rows shown: 2 / 2",
            "| Namespace | Pod | Container | Current State | Pod Start | Ready | Restarts | Last State/Exit | Owner |",
            "| :--- | :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- |",
            "| team-a | `sample-crashy-6fd7d7cfd7-r4nd0` | `app` | Running (CrashLoopBackOff) / waiting:CrashLoopBackOff | 2026-06-22T00:54:32Z | 0/1 | 158 | Error/1 | ReplicaSet/sample-crashy-6fd7d7cfd7 |",
            "| team-a | `healthy-api-7ccbbd8c86-fs28q` | `app` | Running / running since 2026-06-22T00:54:32Z | 2026-06-22T00:54:32Z | 1/1 | 0 | - | ReplicaSet/healthy-api-7ccbbd8c86 |",
        ]
    )

    fallback = build_empty_answer_fallback(
        ChatRequest(message="파드리스트 조회해줘", pageContext={"namespace": "team-a"}),
        classify_request_policy("파드리스트 조회해줘"),
        [],
        gateway_evidence,
    )

    assert "### Pod 목록" in fallback
    assert "`sample-crashy-6fd7d7cfd7-r4nd0`" in fallback
    assert "`healthy-api-7ccbbd8c86-fs28q`" in fallback
    assert "oc get pods -n team-a" in fallback
    assert "### 조치 계획" not in fallback
    assert "대상 Pod를 우선 분석" not in fallback
    assert "- 대상:" not in fallback


def test_parse_natural_action_intent_scales_named_deployment() -> None:
    intent = parse_natural_action_intent(
        ChatRequest(message="komsco-ai-dev 네임스페이스의 aiops-two-pod-exec 파드 3개로 올려줘")
    )

    assert intent
    assert intent["toolName"] == "set_replicas_within_bounds"
    assert intent["namespace"] == "komsco-ai-dev"
    assert intent["targetName"] == "aiops-two-pod-exec"
    assert intent["parameters"]["replicas"] == 3


def test_page_context_aiops_execution_mode_defaults_read_only() -> None:
    assert page_context_aiops_execution_mode(ChatRequest(message="재시작해줘")) == "read-only"


def test_page_context_aiops_execution_mode_accepts_execute() -> None:
    assert (
        page_context_aiops_execution_mode(
            ChatRequest(
                message="재시작해줘",
                pageContext={"aiopsExecutionMode": "execute"},
            )
        )
        == "execute"
    )


@pytest.mark.parametrize(
    ("message", "expected_namespace", "expected_target", "expected_replicas"),
    [
        ("team-a 네임스페이스의 web-api 파드 5개로 올려줘", "team-a", "web-api", 5),
        ("6:cis 파드 3개로 올려줘", "6", "cis", 3),
        ("cis파드 3개로 올려줘", "", "cis", 3),
        ("komsco-ai-dev/worker 2 replicas로 설정", "komsco-ai-dev", "worker", 2),
        ("batch-worker를 1개로 줄여줘", "prod-a", "batch-worker", 1),
        ("deployment/payment-api 7개로 scale", "payments", "payment-api", 7),
        ("`edge-gateway` pods 4 replicas로 설정", "edge", "edge-gateway", 4),
    ],
)
def test_parse_natural_action_intent_accepts_scale_variants(
    message: str,
    expected_namespace: str,
    expected_target: str,
    expected_replicas: int,
) -> None:
    intent = parse_natural_action_intent(
        ChatRequest(
            message=message,
            pageContext={"namespace": expected_namespace},
        )
    )

    assert intent
    assert intent["toolName"] == "set_replicas_within_bounds"
    assert intent["namespace"] == expected_namespace
    assert intent["targetName"] == expected_target
    assert intent["parameters"]["replicas"] == expected_replicas


def test_parse_natural_action_intent_uses_deployment_page_context_for_scale() -> None:
    intent = parse_natural_action_intent(
        ChatRequest(
            message="3개로 올려줘",
            pageContext={
                "pathname": "/k8s/ns/team-b/deployments/report-api",
            },
        )
    )

    assert intent
    assert intent["toolName"] == "set_replicas_within_bounds"
    assert intent["namespace"] == "team-b"
    assert intent["targetName"] == "report-api"
    assert intent["parameters"]["replicas"] == 3


def test_parse_natural_action_intent_uses_deployment_page_context_for_restart() -> None:
    intent = parse_natural_action_intent(
        ChatRequest(
            message="재시작해줘",
            pageContext={
                "pathname": "/k8s/ns/team-a/deployments/web-api",
            },
        )
    )

    assert intent
    assert intent["toolName"] == "rollout_restart_deployment"
    assert intent["namespace"] == "team-a"
    assert intent["targetName"] == "web-api"


@pytest.mark.parametrize(
    ("message", "expected_namespace", "expected_target"),
    [
        ("team-c 네임스페이스의 api-gateway 재시작해줘", "team-c", "api-gateway"),
        ("deployment/worker-a rollout restart", "workers", "worker-a"),
        ("`checkout-api` 리스타트", "shop", "checkout-api"),
    ],
)
def test_parse_natural_action_intent_accepts_restart_variants(
    message: str,
    expected_namespace: str,
    expected_target: str,
) -> None:
    intent = parse_natural_action_intent(
        ChatRequest(
            message=message,
            pageContext={"namespace": expected_namespace},
        )
    )

    assert intent
    assert intent["toolName"] == "rollout_restart_deployment"
    assert intent["namespace"] == expected_namespace
    assert intent["targetName"] == expected_target


@pytest.mark.parametrize(
    ("message", "expected_namespace", "expected_target", "expected_tool", "expected_kind", "expected_parameters"),
    [
        (
            "team-a 네임스페이스의 deployment/web-api revision 2로 롤백해줘",
            "team-a",
            "web-api",
            "rollback_deployment_to_revision",
            "Deployment",
            {"revision": 2},
        ),
        (
            "team-a 네임스페이스의 deployment/web-api 롤백해줘",
            "team-a",
            "web-api",
            "rollback_deployment_to_revision",
            "Deployment",
            {"revision": None},
        ),
        (
            "team-a 네임스페이스의 pod/web-api-abc 교체해줘",
            "team-a",
            "web-api-abc",
            "evict_one_unhealthy_controller_owned_pod",
            "Pod",
            {"reason": "natural_language_unhealthy_pod_eviction"},
        ),
        (
            "team-a 네임스페이스의 hpa/web-hpa 최소 2 최대 8로 변경해줘",
            "team-a",
            "web-hpa",
            "set_hpa_bounds",
            "HorizontalPodAutoscaler",
            {"minReplicas": 2, "maxReplicas": 8, "allowMaxIncrease": False},
        ),
    ],
)
def test_parse_natural_action_intent_accepts_agentic_action_variants(
    message: str,
    expected_namespace: str,
    expected_target: str,
    expected_tool: str,
    expected_kind: str,
    expected_parameters: dict[str, object],
) -> None:
    intent = parse_natural_action_intent(ChatRequest(message=message))

    assert intent
    assert intent["toolName"] == expected_tool
    assert intent["kind"] == expected_kind
    assert intent["namespace"] == expected_namespace
    assert intent["targetName"] == expected_target
    for key, value in expected_parameters.items():
        assert intent["parameters"][key] == value


def test_create_natural_action_plan_uses_intent_target_kind(monkeypatch) -> None:
    observed_paths: list[str] = []

    async def fake_fetch_ocp_json(_client, path: str, _authorization: str, **_kwargs):
        observed_paths.append(path)
        return {
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "metadata": {
                "namespace": "team-a",
                "name": "web-hpa",
                "uid": "hpa-uid-a",
            },
            "spec": {"minReplicas": 1, "maxReplicas": 5},
        }

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.example.test:6443")
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fake_fetch_ocp_json)

    result = asyncio.run(
        gateway_main.create_natural_action_plan(
            ChatRequest(message="team-a 네임스페이스의 hpa/web-hpa 최소 2 최대 5로 변경해줘"),
            "Bearer token",
            safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]}),
            incident_id="inc-hpa",
            run_id="run-hpa",
        )
    )

    assert result
    assert result["status"] == "planned"
    assert result["target"]["kind"] == "HorizontalPodAutoscaler"
    assert observed_paths == ["/apis/autoscaling/v2/namespaces/team-a/horizontalpodautoscalers/web-hpa"]


def test_create_natural_action_plan_resolves_namespace_from_cluster_deployments(monkeypatch) -> None:
    observed_paths: list[str] = []

    async def fake_fetch_ocp_json(_client, path: str, _authorization: str, **_kwargs):
        observed_paths.append(path)
        if path == "/apis/apps/v1/deployments":
            return {
                "items": [
                    {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "metadata": {
                            "name": "cis",
                            "namespace": "cis",
                            "uid": "deployment-cis-uid",
                        },
                        "spec": {"replicas": 1},
                    }
                ]
            }
        raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.example.test:6443")
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fake_fetch_ocp_json)

    result = asyncio.run(
        gateway_main.create_natural_action_plan(
            ChatRequest(message="cis파드 3개로 올려줘"),
            "Bearer token",
            safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]}),
            incident_id="inc-cis-scale",
            run_id="run-cis-scale",
        )
    )

    assert result
    assert result["status"] == "planned"
    assert result["target"]["namespace"] == "cis"
    assert result["target"]["name"] == "cis"
    assert result["parameters"]["replicas"] == 3
    assert observed_paths == ["/apis/apps/v1/deployments"]


def test_create_natural_action_plan_reports_ambiguous_cluster_matches(monkeypatch) -> None:
    async def fake_fetch_ocp_json(_client, path: str, _authorization: str, **_kwargs):
        if path == "/apis/apps/v1/deployments":
            return {
                "items": [
                    {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "metadata": {"name": "web", "namespace": "team-a", "uid": "deployment-a"},
                    },
                    {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "metadata": {"name": "web", "namespace": "team-b", "uid": "deployment-b"},
                    },
                ]
            }
        raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.example.test:6443")
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fake_fetch_ocp_json)

    result = asyncio.run(
        gateway_main.create_natural_action_plan(
            ChatRequest(message="web 파드 2개로 올려줘"),
            "Bearer token",
            safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]}),
            incident_id="inc-web-scale",
            run_id="run-web-scale",
        )
    )

    assert result
    assert result["status"] == "ambiguous"
    assert result["candidates"] == [
        {"kind": "Deployment", "name": "web", "namespace": "team-a"},
        {"kind": "Deployment", "name": "web", "namespace": "team-b"},
    ]


@pytest.mark.parametrize(
    (
        "scenario_id",
        "message",
        "page_context",
        "recent_messages",
        "expected_tool",
        "expected_kind",
        "expected_namespace",
        "expected_target",
    ),
    [
        (
            "S01-explicit-scale",
            "team-a 네임스페이스의 web-api 파드 4개로 올려줘",
            {},
            [],
            "set_replicas_within_bounds",
            "Deployment",
            "team-a",
            "web-api",
        ),
        (
            "S02-contextual-followup-scale",
            "진행해",
            {"aiopsExecutionMode": "unrestricted"},
            [{"role": "user", "content": "team-a 네임스페이스의 web-api 파드 4개로 올려줘"}],
            "set_replicas_within_bounds",
            "Deployment",
            "team-a",
            "web-api",
        ),
        (
            "S03-page-context-rollout-restart",
            "재시작해줘",
            {"pathname": "/k8s/ns/team-a/deployments/web-api"},
            [],
            "rollout_restart_deployment",
            "Deployment",
            "team-a",
            "web-api",
        ),
        (
            "S04-rollback-revision",
            "team-a 네임스페이스의 deployment/web-api revision 2로 롤백해줘",
            {},
            [],
            "rollback_deployment_to_revision",
            "Deployment",
            "team-a",
            "web-api",
        ),
        (
            "S05-unhealthy-pod-eviction",
            "team-a 네임스페이스의 pod/web-api-abc 교체해줘",
            {},
            [],
            "evict_one_unhealthy_controller_owned_pod",
            "Pod",
            "team-a",
            "web-api-abc",
        ),
        (
            "S06-hpa-bounds",
            "team-a 네임스페이스의 hpa/web-hpa 최소 2 최대 8로 변경해줘",
            {},
            [],
            "set_hpa_bounds",
            "HorizontalPodAutoscaler",
            "team-a",
            "web-hpa",
        ),
    ],
)
def test_agentic_action_scenario_matrix_parses_typed_actions(
    scenario_id: str,
    message: str,
    page_context: dict[str, object],
    recent_messages: list[dict[str, str]],
    expected_tool: str,
    expected_kind: str,
    expected_namespace: str,
    expected_target: str,
) -> None:
    request = ChatRequest(
        message=message,
        pageContext=page_context,
        recentMessages=recent_messages,
    )
    contextual = recent_natural_action_request(request) if is_followup_execution_request(message) else None
    intent = parse_natural_action_intent(contextual or request)

    assert intent, scenario_id
    assert intent["toolName"] == expected_tool
    assert intent["kind"] == expected_kind
    assert intent["namespace"] == expected_namespace
    assert intent["targetName"] == expected_target


def test_agentic_safety_and_evidence_scenario_matrix_covers_non_mutating_paths() -> None:
    ambiguous = ChatRequest(
        message="파드 하나 재시작해줘",
        pageContext={"aiopsExecutionMode": "unrestricted"},
    )
    pod_list_policy = classify_request_policy("team-a 네임스페이스 파드 리스트 조회해줘")
    crashloop_policy = classify_request_policy("CrashLoopBackOff 파드 원인 분석해줘")
    diagnostic_request = DiagnosticRequestCreate(
        collector="node_os_readonly_triage",
        targetNode=DiagnosticTargetNode(name="worker-a", uid="node-uid-a"),
        timeRange=DiagnosticTimeRange(since="2026-06-22T00:00:00Z", until="2026-06-22T00:05:00Z"),
        limits=DiagnosticLimits(),
        evidencePolicy=DiagnosticEvidencePolicy(
            classification="restricted",
            rawStorageAllowed=False,
            redactionPolicyDigest="sha256:test-redaction-policy",
        ),
    )
    diagnostic_candidate = build_diagnostic_request_candidate(
        diagnostic_request,
        safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["ops"]}),
    )

    assert parse_natural_action_intent(ambiguous) is None
    assert "대상 리소스 이름이 명확하지 않습니다" in unresolved_natural_action_response(ambiguous)
    assert is_pod_list_request("team-a 네임스페이스 파드 리스트 조회해줘")
    assert pod_list_policy["decision"] == "allow_read_only_evidence"
    assert should_collect_pod_status_evidence("CrashLoopBackOff 파드 원인 분석해줘")
    assert crashloop_policy["decision"] == "allow_read_only_evidence"
    assert diagnostic_candidate["collector"] == "node_os_readonly_triage"
    assert diagnostic_candidate["targetNode"]["name"] == "worker-a"
    assert diagnostic_request_digest(diagnostic_candidate).startswith("sha256:")


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
        plan_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "natural_action_plan"
        ]
        assert plan_results
        assert plan_results[0]["status"] == "success"
        assert "plan-execute-mode" in response.text
        assert "natural_action_execute" not in response.text
        assert "lightspeed_stream" not in response.text
        context = assert_post_answer_rca_before_done(events)
        assert context["confidence"]["level"] == "insufficient_evidence"

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


def test_chat_stream_read_only_action_request_emits_post_answer_rca_context(monkeypatch) -> None:
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
        raise AssertionError("OLS must not be called for read-only action requests")

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
        assert rca_events
        assert rca_events[-1]["context"]["metadata"]["phase"] == "post_answer"
        assert rca_events[-1]["context"]["safety"]["mode"] == "read_only"
        assert rca_events[-1]["context"]["evidence"]["summary"]["collectedCount"] == 0
        assert "읽기 전용 모드" in response.text
        assert "lightspeed_stream" not in response.text

    asyncio.run(run())


def test_cronjob_activity_evidence_trigger_for_15_minute_activity() -> None:
    assert should_collect_cronjob_activity_evidence("여기 15분 단위로 이러는데 맞아?")
    assert should_collect_cronjob_activity_evidence("notebook-cleaner CronJob 이 정상인지 확인해줘")
    assert not should_collect_cronjob_activity_evidence("현재 노드 상태 요약해줘")


def test_build_cronjob_activity_evidence_includes_schedule_env_and_recent_jobs() -> None:
    evidence = build_cronjob_activity_evidence(
        {
            "items": [
                {
                    "metadata": {"namespace": "tools-dev", "name": "notebook-cleaner"},
                    "spec": {
                        "schedule": "*/15 * * * *",
                        "concurrencyPolicy": "Forbid",
                        "successfulJobsHistoryLimit": 2,
                        "failedJobsHistoryLimit": 3,
                        "jobTemplate": {
                            "spec": {
                                "template": {
                                    "spec": {
                                        "containers": [
                                            {
                                                "image": (
                                                    "ghcr.io/jungyuoo/"
                                                    "ocpops-playbookstudio-sandbox:dev"
                                                ),
                                                "env": [
                                                    {
                                                        "name": (
                                                            "NOTEBOOK_HIBERNATE_AFTER_SECONDS"
                                                        ),
                                                        "value": "1800",
                                                    },
                                                    {
                                                        "name": "NOTEBOOK_RETENTION_DELETE_AFTER_SECONDS",
                                                        "value": "1209600",
                                                    },
                                                ],
                                            }
                                        ]
                                    }
                                }
                            }
                        },
                    },
                }
            ]
        },
        {
            "items": [
                {
                    "metadata": {
                        "namespace": "tools-dev",
                        "name": "notebook-cleaner-29147292",
                        "creationTimestamp": "2026-06-21T03:00:00Z",
                        "ownerReferences": [{"kind": "CronJob", "name": "notebook-cleaner"}],
                    },
                    "status": {
                        "startTime": "2026-06-21T03:00:01Z",
                        "completionTime": "2026-06-21T03:00:05Z",
                        "succeeded": 1,
                    },
                }
            ]
        },
        context_text="notebook-cleaner가 15분마다 보여",
    )

    assert "`notebook-cleaner`" in evidence
    assert "`*/15 * * * *`" in evidence
    assert "15분마다" in evidence
    assert "Forbid" in evidence
    assert "2 | 3 |" in evidence
    assert "`NOTEBOOK_HIBERNATE_AFTER_SECONDS`" in evidence
    assert "1800초 (30분)" in evidence
    assert "1209600초 (14일)" in evidence
    assert "threshold values only" in evidence
    assert "`notebook-cleaner-29147292`" in evidence


def test_build_cronjob_activity_evidence_matches_arbitrary_requested_interval() -> None:
    evidence = build_cronjob_activity_evidence(
        {
            "items": [
                {
                    "metadata": {"namespace": "ops", "name": "fifteen-minute-cleaner"},
                    "spec": {"schedule": "*/15 * * * *"},
                },
                {
                    "metadata": {"namespace": "ops", "name": "backup-cleaner"},
                    "spec": {"schedule": "*/30 * * * *"},
                },
            ]
        },
        context_text="backup-cleaner가 30분마다 보여",
    )

    assert "`backup-cleaner`" in evidence
    assert "30분마다" in evidence
    assert "`fifteen-minute-cleaner`" not in evidence


def test_build_pod_status_evidence_sorts_container_restart_counts() -> None:
    evidence = build_pod_status_evidence(
        {
            "items": [
                {
                    "metadata": {
                        "name": "lightspeed-app-server-abc",
                        "namespace": "openshift-lightspeed",
                        "ownerReferences": [{"kind": "ReplicaSet", "name": "lightspeed-app-server"}],
                    },
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": "lightspeed-service-api",
                                "ready": True,
                                "restartCount": 0,
                                "state": {"running": {"startedAt": "2026-06-16T01:40:29Z"}},
                            },
                            {
                                "name": "lightspeed-to-dataverse-exporter",
                                "ready": True,
                                "restartCount": 44,
                                "state": {"running": {"startedAt": "2026-06-16T05:04:55Z"}},
                                "lastState": {
                                    "terminated": {
                                        "reason": "Error",
                                        "exitCode": 137,
                                        "finishedAt": "2026-06-16T04:59:40Z",
                                    }
                                },
                            },
                        ],
                    },
                },
                {
                    "metadata": {
                        "name": "nginx-gateway-fabric-controller-manager-abc",
                        "namespace": "openshift-operators",
                    },
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": "manager",
                                "ready": True,
                                "restartCount": 36,
                                "state": {"running": {"startedAt": "2026-06-20T04:54:32Z"}},
                                "lastState": {
                                    "terminated": {
                                        "reason": "Error",
                                        "exitCode": 1,
                                        "finishedAt": "2026-06-20T04:54:32Z",
                                    }
                                },
                            }
                        ],
                    },
                },
            ]
        }
    )

    assert "Restart counts below are cumulative container-level counts" in evidence
    assert "`lightspeed-to-dataverse-exporter`" in evidence
    assert "`manager`" in evidence
    assert evidence.index("`lightspeed-to-dataverse-exporter`") < evidence.index("`manager`")
    assert "Error/137" in evidence


def test_build_pod_status_evidence_includes_requested_namespace_pod_list() -> None:
    evidence = build_pod_status_evidence(
        {
            "items": [
                {
                    "metadata": {"name": "api-a-111", "namespace": "team-a"},
                    "status": {
                        "phase": "Running",
                        "startTime": "2026-06-22T00:00:00Z",
                        "containerStatuses": [
                            {
                                "name": "app",
                                "ready": True,
                                "restartCount": 0,
                                "state": {"running": {"startedAt": "2026-06-22T00:00:10Z"}},
                            }
                        ],
                    },
                },
                {
                    "metadata": {"name": "worker-a-222", "namespace": "team-a"},
                    "status": {
                        "phase": "Pending",
                        "startTime": "2026-06-22T00:01:00Z",
                        "containerStatuses": [
                            {
                                "name": "worker",
                                "ready": False,
                                "restartCount": 2,
                                "state": {"waiting": {"reason": "ImagePullBackOff"}},
                                "lastState": {"terminated": {"reason": "Error", "exitCode": 1}},
                            }
                        ],
                    },
                },
                {
                    "metadata": {"name": "api-b-333", "namespace": "team-b"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": "app",
                                "ready": True,
                                "restartCount": 0,
                                "state": {"running": {"startedAt": "2026-06-22T00:02:00Z"}},
                            }
                        ],
                    },
                },
            ]
        },
        include_pod_list=True,
        list_namespace="team-a",
    )

    assert "Current Pod list evidence:" in evidence
    assert "Namespace filter: `team-a`" in evidence
    assert "Rows shown: 2 / 2" in evidence
    assert "`api-a-111`" in evidence
    assert "`worker-a-222`" in evidence
    assert "`api-b-333`" not in evidence.split("Current Pod list evidence:", 1)[1]


def test_build_pod_status_evidence_marks_failed_pod_start_time() -> None:
    evidence = build_pod_status_evidence(
        {
            "items": [
                {
                    "metadata": {"name": "installer-1-node-a", "namespace": "openshift-example"},
                    "status": {
                        "phase": "Failed",
                        "startTime": "2026-06-09T08:55:51Z",
                        "containerStatuses": [
                            {
                                "name": "installer",
                                "ready": False,
                                "restartCount": 0,
                                "state": {
                                    "terminated": {
                                        "reason": "Error",
                                        "exitCode": 1,
                                    }
                                },
                            }
                        ],
                    },
                }
            ]
        }
    )

    assert "old Failed pods can be historical artifacts" in evidence
    assert "2026-06-09T08:55:51Z" in evidence
    assert "Failed / terminated:Error/1" in evidence


def test_build_pod_status_evidence_includes_unhealthy_spec_and_owner_chain() -> None:
    evidence = build_pod_status_evidence(
        {
            "items": [
                {
                    "metadata": {
                        "name": "sample-crashy-6fd7d7cfd7-r4nd0",
                        "namespace": "team-a",
                        "labels": {
                            "app": "sample-crashy",
                            "aiops.komsco/scenario": "sample",
                            "pod-template-hash": "6fd7d7cfd7",
                        },
                        "ownerReferences": [{"kind": "ReplicaSet", "name": "sample-crashy-6fd7d7cfd7"}],
                    },
                    "spec": {
                        "containers": [
                            {
                                "name": "app",
                                "image": "registry.example.com/team-a/sample-crashy:v2",
                                "command": ["python", "-c", "raise SystemExit('boom')"],
                                "args": ["--token=my-secret-token-value"],
                            }
                        ],
                    },
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": "app",
                                "ready": False,
                                "restartCount": 3,
                                "state": {"waiting": {"reason": "CrashLoopBackOff"}},
                                "lastState": {
                                    "terminated": {
                                        "reason": "Error",
                                        "exitCode": 1,
                                        "finishedAt": "2026-06-22T01:00:18Z",
                                    }
                                },
                            }
                        ],
                    },
                }
            ]
        },
        {
            "items": [
                {
                    "metadata": {
                        "name": "sample-crashy-6fd7d7cfd7",
                        "namespace": "team-a",
                        "ownerReferences": [{"kind": "Deployment", "name": "sample-crashy"}],
                    }
                }
            ]
        },
    )

    assert "Spec evidence for currently non-healthy or waiting containers" in evidence
    assert "registry.example.com/team-a/sample-crashy:v2" in evidence
    assert "[\"python\", \"-c\", \"raise SystemExit('boom')\"]" in evidence
    assert "--token=[REDACTED]" in evidence
    assert "my-secret-token-value" not in evidence
    assert "app=sample-crashy" in evidence
    assert "aiops.komsco/scenario=sample" in evidence
    assert "ReplicaSet/sample-crashy-6fd7d7cfd7 -> Deployment/sample-crashy" in evidence


def test_build_deployment_rollout_evidence_does_not_treat_ready_as_replaced() -> None:
    evidence = build_deployment_rollout_evidence(
        {
            "items": [
                {
                    "metadata": {
                        "annotations": {"deployment.kubernetes.io/revision": "1"},
                        "name": "two-pod-demo",
                        "namespace": "team-a",
                        "uid": "deployment-uid-a",
                    },
                    "spec": {
                        "replicas": 2,
                        "template": {"metadata": {"labels": {"app": "two-pod-demo"}}},
                    },
                    "status": {
                        "observedGeneration": 1,
                        "readyReplicas": 2,
                        "updatedReplicas": 2,
                    },
                }
            ]
        },
        {
            "items": [
                {
                    "metadata": {
                        "annotations": {"deployment.kubernetes.io/revision": "1"},
                        "name": "two-pod-demo-69c85d74cc",
                        "namespace": "team-a",
                        "ownerReferences": [
                            {"kind": "Deployment", "name": "two-pod-demo", "uid": "deployment-uid-a"}
                        ],
                    },
                    "spec": {"replicas": 2},
                    "status": {"readyReplicas": 2},
                }
            ]
        },
        {
            "items": [
                {
                    "metadata": {
                        "labels": {"app": "two-pod-demo", "pod-template-hash": "69c85d74cc"},
                        "name": "two-pod-demo-69c85d74cc-a",
                        "namespace": "team-a",
                    },
                    "status": {"startTime": "2026-06-22T04:30:47Z"},
                },
                {
                    "metadata": {
                        "labels": {"app": "two-pod-demo", "pod-template-hash": "69c85d74cc"},
                        "name": "two-pod-demo-69c85d74cc-b",
                        "namespace": "team-a",
                    },
                    "status": {"startTime": "2026-06-22T04:30:47Z"},
                },
            ]
        },
    )

    assert "Ready replicas only prove current availability" in evidence
    assert "`two-pod-demo`" in evidence
    assert "| team-a | `two-pod-demo` | 1 | - | 1 | 2/2 | 2 |" in evidence
    assert "two-pod-demo-69c85d74cc(rev=1,desired=2,ready=2)" in evidence
    assert "two-pod-demo-69c85d74cc-a hash=69c85d74cc" in evidence


def test_build_cluster_operator_status_evidence_summarizes_operator_health() -> None:
    evidence = build_cluster_operator_status_evidence(
        {
            "items": [
                {
                    "metadata": {"name": "example-operator"},
                    "status": {
                        "versions": [{"version": "4.20.23"}],
                        "conditions": [
                            {"type": "Available", "status": "True"},
                            {"type": "Degraded", "status": "False"},
                            {"type": "Progressing", "status": "False"},
                        ],
                    },
                }
            ]
        }
    )

    assert "ClusterOperator status evidence" in evidence
    assert "example-operator" in evidence
    assert "Available | Degraded | Progressing" in evidence
    assert "True | False | False" in evidence


def test_gateway_api_reference_filter_removes_misleading_gateway_docs() -> None:
    text_filter = TextReferenceFilter(filter_gateway_api_references=True)

    output = [
        text_filter.filter("대상 미지정입니다.\n---\n\nGateway [gateway.networking.k8s.io/v1]: "),
        text_filter.filter("https://docs.openshift.com/container-platform/4.20/rest_api/network_apis/gateway-gateway-networking-k8s-io-v1.html\n"),
        text_filter.filter("GatewayClass [gateway.networking.k8s.io/v1]: https://docs.openshift.com/container-platform/4.20/rest_api/network_apis/gatewayclass-gateway-networking-k8s-io-v1.html\n"),
        text_filter.flush(),
    ]
    filtered = "".join(output)

    assert "대상 미지정입니다." in filtered
    assert "gateway.networking.k8s.io" not in filtered
    assert "GatewayClass" not in filtered
    assert "---" not in filtered


def test_gateway_api_reference_filter_allows_explicit_gateway_api_questions() -> None:
    assert should_filter_gateway_api_references("pod 재시작해줘")
    assert not should_filter_gateway_api_references("Kubernetes Gateway API 문서 알려줘")


def test_low_signal_reference_filter_removes_unrequested_api_index_links() -> None:
    text_filter = TextReferenceFilter(
        filter_gateway_api_references=False,
        filter_low_signal_references=True,
    )

    output = [
        text_filter.filter("분석 요약입니다.\n---\n\nExtension APIs: https://docs.openshift.com/x\n"),
        text_filter.filter("Admission plugins: https://docs.openshift.com/y\n"),
        text_filter.filter("TokenReview [authentication.k8s.io/v1]: https://docs.openshift.com/z\n"),
        text_filter.filter("ClusterRole [authorization.openshift.io/v1]: https://docs.openshift.com/a\n"),
        text_filter.flush(),
    ]
    filtered = "".join(output)

    assert "분석 요약입니다." in filtered
    assert "Extension APIs" not in filtered
    assert "Admission plugins" not in filtered
    assert "TokenReview" not in filtered
    assert "ClusterRole" not in filtered
    assert "---" not in filtered


def test_low_signal_reference_filter_allows_explicit_doc_questions() -> None:
    assert should_filter_low_signal_references("현재 pod 상태 분석해줘")
    assert not should_filter_low_signal_references("TokenReview API 문서 링크 알려줘")


def test_text_filter_normalizes_restart_frequency_language() -> None:
    text_filter = TextReferenceFilter(
        filter_gateway_api_references=False,
        normalize_restart_language=True,
    )

    filtered = text_filter.filter("높은 빈도의 빈번한 재시작이 확인됩니다.\n")

    assert "높은 빈도" not in filtered
    assert "빈번한 재시작" not in filtered
    assert "높은 누적 재시작 횟수" in filtered
    assert "누적 재시작 이력" in filtered


def test_build_cluster_summary_returns_real_operational_counts() -> None:
    nodes_payload = {
        "items": [
            {
                "metadata": {
                    "name": "node-1",
                    "labels": {
                        "node-role.kubernetes.io/control-plane": "",
                        "node-role.kubernetes.io/worker": "",
                    },
                },
                "status": {
                    "conditions": [
                        {"type": "Ready", "status": "True"},
                        {"type": "DiskPressure", "status": "False"},
                        {"type": "MemoryPressure", "status": "False"},
                        {"type": "PIDPressure", "status": "False"},
                    ],
                    "nodeInfo": {"kubeletVersion": "v1.33.1", "osImage": "RHEL CoreOS 9.6"},
                },
            }
        ]
    }
    node_metrics_payload = {
        "items": [
            {
                "metadata": {"name": "node-1"},
                "usage": {"cpu": "123m", "memory": "456Mi"},
            }
        ]
    }
    cluster_version_payload = {
        "status": {
            "desired": {"version": "4.20.23"},
            "channel": "stable-4.20",
            "availableUpdates": [{"version": "4.20.24"}],
            "conditions": [{"type": "Upgradeable", "status": "False", "reason": "AdminAck"}],
        }
    }
    cluster_operators_payload = {
        "items": [
            {
                "metadata": {"name": "console"},
                "status": {
                    "conditions": [
                        {"type": "Available", "status": "True"},
                        {"type": "Degraded", "status": "False"},
                        {"type": "Progressing", "status": "False"},
                    ]
                },
            },
            {
                "metadata": {"name": "marketplace"},
                "status": {
                    "conditions": [
                        {"type": "Available", "status": "True"},
                        {
                            "type": "Degraded",
                            "status": "True",
                            "reason": "CatalogPodNotReady",
                            "message": "catalog pod is not ready",
                        },
                        {"type": "Progressing", "status": "False"},
                    ]
                },
            },
        ]
    }

    summary = build_cluster_summary(
        nodes_payload,
        node_metrics_payload,
        cluster_version_payload,
        cluster_operators_payload,
    )

    assert summary["nodes"]["total"] == 1
    assert summary["nodes"]["ready"] == 1
    assert summary["nodes"]["items"][0]["usage"]["cpu"] == "123m"
    assert summary["operators"]["degraded"] == 1
    assert summary["operators"]["issues"][0]["name"] == "marketplace"
    assert summary["version"]["updateAvailable"] is True
    assert summary["version"]["upgradeable"] is False
    assert summary["healthScore"] < 100


def test_build_aiops_overview_exposes_control_tower_and_data_sources() -> None:
    cluster_summary = {
        "apiUrl": "https://api.test:6443",
        "healthScore": 96,
        "nodes": {"notReady": 0, "pressureCount": 0},
        "operators": {"degraded": 0, "progressing": 0, "unavailable": 0},
    }
    overview = build_aiops_overview(
        cluster_summary,
        [
            {
                "label": "Node inventory",
                "name": "nodes",
                "path": "/api/v1/nodes",
                "required": True,
                "status": "available",
            },
            {
                "label": "Thanos query probe",
                "name": "thanos-query",
                "path": "/api/v1/query?query=up",
                "required": False,
                "status": "available",
            },
        ],
        {"alertmanager": "https://alertmanager.test", "prometheus": "", "thanos": "https://thanos.test"},
        {"query": "up", "resultCount": 7, "status": "available"},
    )

    assert overview["kind"] == "AIOpsOverview"
    assert overview["spec"]["clusterSummary"] == cluster_summary
    assert overview["spec"]["controlTower"]["status"] == "healthy"
    assert overview["spec"]["controlTower"]["statusLabel"] == "회사 OCP 읽기 전용 관제 정상"
    assert overview["spec"]["dataSources"][0]["name"] == "nodes"
    assert overview["spec"]["monitoring"]["probe"]["resultCount"] == 7
    assert overview["spec"]["monitoring"]["urls"]["thanosConfigured"] is True
    assert overview["spec"]["safety"]["readOnlyDefault"] is True


def test_build_aiops_anomaly_summary_orders_stage2_signals() -> None:
    cluster_summary = {
        "operators": {
            "issues": [
                {
                    "available": False,
                    "degraded": True,
                    "message": "OAuth route unavailable",
                    "name": "authentication",
                    "progressing": False,
                    "reason": "RouteHealth_Failed",
                    "upgradeable": "True",
                }
            ]
        },
        "version": {
            "channel": "stable-4.20",
            "upgradeable": False,
            "upgradeableMessage": "AdminAckRequired blocks upgrade",
            "upgradeableReason": "AdminAckRequired",
            "version": "4.20.23",
        },
    }
    pods_payload = {
        "items": [
            {
                "metadata": {"name": "api-1", "namespace": "prod"},
                "status": {
                    "containerStatuses": [
                        {
                            "lastState": {"terminated": {"reason": "Error"}},
                            "name": "api",
                            "restartCount": 12,
                            "state": {"waiting": {"message": "back-off restarting", "reason": "CrashLoopBackOff"}},
                        }
                    ],
                    "phase": "Running",
                },
            },
            {
                "metadata": {"name": "worker-1", "namespace": "prod"},
                "status": {
                    "containerStatuses": [
                        {
                            "name": "worker",
                            "restartCount": 0,
                            "state": {"waiting": {"message": "manifest unknown", "reason": "ImagePullBackOff"}},
                        }
                    ],
                    "phase": "Pending",
                },
            },
        ]
    }
    events_payload = {
        "items": [
            {
                "involvedObject": {"kind": "Pod", "name": "worker-1", "namespace": "prod"},
                "message": "0/3 nodes are available",
                "metadata": {"name": "worker-schedule", "namespace": "prod"},
                "reason": "FailedScheduling",
                "type": "Warning",
            }
        ]
    }
    alerts_probe = {
        "result": [
            {"metric": {"alertname": "Watchdog"}},
            {"metric": {"alertname": "KubePodCrashLooping", "namespace": "prod", "pod": "api-1", "severity": "warning"}},
        ],
        "status": "available",
    }
    restart_probe = {
        "result": [
            {"metric": {"container": "api", "namespace": "prod", "pod": "api-1"}, "value": [1, "3"]},
        ],
        "status": "available",
    }
    data_sources = [
        {"label": "Cluster operators", "name": "clusteroperators", "path": "", "required": False, "status": "available"},
        {"label": "Pod anomaly signals", "name": "pods", "path": "", "required": True, "status": "available"},
        {"label": "Warning events", "name": "events", "path": "", "required": True, "status": "available"},
        {"label": "Active alerts", "name": "alerts", "path": "", "required": False, "status": "available"},
        {"label": "Restart increase metric", "name": "restart-metrics", "path": "", "required": False, "status": "available"},
    ]

    summary = build_aiops_anomaly_summary(
        cluster_summary,
        pods_payload,
        events_payload,
        alerts_probe,
        restart_probe,
        data_sources,
    )

    spec = summary["spec"]
    findings = spec["findings"]
    finding_types = {finding["type"] for finding in findings}

    assert spec["status"] == "risk"
    assert spec["totals"]["danger"] >= 2
    assert "clusteroperator_condition" in finding_types
    assert "pod_crashloop" in finding_types
    assert "pod_image_pull" in finding_types
    assert "pod_pending" in finding_types
    assert "warning_event" in finding_types
    assert "active_alert" in finding_types
    assert "pod_restart_spike" in finding_types
    assert "upgrade_blocked" in finding_types
    assert [finding["priority"] for finding in findings] == sorted(finding["priority"] for finding in findings)
    assert findings[0]["resource"]["kind"] == "ClusterOperator"
    assert all("candidateCause" in finding and "evidence" in finding for finding in findings)
    assert spec["excludedAlerts"] == [
        {"alertname": "Watchdog", "reason": "Watchdog is an always-firing pipeline health alert."}
    ]


def test_build_aiops_anomaly_summary_does_not_report_false_normal_on_source_gap() -> None:
    cluster_summary = {
        "operators": {"issues": []},
        "version": {"upgradeable": True},
    }

    missing_optional = build_aiops_anomaly_summary(
        cluster_summary,
        {"items": []},
        {"items": []},
        {"status": "unavailable", "result": []},
        {"status": "available", "result": []},
        [
            {"label": "Pod anomaly signals", "name": "pods", "path": "", "required": True, "status": "available"},
            {"label": "Warning events", "name": "events", "path": "", "required": True, "status": "available"},
            {"label": "Active alerts", "name": "alerts", "path": "", "required": False, "status": "unavailable"},
        ],
    )
    failed_required = build_aiops_anomaly_summary(
        cluster_summary,
        None,
        {"items": []},
        {"status": "available", "result": []},
        {"status": "available", "result": []},
        [
            {"label": "Pod anomaly signals", "name": "pods", "path": "", "required": True, "status": "error"},
            {"label": "Warning events", "name": "events", "path": "", "required": True, "status": "available"},
        ],
    )

    assert missing_optional["spec"]["status"] == "unknown"
    assert "정상" not in missing_optional["spec"]["statusLabel"]
    assert failed_required["spec"]["status"] == "error"
    assert failed_required["spec"]["statusLabel"] == "필수 이상 징후 데이터 소스 확인 실패"


def test_build_aiops_action_candidates_are_read_only_and_not_action_records() -> None:
    before_counts = {
        "approvals": len(APPROVAL_DECISIONS),
        "executions": len(EXECUTION_RECORDS),
        "plans": len(SEALED_ACTION_PLANS),
        "proposals": len(ACTION_PROPOSALS),
    }
    cluster_summary = {
        "healthScore": 62,
        "nodes": {"notReady": 0, "pressureCount": 0},
        "operators": {"degraded": 0, "issues": [], "progressing": 0, "unavailable": 0},
        "version": {"upgradeable": True},
    }
    pods_payload = {
        "items": [
            {
                "metadata": {"name": "api-1", "namespace": "prod"},
                "status": {
                    "containerStatuses": [
                        {
                            "lastState": {"terminated": {"reason": "Error"}},
                            "name": "api",
                            "restartCount": 9,
                            "state": {"waiting": {"message": "back-off restarting", "reason": "CrashLoopBackOff"}},
                        }
                    ],
                    "phase": "Running",
                },
            }
        ]
    }
    data_sources = [
        {"label": "Cluster operators", "name": "clusteroperators", "path": "", "required": False, "status": "available"},
        {"label": "Pod anomaly signals", "name": "pods", "path": "", "required": True, "status": "available"},
        {"label": "Warning events", "name": "events", "path": "", "required": True, "status": "available"},
        {"label": "Active alerts", "name": "alerts", "path": "", "required": False, "status": "available"},
        {"label": "Restart increase metric", "name": "restart-metrics", "path": "", "required": False, "status": "available"},
    ]

    anomaly_summary = build_aiops_anomaly_summary(
        cluster_summary,
        pods_payload,
        {"items": []},
        {"result": [], "status": "available"},
        {"result": [], "status": "available"},
        data_sources,
    )
    action_candidates = build_aiops_action_candidates(anomaly_summary, data_sources)
    overview = build_aiops_overview(
        cluster_summary,
        data_sources,
        {"thanos": "https://thanos.test"},
        {"query": "up", "resultCount": 1, "status": "available"},
        anomaly_summary,
    )

    candidate_spec = action_candidates["spec"]
    candidate = candidate_spec["candidates"][0]

    assert action_candidates["kind"] == "AIOpsActionCandidateSummary"
    assert candidate_spec["status"] == "candidates"
    assert candidate_spec["safety"]["mode"] == "read-only"
    assert candidate_spec["safety"]["proposalOnly"] is True
    assert candidate_spec["safety"]["mutationsEnabled"] is False
    assert candidate["approvalRequired"] is True
    assert candidate["executable"] is False
    assert candidate["mutationSubmitted"] is False
    assert candidate["executionPolicy"]["executionEnabled"] is False
    assert candidate["statusLabel"] == "제안만 함 / 실행 안 함"
    assert candidate["riskLevel"] == "high"
    assert candidate["prerequisiteChecks"]
    assert candidate["expectedImpact"]
    assert candidate["verificationChecks"]
    assert candidate["evidenceRefs"][0]["status"] == "collected"
    assert {"apply", "delete", "patch", "scale", "exec"}.issubset(set(candidate["blockedActions"]))
    assert "planId" not in candidate
    assert "approvalId" not in candidate
    assert "executionId" not in candidate
    assert "sealedActionPlan" not in candidate
    assert overview["spec"]["actionCandidates"]["spec"]["candidates"][0]["id"] == candidate["id"]
    assert before_counts == {
        "approvals": len(APPROVAL_DECISIONS),
        "executions": len(EXECUTION_RECORDS),
        "plans": len(SEALED_ACTION_PLANS),
        "proposals": len(ACTION_PROPOSALS),
    }


def test_data_source_status_marks_paginated_lists_as_partial() -> None:
    status = gateway_main.data_source_status(
        label="Pod anomaly signals",
        name="pods",
        path="/api/v1/pods?limit=500",
        payload={"items": [], "metadata": {"continue": "next-page-token"}},
        required=True,
    )

    assert status["status"] == "partial"
    assert status["continueTokenPresent"] is True
    assert "paginated" in status["reason"]


def test_build_node_alert_metric_rca_evidence_summarizes_real_sources() -> None:
    node_evidence = build_node_status_rca_evidence(
        {
            "items": [
                {
                    "metadata": {
                        "labels": {"node-role.kubernetes.io/worker": ""},
                        "name": "worker-a",
                    },
                    "status": {
                        "conditions": [
                            {"type": "Ready", "status": "True"},
                            {"type": "DiskPressure", "status": "False"},
                            {"type": "MemoryPressure", "status": "True"},
                            {"type": "PIDPressure", "status": "False"},
                        ],
                        "nodeInfo": {"kubeletVersion": "v1.33.1"},
                    },
                }
            ]
        },
        {"items": [{"metadata": {"name": "worker-a"}, "usage": {"cpu": "120m", "memory": "512Mi"}}]},
        metrics_status={"status": "available"},
    )
    alert_evidence = build_active_alerts_rca_evidence(
        {
            "result": [
                {"metric": {"alertname": "Watchdog"}},
                {
                    "metric": {
                        "alertname": "KubePodCrashLooping",
                        "namespace": "prod",
                        "pod": "api-1",
                        "severity": "warning",
                    }
                },
            ],
            "resultCount": 2,
            "status": "available",
        }
    )
    metric_evidence = build_restart_metric_rca_evidence(
        {
            "result": [
                {
                    "metric": {"container": "api", "namespace": "prod", "pod": "api-1"},
                    "value": [1, "5"],
                }
            ],
            "resultCount": 1,
            "status": "available",
        }
    )

    assert "EvidenceType: node" in node_evidence
    assert "memory" in node_evidence
    assert "120m" in node_evidence
    assert "EvidenceType: alert" in alert_evidence
    assert "KubePodCrashLooping" in alert_evidence
    assert "excludedWatchdog=1" in alert_evidence
    assert "EvidenceType: metric" in metric_evidence
    assert "Restart increase 1h" in metric_evidence
    assert "| prod | `api-1` | `api` | 5 |" in metric_evidence


def test_build_alert_and_metric_rca_evidence_reports_unavailable_sources() -> None:
    alert_evidence = build_active_alerts_rca_evidence(
        {"status": "unavailable", "reason": "thanosPublicURL is not published"}
    )
    metric_evidence = build_restart_metric_rca_evidence(
        {"status": "error", "reason": "Authorization: Bearer secret-token-value token=raw-secret"}
    )

    assert "Active alert evidence unavailable" in alert_evidence
    assert "thanosPublicURL" in alert_evidence
    assert "Metric RCA evidence unavailable" in metric_evidence
    assert "secret-token-value" not in metric_evidence
    assert "raw-secret" not in metric_evidence


def test_query_thanos_instant_surfaces_prometheus_error_and_partial_results(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, payload: Mapping[str, object], status_code: int = 200) -> None:
            self._payload = payload
            self.status_code = status_code
            self.text = json.dumps(payload)

        def json(self) -> Mapping[str, object]:
            return self._payload

    class FakeAsyncClient:
        payload: Mapping[str, object] = {"status": "success", "data": {"result": []}}

        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def get(self, *args, **kwargs) -> FakeResponse:
            return FakeResponse(self.payload)

    monkeypatch.setattr(gateway_main.httpx, "AsyncClient", FakeAsyncClient)

    async def run() -> None:
        FakeAsyncClient.payload = {
            "error": "bad_data: query failed",
            "errorType": "bad_data",
            "status": "error",
        }
        error_probe = await gateway_main.query_thanos_instant(
            "https://thanos.test",
            "Bearer token",
            "ALERTS",
        )
        FakeAsyncClient.payload = {
            "data": {"result": [{"metric": {"pod": f"pod-{index}"}, "value": [1, "1"]} for index in range(55)]},
            "status": "success",
        }
        partial_probe = await gateway_main.query_thanos_instant(
            "https://thanos.test",
            "Bearer token",
            "up",
        )

        assert error_probe["status"] == "error"
        assert "bad_data" in error_probe["reason"]
        assert partial_probe["status"] == "partial"
        assert partial_probe["resultCount"] == 55
        assert len(partial_probe["result"]) == 50
        assert "capped" in partial_probe["reason"]

    asyncio.run(run())


def test_aiops_overview_api_collects_cluster_and_monitoring_sources(monkeypatch) -> None:
    nodes_payload = {
        "items": [
            {
                "metadata": {"name": "node-1", "labels": {"node-role.kubernetes.io/worker": ""}},
                "status": {
                    "conditions": [
                        {"type": "Ready", "status": "True"},
                        {"type": "DiskPressure", "status": "False"},
                        {"type": "MemoryPressure", "status": "False"},
                        {"type": "PIDPressure", "status": "False"},
                    ],
                    "nodeInfo": {"kubeletVersion": "v1.33.1", "osImage": "RHEL CoreOS 9.6"},
                },
            }
        ]
    }
    payloads = {
        "/api/v1/nodes": nodes_payload,
        "/apis/metrics.k8s.io/v1beta1/nodes": {
            "items": [{"metadata": {"name": "node-1"}, "usage": {"cpu": "42m", "memory": "128Mi"}}]
        },
        "/apis/config.openshift.io/v1/clusterversions/version": {
            "status": {"desired": {"version": "4.20.23"}, "channel": "stable-4.20"}
        },
        "/apis/config.openshift.io/v1/clusteroperators": {
            "items": [
                {
                    "metadata": {"name": "console"},
                    "status": {
                        "conditions": [
                            {"type": "Available", "status": "True"},
                            {"type": "Degraded", "status": "False"},
                            {"type": "Progressing", "status": "False"},
                        ]
                    },
                }
            ]
        },
        "/api/v1/namespaces/openshift-config-managed/configmaps/monitoring-shared-config": {
            "data": {
                "alertmanagerPublicURL": "https://alertmanager.test",
                "prometheusPublicURL": "https://prometheus.test",
                "thanosPublicURL": "https://thanos.test",
            }
        },
        "/api/v1/pods?limit=500": {"items": []},
        "/api/v1/events?limit=500": {"items": []},
    }

    async def fake_fetch_ocp_json_observed(
        _client,
        path: str,
        _authorization: str,
        *,
        label: str,
        name: str,
        required: bool = False,
    ):
        payload = payloads.get(path)
        return payload, gateway_main.data_source_status(
            label=label,
            name=name,
            path=path,
            payload=payload,
            required=required,
        )

    async def fake_probe_thanos_query(thanos_url: str, _authorization: str) -> dict:
        assert thanos_url == "https://thanos.test"
        return {"query": "up", "resultCount": 3, "status": "available"}

    async def fake_query_thanos_instant(thanos_url: str, _authorization: str, query: str) -> dict:
        assert thanos_url == "https://thanos.test"
        return {"query": query, "result": [], "resultCount": 0, "status": "available"}

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.test:6443")
    monkeypatch.setattr(gateway_main, "fetch_ocp_json_observed", fake_fetch_ocp_json_observed)
    monkeypatch.setattr(gateway_main, "probe_thanos_query", fake_probe_thanos_query)
    monkeypatch.setattr(gateway_main, "query_thanos_instant", fake_query_thanos_instant)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/v1/aiops/overview",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["kind"] == "AIOpsOverview"
        assert payload["spec"]["clusterSummary"]["nodes"]["ready"] == 1
        assert payload["spec"]["clusterSummary"]["nodes"]["items"][0]["usage"]["cpu"] == "42m"
        assert payload["spec"]["controlTower"]["mode"] == "read-only"
        assert payload["spec"]["monitoring"]["probe"]["resultCount"] == 3
        assert {source["name"] for source in payload["spec"]["dataSources"]} == {
            "nodes",
            "metrics.k8s.io",
            "clusterversion",
            "clusteroperators",
            "monitoring-shared-config",
            "thanos-query",
            "pods",
            "events",
            "alerts",
            "restart-metrics",
        }
        assert payload["spec"]["anomalies"]["kind"] == "AIOpsAnomalySummary"
        assert payload["spec"]["anomalies"]["spec"]["status"] == "normal"

    asyncio.run(run())


def test_split_plain_text_events_extracts_tool_lines() -> None:
    async def chunks():
        yield 'Tool call: {"name": "get_alerts", "args": {"active": true}, "id": "tool-1"}\n'
        yield 'Tool result: {"name": "get_alerts", "status": "success", "content": "{\\"alerts\\":[{},{}]}", "id": "tool-1"}\n'
        yield "현재 확인된 경고를 정리합니다."

    async def run() -> list[dict]:
        return [event async for event in split_plain_text_events(chunks())]

    events = asyncio.run(run())

    assert events[0]["type"] == "tool_call"
    assert events[0]["name"] == "get_alerts"
    assert events[1]["type"] == "tool_result"
    assert events[1]["summary"] == "경고 2건 조회"
    assert events[2] == {"type": "text", "content": "현재 확인된 경고를 정리합니다."}


def test_split_plain_text_events_summarizes_resource_get_progress() -> None:
    async def chunks():
        yield (
            'Tool call: {"name": "resources_get", "args": {"apiVersion": "v1", '
            '"kind": "Pod", "namespace": "example-namespace", '
            '"name": "example-catalog-pod"}, "id": "tool-1"}\n'
        )
        yield (
            'Tool result: {"name": "resources_get", "status": "success", '
            '"content": "apiVersion: v1\\nkind: Pod\\nmetadata:\\n  name: '
            'example-catalog-pod\\n  namespace: example-namespace\\n", '
            '"id": "tool-1"}\n'
        )
        yield (
            'Tool result: {"name": "resources_get", "status": "error", '
            '"content": "Tool failed: resource not allowed", "id": "tool-2"}\n'
        )

    async def run() -> list[dict]:
        return [event async for event in split_plain_text_events(chunks())]

    events = asyncio.run(run())

    assert events[0]["summary"] == "Pod example-namespace/example-catalog-pod 상세 조회"
    assert events[1]["summary"] == "Pod example-namespace/example-catalog-pod 조회 완료"
    assert events[2]["summary"] == "조회 실패: Tool failed: resource not allowed"


def test_build_evidence_reference_uses_redacted_digest_projection() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    event = {
        "type": "tool_result",
        "name": "resources_get",
        "status": "success",
        "summary": "Pod 조회 완료",
        "detail": "token=my-secret-token-value\nkind: Pod",
    }

    evidence = build_evidence_reference(
        event=event,
        incident_id="inc-1",
        run_id="run-1",
        subject=subject,
    )

    assert evidence["evidenceId"].startswith("ev-")
    assert evidence["contentDigest"].startswith("sha256:")
    assert evidence["originatingSubject"]["username"] == "user@example.com"
    assert evidence["sourceType"] == "ols-tool-result"
    assert evidence["summary"] == "Pod 조회 완료"


def test_build_evidence_reference_events_supports_gateway_preflight_source() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    event = {
        "type": "tool_result",
        "name": "pod_status_evidence",
        "status": "success",
        "summary": "Pod 상태/재시작 증거 수집 완료",
        "detail": "Gateway-collected Pod status evidence",
    }

    events = build_evidence_reference_events(
        event=event,
        incident_id="inc-1",
        run_id="run-1",
        source_type="gateway-preflight-evidence",
        subject=subject,
    )

    assert events[0]["type"] == "tool_call"
    assert events[0]["name"] == "evidence_ref"
    assert events[1]["type"] == "tool_result"
    assert events[1]["result"]["sourceType"] == "gateway-preflight-evidence"
    assert events[1]["result"]["summary"] == "Pod 상태/재시작 증거 수집 완료"


def test_can_subject_read_record_requires_same_observed_identity() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    other_subject = safe_subject({"username": "other@example.com", "uid": "uid-2", "groups": ["ops"]})
    record = {"originatingSubject": subject}

    assert can_subject_read_record(record, subject)
    assert not can_subject_read_record(record, other_subject)


def test_evidence_api_reads_stored_evidence_with_read_time_authorization() -> None:
    EVIDENCE_RECORDS.clear()
    subject = safe_subject(None)
    event = {
        "type": "tool_result",
        "name": "resources_get",
        "status": "success",
        "summary": "테스트 증거",
        "detail": "password=secret-value\nkind: Pod",
    }
    events = build_evidence_reference_events(
        event=event,
        incident_id="inc-test",
        run_id="run-test",
        source_type="gateway-preflight-evidence",
        subject=subject,
    )
    evidence_id = events[1]["result"]["evidenceId"]

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/v1/evidence/{evidence_id}",
                headers={"Authorization": "Bearer test-token"},
            )
            list_response = await client.get(
                "/v1/evidence?incidentId=inc-test",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["kind"] == "Evidence"
        assert payload["spec"]["detail"] == "password=[REDACTED]\nkind: Pod"
        assert list_response.status_code == 200
        assert list_response.json()["items"][0]["evidenceId"] == evidence_id
        assert "detail" not in list_response.json()["items"][0]

    asyncio.run(run())


def test_workflow_and_metrics_endpoints_expose_non_secret_runtime_state() -> None:
    WORKFLOW_RECORDS.clear()
    METRICS["aiops_chat_requests_total"] = 3
    subject = safe_subject(None)
    WORKFLOW_RECORDS["run-test"] = {
        "runId": "run-test",
        "status": "completed",
        "subject": subject,
        "target": {"messageLength": 10},
    }

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            workflow_response = await client.get(
                "/v1/workflows/run-test",
                headers={"Authorization": "Bearer test-token"},
            )
            metrics_response = await client.get("/metrics")

        assert workflow_response.status_code == 200
        assert workflow_response.json()["spec"]["status"] == "completed"
        assert metrics_response.status_code == 200
        assert "aiops_chat_requests_total 3" in metrics_response.text
        assert "Bearer" not in metrics_response.text

    asyncio.run(run())


def test_aiops_status_api_exposes_runtime_capabilities_and_recent_records() -> None:
    AUDIT_RECORDS.clear()
    DIAGNOSTIC_REQUESTS.clear()
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()
    APPROVAL_DECISIONS.clear()
    EXECUTION_RECORDS.clear()
    subject = safe_subject(None)
    DIAGNOSTIC_REQUESTS["diag-runtime"] = {
        "apiVersion": "aiops.komsco/v1",
        "kind": "DiagnosticRequestRecord",
        "metadata": {"name": "diag-runtime", "createdAt": "2026-06-21T00:00:00Z"},
        "spec": {"status": {"phase": "collector_succeeded"}},
        "subject": subject,
    }
    EXECUTION_RECORDS["execution-runtime"] = {
        "apiVersion": "aiops.komsco/v1",
        "kind": "ExecutionRecord",
        "metadata": {"name": "execution-runtime", "createdAt": "2026-06-21T00:01:00Z"},
        "spec": {"mutationOutcome": {"status": "mutation_succeeded"}},
        "subject": subject,
    }
    AUDIT_RECORDS["audit-runtime"] = {
        "schemaVersion": "v1",
        "action": "chat_request_accepted",
        "auditId": "audit-runtime",
        "incidentId": "incident-runtime",
        "policy": {"decision": "allow_read_only_evidence"},
        "requestId": "request-runtime",
        "runId": "run-runtime",
        "subject": subject,
        "target": {"messageLength": 10},
        "timestamp": "2026-06-21T00:02:00Z",
    }

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/v1/aiops/status",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["kind"] == "AIOpsRuntimeStatus"
        assert payload["spec"]["capabilities"]["recordStoreConfigMap"] in {
            "",
            "komsco-ai-gateway-ledger",
        }
        rag_status = payload["spec"]["capabilities"]["rag"]
        assert rag_status["status"] == "not_configured"
        assert rag_status["accessPath"] == "gateway-only"
        assert rag_status["directDatabaseAccess"] is False
        assert rag_status["aclRequired"] is True
        adapters = {
            adapter["name"]: adapter
            for adapter in payload["spec"]["safetyContract"]["adapterStatus"]
        }
        assert adapters["OpenShift"]["status"] == "available"
        assert len(adapters["OpenShift"]["supportedTools"]) >= 3
        assert adapters["Linux"]["status"] == "disabled"
        assert adapters["Linux"]["disabledReason"]
        assert adapters["Linux"]["nextAction"]
        assert adapters["Windows"]["status"] == "planned"
        assert "Windows node agent" in adapters["Windows"]["requirements"]
        assert payload["spec"]["records"]["diagnosticRequests"][0]["metadata"]["name"] == "diag-runtime"
        assert payload["spec"]["records"]["executionRecords"][0]["metadata"]["name"] == "execution-runtime"
        audit_record = payload["spec"]["records"]["auditRecords"][0]
        assert audit_record["metadata"]["name"] == "audit-runtime"
        assert audit_record["spec"]["action"] == "chat_request_accepted"
        assert "Bearer" not in json.dumps(payload)

    asyncio.run(run())


def test_rag_search_returns_not_configured_contract_without_backend() -> None:
    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        headers = {"Authorization": "Bearer test-token"}
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/rag/search",
                headers=headers,
                json={
                    "query": "최근 OpenShift 경고 조치 절차",
                    "topK": 3,
                    "filters": {
                        "sourceTypes": ["runbook"],
                        "namespaces": ["openshift-monitoring"],
                        "customers": ["komsco"],
                        "aclGroups": ["aiops-admins"],
                    },
                },
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["kind"] == "RagSearchResult"
        assert payload["spec"]["status"] == "not_configured"
        assert payload["spec"]["backend"]["status"] == "not_configured"
        assert payload["spec"]["backend"]["accessPath"] == "gateway-only"
        assert payload["spec"]["results"] == []
        assert payload["spec"]["evidence"]["status"] == "missing"
        assert payload["spec"]["evidence"]["missing"][0]["type"] == "runbook"
        assert payload["spec"]["filters"]["aclGroups"] == ["aiops-admins"]
        assert payload["spec"]["safety"]["directDatabaseAccessAllowed"] is False
        assert payload["spec"]["safety"]["aclRequired"] is True
        assert payload["spec"]["safety"]["mockResultsAreProductionEvidence"] is False
        assert "Bearer" not in json.dumps(payload)

    asyncio.run(run())


def test_diagnostic_request_digest_uses_request_projection_without_target_hardcoding() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    request = DiagnosticRequestCreate(
        targetNode=DiagnosticTargetNode(name="node-a.example.com", uid="node-uid-a"),
        collector="node_os_readonly_triage",
        timeRange=DiagnosticTimeRange(
            since="2026-06-21T00:00:00Z",
            until="2026-06-21T00:05:00Z",
        ),
        limits=DiagnosticLimits(deadline="30s", maxBytes=4096, maxLines=1000),
        evidencePolicy=DiagnosticEvidencePolicy(
            classification="restricted",
            rawStorageAllowed=False,
            redactionPolicyDigest="sha256:redaction-policy",
        ),
        policy={
            "policyDecisionId": "pd-1",
            "policyBundleHash": "sha256:bundle",
            "policyInputDigest": "sha256:input",
            "policyDecisionDigest": "sha256:decision",
        },
    )
    candidate = build_diagnostic_request_candidate(request, subject)
    digest = diagnostic_request_digest(candidate)

    changed_target = request.model_copy(
        update={"targetNode": DiagnosticTargetNode(name="node-b.example.com", uid="node-uid-b")}
    )
    changed_candidate = build_diagnostic_request_candidate(changed_target, subject)

    assert digest.startswith("sha256:")
    assert candidate["requester"]["username"] == "user@example.com"
    assert candidate["targetNode"]["name"] == "node-a.example.com"
    assert diagnostic_request_digest(changed_candidate) != digest


def test_diagnostic_request_record_stores_only_grant_reference() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    request = DiagnosticRequestCreate(
        targetNode=DiagnosticTargetNode(name="node-a.example.com", uid="node-uid-a"),
        collector="node_os_readonly_triage",
        timeRange=DiagnosticTimeRange(
            since="2026-06-21T00:00:00Z",
            until="2026-06-21T00:05:00Z",
        ),
    )

    record = build_diagnostic_request_record(request, subject)

    assert record["metadata"]["name"].startswith("diag-")
    assert record["spec"]["grantRef"]["bearerGrantStored"] is False
    assert record["spec"]["status"]["submittedToController"] is False
    assert record["spec"]["status"]["phase"] in {"disabled", "pending_controller_submission"}
    assert "Bearer" not in str(record)


def test_host_diagnostic_collector_registry_rejects_arbitrary_collectors() -> None:
    assert HOST_DIAGNOSTIC_COLLECTOR_DIGEST.startswith("sha256:")
    assert set(HOST_DIAGNOSTIC_COLLECTORS) == {
        "node_os_readonly_triage",
        "node_runtime_readonly_triage",
    }
    assert HOST_DIAGNOSTIC_COLLECTORS["node_os_readonly_triage"]["arbitraryCommandInputAllowed"] is False
    assert HOST_DIAGNOSTIC_COLLECTORS["node_runtime_readonly_triage"]["hostAccess"]["hostPID"] is False
    assert "run_command" not in str(HOST_DIAGNOSTIC_COLLECTORS)
    assert "nsenter" not in str(HOST_DIAGNOSTIC_COLLECTORS)


def test_diagnostic_request_api_creates_disabled_foundation_with_read_authorization() -> None:
    DIAGNOSTIC_REQUESTS.clear()

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            collectors_response = await client.get(
                "/v1/diagnostics/collectors",
                headers={"Authorization": "Bearer test-token"},
            )
            create_response = await client.post(
                "/v1/diagnostics/requests",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "incidentId": "inc-diag",
                    "runId": "run-diag",
                    "targetNode": {"name": "node-a.example.com", "uid": "node-uid-a"},
                    "collector": "node_os_readonly_triage",
                    "timeRange": {
                        "since": "2026-06-21T00:00:00Z",
                        "until": "2026-06-21T00:05:00Z",
                    },
                    "requester": {"username": "attacker@example.com"},
                },
            )

        assert collectors_response.status_code == 200
        assert collectors_response.json()["spec"]["digest"] == HOST_DIAGNOSTIC_COLLECTOR_DIGEST
        assert create_response.status_code == 422

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            create_response = await client.post(
                "/v1/diagnostics/requests",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "incidentId": "inc-diag",
                    "runId": "run-diag",
                    "targetNode": {"name": "node-a.example.com", "uid": "node-uid-a"},
                    "collector": "node_os_readonly_triage",
                    "timeRange": {
                        "since": "2026-06-21T00:00:00Z",
                        "until": "2026-06-21T00:05:00Z",
                    },
                },
            )
            payload = create_response.json()
            request_id = payload["metadata"]["name"]
            read_response = await client.get(
                f"/v1/diagnostics/requests/{request_id}",
                headers={"Authorization": "Bearer test-token"},
            )

        assert create_response.status_code == 200
        assert payload["kind"] == "DiagnosticRequest"
        assert payload["spec"]["candidate"]["requester"]["username"] == "unknown"
        assert payload["spec"]["candidate"]["targetNode"]["name"] == "node-a.example.com"
        assert payload["spec"]["candidate"]["collectorRegistry"]["digest"] == HOST_DIAGNOSTIC_COLLECTOR_DIGEST
        assert payload["spec"]["candidate"]["collectorConstraints"]["arbitraryCommandInputAllowed"] is False
        assert payload["spec"]["grantRef"]["bearerGrantStored"] is False
        assert payload["spec"]["status"]["submittedToController"] is False
        assert read_response.status_code == 200
        assert read_response.json()["metadata"]["name"] == request_id

    asyncio.run(run())


def test_host_diagnostics_collector_builds_bounded_redacted_evidence(tmp_path) -> None:
    (tmp_path / "proc" / "pressure").mkdir(parents=True)
    (tmp_path / "proc" / "loadavg").write_text("0.10 0.20 0.30 1/100 123\n", encoding="utf-8")
    (tmp_path / "proc" / "uptime").write_text("1000 900\n", encoding="utf-8")
    (tmp_path / "proc" / "meminfo").write_text("MemTotal: 1024 kB\n", encoding="utf-8")
    (tmp_path / "proc" / "pressure" / "cpu").write_text("some avg10=0.00\n", encoding="utf-8")
    (tmp_path / "proc" / "pressure" / "memory").write_text("some avg10=0.00\n", encoding="utf-8")
    (tmp_path / "proc" / "pressure" / "io").write_text("some avg10=0.00\n", encoding="utf-8")
    (tmp_path / "proc" / "sys" / "kernel").mkdir(parents=True)
    (tmp_path / "proc" / "sys" / "kernel" / "hostname").write_text("node-a\n", encoding="utf-8")
    (tmp_path / "proc" / "sys" / "kernel" / "tainted").write_text("0\n", encoding="utf-8")
    (tmp_path / "sys").mkdir()
    (tmp_path / "var" / "log").mkdir(parents=True)
    (tmp_path / "var" / "log" / "messages").write_text(
        "safe line\nAuthorization: Bearer secret-token-value-1234567890\n",
        encoding="utf-8",
    )

    evidence = collect_host_diagnostics(
        request_id="diag-test",
        collector="node_os_readonly_triage",
        target_node_name="node-a.example.com",
        target_node_uid="node-uid-a",
        host_root=tmp_path,
        max_bytes=4096,
        max_lines=100,
    )
    serialized = json.dumps(evidence, ensure_ascii=False, sort_keys=True)

    assert evidence["kind"] == "HostDiagnosticEvidence"
    assert evidence["spec"]["collector"]["arbitraryCommandInputAllowed"] is False
    assert {section["name"] for section in evidence["spec"]["sections"]} == {
        "kernel_summary",
        "disk_pressure_summary",
        "host_log_tail",
    }
    assert "secret-token-value-1234567890" not in serialized
    assert "[REDACTED]" in serialized


def test_host_diagnostics_controller_job_manifest_is_fixed_readonly_job() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    request = DiagnosticRequestCreate(
        targetNode=DiagnosticTargetNode(name="node-a.example.com", uid="node-uid-a"),
        collector="node_os_readonly_triage",
        timeRange=DiagnosticTimeRange(
            since="2026-06-21T00:00:00Z",
            until="2026-06-21T00:05:00Z",
        ),
        limits=DiagnosticLimits(deadline="300s", maxBytes=99 * 1024 * 1024, maxLines=499999),
    )
    record = build_diagnostic_request_record(request, subject)

    manifest = build_diagnostic_job_manifest(
        record,
        namespace="komsco-ai-dev",
        runner_image="registry.example/komsco-ai-gateway:test",
        runner_service_account="komsco-ai-host-diagnostics-runner",
    )
    container = manifest["spec"]["template"]["spec"]["containers"][0]

    assert manifest["kind"] == "Job"
    assert manifest["spec"]["template"]["spec"]["nodeName"] == "node-a.example.com"
    assert "seccompProfile" not in str(manifest["spec"]["template"]["spec"])
    assert manifest["spec"]["activeDeadlineSeconds"] == 30
    assert container["command"] == ["python", "-m", "komsco_ai_gateway.host_diagnostics_collector"]
    assert container["securityContext"]["runAsUser"] == 0
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert all(mount.get("readOnly") is True for mount in container["volumeMounts"] if mount["name"].startswith("host-"))
    host_paths = {volume["hostPath"]["path"] for volume in manifest["spec"]["template"]["spec"]["volumes"] if "hostPath" in volume}
    assert host_paths == {"/proc", "/sys", "/var/log"}
    assert "nsenter" not in str(manifest)
    assert "sh -c" not in str(manifest)


def test_diagnostic_controller_unconfigured_status_is_recorded(monkeypatch) -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    request = DiagnosticRequestCreate(
        targetNode=DiagnosticTargetNode(name="node-a.example.com", uid="node-uid-a"),
        collector="node_os_readonly_triage",
        timeRange=DiagnosticTimeRange(
            since="2026-06-21T00:00:00Z",
            until="2026-06-21T00:05:00Z",
        ),
    )
    record = build_diagnostic_request_record(request, subject)

    monkeypatch.setattr(gateway_main, "DIAGNOSTICS_ENABLED", True)
    monkeypatch.setattr(gateway_main, "HOST_DIAGNOSTICS_CONTROLLER_URL", "")
    submitted = asyncio.run(gateway_main.submit_diagnostic_request_to_controller(record))

    assert submitted["spec"]["status"]["phase"] == "controller_unconfigured"
    assert submitted["spec"]["status"]["submittedToController"] is False


def test_controller_submission_compaction_keeps_digest_not_raw_log() -> None:
    compacted = compact_controller_submission(
        {
            "spec": {
                "phase": "completed",
                "collectorPod": {
                    "podPhase": "Succeeded",
                    "logPreview": '{"kind":"HostDiagnosticEvidence","spec":{"requestId":"diag-a"}}',
                    "evidenceSummary": {"sections": ["kernel_summary"]},
                },
            }
        }
    )
    collector_pod = compacted["spec"]["collectorPod"]

    assert normalize_controller_phase("completed") == "succeeded"
    assert "logPreview" not in collector_pod
    assert collector_pod["logPreviewDigest"].startswith("sha256:")
    assert collector_pod["logPreviewBytes"] > 0
    assert collector_pod["evidenceSummary"]["sections"] == ["kernel_summary"]


def test_action_registry_contains_only_initial_allow_list() -> None:
    assert ACTION_REGISTRY_DIGEST.startswith("sha256:")
    assert set(ACTION_REGISTRY_ENTRIES) == {
        "rollout_restart_deployment",
        "set_replicas_within_bounds",
        "evict_one_unhealthy_controller_owned_pod",
        "rollback_deployment_to_revision",
        "set_hpa_bounds",
    }
    assert "patch_resource" not in ACTION_REGISTRY_ENTRIES
    assert "apply_manifest" not in ACTION_REGISTRY_ENTRIES
    assert "run_command" not in ACTION_REGISTRY_ENTRIES


def test_core_action_hpa_guard_requires_review_for_deployment_scale() -> None:
    plan = {
        "target": {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "namespace": "team-a",
            "name": "web-a",
            "uid": "deployment-uid-a",
        },
        "action": {
            "toolName": "set_replicas_within_bounds",
            "normalizedParameters": {
                "replicas": 4,
                "minReplicas": 1,
                "maxReplicas": 5,
                "hpaReviewed": False,
            },
        },
    }
    deployment = {
        "metadata": {"namespace": "team-a", "name": "web-a", "uid": "deployment-uid-a"},
        "spec": {"replicas": 2},
    }
    hpa = {
        "metadata": {"namespace": "team-a", "name": "web-hpa", "uid": "hpa-uid-a"},
        "spec": {
            "scaleTargetRef": {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "name": "web-a",
            }
        },
    }

    assert matching_hpas_for_deployment([hpa], plan["target"])[0]["metadata"]["name"] == "web-hpa"
    with pytest.raises(AiopsCoreError):
        build_mutation_request(plan, live_target=deployment, hpas=[hpa])

    reviewed_plan = {
        **plan,
        "action": {
            **plan["action"],
            "normalizedParameters": {
                **plan["action"]["normalizedParameters"],
                "hpaReviewed": True,
            },
        },
    }
    request = build_mutation_request(reviewed_plan, live_target=deployment, hpas=[hpa])

    assert request.path.endswith("/deployments/web-a/scale")
    assert request.body == {"spec": {"replicas": 4}}


def test_core_action_rollback_uses_owned_replicaset_revision() -> None:
    plan = {
        "target": {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "namespace": "team-a",
            "name": "web-a",
            "uid": "deployment-uid-a",
        },
        "action": {
            "toolName": "rollback_deployment_to_revision",
            "normalizedParameters": {"revision": 2},
        },
    }
    deployment = {
        "metadata": {
            "namespace": "team-a",
            "name": "web-a",
            "uid": "deployment-uid-a",
            "annotations": {"deployment.kubernetes.io/revision": "3"},
        },
        "spec": {"template": {"metadata": {"labels": {"app": "web"}}}},
    }
    replica_set = {
        "metadata": {
            "namespace": "team-a",
            "name": "web-a-abc",
            "uid": "rs-uid-a",
            "annotations": {"deployment.kubernetes.io/revision": "2"},
            "ownerReferences": [{"uid": "deployment-uid-a", "controller": True}],
        },
        "spec": {
            "template": {
                "metadata": {
                    "labels": {"app": "web", "pod-template-hash": "abc"},
                    "annotations": {"deployment.kubernetes.io/revision": "2"},
                },
                "spec": {"containers": [{"name": "web", "image": "example/web:v1"}]},
            }
        },
    }

    request = build_rollback_request(plan, deployment, [replica_set])
    template = request.body["spec"]["template"]

    assert request.path.endswith("/deployments/web-a")
    assert template["metadata"]["labels"] == {"app": "web"}
    assert template["metadata"]["annotations"]["aiops.komsco/rollback-revision"] == "2"
    assert "pod-template-hash" not in str(template)


def test_core_action_hpa_bounds_blocks_unreviewed_max_increase() -> None:
    plan = {
        "target": {
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "namespace": "team-a",
            "name": "web-hpa",
            "uid": "hpa-uid-a",
        },
        "action": {
            "toolName": "set_hpa_bounds",
            "normalizedParameters": {
                "minReplicas": 2,
                "maxReplicas": 8,
                "allowMaxIncrease": False,
            },
        },
    }
    hpa = {
        "metadata": {"namespace": "team-a", "name": "web-hpa", "uid": "hpa-uid-a"},
        "spec": {"minReplicas": 1, "maxReplicas": 5},
    }

    with pytest.raises(AiopsCoreError):
        build_hpa_bounds_request(plan, hpa)

    approved_plan = {
        **plan,
        "action": {
            **plan["action"],
            "normalizedParameters": {
                **plan["action"]["normalizedParameters"],
                "allowMaxIncrease": True,
            },
        },
    }
    request = build_hpa_bounds_request(approved_plan, hpa)

    assert request.path.endswith("/horizontalpodautoscalers/web-hpa")
    assert request.body == {"spec": {"minReplicas": 2, "maxReplicas": 8}}


def test_action_proposal_digest_uses_runtime_target_not_hardcoded_target() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    request = ActionProposalCreate(
        toolName="rollout_restart_deployment",
        target=ActionTarget(
            apiVersion="apps/v1",
            kind="Deployment",
            namespace="team-a",
            name="web-a",
            uid="deployment-uid-a",
        ),
        parameters={"restartedAt": "2026-06-21T00:00:00Z"},
    )
    changed_target_request = request.model_copy(
        update={
            "target": ActionTarget(
                apiVersion="apps/v1",
                kind="Deployment",
                namespace="team-b",
                name="web-b",
                uid="deployment-uid-b",
            )
        }
    )
    record = build_action_proposal_record(request, subject)
    changed_record = build_action_proposal_record(changed_target_request, subject)
    candidate = record["spec"]["candidateActionRequest"]
    changed_candidate = changed_record["spec"]["candidateActionRequest"]

    assert candidate["target"]["namespace"] == "team-a"
    assert candidate["target"]["name"] == "web-a"
    assert candidate_action_request_digest(candidate) != candidate_action_request_digest(changed_candidate)


def test_action_access_review_request_is_derived_from_sealed_plan_target() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    proposal = build_action_proposal_record(
        ActionProposalCreate(
            toolName="set_hpa_bounds",
            target=ActionTarget(
                apiVersion="autoscaling/v2",
                kind="HorizontalPodAutoscaler",
                namespace="dynamic-team",
                name="web-hpa",
                uid="hpa-uid-a",
            ),
            parameters={"minReplicas": 2, "maxReplicas": 5},
        ),
        subject,
    )
    plan_record = build_sealed_action_plan_record(proposal)
    review_request = build_action_access_review_request(plan_record["spec"]["sealedActionPlan"])
    attributes = review_request["spec"]["resourceAttributes"]

    assert attributes == {
        "group": "autoscaling",
        "resource": "horizontalpodautoscalers",
        "verb": "patch",
        "namespace": "dynamic-team",
        "name": "web-hpa",
    }


def test_sealed_action_plan_digest_excludes_mutable_status_and_digest_fields() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    proposal = build_action_proposal_record(
        ActionProposalCreate(
            toolName="rollout_restart_deployment",
            target=ActionTarget(
                apiVersion="apps/v1",
                kind="Deployment",
                namespace="team-a",
                name="web-a",
                uid="deployment-uid-a",
            ),
            parameters={"restartedAt": "2026-06-21T00:00:00Z"},
        ),
        subject,
    )
    plan_record = build_sealed_action_plan_record(proposal)
    plan = plan_record["spec"]["sealedActionPlan"]
    plan_digest = plan["digest"]["planDigest"]
    mutable_copy = {
        **plan,
        "digest": {"planDigest": "sha256:tampered"},
        "executionStatus": {"phase": "mutation_succeeded"},
    }

    assert sealed_action_plan_digest(plan) == plan_digest
    assert sealed_action_plan_digest(mutable_copy) == plan_digest
    grant_ref = plan["safety"]["planValidationGrantRef"]
    assert grant_ref["grantId"].startswith("validation-")
    assert grant_ref["grantDigest"].startswith("sha256:")
    assert grant_ref["bearerGrantStored"] is False


def test_execution_evidence_freshness_rejects_expired_evidence_refs() -> None:
    expired = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    plan = {
        "approvalPresentation": {
            "evidenceRefs": [
                {
                    "evidenceId": "ev-expired",
                    "requiredFreshUntil": expired,
                }
            ]
        }
    }

    with pytest.raises(HTTPException) as exc_info:
        validate_execution_evidence_freshness(plan)
    assert exc_info.value.status_code == 409
    assert "evidence is no longer fresh" in str(exc_info.value.detail)
    assert "create a new plan and approval" in str(exc_info.value.detail)


def test_actions_api_rejects_stale_approval_and_blocks_disabled_execution() -> None:
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()
    APPROVAL_DECISIONS.clear()
    EXECUTION_RECORDS.clear()

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        headers = {"Authorization": "Bearer test-token"}
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            registry_response = await client.get("/v1/actions/registry", headers=headers)
            proposal_response = await client.post(
                "/v1/actions/proposals",
                headers=headers,
                json={
                    "incidentId": "inc-action",
                    "runId": "run-action",
                    "toolName": "rollout_restart_deployment",
                    "target": {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "namespace": "team-a",
                        "name": "web-a",
                        "uid": "deployment-uid-a",
                    },
                    "parameters": {"restartedAt": "2026-06-21T00:00:00Z"},
                },
            )
            proposal_id = proposal_response.json()["metadata"]["name"]
            plan_response = await client.post(
                "/v1/actions/plans",
                headers=headers,
                json={"proposalId": proposal_id},
            )
            plan_payload = plan_response.json()
            plan_id = plan_payload["metadata"]["name"]
            plan_digest = plan_payload["spec"]["sealedActionPlan"]["digest"]["planDigest"]
            stale_approval_response = await client.post(
                "/v1/actions/approvals",
                headers=headers,
                json={"planId": plan_id, "expectedPlanDigest": "sha256:stale"},
            )
            approval_response = await client.post(
                "/v1/actions/approvals",
                headers=headers,
                json={"planId": plan_id, "expectedPlanDigest": plan_digest},
            )
            approval_id = approval_response.json()["metadata"]["name"]
            execution_response = await client.post(
                "/v1/actions/execute",
                headers=headers,
                json={
                    "approvalId": approval_id,
                    "planId": plan_id,
                    "expectedPlanDigest": plan_digest,
                },
            )

        assert registry_response.status_code == 200
        assert registry_response.json()["spec"]["mutationsEnabled"] is False
        assert proposal_response.status_code == 200
        assert plan_response.status_code == 200
        assert stale_approval_response.status_code == 409
        assert approval_response.status_code == 200
        approval_decision = approval_response.json()["spec"]["approvalDecision"]
        assert approval_decision["authorizationAttestationRef"]["bearerAttestationStored"] is False
        assert approval_decision["authorizationAttestationRef"]["attestationDigest"].startswith("sha256:")
        assert approval_decision["kubernetesAuthorization"]["ssarDecision"] == "allowed"
        assert execution_response.status_code == 403
        assert execution_response.json()["detail"]["mutationOutcome"]["status"] == "mutation_disabled"
        assert len(EXECUTION_RECORDS) == 1
        execution_record = next(iter(EXECUTION_RECORDS.values()))
        assert execution_record["spec"]["executionGrantRef"]["bearerGrantStored"] is False
        assert "claims" not in execution_record["spec"]["executionGrantRef"]
        assert execution_record["spec"]["executionAuthorization"]["allowed"] is True

    asyncio.run(run())


def test_medium_risk_action_requires_separation_of_duties() -> None:
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        headers = {"Authorization": "Bearer test-token"}
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            proposal_response = await client.post(
                "/v1/actions/proposals",
                headers=headers,
                json={
                    "toolName": "set_replicas_within_bounds",
                    "target": {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "namespace": "team-a",
                        "name": "web-a",
                        "uid": "deployment-uid-a",
                    },
                    "parameters": {"replicas": 2, "minReplicas": 1, "maxReplicas": 3},
                },
            )
            proposal_id = proposal_response.json()["metadata"]["name"]
            plan_response = await client.post(
                "/v1/actions/plans",
                headers=headers,
                json={"proposalId": proposal_id},
            )
            plan_payload = plan_response.json()
            approval_response = await client.post(
                "/v1/actions/approvals",
                headers=headers,
                json={
                    "planId": plan_payload["metadata"]["name"],
                    "expectedPlanDigest": plan_payload["spec"]["sealedActionPlan"]["digest"]["planDigest"],
                },
            )

        assert proposal_response.status_code == 200
        assert plan_response.status_code == 200
        assert approval_response.status_code == 409
        assert "separation of duties" in approval_response.json()["detail"]

    asyncio.run(run())


def test_approved_different_subject_can_execute_with_product_access(monkeypatch) -> None:
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()
    APPROVAL_DECISIONS.clear()
    EXECUTION_RECORDS.clear()
    requester = safe_subject({"username": "requester@example.com", "uid": "uid-requester", "groups": ["ops"]})
    approver = safe_subject({"username": "approver@example.com", "uid": "uid-approver", "groups": ["ops"]})

    async def fake_subject_review(user_auth_header: str) -> dict:
        if user_auth_header == "Bearer requester-token":
            return requester
        return approver

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {"allowed": True, "enabled": True, "required": False}

    async def fake_action_access_review(_user_auth_header: str, _plan: dict) -> dict:
        return {"allowed": True, "enabled": True, "resourceAttributes": {"resource": "deployments"}}

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "fetch_action_access_review", fake_action_access_review)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        requester_headers = {"Authorization": "Bearer requester-token"}
        approver_headers = {"Authorization": "Bearer approver-token"}
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            proposal_response = await client.post(
                "/v1/actions/proposals",
                headers=requester_headers,
                json={
                    "toolName": "set_replicas_within_bounds",
                    "target": {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "namespace": "team-a",
                        "name": "web-a",
                        "uid": "deployment-uid-a",
                    },
                    "parameters": {"replicas": 2, "minReplicas": 1, "maxReplicas": 3},
                },
            )
            proposal_id = proposal_response.json()["metadata"]["name"]
            plan_response = await client.post(
                "/v1/actions/plans",
                headers=requester_headers,
                json={"proposalId": proposal_id},
            )
            plan_payload = plan_response.json()
            plan_digest = plan_payload["spec"]["sealedActionPlan"]["digest"]["planDigest"]
            approval_response = await client.post(
                "/v1/actions/approvals",
                headers=approver_headers,
                json={"planId": plan_payload["metadata"]["name"], "expectedPlanDigest": plan_digest},
            )
            execution_response = await client.post(
                "/v1/actions/execute",
                headers=approver_headers,
                json={
                    "approvalId": approval_response.json()["metadata"]["name"],
                    "planId": plan_payload["metadata"]["name"],
                    "expectedPlanDigest": plan_digest,
                },
            )

        assert proposal_response.status_code == 200
        assert plan_response.status_code == 200
        assert approval_response.status_code == 200
        assert execution_response.status_code == 403
        assert execution_response.json()["detail"]["mutationOutcome"]["status"] == "mutation_disabled"

    asyncio.run(run())


def test_runbook_registry_allows_only_runbook_defined_action_steps() -> None:
    assert RUNBOOK_REGISTRY_DIGEST.startswith("sha256:")
    assert set(RUNBOOK_REGISTRY_ENTRIES) == {
        "deployment_rollout_restart_v1",
        "deployment_bounded_scale_v1",
        "controller_owned_unhealthy_pod_eviction_v1",
        "deployment_rollout_rollback_v1",
        "hpa_bounds_adjustment_v1",
    }
    for runbook in RUNBOOK_REGISTRY_ENTRIES.values():
        for step in runbook["allowedSteps"]:
            assert step["toolName"] in ACTION_REGISTRY_ENTRIES
    assert "delete_pod" not in str(RUNBOOK_REGISTRY_ENTRIES)
    assert "run_command" not in str(RUNBOOK_REGISTRY_ENTRIES)


def test_runbook_plan_uses_runtime_target_and_denies_platform_namespace_without_policy() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    request = RunbookPlanCreate(
        runbookId="deployment_rollout_restart_v1",
        target=ActionTarget(
            apiVersion="apps/v1",
            kind="Deployment",
            namespace="openshift-example",
            name="operator-managed-app",
            uid="deployment-uid-a",
        ),
        parameters={"restartedAt": "2026-06-21T00:00:00Z"},
    )

    record = build_runbook_plan_record(request, subject)

    assert record["metadata"]["name"].startswith("runbook-plan-")
    assert record["spec"]["target"]["namespace"] == "openshift-example"
    assert record["spec"]["policyResult"]["decision"] == "denied"
    assert "allowPlatformNamespace=true" in record["spec"]["policyResult"]["failures"][0]
    assert record["spec"]["stepPlans"][0]["candidateActionRequest"]["target"]["name"] == "operator-managed-app"


def test_preapproved_patch_schema_rejects_undocumented_or_out_of_bounds_fields() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    valid_request = PatchPreapprovedFieldCreate(
        fieldSchemaId="deployment_progress_deadline_seconds_v1",
        target=ActionTarget(
            apiVersion="apps/v1",
            kind="Deployment",
            namespace="team-a",
            name="web-a",
            uid="deployment-uid-a",
        ),
        value=120,
    )
    record = build_preapproved_patch_record(valid_request, subject)

    assert record["metadata"]["name"].startswith("prepatch-")
    assert record["spec"]["patch"] == {
        "op": "replace",
        "path": "/spec/progressDeadlineSeconds",
        "value": 120,
    }
    assert record["spec"]["status"]["mutationSubmitted"] is False

    with pytest.raises(HTTPException):
        build_preapproved_patch_record(
            valid_request.model_copy(update={"fieldSchemaId": "deployment_unreviewed_field_v1"}),
            subject,
        )
    with pytest.raises(HTTPException):
        build_preapproved_patch_record(valid_request.model_copy(update={"value": 999999}), subject)


def test_runbook_and_preapproved_patch_apis_expose_foundation_records() -> None:
    RUNBOOK_PLANS.clear()
    PREAPPROVED_PATCH_REQUESTS.clear()

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        headers = {"Authorization": "Bearer test-token"}
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            registry_response = await client.get("/v1/runbooks/registry", headers=headers)
            plan_response = await client.post(
                "/v1/runbooks/plans",
                headers=headers,
                json={
                    "runbookId": "deployment_rollout_restart_v1",
                    "target": {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "namespace": "team-a",
                        "name": "web-a",
                        "uid": "deployment-uid-a",
                    },
                    "parameters": {"restartedAt": "2026-06-21T00:00:00Z"},
                },
            )
            patch_response = await client.post(
                "/v1/runbooks/patch-preapproved-field",
                headers=headers,
                json={
                    "fieldSchemaId": "deployment_revision_history_limit_v1",
                    "target": {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "namespace": "team-a",
                        "name": "web-a",
                        "uid": "deployment-uid-a",
                    },
                    "value": 5,
                },
            )

        assert registry_response.status_code == 200
        assert registry_response.json()["spec"]["digest"] == RUNBOOK_REGISTRY_DIGEST
        assert plan_response.status_code == 200
        assert plan_response.json()["spec"]["status"]["phase"] == "waiting_for_approval"
        assert patch_response.status_code == 200
        assert patch_response.json()["spec"]["status"]["mutationSubmitted"] is False
        assert len(RUNBOOK_PLANS) == 1
        assert len(PREAPPROVED_PATCH_REQUESTS) == 1

    asyncio.run(run())


def test_break_glass_profile_is_disabled_by_default_and_fixed_entrypoint_only() -> None:
    profile = BREAK_GLASS_PROFILES["node_readonly_triage_v1"]

    assert BREAK_GLASS_PROFILE_DIGEST.startswith("sha256:")
    assert profile["enabled"] is False
    assert profile["imageDigest"] == "not-configured"
    assert profile["arbitraryCommandInputAllowed"] is False
    assert profile["fixedEntrypoint"] == [
        "/aiops/breakglass-runner",
        "--profile",
        "node-readonly-triage",
    ]
    assert profile["cleanup"]["activeDeadlineSeconds"] == 300
    assert profile["cleanup"]["ttlSecondsAfterFinished"] == 600
    assert profile["network"]["egressPolicy"] == "deny-except-controller"


def test_break_glass_request_records_disabled_status_without_job_submission() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    request = BreakGlassRequestCreate(
        profileId="node_readonly_triage_v1",
        targetNode=BreakGlassTargetNode(name="worker-a.example.com", uid="node-uid-a"),
        justification="Need emergency read-only node diagnostics for incident review.",
    )

    record = build_break_glass_request_record(request, subject)

    assert record["metadata"]["name"].startswith("breakglass-")
    assert record["spec"]["profile"]["enabled"] is False
    assert record["spec"]["profile"]["arbitraryCommandInputAllowed"] is False
    assert record["spec"]["status"]["phase"] == "disabled"
    assert record["spec"]["status"]["jobSubmitted"] is False
    assert record["spec"]["jobTemplateConstraints"]["scheduling"]["targetNodeName"] == "worker-a.example.com"
    assert record["spec"]["jobTemplateConstraints"]["scheduling"]["targetNodeUid"] == "node-uid-a"
    assert record["spec"]["audit"]["stream"] == "aiopsBreakGlassAudit"


def test_break_glass_api_rejects_arbitrary_command_input_and_records_request() -> None:
    BREAK_GLASS_REQUESTS.clear()

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        headers = {"Authorization": "Bearer test-token"}
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            profiles_response = await client.get("/v1/breakglass/profiles", headers=headers)
            command_response = await client.post(
                "/v1/breakglass/requests",
                headers=headers,
                json={
                    "profileId": "node_readonly_triage_v1",
                    "targetNode": {"name": "worker-a.example.com", "uid": "node-uid-a"},
                    "justification": "Need emergency read-only node diagnostics for incident review.",
                    "command": "nsenter --mount=/proc/1/ns/mnt sh",
                },
            )
            request_response = await client.post(
                "/v1/breakglass/requests",
                headers=headers,
                json={
                    "profileId": "node_readonly_triage_v1",
                    "targetNode": {"name": "worker-a.example.com", "uid": "node-uid-a"},
                    "justification": "Need emergency read-only node diagnostics for incident review.",
                },
            )

        assert profiles_response.status_code == 200
        assert profiles_response.json()["spec"]["enabled"] is False
        assert command_response.status_code == 422
        assert request_response.status_code == 200
        assert request_response.json()["spec"]["status"]["phase"] == "disabled"
        assert request_response.json()["spec"]["status"]["jobSubmitted"] is False
        assert len(BREAK_GLASS_REQUESTS) == 1

    asyncio.run(run())


def test_rag_context_detail_and_answer_citation_show_sources_without_raw_dump() -> None:
    results = [
        {
            "contentPreview": "업로드 문서 preview",
            "documentId": "user-upload:abc123",
            "score": 0.91,
            "sourceType": "user-upload",
            "sourceUri": "upload://user-upload:abc123/ops.md#chunk-0",
            "title": "ops.md",
        }
    ]

    detail = build_rag_context_detail(results, "ok")
    citation = build_rag_answer_citation_text(results)

    assert "Gateway-collected RAG evidence" in detail
    assert "ops.md" in detail
    assert "user-upload" in detail
    assert "업로드 문서 preview" in detail
    assert "[ RAG 근거 ]" in citation
    assert "upload://user-upload:abc123/ops.md#chunk-0" in citation
    assert "rawContent" not in citation
