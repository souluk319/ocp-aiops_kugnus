"""Ver.0.1.7 RAG feature tests: semantic embedding fallback, schema migration, auto-sync CLI."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_rag_module():
    import komsco_ai_gateway.rag_pgvector as m
    return m


SYNC_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "kugnus-rag-sync.py"


def _load_sync_module():
    spec = importlib.util.spec_from_file_location("kugnus_rag_sync", SYNC_SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Stage 1: Semantic Embedding fallback
# ---------------------------------------------------------------------------

def test_call_embedding_service_async_returns_none_when_not_configured() -> None:
    m = _import_rag_module()
    original = m.RAG_EMBEDDING_SERVICE_URL
    try:
        m.RAG_EMBEDDING_SERVICE_URL = ""
        result = asyncio.run(m.call_embedding_service_async("hello"))
        assert result is None
    finally:
        m.RAG_EMBEDDING_SERVICE_URL = original


def test_call_embedding_service_async_falls_back_on_http_error() -> None:
    """If the embedding service returns an error, call_embedding_service_async returns None."""
    import httpx

    m = _import_rag_module()
    original = m.RAG_EMBEDDING_SERVICE_URL

    async def run():
        m.RAG_EMBEDDING_SERVICE_URL = "http://localhost:19999/embed"
        try:
            with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("refused")):
                return await m.call_embedding_service_async("test query")
        finally:
            m.RAG_EMBEDDING_SERVICE_URL = original

    result = asyncio.run(run())
    assert result is None


def test_build_rag_embedding_still_works_without_service() -> None:
    m = _import_rag_module()
    original = m.RAG_EMBEDDING_SERVICE_URL
    try:
        m.RAG_EMBEDDING_SERVICE_URL = ""
        vec = m.build_rag_embedding("pod crash loop backoff")
        assert len(vec) == m.RAG_EFFECTIVE_VECTOR_DIMENSIONS
        assert abs(sum(v * v for v in vec) - 1.0) < 0.01
    finally:
        m.RAG_EMBEDDING_SERVICE_URL = original


# ---------------------------------------------------------------------------
# Stage 3: Schema Migration
# ---------------------------------------------------------------------------

def _make_mock_conn(existing_versions: list[int] | None = None):
    """Return a MagicMock that simulates a psycopg connection with a version table."""
    executed: list[tuple] = []
    version_rows = [{"version": v} for v in (existing_versions or [])]

    conn = MagicMock()

    def fake_execute(sql, params=None):
        executed.append((sql.strip()[:80], params))
        result = MagicMock()
        if "SELECT version FROM aiops_rag_schema_version" in sql:
            result.fetchall.return_value = version_rows
        else:
            result.fetchall.return_value = []
        return result

    conn.execute.side_effect = fake_execute
    conn._executed = executed
    return conn


def test_apply_rag_migrations_creates_version_table() -> None:
    m = _import_rag_module()
    conn = _make_mock_conn()
    m.apply_rag_migrations(conn)
    sqls = [e[0] for e in conn._executed]
    assert any("aiops_rag_schema_version" in s for s in sqls)


def test_apply_rag_migrations_inserts_all_migrations_on_fresh_db() -> None:
    m = _import_rag_module()
    conn = _make_mock_conn(existing_versions=[])
    m.apply_rag_migrations(conn)
    inserts = [e for e in conn._executed if e[1] is not None and isinstance(e[1], tuple) and len(e[1]) == 2]
    inserted_versions = {p[0] for _, p in inserts if isinstance(p, tuple) and len(p) == 2 and isinstance(p[0], int)}
    expected = {v for v, _, _ in m.RAG_MIGRATIONS}
    assert expected.issubset(inserted_versions)


def test_apply_rag_migrations_skips_already_applied() -> None:
    m = _import_rag_module()
    all_versions = [v for v, _, _ in m.RAG_MIGRATIONS]
    conn = _make_mock_conn(existing_versions=all_versions)
    m.apply_rag_migrations(conn)
    inserts = [e for e in conn._executed if e[1] is not None and "INSERT INTO aiops_rag_schema_version" in e[0]]
    assert len(inserts) == 0, "No new inserts expected when all migrations already applied"


def test_apply_rag_migrations_idempotent_on_second_run() -> None:
    m = _import_rag_module()
    conn1 = _make_mock_conn(existing_versions=[])
    m.apply_rag_migrations(conn1)

    all_versions = [v for v, _, _ in m.RAG_MIGRATIONS]
    conn2 = _make_mock_conn(existing_versions=all_versions)
    m.apply_rag_migrations(conn2)

    inserts_second = [e for e in conn2._executed if e[1] is not None and "INSERT INTO aiops_rag_schema_version" in e[0]]
    assert len(inserts_second) == 0


# ---------------------------------------------------------------------------
# Stage 2: Auto-Ingest CLI (kugnus-rag-sync.py)
# ---------------------------------------------------------------------------

def test_kugnus_rag_sync_exits_nonzero_without_dir() -> None:
    sync = _load_sync_module()
    with patch("sys.argv", ["kugnus-rag-sync.py"]):
        with patch.dict("os.environ", {"KOMSCO_AI_RAG_SYNC_DIR": ""}):
            rc = sync.main()
    assert rc != 0


def test_kugnus_rag_sync_dry_run_lists_files(tmp_path) -> None:
    (tmp_path / "runbook.md").write_text("# Title\n\nStep 1.", encoding="utf-8")
    (tmp_path / "guide.txt").write_text("Guide content.", encoding="utf-8")
    sync = _load_sync_module()

    with patch("sys.argv", ["kugnus-rag-sync.py", "--dir", str(tmp_path), "--dry-run"]):
        rc = sync.main()
    assert rc == 0


def test_kugnus_rag_sync_apply_sends_correct_payload(tmp_path) -> None:
    (tmp_path / "ops.md").write_text("# Ops\n\nCheck pod status.", encoding="utf-8")
    sync = _load_sync_module()

    applied_calls: list[dict] = []
    ingest_mod = sync.load_ingest_module()

    def fake_apply(plan, gateway_url, token):
        applied_calls.append({"url": gateway_url, "token": token})
        return {"status": "applied", "httpStatus": 200, "documentId": "x", "expectedChunks": 1, "gatewayUrl": gateway_url, "response": {}}

    # Patch load_ingest_module to always return the same module instance (with fake_apply)
    ingest_mod.apply_plan = fake_apply
    with patch.object(sync, "load_ingest_module", return_value=ingest_mod):
        with patch("sys.argv", ["kugnus-rag-sync.py", "--dir", str(tmp_path), "--token", "tok", "--gateway-url", "http://localhost:18080"]):
            rc = sync.main()

    assert rc == 0
    assert len(applied_calls) == 1
    assert applied_calls[0]["token"] == "tok"


# ---------------------------------------------------------------------------
# Stage 3: Casual greeting fallback (answer_planning.py)
# ---------------------------------------------------------------------------

def _import_answer_planning():
    import komsco_ai_gateway.answer_planning as ap
    return ap


@pytest.mark.parametrize("message", [
    "헤이",
    "안녕",
    "안녕하세요",
    "hi",
    "hello",
    "Hey",
    "test",
    "테스트",
    "ㅎㅇ",
])
def test_casual_greeting_returns_simple_response(message: str) -> None:
    ap = _import_answer_planning()
    plan = ap.build_gateway_fallback_answer_plan(message, {}, [], None)
    assert plan is not None, f"Expected AnswerPlan for '{message}', got None"
    assert plan.kind == ap.ANSWER_KIND_CASUAL
    rendered = ap.render_answer_plan(plan)
    assert "RCA" not in rendered, f"RCA report leaked into casual response for '{message}'"
    assert "OCP" in rendered or "질문" in rendered


@pytest.mark.parametrize("message", [
    "오픈시프트가뭐야",
    "오픈시프트가 뭐야",
    "OpenShift가 뭐야",
    "OCP가 뭐야",
    "쿠버네티스가 뭐야",
])
def test_platform_concept_question_does_not_match_casual(message: str) -> None:
    ap = _import_answer_planning()
    kind = ap.classify_fallback_answer_kind(message, {})
    assert kind == ap.ANSWER_KIND_PLATFORM_CONCEPT

    plan = ap.build_gateway_fallback_answer_plan(message, {}, [], None)
    assert plan is not None
    assert plan.kind == ap.ANSWER_KIND_PLATFORM_CONCEPT
    rendered = ap.render_answer_plan(plan)
    assert "컨테이너 플랫폼" in rendered
    assert "예시:" not in rendered
    assert "안녕하세요" not in rendered


@pytest.mark.parametrize("message", [
    "Pod가 자꾸 재시작돼요",
    "CPU 사용량이 높아요",
    "네임스페이스 상태 확인해줘",
    "crashloop 발생했어요",
])
def test_rca_query_does_not_match_casual(message: str) -> None:
    ap = _import_answer_planning()
    kind = ap.classify_fallback_answer_kind(message, {})
    assert kind != ap.ANSWER_KIND_CASUAL, f"'{message}' should not match casual"
