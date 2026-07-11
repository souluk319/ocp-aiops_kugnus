import asyncio
import json

import httpx

import komsco_ai_gateway.main as gateway_main
from komsco_ai_gateway.main import app


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

    async def fake_persist(record: dict) -> tuple[str, str, dict]:
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
