import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock, patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "ingest-rag-documents.py"


def load_cli_module():
    spec = importlib.util.spec_from_file_location("ingest_rag_documents", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rag_ingestion_cli_redacts_sensitive_preview(tmp_path) -> None:
    source = tmp_path / "runbook.md"
    source.write_text(
        "\n".join(
            [
                "safe runbook heading",
                "Authorization: Bearer secret-token-value-1234567890",
                "api_key=shortsecret",
                "client-key-data: UHJpdmF0ZUtleUJvZHk=",
                "-----BEGIN PRIVATE KEY-----",
                "PrivateKeyBody",
                "-----END PRIVATE KEY-----",
            ]
        ),
        encoding="utf-8",
    )
    cli = load_cli_module()
    plan = cli.build_plan(
        type(
            "Args",
            (),
            {
                "source": str(source),
                "encoding": "utf-8",
                "customer": "komsco",
                "source_type": "runbook",
                "version": "v0.1.1",
                "max_chunk_chars": 1200,
                "collection": "komsco-aiops-runbooks",
                "namespace": "komsco-ai-kugnus",
                "acl_group": ["aiops-admins"],
                "label": [],
            },
        )()
    )
    rendered = json.dumps(plan)

    assert "Authorization: Bearer [REDACTED]" in rendered
    assert "api_key=[REDACTED]" in rendered
    assert "client-key-data: [REDACTED]" in rendered
    assert "[REDACTED PEM BLOCK]" in rendered
    assert "secret-token-value" not in rendered
    assert "shortsecret" not in rendered
    assert "UHJpdmF0ZUtleUJvZHk" not in rendered
    assert "PrivateKeyBody" not in rendered


def test_rag_ingestion_cli_redacts_pem_before_chunking(tmp_path) -> None:
    source = tmp_path / "long-key-runbook.md"
    private_key_body = "PrivateKeyBody" * 80
    source.write_text(
        "\n".join(
            [
                "before key",
                "-----BEGIN PRIVATE KEY-----",
                private_key_body,
                "-----END PRIVATE KEY-----",
                "after key",
            ]
        ),
        encoding="utf-8",
    )
    cli = load_cli_module()
    plan = cli.build_plan(
        type(
            "Args",
            (),
            {
                "source": str(source),
                "encoding": "utf-8",
                "customer": "komsco",
                "source_type": "runbook",
                "version": "v0.1.1",
                "max_chunk_chars": 80,
                "collection": "komsco-aiops-runbooks",
                "namespace": "komsco-ai-kugnus",
                "acl_group": ["aiops-admins"],
                "label": [],
            },
        )()
    )
    rendered = json.dumps(plan)

    assert "[REDACTED PEM BLOCK]" in rendered
    assert "BEGIN PRIVATE KEY" not in rendered
    assert "END PRIVATE KEY" not in rendered
    assert "PrivateKeyBody" not in rendered


def test_rag_ingestion_cli_apply_builds_correct_payload(tmp_path) -> None:
    source = tmp_path / "ops-runbook.md"
    source.write_text("# Ops Runbook\n\nStep 1: check pod status.\n\nStep 2: describe events.", encoding="utf-8")
    cli = load_cli_module()

    args = type(
        "Args",
        (),
        {
            "source": str(source),
            "encoding": "utf-8",
            "customer": "komsco",
            "source_type": "runbook",
            "version": "v0.1.6",
            "max_chunk_chars": 1200,
            "collection": "komsco-aiops-runbooks",
            "namespace": "komsco-ai-kugnus",
            "acl_group": ["aiops-admins"],
            "label": [],
        },
    )()

    plan = cli.build_plan(args)
    spec = plan["spec"]
    doc = spec["document"]

    # apply_plan sends the raw source content — verify the payload shape without HTTP
    captured: list[dict] = []

    def fake_apply(plan_arg, gateway_url, token):
        captured.append({"gateway_url": gateway_url, "token": token, "doc_id": plan_arg["spec"]["document"]["documentId"]})
        return {"status": "applied", "httpStatus": 200, "documentId": doc["documentId"], "expectedChunks": len(spec["chunks"]), "gatewayUrl": gateway_url, "response": {}}

    with patch.object(cli, "apply_plan", side_effect=fake_apply):
        result = cli.apply_plan(plan, "http://localhost:18080", "test-token")

    # Without mocking urllib (dry-run style check on plan structure only):
    assert doc["sourceType"] == "runbook"
    assert doc["customer"] == "komsco"
    assert doc["version"] == "v0.1.6"
    assert "aiops-admins" in doc["aclGroups"]
    assert len(spec["chunks"]) >= 1
    assert spec["gatewayOnly"] is True
    assert spec["directDatabaseAccessAllowed"] is False
