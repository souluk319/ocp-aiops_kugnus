import ast
import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import HTTPException

from komsco_ai_gateway import main as gateway_main
from komsco_ai_gateway import persistence_runtime
from komsco_ai_gateway.gateway_state import CHAT_TRANSCRIPTS, RATE_LIMIT_BUCKETS


def runtime_parts() -> tuple[
    persistence_runtime.PersistenceRuntimeConfig,
    persistence_runtime.PersistenceRuntimeStores,
    persistence_runtime.PersistenceRuntimeCallbacks,
    dict[str, int],
]:
    metrics: dict[str, int] = {}
    record_store: dict[str, dict[str, Any]] = {}
    workflows: dict[str, dict[str, Any]] = {}
    rates: dict[str, list[float]] = {}

    def bounded_put(store: dict, key: str, value: dict, limit: int) -> None:
        store[key] = value
        while len(store) > limit:
            store.pop(next(iter(store)))

    config = persistence_runtime.PersistenceRuntimeConfig(
        record_store_enabled=True,
        record_store_configmap="ledger",
        record_store_token_file="/missing/token",
        record_store_namespace="test-ns",
        serviceaccount_namespace_file="/missing/namespace",
        openshift_api_url="https://api.test",
        openshift_api_ca_file=False,
        rate_limit_per_minute=1,
        workflow_max_records=2,
        chat_transcript_max_message_chars=20,
        chat_transcript_max_answer_chars=30,
        chat_transcript_jsonl_path="",
    )
    stores = persistence_runtime.PersistenceRuntimeStores(
        record_stores={"chatTranscripts": (record_store, 2, "chatTranscripts.json")},
        workflow_records=workflows,
        rate_limit_buckets=rates,
        action_proposals={},
        sealed_action_plans={},
        approval_decisions={},
        execution_records={},
    )
    callbacks = persistence_runtime.PersistenceRuntimeCallbacks(
        bounded_put=bounded_put,
        canonical_digest=lambda value: "sha256:" + str(value),
        increment_metric=lambda name: metrics.__setitem__(name, metrics.get(name, 0) + 1),
        now_rfc3339=lambda: "2026-07-11T00:00:00+00:00",
        redact_sensitive=lambda value: value,
        safe_subject=lambda _subject: {"username": "anonymous"},
    )
    return config, stores, callbacks, metrics


def test_runtime_module_has_no_main_import() -> None:
    source = Path(persistence_runtime.__file__).read_text(encoding="utf-8")
    imports = {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "main" not in imports
    assert "komsco_ai_gateway.main" not in imports


def test_main_runtime_stores_preserve_public_state_identity() -> None:
    stores = gateway_main.persistence_runtime_stores()

    assert stores.record_stores is gateway_main.RECORD_STORES
    assert stores.record_stores["chatTranscripts"][0] is CHAT_TRANSCRIPTS
    assert stores.rate_limit_buckets is RATE_LIMIT_BUCKETS


def test_main_bounded_put_record_uses_monkeypatched_persist_callback(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_persist(store_name: str) -> None:
        calls.append(store_name)

    monkeypatch.setattr(gateway_main, "persist_record_store", fake_persist)
    CHAT_TRANSCRIPTS.clear()
    try:
        asyncio.run(gateway_main.bounded_put_record("chatTranscripts", "transcript-1", {"kind": "test"}))
        assert CHAT_TRANSCRIPTS["transcript-1"]["kind"] == "test"
        assert calls == ["chatTranscripts"]
    finally:
        CHAT_TRANSCRIPTS.clear()


def test_load_record_store_updates_existing_store_in_place_and_enforces_limit() -> None:
    config, stores, callbacks, metrics = runtime_parts()
    target_store = stores.record_stores["chatTranscripts"][0]
    original_identity = id(target_store)
    response = httpx.Response(
        200,
        json={
            "data": {
                "chatTranscripts.json": json.dumps(
                    {"old": {"n": 1}, "middle": {"n": 2}, "new": {"n": 3}}
                )
            }
        },
    )

    async def request(*_args, **_kwargs) -> httpx.Response:
        return response

    asyncio.run(persistence_runtime.load_record_store(config, stores, callbacks, request))

    assert id(target_store) == original_identity
    assert list(target_store) == ["middle", "new"]
    assert metrics == {"aiops_record_store_loads_total": 1}


def test_jsonl_persistence_redacts_and_write_failure_is_measured(tmp_path) -> None:
    config, _stores, callbacks, metrics = runtime_parts()
    path = tmp_path / "chat" / "transcripts.jsonl"
    config = replace(config, chat_transcript_jsonl_path=str(path))
    callbacks = replace(
        callbacks,
        redact_sensitive=lambda value: {**value, "secret": "[REDACTED]"},
    )

    persistence_runtime.write_chat_transcript_jsonl(config, callbacks, {"kind": "ChatTranscriptRecord"})
    assert json.loads(path.read_text(encoding="utf-8"))["secret"] == "[REDACTED]"

    def fail_write(_record) -> None:
        raise OSError("disk full")

    asyncio.run(persistence_runtime.append_chat_transcript_jsonl(callbacks, {}, fail_write))
    assert metrics["aiops_chat_transcript_jsonl_write_failures_total"] == 1


def test_rate_limit_and_record_readability_keep_existing_contract() -> None:
    config, stores, callbacks, metrics = runtime_parts()
    subject = {"username": "operator", "uid": "uid-1", "groupsDigest": "sha256:groups"}

    persistence_runtime.enforce_rate_limit(config, stores, callbacks, "Bearer token")
    with pytest.raises(HTTPException) as exc_info:
        persistence_runtime.enforce_rate_limit(config, stores, callbacks, "Bearer token")

    assert exc_info.value.status_code == 429
    assert metrics["aiops_rate_limited_total"] == 1
    assert persistence_runtime.can_subject_read_record({"subject": subject}, subject)
    assert not persistence_runtime.can_subject_read_record(
        {"subject": subject},
        {**subject, "uid": "uid-2"},
    )
