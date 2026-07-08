import asyncio
from typing import Any


METRICS: dict[str, int] = {
    "aiops_chat_requests_total": 0,
    "aiops_chat_completed_total": 0,
    "aiops_chat_failed_total": 0,
    "aiops_audit_records_total": 0,
    "aiops_evidence_records_total": 0,
    "aiops_diagnostic_requests_total": 0,
    "aiops_action_proposals_total": 0,
    "aiops_action_plans_total": 0,
    "aiops_approval_decisions_total": 0,
    "aiops_execution_requests_total": 0,
    "aiops_execution_dry_run_total": 0,
    "aiops_execution_mutation_succeeded_total": 0,
    "aiops_execution_mutation_failed_total": 0,
    "aiops_evidence_freshness_failures_total": 0,
    "aiops_runbook_plans_total": 0,
    "aiops_rag_search_requests_total": 0,
    "aiops_preapproved_patch_requests_total": 0,
    "aiops_break_glass_requests_total": 0,
    "aiops_product_access_reviews_total": 0,
    "aiops_rate_limited_total": 0,
    "aiops_record_store_loads_total": 0,
    "aiops_record_store_writes_total": 0,
    "aiops_record_store_failures_total": 0,
    "aiops_chat_transcripts_total": 0,
    "aiops_chat_transcript_jsonl_write_failures_total": 0,
    "aiops_chat_feedback_total": 0,
}

AUDIT_RECORDS: dict[str, dict[str, Any]] = {}
EVIDENCE_RECORDS: dict[str, dict[str, Any]] = {}
WORKFLOW_RECORDS: dict[str, dict[str, Any]] = {}
CHAT_TRANSCRIPTS: dict[str, dict[str, Any]] = {}
CHAT_FEEDBACK: dict[str, dict[str, Any]] = {}
DIAGNOSTIC_REQUESTS: dict[str, dict[str, Any]] = {}
ACTION_PROPOSALS: dict[str, dict[str, Any]] = {}
SEALED_ACTION_PLANS: dict[str, dict[str, Any]] = {}
APPROVAL_DECISIONS: dict[str, dict[str, Any]] = {}
EXECUTION_RECORDS: dict[str, dict[str, Any]] = {}
NAMESPACE_CLEANUP_CHAT_CANDIDATES: dict[str, dict[str, Any]] = {}
RUNBOOK_PLANS: dict[str, dict[str, Any]] = {}
PREAPPROVED_PATCH_REQUESTS: dict[str, dict[str, Any]] = {}
BREAK_GLASS_REQUESTS: dict[str, dict[str, Any]] = {}
RATE_LIMIT_BUCKETS: dict[str, list[float]] = {}
_AUTO_EXECUTE_TARGET_LOCKS: dict[str, asyncio.Lock] = {}

OLS_STREAM_STATUS: dict[str, Any] = {
    "streamProbe": "not_started",
    "lastStatus": "not_started",
    "lastContextDigest": "",
    "lastStartedAt": "",
    "lastCompletedAt": "",
    "lastError": "",
    "fallbackActive": False,
}


def increment_metric(name: str, value: int = 1) -> None:
    METRICS[name] = METRICS.get(name, 0) + value


def bounded_put(store: dict[str, dict[str, Any]], key: str, value: dict[str, Any], limit: int) -> None:
    store[key] = value
    while len(store) > limit:
        oldest_key = next(iter(store))
        store.pop(oldest_key, None)
