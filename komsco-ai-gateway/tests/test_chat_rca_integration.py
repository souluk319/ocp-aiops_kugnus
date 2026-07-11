import asyncio
import json

import httpx

import komsco_ai_gateway.main as gateway_main
from komsco_ai_gateway.main import CHAT_TRANSCRIPTS, EVIDENCE_RECORDS, app
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


def test_chat_stream_persists_chat_transcript_record(monkeypatch, tmp_path) -> None:
    CHAT_TRANSCRIPTS.clear()
    EVIDENCE_RECORDS.clear()
    gateway_main.LAST_RCA_CONTEXT = None
    transcript_jsonl_path = tmp_path / "chat-transcripts.jsonl"

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_ols_stream(*_args, **_kwargs):
        yield {
            "type": "text",
            "content": "현재 확인된 OpenShift 상태를 기준으로 답변합니다.",
        }
        yield {"type": "end", "conversationId": "conv-transcript-test"}

    async def fake_rag_search(*_args, **_kwargs):
        return ("not_configured", "RAG backend not configured", [])

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "call_ols_stream", fake_ols_stream)
    monkeypatch.setattr(gateway_main, "search_pgvector_runbooks", fake_rag_search)
    monkeypatch.setattr(gateway_main, "CHAT_TRANSCRIPT_JSONL_PATH", str(transcript_jsonl_path))

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "conversationId": "conv-transcript-test",
                    "message": "최근 OpenShift 경고를 근거와 추가 확인으로 나눠줘",
                    "runId": "run-transcript-test",
                },
            )
            status_response = await client.get(
                "/v1/aiops/status",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        assert status_response.status_code == 200
        assert len(CHAT_TRANSCRIPTS) == 1
        transcript = next(iter(CHAT_TRANSCRIPTS.values()))
        assert transcript["kind"] == "ChatTranscriptRecord"
        assert transcript["spec"]["conversationId"] == "conv-transcript-test"
        assert transcript["spec"]["runId"] == "run-transcript-test"
        assert "최근 OpenShift 경고" in transcript["spec"]["userMessage"]
        assert "현재 확인된 OpenShift 상태" in transcript["spec"]["assistantAnswer"]
        assert transcript["spec"]["observedState"]["rcaContextDigest"].startswith("sha256:")
        assert transcript["spec"]["observedState"]["taskType"]
        assert transcript["spec"]["workflow"]["incidentId"] == "conv-transcript-test"
        assert status_response.json()["spec"]["records"]["chatTranscripts"][0]["kind"] == "ChatTranscriptRecord"
        jsonl_records = [
            json.loads(line)
            for line in transcript_jsonl_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(jsonl_records) == 1
        assert jsonl_records[0]["kind"] == "ChatTranscriptRecord"
        assert jsonl_records[0]["spec"]["conversationId"] == "conv-transcript-test"
        assert "최근 OpenShift 경고" in jsonl_records[0]["spec"]["userMessage"]
        assert "현재 확인된 OpenShift 상태" in jsonl_records[0]["spec"]["assistantAnswer"]

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
            "summary": "Node 상태 RCA 조회 결과 수집 완료",
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
            "summary": "Restart metric RCA 조회 결과 수집 불가",
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
                "summary": "공식 Pod 재시작 namespace Event 조회 결과 수집 완료",
            },
            {
                "type": "tool_result",
                "detail": '{"candidatePods": [{"name": "sample", "restartCount": 3}]}',
                "evidenceType": "snapshot",
                "id": f"{request_id}-official-namespace-restart-snapshot",
                "name": "official_namespace_restart_snapshot",
                "sourcePath": "/api/v1/namespaces/default/pods?limit=200",
                "status": "success",
                "summary": "공식 Pod 재시작 namespace snapshot 조회 결과 수집 완료",
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

