import asyncio
import httpx
from komsco_ai_gateway.main import EVIDENCE_RECORDS, app, build_evidence_reference_events
from komsco_ai_gateway.security import build_evidence_reference, safe_subject


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
        "summary": "Pod 상태/재시작 조회 결과 수집 완료",
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
    assert events[1]["result"]["summary"] == "Pod 상태/재시작 조회 결과 수집 완료"


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
