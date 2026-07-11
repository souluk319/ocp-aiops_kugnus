import asyncio
import json
import httpx
import komsco_ai_gateway.main as gateway_main
from komsco_ai_gateway.host_diagnostics_collector import collect_host_diagnostics
from komsco_ai_gateway.host_diagnostics_controller import build_diagnostic_job_manifest
from komsco_ai_gateway.main import DIAGNOSTIC_REQUESTS, HOST_DIAGNOSTIC_COLLECTOR_DIGEST, HOST_DIAGNOSTIC_COLLECTORS, app, build_diagnostic_request_candidate, build_diagnostic_request_record, DiagnosticEvidencePolicy, DiagnosticLimits, DiagnosticRequestCreate, DiagnosticTargetNode, DiagnosticTimeRange, diagnostic_request_digest
from komsco_ai_gateway.security import safe_subject


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
