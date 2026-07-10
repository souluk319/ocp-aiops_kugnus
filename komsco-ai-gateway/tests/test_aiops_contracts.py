from komsco_ai_gateway.aiops_contracts import (
    assert_evidence_check_tool_plan,
    build_adapter_registry,
    build_rca_context,
    build_runtime_safety_contract,
    build_runtime_tool_plan,
    create_evidence_status,
    resolve_tool_plan_adapters,
)


def test_aiops_contract_rejects_mutating_tool_plan() -> None:
    result = assert_evidence_check_tool_plan(
        {
            "execution_policy": {"mode": "evidence_check"},
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


def test_runtime_safety_contract_defaults_to_evidence_check() -> None:
    contract = build_runtime_safety_contract(
        mutations_enabled=False,
        unrestricted_commands_enabled=False,
        diagnostics_enabled=False,
        record_store_enabled=False,
    )

    assert contract["mode"] == "evidence_check"
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
        "gateway_rag_runbook_search",
    }
    resolution_by_tool = {item["tool"]: item for item in resolutions}
    assert resolution_by_tool["openshift_event_lookup"]["status"] == "resolved"
    assert resolution_by_tool["openshift_pod_status_lookup"]["resolved"] is True
    assert resolution_by_tool["openshift_pod_log_pattern_probe"]["resolved"] is True
    assert resolution_by_tool["openshift_node_status_lookup"]["status"] == "resolved"
    assert resolution_by_tool["openshift_alert_lookup"]["status"] == "resolved"
    assert resolution_by_tool["openshift_metric_query"]["status"] == "resolved"
    assert resolution_by_tool["gateway_rag_runbook_search"]["status"] == "resolved"
    assert {item["adapter"] for item in resolutions} == {"OpenShift", "AI Gateway"}
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


def test_runtime_tool_plan_generates_controlled_execution_pod_restart_rca() -> None:
    plan = build_runtime_tool_plan(
        "어제 새벽 default 네임스페이스 pod가 왜 재시작됐어?",
        execution_mode="execute",
    )

    assert plan["kind"] == "ToolPlan"
    assert plan["task_type"] == "pod_restart_rca"
    assert plan["target"]["namespace"] == "default"
    assert plan["execution_policy"]["mode"] == "controlled_execution"
    assert plan["validation"]["ok"] is True
    assert len(plan["adapter_resolution"]) >= 3
    resolution_by_tool = {item["tool"]: item for item in plan["adapter_resolution"]}
    assert resolution_by_tool["openshift_pod_status_lookup"]["resolved"] is True
    assert resolution_by_tool["openshift_event_lookup"]["resolved"] is True
    assert resolution_by_tool["openshift_node_status_lookup"]["status"] == "resolved"
    assert resolution_by_tool["openshift_alert_lookup"]["status"] == "resolved"
    assert resolution_by_tool["openshift_metric_query"]["status"] == "resolved"
    assert resolution_by_tool["gateway_rag_runbook_search"]["status"] == "resolved"
    assert {step["adapter"] for step in plan["tool_plan"]} == {"OpenShift", "AI Gateway"}
    assert {step["verb"] for step in plan["tool_plan"]} <= {"get", "list", "watch"}
    missing_types = {item["type"] for item in plan["missing_evidence"]}
    assert "clusteroperator" in missing_types
    assert "runbook" not in missing_types
    assert {"event", "pod_log", "snapshot"}.isdisjoint(missing_types)
    assert {"node", "alert", "metric"}.isdisjoint(missing_types)


def test_runtime_tool_plan_promotes_current_pod_screen_to_rca() -> None:
    plan = build_runtime_tool_plan(
        "현재 화면 기준으로 안전한 확인 절차를 단계별로 제안해줘.",
        page_context={
            "namespace": "openshift-marketplace",
            "resourceKind": "Pod",
            "resourceName": "appscan360-catalog-457gn",
            "pathname": "/k8s/ns/openshift-marketplace/pods/appscan360-catalog-457gn",
        },
        execution_mode="execute",
    )

    assert plan["task_type"] == "pod_screen_rca"
    assert plan["target"]["namespace"] == "openshift-marketplace"
    assert plan["target"]["resourceKind"] == "Pod"
    assert plan["target"]["resourceName"] == "appscan360-catalog-457gn"
    assert plan["execution_policy"]["mode"] == "controlled_execution"
    assert plan["validation"]["ok"] is True
    assert {step["tool"] for step in plan["tool_plan"]} >= {
        "openshift_pod_status_lookup",
        "openshift_pod_snapshot_lookup",
        "openshift_event_lookup",
        "openshift_deployment_lookup",
        "gateway_rag_runbook_search",
    }
    assert {step["verb"] for step in plan["tool_plan"]} <= {"get", "list", "watch"}


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
                "summary": "Pod 상태/재시작 조회 결과 수집 완료",
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
    assert not any(item["type"] == "runbook" for item in context["evidence"]["missing"])
    assert context["confidence"]["level"] == "evidence_based"
    assert context["analysisPlan"]["mode"] == "evidence_first"
    assert context["analysisPlan"]["answerContract"]["format"] == "operations_rca_report"
    assert context["analysisPlan"]["answerContract"]["mustNotInventEvidence"] is True
    assert context["analysisPlan"]["answerContract"]["mustNotExposeRawToolPlanInDefaultAnswer"] is True
    assert context["analysisPlan"]["answerContract"]["supportedExecutionModes"] == [
        "evidence_check",
        "controlled_execution",
        "unrestricted",
    ]
    assert "원인 후보" in context["analysisPlan"]["answerContract"]["requiredSections"]
    assert "확인 결과" in context["analysisPlan"]["answerContract"]["requiredSections"]
    step_status = {
        item["evidenceType"]: item
        for item in context["analysisPlan"]["evidenceCollectionSteps"]
    }
    query_plan = context["answerExperience"]["queryPlan"]
    assert query_plan[0]["status"] in {"collected", "not_attempted", "missing"}
    assert step_status["pod_status"]["status"] == "collected"
    assert step_status["pod_status"]["evidenceId"] == "ev-abc"
    assert step_status["event"]["status"] == "not_attempted"
    assert step_status["pod_log"]["status"] == "not_attempted"
    assert step_status["node"]["status"] == "not_attempted"
    assert step_status["alert"]["status"] == "not_attempted"
    assert step_status["metric"]["status"] == "not_attempted"
    assert step_status["runbook"]["status"] == "not_attempted"


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
                "summary": "Node 상태 RCA 조회 결과 수집 완료",
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
                "summary": "Restart metric RCA 조회 결과 수집 불가",
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
                "summary": "Pod 상태/재시작 조회 결과 수집 완료",
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
                "summary": "clusteroperator 상태 조회 결과 수집 완료",
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
