import asyncio
import json
import httpx
from fastapi import HTTPException
import komsco_ai_gateway.main as gateway_main
from komsco_ai_gateway.main import ACTION_PROPOSALS, APPROVAL_DECISIONS, AUDIT_RECORDS, EXECUTION_RECORDS, SEALED_ACTION_PLANS, DIAGNOSTIC_REQUESTS, app, build_aiops_overview
from komsco_ai_gateway.security import safe_subject


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
    assert overview["spec"]["controlTower"]["statusLabel"] == "회사 OCP 승인 실행 관제 정상"
    assert overview["spec"]["dataSources"][0]["name"] == "nodes"
    assert overview["spec"]["monitoring"]["probe"]["resultCount"] == 7
    assert overview["spec"]["monitoring"]["urls"]["thanosConfigured"] is True
    assert overview["spec"]["safety"]["executionDefault"] is True


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
        assert payload["spec"]["controlTower"]["mode"] == "execute"
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
        "policy": {"decision": "allow_evidence_collection"},
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


def test_aiops_events_api_merges_kubernetes_events_pod_signals_and_records(monkeypatch) -> None:
    AUDIT_RECORDS.clear()
    DIAGNOSTIC_REQUESTS.clear()
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()
    APPROVAL_DECISIONS.clear()
    EXECUTION_RECORDS.clear()

    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    AUDIT_RECORDS["audit-runtime"] = {
        "schemaVersion": "v1",
        "action": "chat_request_accepted",
        "auditId": "audit-runtime",
        "incidentId": "incident-runtime",
        "policy": {"decision": "allow_evidence_collection"},
        "requestId": "request-runtime",
        "runId": "run-runtime",
        "subject": subject,
        "target": {"messageLength": 10},
        "timestamp": "2026-06-21T00:02:00Z",
    }
    EXECUTION_RECORDS["execution-runtime"] = {
        "apiVersion": "aiops.komsco/v1",
        "kind": "ExecutionRecord",
        "metadata": {"name": "execution-runtime", "createdAt": "2026-06-21T00:01:00Z"},
        "spec": {
            "mutationOutcome": {"status": "mutation_succeeded"},
            "target": {"kind": "Deployment", "name": "web", "namespace": "team-a"},
        },
        "subject": subject,
    }

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return subject

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {"allowed": True}

    async def fake_fetch_ocp_json(_client, path, _authorization, **_kwargs):
        if path.startswith("/api/v1/events"):
            return {
                "items": [
                    {
                        "eventTime": "2026-06-21T00:03:00Z",
                        "involvedObject": {"kind": "Pod", "name": "web-1", "namespace": "team-a"},
                        "message": "Back-off restarting failed container",
                        "metadata": {"uid": "event-1", "namespace": "team-a"},
                        "reason": "BackOff",
                        "type": "Warning",
                    }
                ]
            }
        if path == "/api/v1/pods":
            return {
                "items": [
                    {
                        "metadata": {"creationTimestamp": "2026-06-21T00:00:00Z", "name": "web-1", "namespace": "team-a"},
                        "status": {
                            "containerStatuses": [
                                {
                                    "lastState": {"terminated": {"finishedAt": "2026-06-21T00:02:30Z", "reason": "Error"}},
                                    "name": "web",
                                    "ready": False,
                                    "restartCount": 5,
                                    "state": {"waiting": {"reason": "CrashLoopBackOff"}},
                                }
                            ],
                            "phase": "Running",
                        },
                    },
                    {
                        "metadata": {
                            "creationTimestamp": "2026-06-21T00:00:00Z",
                            "labels": {
                                "buildconfig": "komsco-ai-console-plugin",
                                "openshift.io/build.name": "komsco-ai-console-plugin-8",
                            },
                            "name": "komsco-ai-console-plugin-8-build",
                            "namespace": "cywell-aiops",
                        },
                        "status": {
                            "containerStatuses": [
                                {
                                    "name": "docker-build",
                                    "ready": False,
                                    "restartCount": 0,
                                    "state": {"terminated": {"reason": "Error"}},
                                }
                            ],
                            "phase": "Failed",
                        },
                    },
                ]
            }
        return None

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.test:6443")
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fake_fetch_ocp_json)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/v1/aiops/events",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["kind"] == "AIOpsEventFeed"
        assert {"AIOps Gateway", "Kubernetes Event", "Pod status"}.issubset(set(payload["spec"]["sources"]))
        items = payload["spec"]["items"]
        assert any(item["source"] == "Kubernetes Event" and item["severity"] in {"warn", "risk"} for item in items)
        assert any(item["source"] == "Pod status" and item["target"] == "team-a/Pod/web-1" for item in items)
        assert not any(item["target"] == "cywell-aiops/Pod/komsco-ai-console-plugin-8-build" for item in items)
        assert any(item["source"] == "AIOps Gateway" and item["title"] == "chat_request_accepted" for item in items)
        assert "Bearer" not in json.dumps(payload)

    asyncio.run(run())


def test_aiops_status_api_degrades_without_exposing_records_when_subject_review_times_out(
    monkeypatch,
) -> None:
    AUDIT_RECORDS.clear()
    DIAGNOSTIC_REQUESTS.clear()
    EXECUTION_RECORDS.clear()
    record_subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    DIAGNOSTIC_REQUESTS["diag-runtime"] = {
        "apiVersion": "aiops.komsco/v1",
        "kind": "DiagnosticRequestRecord",
        "metadata": {"name": "diag-runtime", "createdAt": "2026-06-21T00:00:00Z"},
        "spec": {"status": {"phase": "collector_succeeded"}},
        "subject": record_subject,
    }
    EXECUTION_RECORDS["execution-runtime"] = {
        "apiVersion": "aiops.komsco/v1",
        "kind": "ExecutionRecord",
        "metadata": {"name": "execution-runtime", "createdAt": "2026-06-21T00:01:00Z"},
        "spec": {"mutationOutcome": {"status": "mutation_succeeded"}},
        "subject": record_subject,
    }
    monkeypatch.setattr(
        gateway_main,
        "OLS_STREAM_STATUS",
        {
            "streamProbe": "succeeded",
            "lastStatus": "succeeded",
            "lastContextDigest": "sha256:test",
            "lastStartedAt": "2026-06-21T00:00:00Z",
            "lastCompletedAt": "2026-06-21T00:00:05Z",
            "lastError": "",
            "fallbackActive": False,
        },
    )

    async def failing_subject_review(_user_auth_header: str) -> dict:
        raise HTTPException(
            status_code=504,
            detail={
                "code": "openshift_api_unavailable",
                "operation": "self_subject_review",
                "message": "synthetic timeout",
            },
        )

    async def product_access_review_should_not_run(_user_auth_header: str) -> dict:
        raise AssertionError("product access review should be skipped when subject review fails")

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", failing_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", product_access_review_should_not_run)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/v1/aiops/status",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        payload = response.json()
        spec = payload["spec"]
        assert spec["accessReviewStatus"]["status"] == "degraded"
        assert spec["accessReviewStatus"]["recordsVisible"] is False
        assert spec["accessReviewStatus"]["subjectReview"]["statusCode"] == 504
        assert spec["safetyContract"]["lightspeedStatus"]["streamProbe"] == "succeeded"
        assert spec["safetyContract"]["lightspeedStatus"]["fallbackActive"] is False
        assert spec["records"]["diagnosticRequests"] == []
        assert spec["records"]["executionRecords"] == []
        assert "diag-runtime" not in json.dumps(payload, ensure_ascii=False)
        assert "execution-runtime" not in json.dumps(payload, ensure_ascii=False)
        assert "Bearer" not in json.dumps(payload, ensure_ascii=False)

    asyncio.run(run())
