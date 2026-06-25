import asyncio
import base64
import binascii
import hashlib
import io
import json
import math
import mimetypes
import os
import re
import time
import uuid
import zipfile
from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import unquote
import xml.etree.ElementTree as ET

import httpx
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except ImportError:  # pragma: no cover - optional local RAG backend dependency
    psycopg = None
    dict_row = None
    Jsonb = None

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - optional document parser dependency
    PdfReader = None

from .aiops_core import (
    HOST_DIAGNOSTIC_COLLECTORS,
    AiopsCoreError,
    action_from_plan,
    build_mutation_request,
    deployment_scale_path,
    get_host_diagnostic_collector,
    parameters_from_plan,
    path_segment,
    target_path,
    target_from_plan,
)
from .aiops_contracts import build_rca_context, build_runtime_safety_contract, build_runtime_tool_plan
from .security import (
    build_evidence_reference,
    build_gateway_guardrail,
    build_trace_record,
    canonical_digest,
    classify_request_policy,
    now_rfc3339,
    redact_sensitive,
    safe_subject,
)

app = FastAPI(title="KOMSCO AI Gateway", version="0.1.5")


def parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_ols_verify(value: str | None) -> bool | str:
    if value is None or value.strip() == "":
        return True

    normalized = value.strip().lower()
    if normalized in {"0", "false", "no", "off"}:
        return False
    if normalized in {"1", "true", "yes", "on"}:
        return True

    return value


OLS_BASE_URL = os.getenv("OLS_BASE_URL", "").rstrip("/")
OLS_CA_FILE = parse_ols_verify(os.getenv("OLS_CA_FILE"))
DEV_ECHO = parse_bool(os.getenv("KOMSCO_AI_DEV_ECHO"))
OPENSHIFT_API_URL = os.getenv("OPENSHIFT_API_URL", "").rstrip("/")
if not OPENSHIFT_API_URL and os.getenv("KUBERNETES_SERVICE_HOST"):
    kubernetes_host = os.getenv("KUBERNETES_SERVICE_HOST")
    kubernetes_port = os.getenv("KUBERNETES_SERVICE_PORT", "443")
    OPENSHIFT_API_URL = f"https://{kubernetes_host}:{kubernetes_port}"
OPENSHIFT_API_CA_FILE = parse_ols_verify(
    os.getenv(
        "OPENSHIFT_API_CA_FILE",
        "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
        if os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
        else "",
    )
)
PRODUCT_ACCESS_REVIEW_ENABLED = parse_bool(
    os.getenv("KOMSCO_AI_PRODUCT_ACCESS_REVIEW_ENABLED"),
    default=True,
)
PRODUCT_ACCESS_REVIEW_REQUIRED = parse_bool(
    os.getenv("KOMSCO_AI_PRODUCT_ACCESS_REVIEW_REQUIRED"),
    default=False,
)
PRODUCT_ACCESS_REVIEW_GROUP = os.getenv(
    "KOMSCO_AI_PRODUCT_ACCESS_REVIEW_GROUP",
    "console.openshift.io",
)
PRODUCT_ACCESS_REVIEW_RESOURCE = os.getenv(
    "KOMSCO_AI_PRODUCT_ACCESS_REVIEW_RESOURCE",
    "consoleplugins",
)
PRODUCT_ACCESS_REVIEW_VERB = os.getenv("KOMSCO_AI_PRODUCT_ACCESS_REVIEW_VERB", "get")
PRODUCT_ACCESS_REVIEW_NAME = os.getenv(
    "KOMSCO_AI_PRODUCT_ACCESS_REVIEW_NAME",
    "komsco-ai-console-plugin-kugnus",
)
RATE_LIMIT_PER_MINUTE = int(os.getenv("KOMSCO_AI_RATE_LIMIT_PER_MINUTE", "60"))
AUDIT_MAX_RECORDS = int(os.getenv("KOMSCO_AI_AUDIT_MAX_RECORDS", "1000"))
EVIDENCE_MAX_RECORDS = int(os.getenv("KOMSCO_AI_EVIDENCE_MAX_RECORDS", "1000"))
WORKFLOW_MAX_RECORDS = int(os.getenv("KOMSCO_AI_WORKFLOW_MAX_RECORDS", "1000"))
DIAGNOSTICS_ENABLED = parse_bool(os.getenv("KOMSCO_AI_DIAGNOSTICS_ENABLED"), default=False)
DIAGNOSTIC_MAX_RECORDS = int(os.getenv("KOMSCO_AI_DIAGNOSTIC_MAX_RECORDS", "1000"))
DEMO_NAMESPACE_ALLOWLIST = {
    item.strip()
    for item in os.getenv("KOMSCO_AIOPS_DEMO_NAMESPACE_ALLOWLIST", "komsco-ai-dev,default").split(",")
    if item.strip()
}
HOST_DIAGNOSTICS_CONTROLLER_URL = os.getenv("KOMSCO_AI_HOST_DIAGNOSTICS_CONTROLLER_URL", "").rstrip("/")
HOST_DIAGNOSTICS_CONTROLLER_SHARED_TOKEN = os.getenv(
    "KOMSCO_AI_HOST_DIAGNOSTICS_CONTROLLER_SHARED_TOKEN",
    "",
)
RECORD_STORE_ENABLED = parse_bool(os.getenv("KOMSCO_AI_RECORD_STORE_ENABLED"), default=False)
RECORD_STORE_CONFIGMAP = os.getenv("KOMSCO_AI_RECORD_STORE_CONFIGMAP", "komsco-ai-gateway-ledger")
RECORD_STORE_TOKEN_FILE = os.getenv(
    "KOMSCO_AI_RECORD_STORE_TOKEN_FILE",
    "/var/run/secrets/kubernetes.io/serviceaccount/token",
)
RECORD_STORE_NAMESPACE = os.getenv("KOMSCO_AI_RECORD_STORE_NAMESPACE", "")
RAG_BACKEND_URL = os.getenv("KOMSCO_AI_RAG_BACKEND_URL", "").rstrip("/")
RAG_BACKEND_TYPE = os.getenv("KOMSCO_AI_RAG_BACKEND_TYPE", "pgvector")
RAG_COLLECTION = os.getenv("KOMSCO_AI_RAG_COLLECTION", "komsco-aiops-runbooks")
RAG_EMBEDDING_MODEL = os.getenv("KOMSCO_AI_RAG_EMBEDDING_MODEL", "")
RAG_VECTOR_DIMENSIONS = int(os.getenv("KOMSCO_AI_RAG_VECTOR_DIMENSIONS", "0") or "0")
RAG_EFFECTIVE_VECTOR_DIMENSIONS = RAG_VECTOR_DIMENSIONS or 64
RAG_DEMO_SEED_ENABLED = parse_bool(os.getenv("KOMSCO_AI_RAG_DEMO_SEED_ENABLED"), default=True)
RAG_UPLOAD_MAX_BYTES = int(os.getenv("KOMSCO_AI_RAG_UPLOAD_MAX_BYTES", str(5 * 1024 * 1024)))
RAG_UPLOAD_MAX_CHARS = int(os.getenv("KOMSCO_AI_RAG_UPLOAD_MAX_CHARS", "120000"))
RAG_UPLOAD_MAX_CHUNKS = int(os.getenv("KOMSCO_AI_RAG_UPLOAD_MAX_CHUNKS", "80"))
RAG_UPLOAD_MAX_CHUNK_CHARS = int(os.getenv("KOMSCO_AI_RAG_UPLOAD_MAX_CHUNK_CHARS", "1200"))
RAG_DANGEROUS_CONTENT_RE = re.compile(
    r"\b(?:oc|kubectl)\s+(?:delete|patch|replace|scale|adm|debug|exec)\b|"
    r"\brm\s+-rf\b|"
    r"\bchmod\s+777\b|"
    r"\bdefrag\b",
    re.IGNORECASE,
)
RAG_BROAD_SYSTEM_GROUPS = {
    "system:authenticated",
    "system:authenticated:oauth",
    "system:unauthenticated",
}
SERVICEACCOUNT_NAMESPACE_FILE = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
CLUSTER_ID = os.getenv("KOMSCO_AI_CLUSTER_ID", "unknown-cluster")
MUTATIONS_ENABLED = parse_bool(os.getenv("KOMSCO_AI_ENABLE_MUTATIONS"), default=False)
ACTION_MAX_RECORDS = int(os.getenv("KOMSCO_AI_ACTION_MAX_RECORDS", "1000"))
ACTION_EXECUTOR_TOKEN_FILE = os.getenv(
    "KOMSCO_AI_ACTION_EXECUTOR_TOKEN_FILE",
    "/var/run/secrets/kubernetes.io/serviceaccount/token",
)
ACTION_EXECUTOR_FIELD_MANAGER = os.getenv(
    "KOMSCO_AI_ACTION_EXECUTOR_FIELD_MANAGER",
    "komsco-ai-action-executor",
)
ACTION_EXECUTOR_URL = os.getenv("KOMSCO_AI_ACTION_EXECUTOR_URL", "").rstrip("/")
ACTION_EXECUTOR_SHARED_TOKEN = os.getenv("KOMSCO_AI_ACTION_EXECUTOR_SHARED_TOKEN", "")
APPROVAL_ACCESS_REVIEW_REQUIRED = parse_bool(
    os.getenv("KOMSCO_AI_APPROVAL_ACCESS_REVIEW_REQUIRED"),
    default=False,
)
RUNBOOK_MAX_RECORDS = int(os.getenv("KOMSCO_AI_RUNBOOK_MAX_RECORDS", "1000"))
BREAK_GLASS_ENABLED = parse_bool(os.getenv("KOMSCO_AI_BREAK_GLASS_ENABLED"), default=False)
BREAK_GLASS_MAX_RECORDS = int(os.getenv("KOMSCO_AI_BREAK_GLASS_MAX_RECORDS", "1000"))
BREAK_GLASS_IMAGE_DIGEST = os.getenv("KOMSCO_AI_BREAK_GLASS_IMAGE_DIGEST", "")
UNRESTRICTED_COMMANDS_ENABLED = parse_bool(
    os.getenv("KOMSCO_AI_ENABLE_UNRESTRICTED_COMMANDS"),
    default=False,
)
UNRESTRICTED_COMMAND_CWD = os.getenv("KOMSCO_AI_UNRESTRICTED_COMMAND_CWD", os.getcwd())
UNRESTRICTED_COMMAND_TIMEOUT_SECONDS = int(
    os.getenv("KOMSCO_AI_UNRESTRICTED_COMMAND_TIMEOUT_SECONDS", "60")
)
UNRESTRICTED_COMMAND_MAX_OUTPUT_BYTES = int(
    os.getenv("KOMSCO_AI_UNRESTRICTED_COMMAND_MAX_OUTPUT_BYTES", "20000")
)
TOOL_LINE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("Tool call:", "tool_call"),
    ("Tool result:", "tool_result"),
)
MAX_TOOL_DETAIL_CHARS = 4000
RUN_HEARTBEAT_SECONDS = 5.0
MAX_IMAGE_ATTACHMENTS = 4
MAX_IMAGE_ATTACHMENT_BYTES = 2 * 1024 * 1024
MAX_IMAGE_ATTACHMENT_TOTAL_BYTES = 6 * 1024 * 1024
ALLOWED_IMAGE_MIME_TYPES = {"image/gif", "image/jpeg", "image/png", "image/webp"}
DISALLOWED_GATEWAY_API_REFERENCE_RE = re.compile(
    r"^\s*(Gateway|GatewayClass)\s+\[gateway\.networking\.k8s\.io/v1\]:\s+https?://",
    re.IGNORECASE,
)
EXPLICIT_KUBERNETES_GATEWAY_API_RE = re.compile(
    r"(?i)(gatewayclass|gateway\.networking\.k8s\.io|kubernetes gateway api|openshift gateway api|gateway api)"
)
LOW_SIGNAL_REFERENCE_RE = re.compile(
    r"^\s*("
    r"Extension APIs|"
    r"Admission plugins|"
    r"TokenReview\s+\[authentication\.k8s\.io/v1\]|"
    r"ClusterRole\s+\[authorization\.openshift\.io/v1\]"
    r"):\s+https?://",
    re.IGNORECASE,
)
EXPLICIT_OPENSHIFT_DOC_REFERENCE_RE = re.compile(
    r"(?i)(문서|docs?|reference|참고 링크|api\s*문서|extension api|admission plugin|tokenreview|clusterrole)"
)
POD_STATUS_ANALYSIS_RE = re.compile(
    r"(?i)((pod|pods|파드).*(상태|현황|이력|횟수|많은|높은|분석|확인|조회|"
    r"crashloop|imagepull|backoff|failed|error|pending|교체|replacement|rollout|"
    r"restart\s+(count|history|status|analysis|summary)|"
    r"(many|high|top)\s+restarts)|"
    r"(상태|현황|이력|횟수|많은|높은|분석|확인|조회|crashloop|imagepull|backoff|failed|"
    r"error|pending|교체|replacement|rollout|restart\s+count|"
    r"restart\s+(history|status|analysis|summary)|(many|high|top)\s+restarts).*(pod|pods|파드)|"
    r"(deployment|deployments|디플로이먼트).*(상태|현황|확인|조회|rollout|restart|재시작|교체|replacement)|"
    r"(상태|현황|확인|조회|rollout|restart|재시작|교체|replacement).*(deployment|deployments|디플로이먼트))"
)
POD_LIST_REQUEST_RE = re.compile(
    r"(?i)((pod|pods|파드).*(list|리스트|목록|전체|조회)|"
    r"(list|리스트|목록|전체|조회).*(pod|pods|파드))"
)
POD_COUNT_QUERY_RE = re.compile(
    r"(?i)((pod|pods|파드).*(몇\s*개|몇개|개수|count|떠\s*있|떠있|띄|running|ready)|"
    r"(몇\s*개|몇개|개수|count|떠\s*있|떠있|띄|running|ready).*(pod|pods|파드))"
)
CLUSTER_OPERATOR_ANALYSIS_RE = re.compile(
    r"(?i)(clusteroperator|cluster\s*operator|클러스터\s*오퍼레이터|operator\s+status|오퍼레이터\s*상태)"
)
CRONJOB_ACTIVITY_ANALYSIS_RE = re.compile(
    r"(?i)(cron\s*job|cronjob|크론잡|scheduled\s+job|schedule|스케줄|"
    r"\d+\s*(분|minute|min)|\*/\d+|0/\d+|"
    r"반복\s*(실행|활동)|주기|activity|활동|이벤트)"
)
RCA_SIGNAL_ANALYSIS_RE = re.compile(
    r"(?i)(rca|root\s*cause|원인|왜|장애|이상|anomaly|anomalies|"
    r"alert|alerts|알림|경고|node|nodes|노드|pressure|압력|"
    r"metric|metrics|메트릭|prometheus|thanos|cpu|memory|메모리|restart|재시작|"
    r"crashloop|crashloopbackoff|backoff)"
)
CRONJOB_POLICY_ENV_RE = re.compile(
    r"(?i)(workspace|notebook|sandbox|hibernate|suspend|sleep|idle|delete|ttl|"
    r"expire|expiration|cleanup|retention|prune|archive|max[_-]?age|timeout|gc)"
)
SECRET_ENV_RE = re.compile(r"(?i)(secret|token|password|passwd|private|credential|key)")
K8S_NAME_RE = r"[a-z0-9](?:[-a-z0-9.]{0,251}[a-z0-9])?"
NAMESPACE_MENTION_RE = re.compile(
    rf"(?:\b(?P<namespace>{K8S_NAME_RE})\s*(?:namespace|네임스페이스)|"
    rf"(?:namespace|네임스페이스)\s*(?P<namespace_after>{K8S_NAME_RE})\b)",
    re.IGNORECASE,
)
DEPLOYMENT_RESOURCE_RE = re.compile(rf"\b(?:deployment|deploy|디플로이먼트)/(?P<name>{K8S_NAME_RE})\b", re.IGNORECASE)
POD_RESOURCE_RE = re.compile(rf"\b(?:pod|pods|파드)/(?P<name>{K8S_NAME_RE})\b", re.IGNORECASE)
POD_COUNT_TARGET_BEFORE_POD_RE = re.compile(
    rf"(?i)(?:^|[^A-Za-z0-9._-])(?P<name>{K8S_NAME_RE})`?\s*"
    r"(?:deployment|deploy|디플로이먼트)?\s*(?:의|에|에서|은|는|이|가)?\s*"
    r"(?:파드|pod|pods)"
)
POD_COUNT_TARGET_AFTER_POD_RE = re.compile(
    rf"(?i)(?:파드|pod|pods)\s*(?:of|for|대상|이름)?\s*(?P<name>{K8S_NAME_RE})"
)
POD_COUNT_RESERVED_TARGET_NAMES = {
    "all",
    "count",
    "list",
    "pod",
    "pods",
    "ready",
    "running",
    "status",
}
HPA_RESOURCE_RE = re.compile(
    rf"\b(?:hpa|horizontalpodautoscaler|horizontalpodautoscalers|오토스케일러)/(?P<name>{K8S_NAME_RE})\b",
    re.IGNORECASE,
)
NAMESPACED_RESOURCE_SHORTHAND_RE = re.compile(rf"\b(?P<namespace>{K8S_NAME_RE})[:/](?P<name>{K8S_NAME_RE})\b")
BACKTICK_RESOURCE_RE = re.compile(r"`(?P<name>[A-Za-z0-9._-]+)`")
SCALE_INTENT_RE = re.compile(
    rf"(?P<name>{K8S_NAME_RE})\s*(?:파드|pod|pods|deployment|deploy)?\s*(?:를|을|은|는)?\s*"
    r"(?P<replicas>[0-9]{1,3})\s*(?:개|대|replica|replicas|pods?)?\s*(?:로|으로)?\s*"
    r"(?:올려|늘려|줄여|맞춰|변경|설정|스케일|scale)",
    re.IGNORECASE,
)
SCALE_REPLICAS_RE = re.compile(
    r"(?P<replicas>[0-9]{1,3})\s*(?:개|대|replica|replicas|pods?)?\s*(?:로|으로)?\s*"
    r"(?:올려|늘려|줄여|맞춰|변경|설정|스케일|scale)",
    re.IGNORECASE,
)
RESTART_INTENT_RE = re.compile(
    rf"(?P<name>{K8S_NAME_RE})\s*(?:deployment|deploy|디플로이먼트|파드|pod|pods)?\s*(?:를|을|은|는)?\s*"
    r"(?:재시작|리스타트|restart|rollout\s+restart)",
    re.IGNORECASE,
)
RESTART_REQUEST_RE = re.compile(r"(?:재시작|리스타트|restart|rollout\s+restart)", re.IGNORECASE)
POD_EVICTION_REQUEST_RE = re.compile(
    r"(?:evict|eviction|퇴거|교체|재생성|pod\s+delete|delete\s+pod|파드\s*삭제|삭제)",
    re.IGNORECASE,
)
ROLLBACK_REQUEST_RE = re.compile(r"(?:rollback|roll\s*back|rollout\s+undo|롤백|되돌려|복구)", re.IGNORECASE)
ROLLBACK_REVISION_RE = re.compile(
    r"(?:revision|rev|리비전)\s*(?P<revision>[0-9]{1,4})|(?P<korean_revision>[0-9]{1,4})\s*번\s*(?:revision|리비전)?",
    re.IGNORECASE,
)
HPA_REQUEST_RE = re.compile(r"(?:\bhpa\b|horizontalpodautoscaler|오토스케일|autoscal)", re.IGNORECASE)
HPA_MIN_RE = re.compile(r"(?:min(?:Replicas)?|최소)\s*(?P<value>[0-9]{1,3})", re.IGNORECASE)
HPA_MAX_RE = re.compile(r"(?:max(?:Replicas)?|최대)\s*(?P<value>[0-9]{1,3})", re.IGNORECASE)
FOLLOWUP_EXECUTION_RE = re.compile(
    r"^\s*(?:승인|승인해|실행|실행해|진행|진행해|수행|수행해|적용|적용해|해|해줘|yes|ok|확인)\s*[.!?。]*\s*$",
    re.IGNORECASE,
)
POD_RESTART_LANGUAGE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("재시작 빈도", "누적 재시작 횟수"),
    ("높은 빈도", "높은 누적 재시작 횟수"),
    ("빈번한 재시작", "누적 재시작 이력"),
    ("재시작이 빈번하게 발생", "재시작 이력이 누적"),
    ("재시작이 빈번", "누적 재시작 횟수가 높음"),
)
VISION_SYSTEM_PROMPT = (
    "You are an image analysis component for an OpenShift AIOps assistant. "
    "Extract visible text, UI state, error messages, resource names, namespace names, "
    "and operational signals from the attached image. Be concise and do not invent "
    "details that are not visible."
)
K8S_RESOURCE_KIND_BY_ROUTE_SEGMENT = {
    "buildconfigs": "BuildConfig",
    "configmaps": "ConfigMap",
    "cronjobs": "CronJob",
    "daemonsets": "DaemonSet",
    "deployments": "Deployment",
    "deploymentconfigs": "DeploymentConfig",
    "events": "Event",
    "horizontalpodautoscalers": "HorizontalPodAutoscaler",
    "hpas": "HorizontalPodAutoscaler",
    "ingresses": "Ingress",
    "jobs": "Job",
    "namespaces": "Namespace",
    "nodes": "Node",
    "pods": "Pod",
    "projects": "Project",
    "replicasets": "ReplicaSet",
    "replicationcontrollers": "ReplicationController",
    "routes": "Route",
    "secrets": "Secret",
    "services": "Service",
    "statefulsets": "StatefulSet",
}
PAGE_CONTEXT_ALLOWED_KEYS = {
    "aiopsDemoCycle",
    "aiopsExecutionMode",
    "clusterScope",
    "href",
    "namespace",
    "pathname",
    "perspective",
    "resourceKind",
    "resourceList",
    "resourceName",
    "route",
}
AIOPS_DEMO_CYCLE_ALLOWED_KEYS = {
    "candidateId",
    "candidateStatusLabel",
    "findingId",
    "findingTitle",
    "readOnlyOnly",
    "scenarioId",
    "selectedAt",
    "source",
}
AIOPS_DEMO_CYCLE_TARGET_ALLOWED_KEYS = {
    "kind",
    "name",
    "namespace",
}
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
}
AUDIT_RECORDS: dict[str, dict[str, Any]] = {}
EVIDENCE_RECORDS: dict[str, dict[str, Any]] = {}
WORKFLOW_RECORDS: dict[str, dict[str, Any]] = {}
DIAGNOSTIC_REQUESTS: dict[str, dict[str, Any]] = {}
ACTION_PROPOSALS: dict[str, dict[str, Any]] = {}
SEALED_ACTION_PLANS: dict[str, dict[str, Any]] = {}
APPROVAL_DECISIONS: dict[str, dict[str, Any]] = {}
EXECUTION_RECORDS: dict[str, dict[str, Any]] = {}
RUNBOOK_PLANS: dict[str, dict[str, Any]] = {}
PREAPPROVED_PATCH_REQUESTS: dict[str, dict[str, Any]] = {}
BREAK_GLASS_REQUESTS: dict[str, dict[str, Any]] = {}
RATE_LIMIT_BUCKETS: dict[str, list[float]] = {}
LAST_RUNTIME_TOOL_PLAN: dict[str, Any] | None = None
LAST_RCA_CONTEXT: dict[str, Any] | None = None
OLS_STREAM_STATUS: dict[str, Any] = {
    "streamProbe": "not_started",
    "lastStatus": "not_started",
    "lastContextDigest": "",
    "lastStartedAt": "",
    "lastCompletedAt": "",
    "lastError": "",
    "fallbackActive": False,
}
ACTION_REGISTRY_VERSION = "v1"
ACTION_REGISTRY_ENTRIES: dict[str, dict[str, Any]] = {
    "rollout_restart_deployment": {
        "toolName": "rollout_restart_deployment",
        "toolVersion": "v1",
        "targetKind": "Deployment",
        "risk": "low",
        "authorization": {
            "apiGroup": "apps",
            "resource": "deployments",
            "subresource": "",
            "verb": "patch",
        },
        "request": {
            "method": "PATCH",
            "pathTemplate": "/apis/apps/v1/namespaces/{namespace}/deployments/{name}",
        },
    },
    "set_replicas_within_bounds": {
        "toolName": "set_replicas_within_bounds",
        "toolVersion": "v1",
        "targetKind": "Deployment",
        "risk": "medium",
        "authorization": {
            "apiGroup": "apps",
            "resource": "deployments",
            "subresource": "scale",
            "verb": "update",
        },
        "request": {
            "method": "PATCH",
            "pathTemplate": "/apis/apps/v1/namespaces/{namespace}/deployments/{name}/scale",
        },
    },
    "evict_one_unhealthy_controller_owned_pod": {
        "toolName": "evict_one_unhealthy_controller_owned_pod",
        "toolVersion": "v1",
        "targetKind": "Pod",
        "risk": "medium",
        "authorization": {
            "apiGroup": "",
            "resource": "pods",
            "subresource": "eviction",
            "verb": "create",
        },
        "request": {
            "method": "POST",
            "pathTemplate": "/api/v1/namespaces/{namespace}/pods/{name}/eviction",
        },
    },
    "rollback_deployment_to_revision": {
        "toolName": "rollback_deployment_to_revision",
        "toolVersion": "v1",
        "targetKind": "Deployment",
        "risk": "medium",
        "authorization": {
            "apiGroup": "apps",
            "resource": "deployments",
            "subresource": "",
            "verb": "patch",
        },
        "request": {
            "method": "PATCH",
            "pathTemplate": "/apis/apps/v1/namespaces/{namespace}/deployments/{name}",
        },
    },
    "set_hpa_bounds": {
        "toolName": "set_hpa_bounds",
        "toolVersion": "v1",
        "targetKind": "HorizontalPodAutoscaler",
        "risk": "medium",
        "authorization": {
            "apiGroup": "autoscaling",
            "resource": "horizontalpodautoscalers",
            "subresource": "",
            "verb": "patch",
        },
        "request": {
            "method": "PATCH",
            "pathTemplate": "/apis/autoscaling/v2/namespaces/{namespace}/horizontalpodautoscalers/{name}",
        },
    },
}
ACTION_REGISTRY_BUNDLE = {
    "schemaVersion": "v1",
    "version": ACTION_REGISTRY_VERSION,
    "entries": ACTION_REGISTRY_ENTRIES,
}
ACTION_REGISTRY_DIGEST = canonical_digest(ACTION_REGISTRY_BUNDLE)
RUNBOOK_REGISTRY_VERSION = "v1"
RUNBOOK_REGISTRY_ENTRIES: dict[str, dict[str, Any]] = {
    "deployment_rollout_restart_v1": {
        "runbookId": "deployment_rollout_restart_v1",
        "runbookVersion": "v1",
        "incidentClass": "deployment_rollout_recovery",
        "targetKind": "Deployment",
        "allowedSteps": [
            {
                "stepId": "restart_deployment",
                "toolName": "rollout_restart_deployment",
                "toolVersion": "v1",
                "requiredParameters": ["restartedAt"],
            }
        ],
        "policyChecks": {
            "namespaceRequired": True,
            "targetUidRequired": True,
            "platformNamespaceRequiresExplicitPolicy": True,
            "ownerReviewRequired": True,
        },
    },
    "deployment_bounded_scale_v1": {
        "runbookId": "deployment_bounded_scale_v1",
        "runbookVersion": "v1",
        "incidentClass": "deployment_capacity_adjustment",
        "targetKind": "Deployment",
        "allowedSteps": [
            {
                "stepId": "set_replicas",
                "toolName": "set_replicas_within_bounds",
                "toolVersion": "v1",
                "requiredParameters": ["replicas", "minReplicas", "maxReplicas"],
            }
        ],
        "policyChecks": {
            "namespaceRequired": True,
            "targetUidRequired": True,
            "platformNamespaceRequiresExplicitPolicy": True,
            "hpaReviewRequired": True,
            "ownerReviewRequired": True,
        },
    },
    "controller_owned_unhealthy_pod_eviction_v1": {
        "runbookId": "controller_owned_unhealthy_pod_eviction_v1",
        "runbookVersion": "v1",
        "incidentClass": "single_unhealthy_controller_owned_pod",
        "targetKind": "Pod",
        "allowedSteps": [
            {
                "stepId": "evict_unhealthy_pod",
                "toolName": "evict_one_unhealthy_controller_owned_pod",
                "toolVersion": "v1",
                "requiredParameters": ["reason"],
            }
        ],
        "policyChecks": {
            "namespaceRequired": True,
            "targetUidRequired": True,
            "controllerOwnerRequired": True,
            "pdbReviewRequired": True,
            "replacementCapacityReviewRequired": True,
        },
    },
    "deployment_rollout_rollback_v1": {
        "runbookId": "deployment_rollout_rollback_v1",
        "runbookVersion": "v1",
        "incidentClass": "deployment_bad_rollout_recovery",
        "targetKind": "Deployment",
        "allowedSteps": [
            {
                "stepId": "rollback_deployment",
                "toolName": "rollback_deployment_to_revision",
                "toolVersion": "v1",
                "requiredParameters": ["revision"],
            }
        ],
        "policyChecks": {
            "namespaceRequired": True,
            "targetUidRequired": True,
            "platformNamespaceRequiresExplicitPolicy": True,
            "ownerReviewRequired": True,
            "rollbackRevisionReviewRequired": True,
        },
    },
    "hpa_bounds_adjustment_v1": {
        "runbookId": "hpa_bounds_adjustment_v1",
        "runbookVersion": "v1",
        "incidentClass": "hpa_scaling_policy_adjustment",
        "targetKind": "HorizontalPodAutoscaler",
        "allowedSteps": [
            {
                "stepId": "set_hpa_bounds",
                "toolName": "set_hpa_bounds",
                "toolVersion": "v1",
                "requiredParameters": ["minReplicas", "maxReplicas"],
            }
        ],
        "policyChecks": {
            "namespaceRequired": True,
            "targetUidRequired": True,
            "platformNamespaceRequiresExplicitPolicy": True,
            "hpaPolicyReviewRequired": True,
        },
    },
}
RUNBOOK_REGISTRY_BUNDLE = {
    "schemaVersion": "v1",
    "version": RUNBOOK_REGISTRY_VERSION,
    "entries": RUNBOOK_REGISTRY_ENTRIES,
}
RUNBOOK_REGISTRY_DIGEST = canonical_digest(RUNBOOK_REGISTRY_BUNDLE)
PREAPPROVED_PATCH_FIELD_SCHEMAS: dict[str, dict[str, Any]] = {
    "deployment_progress_deadline_seconds_v1": {
        "fieldSchemaId": "deployment_progress_deadline_seconds_v1",
        "targetKind": "Deployment",
        "apiVersion": "apps/v1",
        "jsonPointer": "/spec/progressDeadlineSeconds",
        "valueType": "integer",
        "minimum": 30,
        "maximum": 3600,
        "risk": "medium",
    },
    "deployment_revision_history_limit_v1": {
        "fieldSchemaId": "deployment_revision_history_limit_v1",
        "targetKind": "Deployment",
        "apiVersion": "apps/v1",
        "jsonPointer": "/spec/revisionHistoryLimit",
        "valueType": "integer",
        "minimum": 1,
        "maximum": 20,
        "risk": "low",
    },
}
PREAPPROVED_PATCH_FIELD_BUNDLE = {
    "schemaVersion": "v1",
    "version": RUNBOOK_REGISTRY_VERSION,
    "schemas": PREAPPROVED_PATCH_FIELD_SCHEMAS,
}
PREAPPROVED_PATCH_FIELD_DIGEST = canonical_digest(PREAPPROVED_PATCH_FIELD_BUNDLE)
BREAK_GLASS_PROFILE_VERSION = "v1"
BREAK_GLASS_PROFILES: dict[str, dict[str, Any]] = {
    "node_readonly_triage_v1": {
        "profileId": "node_readonly_triage_v1",
        "profileVersion": BREAK_GLASS_PROFILE_VERSION,
        "enabled": BREAK_GLASS_ENABLED and bool(BREAK_GLASS_IMAGE_DIGEST),
        "imageDigest": BREAK_GLASS_IMAGE_DIGEST or "not-configured",
        "fixedEntrypoint": ["/aiops/breakglass-runner", "--profile", "node-readonly-triage"],
        "arbitraryCommandInputAllowed": False,
        "privilegedJob": {
            "enabled": BREAK_GLASS_ENABLED and bool(BREAK_GLASS_IMAGE_DIGEST),
            "hostPID": True,
            "privileged": True,
            "readOnlyRootFilesystem": True,
        },
        "scheduling": {
            "nodeBinding": "targetNodeNameAndUid",
            "tolerations": "profile-defined-only",
            "serviceAccount": "aiops-breakglass",
        },
        "network": {
            "egressPolicy": "deny-except-controller",
        },
        "cleanup": {
            "activeDeadlineSeconds": 300,
            "ttlSecondsAfterFinished": 600,
            "reconciliationCleanupRequired": True,
        },
        "audit": {
            "stream": "aiopsBreakGlassAudit",
            "separateAuditRequired": True,
        },
    }
}
BREAK_GLASS_PROFILE_BUNDLE = {
    "schemaVersion": "v1",
    "version": BREAK_GLASS_PROFILE_VERSION,
    "profiles": BREAK_GLASS_PROFILES,
}
BREAK_GLASS_PROFILE_DIGEST = canonical_digest(BREAK_GLASS_PROFILE_BUNDLE)
HOST_DIAGNOSTIC_COLLECTOR_VERSION = "v1"
HOST_DIAGNOSTIC_COLLECTOR_BUNDLE = {
    "schemaVersion": "v1",
    "version": HOST_DIAGNOSTIC_COLLECTOR_VERSION,
    "collectors": HOST_DIAGNOSTIC_COLLECTORS,
}
HOST_DIAGNOSTIC_COLLECTOR_DIGEST = canonical_digest(HOST_DIAGNOSTIC_COLLECTOR_BUNDLE)
DIAGNOSTIC_REQUEST_DIGEST_FIELDS = (
    "schemaVersion",
    "clusterId",
    "requester",
    "targetNode",
    "collector",
    "collectorVersion",
    "collectorProfile",
    "timeRange",
    "limits",
    "evidencePolicy",
    "policy",
)
CANDIDATE_ACTION_DIGEST_FIELDS = (
    "schemaVersion",
    "clusterId",
    "requester",
    "target",
    "action",
    "policy",
)
SEALED_ACTION_PLAN_DIGEST_FIELDS = (
    "schemaVersion",
    "clusterId",
    "metadata",
    "target",
    "action",
    "safety",
    "approvalPresentation",
)


def increment_metric(name: str, value: int = 1) -> None:
    METRICS[name] = METRICS.get(name, 0) + value


def bounded_put(store: dict[str, dict[str, Any]], key: str, value: dict[str, Any], limit: int) -> None:
    store[key] = value
    while len(store) > limit:
        oldest_key = next(iter(store))
        store.pop(oldest_key, None)


def current_namespace() -> str:
    if RECORD_STORE_NAMESPACE:
        return RECORD_STORE_NAMESPACE
    try:
        return open(SERVICEACCOUNT_NAMESPACE_FILE, encoding="utf-8").read().strip() or "default"
    except OSError:
        return "default"


def record_store_auth_header() -> str:
    try:
        token = open(RECORD_STORE_TOKEN_FILE, encoding="utf-8").read().strip()
    except OSError as exc:
        raise HTTPException(status_code=503, detail="record store token is unavailable") from exc
    return f"Bearer {token}"


RECORD_STORES: dict[str, tuple[dict[str, dict[str, Any]], int, str]] = {
    "diagnosticRequests": (DIAGNOSTIC_REQUESTS, DIAGNOSTIC_MAX_RECORDS, "diagnosticRequests.json"),
    "actionProposals": (ACTION_PROPOSALS, ACTION_MAX_RECORDS, "actionProposals.json"),
    "sealedActionPlans": (SEALED_ACTION_PLANS, ACTION_MAX_RECORDS, "sealedActionPlans.json"),
    "approvalDecisions": (APPROVAL_DECISIONS, ACTION_MAX_RECORDS, "approvalDecisions.json"),
    "executionRecords": (EXECUTION_RECORDS, ACTION_MAX_RECORDS, "executionRecords.json"),
    "runbookPlans": (RUNBOOK_PLANS, RUNBOOK_MAX_RECORDS, "runbookPlans.json"),
    "preapprovedPatchRequests": (
        PREAPPROVED_PATCH_REQUESTS,
        RUNBOOK_MAX_RECORDS,
        "preapprovedPatchRequests.json",
    ),
    "breakGlassRequests": (BREAK_GLASS_REQUESTS, BREAK_GLASS_MAX_RECORDS, "breakGlassRequests.json"),
}


def record_store_path(namespace: str) -> str:
    return f"/api/v1/namespaces/{namespace}/configmaps/{RECORD_STORE_CONFIGMAP}"


async def record_store_request(
    method: str,
    path: str,
    *,
    body: Mapping[str, Any] | None = None,
    content_type: str = "application/json",
) -> httpx.Response:
    if not OPENSHIFT_API_URL:
        raise HTTPException(status_code=503, detail="OPENSHIFT_API_URL is not configured")
    headers = {
        "Accept": "application/json",
        "Authorization": record_store_auth_header(),
    }
    if body is not None:
        headers["Content-Type"] = content_type
    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        return await client.request(method, f"{OPENSHIFT_API_URL}{path}", headers=headers, json=body)


async def load_record_store() -> None:
    if not RECORD_STORE_ENABLED:
        return
    namespace = current_namespace()
    try:
        response = await record_store_request("GET", record_store_path(namespace))
        if response.status_code == 404:
            increment_metric("aiops_record_store_loads_total")
            return
        if response.status_code >= 400:
            increment_metric("aiops_record_store_failures_total")
            return
        payload = response.json()
        data = payload.get("data") if isinstance(payload, Mapping) else {}
        if not isinstance(data, Mapping):
            return
        for _store_name, (store, limit, key) in RECORD_STORES.items():
            raw = data.get(key)
            if not isinstance(raw, str) or not raw.strip():
                continue
            loaded = json.loads(raw)
            if not isinstance(loaded, Mapping):
                continue
            store.clear()
            for record_key, record in list(loaded.items())[-limit:]:
                if isinstance(record_key, str) and isinstance(record, Mapping):
                    store[record_key] = dict(record)
        increment_metric("aiops_record_store_loads_total")
    except Exception:
        increment_metric("aiops_record_store_failures_total")


async def persist_record_store(store_name: str) -> None:
    if not RECORD_STORE_ENABLED:
        return
    definition = RECORD_STORES.get(store_name)
    if not definition:
        return
    store, _limit, key = definition
    namespace = current_namespace()
    data_value = json.dumps(redact_sensitive(store), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    patch_body = {"data": {key: data_value}}
    try:
        response = await record_store_request(
            "PATCH",
            record_store_path(namespace),
            body=patch_body,
            content_type="application/merge-patch+json",
        )
        if response.status_code == 404:
            create_body = {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {
                    "name": RECORD_STORE_CONFIGMAP,
                    "namespace": namespace,
                    "labels": {"app": "komsco-ai-gateway", "aiops.komsco/store": "ledger"},
                },
                "data": {key: data_value},
            }
            response = await record_store_request(
                "POST",
                f"/api/v1/namespaces/{namespace}/configmaps",
                body=create_body,
            )
        if response.status_code >= 400:
            increment_metric("aiops_record_store_failures_total")
            return
        increment_metric("aiops_record_store_writes_total")
    except Exception:
        increment_metric("aiops_record_store_failures_total")


async def bounded_put_record(
    store_name: str,
    key: str,
    value: dict[str, Any],
) -> None:
    store, limit, _data_key = RECORD_STORES[store_name]
    bounded_put(store, key, value, limit)
    await persist_record_store(store_name)


@app.on_event("startup")
async def startup_load_record_store() -> None:
    await load_record_store()


def enforce_rate_limit(user_auth_header: str) -> None:
    if RATE_LIMIT_PER_MINUTE <= 0:
        return

    now = time.monotonic()
    bucket_key = canonical_digest(user_auth_header)
    bucket = [item for item in RATE_LIMIT_BUCKETS.get(bucket_key, []) if now - item < 60.0]
    if len(bucket) >= RATE_LIMIT_PER_MINUTE:
        increment_metric("aiops_rate_limited_total")
        raise HTTPException(status_code=429, detail="KOMSCO AI request rate limit exceeded")

    bucket.append(now)
    RATE_LIMIT_BUCKETS[bucket_key] = bucket


def record_workflow(
    *,
    run_id: str,
    incident_id: str,
    policy: Mapping[str, Any],
    request_id: str,
    stage: str,
    status: str,
    subject: Mapping[str, Any] | None,
    target: Mapping[str, Any] | None = None,
) -> None:
    existing = WORKFLOW_RECORDS.get(run_id, {})
    record = {
        "schemaVersion": "v1",
        "createdAt": existing.get("createdAt") or now_rfc3339(),
        "incidentId": incident_id,
        "lastUpdatedAt": now_rfc3339(),
        "policy": redact_sensitive(dict(policy)),
        "requestId": request_id,
        "runId": run_id,
        "stage": stage,
        "status": status,
        "subject": redact_sensitive(dict(subject or safe_subject(None))),
        "target": redact_sensitive(dict(target or existing.get("target") or {})),
    }
    bounded_put(WORKFLOW_RECORDS, run_id, record, WORKFLOW_MAX_RECORDS)


def can_subject_read_record(record: Mapping[str, Any], subject: Mapping[str, Any]) -> bool:
    record_subject = record.get("originatingSubject") or record.get("subject") or {}
    if not isinstance(record_subject, Mapping):
        return False

    return (
        record_subject.get("username") == subject.get("username")
        and record_subject.get("uid") == subject.get("uid")
        and record_subject.get("groupsDigest") == subject.get("groupsDigest")
    )


def diagnostic_request_digest(candidate: Mapping[str, Any]) -> str:
    projection = {field: candidate.get(field) for field in DIAGNOSTIC_REQUEST_DIGEST_FIELDS}
    return canonical_digest(redact_sensitive(projection))


def build_diagnostic_request_candidate(
    request: "DiagnosticRequestCreate",
    subject: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        collector_profile = get_host_diagnostic_collector(request.collector)
    except AiopsCoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if request.collectorVersion != collector_profile["collectorVersion"]:
        raise HTTPException(status_code=400, detail="collectorVersion does not match the registry")
    if request.collectorProfile != collector_profile["collectorProfile"]:
        raise HTTPException(status_code=400, detail="collectorProfile does not match the registry")
    candidate = {
        "schemaVersion": "v1",
        "clusterId": CLUSTER_ID,
        "requester": redact_sensitive(dict(subject)),
        "targetNode": request.targetNode.model_dump(),
        "collector": request.collector,
        "collectorVersion": request.collectorVersion,
        "collectorProfile": request.collectorProfile,
        "collectorRegistry": {
            "version": HOST_DIAGNOSTIC_COLLECTOR_VERSION,
            "digest": HOST_DIAGNOSTIC_COLLECTOR_DIGEST,
        },
        "collectorConstraints": collector_profile,
        "timeRange": request.timeRange.model_dump(),
        "limits": request.limits.model_dump(),
        "evidencePolicy": request.evidencePolicy.model_dump(),
        "policy": redact_sensitive(dict(request.policy)),
    }
    return candidate


def build_diagnostic_request_record(
    request: "DiagnosticRequestCreate",
    subject: Mapping[str, Any],
) -> dict[str, Any]:
    candidate = build_diagnostic_request_candidate(request, subject)
    request_digest = diagnostic_request_digest(candidate)
    request_id = f"diag-{request_digest.removeprefix('sha256:')[:16]}"
    grant_reference_digest = canonical_digest(
        {
            "audience": "aiops-host-diagnostics-controller",
            "requestDigest": request_digest,
            "requestId": request_id,
        }
    )
    return {
        "schemaVersion": "v1",
        "apiVersion": "aiops.komsco/v1",
        "kind": "DiagnosticRequestRecord",
        "metadata": {
            "name": request_id,
            "createdAt": now_rfc3339(),
        },
        "spec": {
            "candidate": candidate,
            "diagnosticRequestDigest": request_digest,
            "digestSchema": {
                "name": "diagnostic-request-digest-v1",
                "canonicalization": "stable-json-sort-keys",
                "includedFields": list(DIAGNOSTIC_REQUEST_DIGEST_FIELDS),
            },
            "grantRef": {
                "grantId": f"diag-grant-{request_digest.removeprefix('sha256:')[:16]}",
                "grantDigest": grant_reference_digest,
                "bearerGrantStored": False,
            },
            "incidentId": request.incidentId,
            "runId": request.runId,
            "status": {
                "phase": "pending_controller_submission" if DIAGNOSTICS_ENABLED else "disabled",
                "reason": (
                    "Host diagnostics controller submission is enabled."
                    if DIAGNOSTICS_ENABLED
                    else "Host diagnostics controller submission is disabled by configuration."
                ),
                "submittedToController": False,
            },
        },
        "subject": redact_sensitive(dict(subject)),
    }


async def submit_diagnostic_request_to_controller(record: dict[str, Any]) -> dict[str, Any]:
    status = record["spec"]["status"]
    if not DIAGNOSTICS_ENABLED:
        return record
    if not HOST_DIAGNOSTICS_CONTROLLER_URL:
        status.update(
            {
                "phase": "controller_unconfigured",
                "reason": "Host diagnostics controller URL is not configured.",
                "submittedToController": False,
            }
        )
        return record

    headers: dict[str, str] = {}
    if HOST_DIAGNOSTICS_CONTROLLER_SHARED_TOKEN:
        headers["Authorization"] = f"Bearer {HOST_DIAGNOSTICS_CONTROLLER_SHARED_TOKEN}"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
            response = await client.post(
                f"{HOST_DIAGNOSTICS_CONTROLLER_URL}/v1/controller/diagnostics/requests",
                headers=headers,
                json={"diagnosticRequest": record},
            )
    except httpx.HTTPError as exc:
        status.update(
            {
                "phase": "controller_submission_failed",
                "reason": f"Host diagnostics controller request failed: {exc.__class__.__name__}",
                "submittedToController": False,
            }
        )
        return record

    if response.status_code >= 400:
        status.update(
            {
                "phase": "controller_submission_failed",
                "reason": f"Host diagnostics controller returned HTTP {response.status_code}",
                "submittedToController": False,
                "controllerError": redact_sensitive(response.text[:1000]),
            }
        )
        return record

    try:
        controller_result = response.json()
    except ValueError:
        controller_result = {"raw": response.text[:1000]}
    status.update(
        {
            "phase": "controller_submitted",
            "reason": "Host diagnostics controller accepted the request.",
            "submittedToController": True,
            "controllerSubmission": redact_sensitive(controller_result),
        }
    )
    return record


def compact_controller_submission(controller_result: Mapping[str, Any]) -> dict[str, Any]:
    compacted = redact_sensitive(dict(controller_result))
    spec = compacted.get("spec") if isinstance(compacted.get("spec"), Mapping) else {}
    collector_pod = spec.get("collectorPod") if isinstance(spec.get("collectorPod"), Mapping) else {}
    log_preview = collector_pod.get("logPreview")
    if isinstance(log_preview, str):
        collector_pod["logPreviewDigest"] = canonical_digest(log_preview)
        collector_pod["logPreviewBytes"] = len(log_preview.encode("utf-8"))
        collector_pod.pop("logPreview", None)
    return compacted


def normalize_controller_phase(phase: str) -> str:
    if phase == "completed":
        return "succeeded"
    return phase


async def refresh_diagnostic_request_from_controller(record: dict[str, Any]) -> dict[str, Any]:
    status = record["spec"]["status"]
    if not DIAGNOSTICS_ENABLED or not HOST_DIAGNOSTICS_CONTROLLER_URL:
        return record
    if status.get("submittedToController") is not True:
        return record
    request_id = str(record["metadata"]["name"])
    headers: dict[str, str] = {}
    if HOST_DIAGNOSTICS_CONTROLLER_SHARED_TOKEN:
        headers["Authorization"] = f"Bearer {HOST_DIAGNOSTICS_CONTROLLER_SHARED_TOKEN}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
            response = await client.get(
                f"{HOST_DIAGNOSTICS_CONTROLLER_URL}/v1/controller/diagnostics/requests/{request_id}",
                headers=headers,
            )
    except httpx.HTTPError:
        return record
    if response.status_code >= 400:
        return record
    try:
        controller_result = response.json()
    except ValueError:
        return record
    controller_spec = (
        controller_result.get("spec") if isinstance(controller_result, Mapping) else {}
    )
    phase = controller_spec.get("phase") if isinstance(controller_spec, Mapping) else None
    if isinstance(phase, str) and phase:
        status["phase"] = f"collector_{normalize_controller_phase(phase)}"
    status["controllerSubmission"] = compact_controller_submission(controller_result)
    return record


def expires_at_rfc3339(delta: timedelta) -> str:
    return (datetime.now(UTC) + delta).isoformat()


def get_action_registry_entry(tool_name: str, tool_version: str) -> dict[str, Any]:
    entry = ACTION_REGISTRY_ENTRIES.get(tool_name)
    if not entry or entry.get("toolVersion") != tool_version:
        raise HTTPException(status_code=400, detail="Action is not in the configured allow-list")
    return entry


def normalize_action_parameters(
    action: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    tool_name = action.get("toolName")
    if tool_name == "rollout_restart_deployment":
        restarted_at = parameters.get("restartedAt")
        return {
            "restartedAt": restarted_at if isinstance(restarted_at, str) else now_rfc3339(),
        }

    if tool_name == "set_replicas_within_bounds":
        replicas = parameters.get("replicas")
        min_replicas = parameters.get("minReplicas", 0)
        max_replicas = parameters.get("maxReplicas", 20)
        hpa_reviewed = parameters.get("hpaReviewed", False)
        if (
            isinstance(replicas, bool)
            or isinstance(min_replicas, bool)
            or isinstance(max_replicas, bool)
            or not isinstance(hpa_reviewed, bool)
            or not isinstance(replicas, int)
            or not isinstance(min_replicas, int)
            or not isinstance(max_replicas, int)
        ):
            raise HTTPException(status_code=400, detail="replicas bounds must be integer values")
        if min_replicas < 0 or max_replicas < min_replicas or not (min_replicas <= replicas <= max_replicas):
            raise HTTPException(status_code=400, detail="replicas must be within minReplicas/maxReplicas")
        return {
            "maxReplicas": max_replicas,
            "minReplicas": min_replicas,
            "replicas": replicas,
            "hpaReviewed": hpa_reviewed,
        }

    if tool_name == "evict_one_unhealthy_controller_owned_pod":
        reason = parameters.get("reason")
        return {"reason": reason if isinstance(reason, str) else "approved_unhealthy_pod_eviction"}

    if tool_name == "rollback_deployment_to_revision":
        revision = parameters.get("revision")
        if revision is None:
            return {"revision": None}
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise HTTPException(status_code=400, detail="rollback revision must be a positive integer")
        return {"revision": revision}

    if tool_name == "set_hpa_bounds":
        min_replicas = parameters.get("minReplicas")
        max_replicas = parameters.get("maxReplicas")
        allow_max_increase = parameters.get("allowMaxIncrease", False)
        if (
            isinstance(min_replicas, bool)
            or isinstance(max_replicas, bool)
            or not isinstance(min_replicas, int)
            or not isinstance(max_replicas, int)
            or not isinstance(allow_max_increase, bool)
        ):
            raise HTTPException(status_code=400, detail="HPA replica bounds must be integer values")
        if min_replicas < 1 or max_replicas < min_replicas:
            raise HTTPException(status_code=400, detail="HPA maxReplicas must be >= minReplicas")
        return {
            "allowMaxIncrease": allow_max_increase,
            "maxReplicas": max_replicas,
            "minReplicas": min_replicas,
        }

    raise HTTPException(status_code=400, detail="Unsupported action")


def validate_action_target(action: Mapping[str, Any], target: "ActionTarget") -> None:
    expected_kind = action.get("targetKind")
    if expected_kind and target.kind != expected_kind:
        raise HTTPException(
            status_code=400,
            detail=f"Action target kind must be {expected_kind}",
        )


def default_policy_binding(policy: Mapping[str, Any]) -> dict[str, Any]:
    policy_projection = redact_sensitive(dict(policy))
    policy_digest = canonical_digest(policy_projection)
    return {
        "policyDecisionId": policy_projection.get("policyDecisionId") or "pd-local-foundation",
        "policyBundleHash": policy_projection.get("policyBundleHash") or "sha256:local-foundation",
        "policyInputDigest": policy_projection.get("policyInputDigest") or policy_digest,
        "policyDecisionDigest": policy_projection.get("policyDecisionDigest") or policy_digest,
    }


def subject_digest(subject: Mapping[str, Any]) -> str:
    return canonical_digest(
        {
            "groupsDigest": subject.get("groupsDigest"),
            "uid": subject.get("uid"),
            "username": subject.get("username"),
        }
    )


def normalized_parameters_digest(candidate: Mapping[str, Any]) -> str:
    action = candidate.get("action") if isinstance(candidate.get("action"), Mapping) else {}
    return canonical_digest(action.get("normalizedParameters") or {})


def policy_binding_digest(policy: Mapping[str, Any]) -> str:
    return canonical_digest(default_policy_binding(policy))


def candidate_action_request_digest(candidate: Mapping[str, Any]) -> str:
    projection = {field: candidate.get(field) for field in CANDIDATE_ACTION_DIGEST_FIELDS}
    return canonical_digest(redact_sensitive(projection))


def sealed_action_plan_digest(plan: Mapping[str, Any]) -> str:
    projection = {field: plan.get(field) for field in SEALED_ACTION_PLAN_DIGEST_FIELDS}
    return canonical_digest(redact_sensitive(projection))


def build_candidate_action_request(
    request: "ActionProposalCreate",
    subject: Mapping[str, Any],
) -> dict[str, Any]:
    registry_entry = get_action_registry_entry(request.toolName, request.toolVersion)
    validate_action_target(registry_entry, request.target)
    normalized_parameters = normalize_action_parameters(registry_entry, request.parameters)
    return {
        "schemaVersion": "v1",
        "clusterId": CLUSTER_ID,
        "requester": redact_sensitive(dict(subject)),
        "target": request.target.model_dump(),
        "action": {
            "toolName": request.toolName,
            "toolVersion": request.toolVersion,
            "actionRegistry": {
                "version": ACTION_REGISTRY_VERSION,
                "digest": ACTION_REGISTRY_DIGEST,
            },
            "authorization": registry_entry["authorization"],
            "request": registry_entry["request"],
            "normalizedParameters": normalized_parameters,
        },
        "policy": default_policy_binding(request.policy),
    }


def build_action_proposal_record(
    request: "ActionProposalCreate",
    subject: Mapping[str, Any],
) -> dict[str, Any]:
    candidate = build_candidate_action_request(request, subject)
    candidate_digest = candidate_action_request_digest(candidate)
    proposal_id = f"proposal-{candidate_digest.removeprefix('sha256:')[:16]}"
    return {
        "schemaVersion": "v1",
        "apiVersion": "aiops.komsco/v1",
        "kind": "ActionProposalRecord",
        "metadata": {
            "name": proposal_id,
            "createdAt": now_rfc3339(),
        },
        "spec": {
            "candidateActionRequest": candidate,
            "candidateRequestDigest": candidate_digest,
            "digestSchema": {
                "name": "candidate-action-request-digest-v1",
                "canonicalization": "stable-json-sort-keys",
                "includedFields": list(CANDIDATE_ACTION_DIGEST_FIELDS),
            },
            "evidenceRefs": redact_sensitive(request.evidenceRefs),
            "incidentId": request.incidentId,
            "runId": request.runId,
            "runbookRefs": redact_sensitive(request.runbookRefs),
            "status": {"phase": "proposed"},
        },
        "subject": redact_sensitive(dict(subject)),
    }


def build_sealed_action_plan_record(
    proposal: Mapping[str, Any],
) -> dict[str, Any]:
    spec = proposal.get("spec") if isinstance(proposal.get("spec"), Mapping) else {}
    candidate = spec.get("candidateActionRequest") if isinstance(spec.get("candidateActionRequest"), Mapping) else {}
    action = candidate.get("action") if isinstance(candidate.get("action"), Mapping) else {}
    target = candidate.get("target") if isinstance(candidate.get("target"), Mapping) else {}
    requester = candidate.get("requester") if isinstance(candidate.get("requester"), Mapping) else safe_subject(None)
    policy = candidate.get("policy") if isinstance(candidate.get("policy"), Mapping) else {}
    registry_digest = action.get("actionRegistry", {}).get("digest") if isinstance(action.get("actionRegistry"), Mapping) else ""
    plan_id = f"plan-{uuid.uuid4()}"
    incident_id = spec.get("incidentId") or f"inc-{uuid.uuid4()}"
    created_at = now_rfc3339()
    expires_at = expires_at_rfc3339(timedelta(minutes=5))
    dry_run_projection = {
        "candidateRequestDigest": spec.get("candidateRequestDigest"),
        "decision": "not_executed_foundation",
        "mutationsEnabled": MUTATIONS_ENABLED,
    }
    impact_projection = {
        "action": action.get("toolName"),
        "target": target,
    }
    plan_validation_claims = {
        "schemaVersion": "v1",
        "issuer": "aiops-approval-api",
        "audience": "aiops-action-executor",
        "grantId": f"validation-{uuid.uuid4()}",
        "issuedAt": created_at,
        "notBefore": created_at,
        "expiresAt": expires_at_rfc3339(timedelta(seconds=30)),
        "maxUses": 1,
        "clusterId": CLUSTER_ID,
        "candidateRequestDigest": spec.get("candidateRequestDigest"),
        "normalizedParametersDigest": normalized_parameters_digest(candidate),
        "actionRegistryDigest": registry_digest,
        "requesterSubjectDigest": subject_digest(requester),
        "policyDecisionDigest": policy.get("policyDecisionDigest"),
        "policyBindingDigest": policy_binding_digest(policy),
        "action": {
            "toolName": action.get("toolName"),
            "toolVersion": action.get("toolVersion"),
        },
        "target": target,
        "allowedOperation": "server_side_dry_run_only",
    }
    plan_validation_grant_ref = {
        "grantId": plan_validation_claims["grantId"],
        "grantDigest": canonical_digest(plan_validation_claims),
        "bearerGrantStored": False,
        "claimsDigest": canonical_digest(
            {
                "candidateRequestDigest": plan_validation_claims["candidateRequestDigest"],
                "normalizedParametersDigest": plan_validation_claims["normalizedParametersDigest"],
                "actionRegistryDigest": plan_validation_claims["actionRegistryDigest"],
                "requesterSubjectDigest": plan_validation_claims["requesterSubjectDigest"],
                "policyDecisionDigest": plan_validation_claims["policyDecisionDigest"],
                "policyBindingDigest": plan_validation_claims["policyBindingDigest"],
            }
        ),
    }
    plan = {
        "schemaVersion": "v1",
        "clusterId": CLUSTER_ID,
        "metadata": {
            "planId": plan_id,
            "incidentId": incident_id,
            "requester": requester,
            "idempotencyKey": f"idem-{uuid.uuid4()}",
            "createdAt": created_at,
            "apiCallTimeout": "30s",
            "verificationDeadline": "10m",
            "maxMutationAttempts": 1,
            "maxVerificationAttempts": 3,
        },
        "target": target,
        "action": action,
        "safety": {
            "risk": get_action_registry_entry(str(action.get("toolName")), str(action.get("toolVersion")))[
                "risk"
            ],
            "policy": default_policy_binding(policy),
            "planValidationGrantRef": plan_validation_grant_ref,
            "dryRun": {
                "requestDigest": canonical_digest(dry_run_projection),
                "normalizedDiffDigest": canonical_digest(dry_run_projection),
                "decision": "not_executed_foundation",
            },
            "preconditions": [
                {"type": "UIDEquals", "value": target.get("uid")},
                {"type": "ActionRegistryDigestEquals", "value": registry_digest},
                {"type": "RequiresFreshDryRun", "value": True},
            ],
            "hardPostconditions": [
                {"type": "ExecutionRecordTerminalState", "value": True},
            ],
            "observationalPostconditions": [],
            "rollbackDescription": "No automatic rollback is generated by this foundation API.",
            "typedRollbackAction": None,
            "rollbackRequiresApproval": False,
            "rollbackPossible": False,
            "expiresAt": expires_at,
        },
        "approvalPresentation": {
            "impact": {
                "affectedWorkloads": 1,
                "affectedPods": None,
                "availabilityRisk": "unknown",
                "summaryDigest": canonical_digest(impact_projection),
            },
            "dryRun": {
                "normalizedDiffDigest": canonical_digest(dry_run_projection),
                "decision": "not_executed_foundation",
            },
            "evidenceRefs": spec.get("evidenceRefs") or [],
            "runbookRefs": spec.get("runbookRefs") or [],
        },
    }
    plan_digest = sealed_action_plan_digest(plan)
    plan["digest"] = {
        "planDigest": plan_digest,
        "canonicalization": "stable-json-sort-keys",
        "digestSchema": "sealed-action-plan-digest-v1",
        "includedFields": list(SEALED_ACTION_PLAN_DIGEST_FIELDS),
        "excludedFields": ["/digest"],
    }
    return {
        "schemaVersion": "v1",
        "apiVersion": "aiops.komsco/v1",
        "kind": "SealedActionPlanRecord",
        "metadata": {"name": plan_id, "createdAt": created_at},
        "spec": {"sealedActionPlan": plan, "status": {"phase": "sealed"}},
        "subject": redact_sensitive(dict(requester)),
    }


def same_observed_subject(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return (
        left.get("username") == right.get("username")
        and left.get("uid") == right.get("uid")
        and left.get("groupsDigest") == right.get("groupsDigest")
    )


def build_approval_decision_record(
    plan_record: Mapping[str, Any],
    request: "ApprovalDecisionCreate",
    approver: Mapping[str, Any],
    action_access_review: Mapping[str, Any],
    *,
    allow_self_approval: bool = False,
) -> dict[str, Any]:
    plan = plan_record["spec"]["sealedActionPlan"]
    plan_digest = plan["digest"]["planDigest"]
    if request.expectedPlanDigest != plan_digest:
        raise HTTPException(status_code=409, detail="expectedPlanDigest does not match the sealed plan")
    risk = plan["safety"]["risk"]
    requester = plan["metadata"]["requester"]
    if risk in {"medium", "high"} and same_observed_subject(requester, approver) and not allow_self_approval:
        raise HTTPException(status_code=409, detail="separation of duties requires requester and approver to differ")

    approval_id = f"approval-{uuid.uuid4()}"
    approved_at = now_rfc3339()
    expires_at = expires_at_rfc3339(timedelta(minutes=5))
    action = plan["action"]
    target = plan["target"]
    authorization = action.get("authorization") if isinstance(action.get("authorization"), Mapping) else {}
    attestation_claims = {
        "schemaVersion": "v1",
        "issuer": "aiops-tool-broker",
        "audience": "aiops-approval-api",
        "attestationId": f"authz-{uuid.uuid4()}",
        "issuedAt": approved_at,
        "notBefore": approved_at,
        "expiresAt": expires_at_rfc3339(timedelta(seconds=30)),
        "clusterId": CLUSTER_ID,
        "approver": redact_sensitive(dict(approver)),
        "planDigest": plan_digest,
        "action": {
            "toolName": action.get("toolName"),
            "toolVersion": action.get("toolVersion"),
            "actionRegistry": action.get("actionRegistry"),
        },
        "target": target,
        "kubernetesAuthorization": {
            "apiGroup": authorization.get("apiGroup", ""),
            "resource": authorization.get("resource", ""),
            "subresource": authorization.get("subresource", ""),
            "verb": authorization.get("verb", ""),
        },
    }
    return {
        "schemaVersion": "v1",
        "apiVersion": "aiops.komsco/v1",
        "kind": "ApprovalDecisionRecord",
        "metadata": {"name": approval_id, "createdAt": approved_at},
        "spec": {
            "approvalDecision": {
                "approvalId": approval_id,
                "planDigest": plan_digest,
                "status": "approved",
                "approver": redact_sensitive(dict(approver)),
                "approvedAt": approved_at,
                "expiresAt": expires_at,
                "approvalScope": request.approvalScope,
                "target": target,
                "authorizationAttestationRef": {
                    "attestationId": attestation_claims["attestationId"],
                    "attestationDigest": canonical_digest(attestation_claims),
                    "bearerAttestationStored": False,
                    "issuer": attestation_claims["issuer"],
                    "audience": attestation_claims["audience"],
                },
                "kubernetesAuthorization": {
                    "apiGroup": authorization.get("apiGroup", ""),
                    "resource": authorization.get("resource", ""),
                    "subresource": authorization.get("subresource", ""),
                    "verb": authorization.get("verb", ""),
                    "ssarDecision": "allowed" if action_access_review.get("allowed") is True else "denied",
                    "evaluatedAt": approved_at,
                    "review": redact_sensitive(dict(action_access_review)),
                },
                "action": {
                    "toolName": action.get("toolName"),
                    "toolVersion": action.get("toolVersion"),
                    "actionRegistry": action.get("actionRegistry"),
                },
            }
        },
        "subject": redact_sensitive(dict(approver)),
    }


def parse_rfc3339(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def validate_execution_evidence_freshness(plan: Mapping[str, Any]) -> None:
    presentation = plan.get("approvalPresentation")
    if not isinstance(presentation, Mapping):
        return
    evidence_refs = presentation.get("evidenceRefs")
    if not isinstance(evidence_refs, list):
        return
    now = datetime.now(UTC)
    for evidence_ref in evidence_refs:
        if not isinstance(evidence_ref, Mapping):
            continue
        required_until = parse_rfc3339(evidence_ref.get("requiredFreshUntil"))
        if required_until and required_until < now:
            increment_metric("aiops_evidence_freshness_failures_total")
            raise HTTPException(
                status_code=409,
                detail=(
                    "Sealed action plan evidence is no longer fresh; "
                    "create a new plan and approval"
                ),
            )


def validate_approval_is_active(approval_decision: Mapping[str, Any]) -> None:
    expires_at = parse_rfc3339(approval_decision.get("expiresAt"))
    if expires_at and expires_at < datetime.now(UTC):
        raise HTTPException(status_code=409, detail="Approval decision is expired")


def approval_already_executed(approval_id: str) -> bool:
    return any(
        record.get("spec", {}).get("approvalId") == approval_id
        for record in EXECUTION_RECORDS.values()
        if isinstance(record.get("spec"), Mapping)
    )


def build_execution_grant_reference(
    approval: Mapping[str, Any],
    plan: Mapping[str, Any],
    approver: Mapping[str, Any],
) -> dict[str, Any]:
    decision = approval["spec"]["approvalDecision"]
    sealed_plan = plan["spec"]["sealedActionPlan"]
    grant_id = f"exec-grant-{uuid.uuid4()}"
    issued_at = now_rfc3339()
    expires_at = expires_at_rfc3339(timedelta(seconds=30))
    grant_claims = {
        "schemaVersion": "v1",
        "issuer": "aiops-approval-api",
        "audience": "aiops-action-executor",
        "grantId": grant_id,
        "issuedAt": issued_at,
        "notBefore": issued_at,
        "expiresAt": expires_at,
        "clusterId": CLUSTER_ID,
        "planDigest": decision["planDigest"],
        "approvalId": decision["approvalId"],
        "approver": redact_sensitive(dict(approver)),
        "action": decision["action"],
        "target": decision["target"],
        "kubernetesAuthorization": decision["kubernetesAuthorization"],
        "policyBundleHash": sealed_plan["safety"]["policy"]["policyBundleHash"],
    }
    return {
        "grantId": grant_id,
        "grantDigest": canonical_digest(grant_claims),
        "bearerGrantStored": False,
        "claims": grant_claims,
    }


def get_runbook_entry(runbook_id: str) -> dict[str, Any]:
    entry = RUNBOOK_REGISTRY_ENTRIES.get(runbook_id)
    if not entry:
        raise HTTPException(status_code=400, detail="Runbook is not in the configured registry")
    return entry


def platform_namespace_requires_explicit_policy(namespace: str) -> bool:
    return namespace.startswith(("kube-", "openshift-"))


def evaluate_runbook_policy(
    runbook: Mapping[str, Any],
    target: "ActionTarget",
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    checks = runbook.get("policyChecks") if isinstance(runbook.get("policyChecks"), Mapping) else {}
    failures: list[str] = []
    warnings: list[str] = []
    if checks.get("namespaceRequired") and not target.namespace:
        failures.append("namespace is required")
    if checks.get("targetUidRequired") and not target.uid:
        failures.append("target uid is required")
    if target.kind != runbook.get("targetKind"):
        failures.append(f"target kind must be {runbook.get('targetKind')}")
    if checks.get("platformNamespaceRequiresExplicitPolicy") and platform_namespace_requires_explicit_policy(
        target.namespace
    ):
        if policy.get("allowPlatformNamespace") is not True:
            failures.append("platform namespace requires explicit policy allowPlatformNamespace=true")
    if checks.get("ownerReviewRequired"):
        warnings.append("owner, GitOps, Operator, and external controller review required before execution")
    if checks.get("hpaReviewRequired"):
        warnings.append("HPA ownership review required before bounded scale execution")
    if checks.get("hpaPolicyReviewRequired"):
        warnings.append("HPA min/max bounds and targetRef review required before execution")
    if checks.get("rollbackRevisionReviewRequired"):
        warnings.append("ReplicaSet revision, image digest, and template diff review required before rollback")
    if checks.get("controllerOwnerRequired"):
        warnings.append("controller owner reference must be verified before eviction execution")
    if checks.get("pdbReviewRequired"):
        warnings.append("PDB allowance must be verified before eviction execution")
    return {
        "decision": "denied" if failures else "requires_approval",
        "failures": failures,
        "warnings": warnings,
    }


def build_runbook_plan_record(
    request: "RunbookPlanCreate",
    subject: Mapping[str, Any],
) -> dict[str, Any]:
    runbook = get_runbook_entry(request.runbookId)
    policy = default_policy_binding(request.policy)
    policy_result = evaluate_runbook_policy(runbook, request.target, request.policy)
    step_plans: list[dict[str, Any]] = []
    for step in runbook["allowedSteps"]:
        action_request = ActionProposalCreate(
            incidentId=request.incidentId,
            runId=request.runId,
            toolName=step["toolName"],
            toolVersion=step["toolVersion"],
            target=request.target,
            parameters=request.parameters,
            evidenceRefs=request.evidenceRefs,
            runbookRefs=[
                {
                    "id": runbook["runbookId"],
                    "version": runbook["runbookVersion"],
                    "contentDigest": RUNBOOK_REGISTRY_DIGEST,
                }
            ],
            policy=policy,
        )
        candidate = build_candidate_action_request(action_request, subject)
        step_plans.append(
            {
                "stepId": step["stepId"],
                "toolName": step["toolName"],
                "toolVersion": step["toolVersion"],
                "candidateActionRequest": candidate,
                "candidateRequestDigest": candidate_action_request_digest(candidate),
            }
        )

    plan_digest = canonical_digest(
        {
            "runbook": {
                "runbookId": runbook["runbookId"],
                "runbookVersion": runbook["runbookVersion"],
                "registryDigest": RUNBOOK_REGISTRY_DIGEST,
            },
            "stepPlans": step_plans,
            "target": request.target.model_dump(),
            "policy": policy,
        }
    )
    plan_id = f"runbook-plan-{plan_digest.removeprefix('sha256:')[:16]}"
    created_at = now_rfc3339()
    return {
        "schemaVersion": "v1",
        "apiVersion": "aiops.komsco/v1",
        "kind": "RunbookPlanRecord",
        "metadata": {"name": plan_id, "createdAt": created_at},
        "spec": {
            "runbook": {
                "runbookId": runbook["runbookId"],
                "runbookVersion": runbook["runbookVersion"],
                "incidentClass": runbook["incidentClass"],
                "registryDigest": RUNBOOK_REGISTRY_DIGEST,
            },
            "target": request.target.model_dump(),
            "stepPlans": step_plans,
            "policy": policy,
            "policyResult": policy_result,
            "evidenceRefs": redact_sensitive(request.evidenceRefs),
            "incidentId": request.incidentId,
            "runId": request.runId,
            "digest": {
                "runbookPlanDigest": plan_digest,
                "canonicalization": "stable-json-sort-keys",
            },
            "status": {"phase": "denied" if policy_result["failures"] else "waiting_for_approval"},
        },
        "subject": redact_sensitive(dict(subject)),
    }


def get_preapproved_patch_schema(field_schema_id: str) -> dict[str, Any]:
    schema = PREAPPROVED_PATCH_FIELD_SCHEMAS.get(field_schema_id)
    if not schema:
        raise HTTPException(status_code=400, detail="Field schema is not preapproved")
    return schema


def validate_preapproved_patch_value(schema: Mapping[str, Any], target: "ActionTarget", value: Any) -> None:
    if target.kind != schema.get("targetKind"):
        raise HTTPException(status_code=400, detail=f"Patch target kind must be {schema.get('targetKind')}")
    if target.apiVersion != schema.get("apiVersion"):
        raise HTTPException(status_code=400, detail=f"Patch target apiVersion must be {schema.get('apiVersion')}")
    if schema.get("valueType") == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise HTTPException(status_code=400, detail="Preapproved patch value must be an integer")
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, int) and value < minimum:
            raise HTTPException(status_code=400, detail="Preapproved patch value is below the documented minimum")
        if isinstance(maximum, int) and value > maximum:
            raise HTTPException(status_code=400, detail="Preapproved patch value exceeds the documented maximum")


def build_preapproved_patch_record(
    request: "PatchPreapprovedFieldCreate",
    subject: Mapping[str, Any],
) -> dict[str, Any]:
    schema = get_preapproved_patch_schema(request.fieldSchemaId)
    validate_preapproved_patch_value(schema, request.target, request.value)
    policy = default_policy_binding(request.policy)
    request_projection = {
        "schemaVersion": "v1",
        "clusterId": CLUSTER_ID,
        "requester": redact_sensitive(dict(subject)),
        "target": request.target.model_dump(),
        "fieldSchema": schema,
        "value": redact_sensitive(request.value),
        "policy": policy,
        "evidenceRefs": redact_sensitive(request.evidenceRefs),
    }
    request_digest = canonical_digest(request_projection)
    request_id = f"prepatch-{request_digest.removeprefix('sha256:')[:16]}"
    return {
        "schemaVersion": "v1",
        "apiVersion": "aiops.komsco/v1",
        "kind": "PatchPreapprovedFieldRequestRecord",
        "metadata": {"name": request_id, "createdAt": now_rfc3339()},
        "spec": {
            "fieldSchema": schema,
            "target": request.target.model_dump(),
            "value": redact_sensitive(request.value),
            "patch": {
                "op": "replace",
                "path": schema["jsonPointer"],
                "value": redact_sensitive(request.value),
            },
            "policy": policy,
            "evidenceRefs": redact_sensitive(request.evidenceRefs),
            "incidentId": request.incidentId,
            "runId": request.runId,
            "digest": {
                "patchRequestDigest": request_digest,
                "schemaBundleDigest": PREAPPROVED_PATCH_FIELD_DIGEST,
                "canonicalization": "stable-json-sort-keys",
            },
            "status": {
                "phase": "waiting_for_approval",
                "mutationSubmitted": False,
                "reason": "patch_preapproved_field is a documented request only until Action Executor integration.",
            },
        },
        "subject": redact_sensitive(dict(subject)),
    }


def get_break_glass_profile(profile_id: str) -> dict[str, Any]:
    profile = BREAK_GLASS_PROFILES.get(profile_id)
    if not profile:
        raise HTTPException(status_code=400, detail="Break-glass profile is not configured")
    return profile


def build_break_glass_request_record(
    request: "BreakGlassRequestCreate",
    subject: Mapping[str, Any],
) -> dict[str, Any]:
    profile = get_break_glass_profile(request.profileId)
    policy = default_policy_binding(request.policy)
    request_projection = {
        "schemaVersion": "v1",
        "clusterId": CLUSTER_ID,
        "requester": redact_sensitive(dict(subject)),
        "profile": {
            "profileId": profile["profileId"],
            "profileVersion": profile["profileVersion"],
            "profileDigest": BREAK_GLASS_PROFILE_DIGEST,
            "imageDigest": profile["imageDigest"],
            "fixedEntrypoint": profile["fixedEntrypoint"],
        },
        "targetNode": request.targetNode.model_dump(),
        "justificationDigest": canonical_digest(redact_sensitive(request.justification)),
        "policy": policy,
        "evidenceRefs": redact_sensitive(request.evidenceRefs),
    }
    request_digest = canonical_digest(request_projection)
    request_id = f"breakglass-{request_digest.removeprefix('sha256:')[:16]}"
    enabled = bool(profile.get("enabled"))
    phase = "pending_privileged_job_controller" if enabled else "disabled"
    reason = (
        "Break-glass profile is enabled and ready for a dedicated controller."
        if enabled
        else "Break-glass host operations are disabled by configuration or missing fixed image digest."
    )
    return {
        "schemaVersion": "v1",
        "apiVersion": "aiops.komsco/v1",
        "kind": "BreakGlassRequestRecord",
        "metadata": {"name": request_id, "createdAt": now_rfc3339()},
        "spec": {
            "profile": {
                "profileId": profile["profileId"],
                "profileVersion": profile["profileVersion"],
                "profileDigest": BREAK_GLASS_PROFILE_DIGEST,
                "enabled": enabled,
                "imageDigest": profile["imageDigest"],
                "fixedEntrypoint": profile["fixedEntrypoint"],
                "arbitraryCommandInputAllowed": False,
            },
            "targetNode": request.targetNode.model_dump(),
            "justificationDigest": canonical_digest(redact_sensitive(request.justification)),
            "policy": policy,
            "evidenceRefs": redact_sensitive(request.evidenceRefs),
            "incidentId": request.incidentId,
            "runId": request.runId,
            "jobTemplateConstraints": {
                "privilegedJob": profile["privilegedJob"],
                "scheduling": {
                    **profile["scheduling"],
                    "targetNodeName": request.targetNode.name,
                    "targetNodeUid": request.targetNode.uid,
                },
                "network": profile["network"],
                "cleanup": profile["cleanup"],
            },
            "digest": {
                "breakGlassRequestDigest": request_digest,
                "profileBundleDigest": BREAK_GLASS_PROFILE_DIGEST,
                "canonicalization": "stable-json-sort-keys",
            },
            "audit": profile["audit"],
            "status": {
                "phase": phase,
                "jobSubmitted": False,
                "arbitraryCommandRejected": True,
                "reason": reason,
            },
        },
        "subject": redact_sensitive(dict(subject)),
    }


class ImageAttachment(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=180)
    mimeType: str = Field(min_length=1, max_length=80)
    size: int = Field(ge=1, le=MAX_IMAGE_ATTACHMENT_BYTES)
    data: str = Field(min_length=1)


class ChatContextMessage(BaseModel):
    role: str = Field(min_length=1, max_length=20)
    content: str = Field(default="", max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=4000)
    pageContext: dict[str, Any] | None = None
    conversationId: str | None = None
    runId: str | None = None
    recentMessages: list[ChatContextMessage] = Field(default_factory=list, max_length=8)
    attachments: list[ImageAttachment] = Field(default_factory=list, max_length=MAX_IMAGE_ATTACHMENTS)


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DiagnosticTargetNode(StrictBaseModel):
    name: str = Field(min_length=1, max_length=253)
    uid: str = Field(min_length=1, max_length=128)


class DiagnosticTimeRange(StrictBaseModel):
    since: str = Field(min_length=1, max_length=80)
    until: str = Field(min_length=1, max_length=80)


class DiagnosticLimits(StrictBaseModel):
    deadline: str = Field(default="30s", min_length=1, max_length=32)
    maxBytes: int = Field(default=10 * 1024 * 1024, ge=1, le=100 * 1024 * 1024)
    maxLines: int = Field(default=50000, ge=1, le=500000)


class DiagnosticEvidencePolicy(StrictBaseModel):
    classification: str = Field(default="restricted", min_length=1, max_length=64)
    rawStorageAllowed: bool = False
    redactionPolicyDigest: str = Field(default="sha256:unspecified", min_length=1, max_length=128)


class DiagnosticRequestCreate(StrictBaseModel):
    incidentId: str | None = Field(default=None, max_length=120)
    runId: str | None = Field(default=None, max_length=120)
    targetNode: DiagnosticTargetNode
    collector: str = Field(min_length=1, max_length=120)
    collectorVersion: str = Field(default="v1", min_length=1, max_length=64)
    collectorProfile: str = Field(default="passive-readonly", min_length=1, max_length=80)
    timeRange: DiagnosticTimeRange
    limits: DiagnosticLimits = Field(default_factory=DiagnosticLimits)
    evidencePolicy: DiagnosticEvidencePolicy = Field(default_factory=DiagnosticEvidencePolicy)
    policy: dict[str, Any] = Field(default_factory=dict)


class ActionTarget(StrictBaseModel):
    apiVersion: str = Field(min_length=1, max_length=80)
    kind: str = Field(min_length=1, max_length=80)
    namespace: str = Field(min_length=1, max_length=253)
    name: str = Field(min_length=1, max_length=253)
    uid: str = Field(min_length=1, max_length=128)


class ActionProposalCreate(StrictBaseModel):
    incidentId: str | None = Field(default=None, max_length=120)
    runId: str | None = Field(default=None, max_length=120)
    toolName: str = Field(min_length=1, max_length=120)
    toolVersion: str = Field(default="v1", min_length=1, max_length=64)
    target: ActionTarget
    parameters: dict[str, Any] = Field(default_factory=dict)
    evidenceRefs: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    runbookRefs: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    policy: dict[str, Any] = Field(default_factory=dict)


class SealedActionPlanCreate(StrictBaseModel):
    proposalId: str = Field(min_length=1, max_length=120)


class ApprovalDecisionCreate(StrictBaseModel):
    planId: str = Field(min_length=1, max_length=120)
    expectedPlanDigest: str = Field(min_length=1, max_length=128)
    approvalScope: str = Field(default="single-target", min_length=1, max_length=80)


class ActionExecutionCreate(StrictBaseModel):
    approvalId: str = Field(min_length=1, max_length=120)
    planId: str = Field(min_length=1, max_length=120)
    expectedPlanDigest: str = Field(min_length=1, max_length=128)


class UnrestrictedCommandExecuteCreate(StrictBaseModel):
    command: str = Field(min_length=1, max_length=8000)
    cwd: str | None = Field(default=None, max_length=1000)
    timeoutSeconds: int | None = Field(default=None, ge=1, le=3600)


class RunbookPlanCreate(StrictBaseModel):
    runbookId: str = Field(min_length=1, max_length=160)
    incidentId: str | None = Field(default=None, max_length=120)
    runId: str | None = Field(default=None, max_length=120)
    target: ActionTarget
    parameters: dict[str, Any] = Field(default_factory=dict)
    evidenceRefs: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    policy: dict[str, Any] = Field(default_factory=dict)


class RagSearchFilters(StrictBaseModel):
    sourceTypes: list[str] = Field(default_factory=list, max_length=20)
    namespaces: list[str] = Field(default_factory=list, max_length=20)
    customers: list[str] = Field(default_factory=list, max_length=20)
    aclGroups: list[str] = Field(default_factory=list, max_length=40)
    runbookIds: list[str] = Field(default_factory=list, max_length=40)
    versions: list[str] = Field(default_factory=list, max_length=20)
    labels: dict[str, str] = Field(default_factory=dict)


class RagSearchCreate(StrictBaseModel):
    query: str = Field(min_length=1, max_length=1000)
    topK: int = Field(default=5, ge=1, le=20)
    filters: RagSearchFilters = Field(default_factory=RagSearchFilters)
    includeContent: bool = False
    runId: str | None = Field(default=None, max_length=120)


class RagDocumentUploadCreate(StrictBaseModel):
    name: str = Field(min_length=1, max_length=220)
    mimeType: str = Field(default="text/markdown", min_length=1, max_length=120)
    content: str | None = Field(default=None, max_length=RAG_UPLOAD_MAX_CHARS)
    data: str | None = Field(default=None, max_length=((RAG_UPLOAD_MAX_BYTES * 4) // 3) + 8)
    sourceUri: str | None = Field(default=None, max_length=500)
    sourceType: str = Field(default="user-upload", min_length=1, max_length=80)
    customer: str = Field(default="komsco", min_length=1, max_length=80)
    namespace: str = Field(default="user-upload", min_length=1, max_length=253)
    version: str = Field(default="v0.1.4", min_length=1, max_length=80)
    aclGroups: list[str] = Field(default_factory=list, max_length=40)
    labels: dict[str, str] = Field(default_factory=dict)
    runId: str | None = Field(default=None, max_length=120)


class PatchPreapprovedFieldCreate(StrictBaseModel):
    fieldSchemaId: str = Field(min_length=1, max_length=160)
    incidentId: str | None = Field(default=None, max_length=120)
    runId: str | None = Field(default=None, max_length=120)
    target: ActionTarget
    value: Any
    evidenceRefs: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    policy: dict[str, Any] = Field(default_factory=dict)


class BreakGlassTargetNode(StrictBaseModel):
    name: str = Field(min_length=1, max_length=253)
    uid: str = Field(min_length=1, max_length=128)


class BreakGlassRequestCreate(StrictBaseModel):
    profileId: str = Field(min_length=1, max_length=160)
    incidentId: str | None = Field(default=None, max_length=120)
    runId: str | None = Field(default=None, max_length=120)
    targetNode: BreakGlassTargetNode
    justification: str = Field(min_length=12, max_length=1000)
    evidenceRefs: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    policy: dict[str, Any] = Field(default_factory=dict)


def page_context_namespace(req: ChatRequest) -> str:
    context = normalize_console_page_context(req.pageContext)
    namespace = context.get("namespace")
    return str(namespace) if namespace else ""


def page_context_resource_name(req: ChatRequest, expected_kind: str = "Deployment") -> str:
    context = normalize_console_page_context(req.pageContext)
    kind = str(context.get("resourceKind") or "")
    name = context.get("resourceName")
    if kind == expected_kind and name:
        return str(name)
    return ""


def page_context_aiops_execution_mode(req: ChatRequest) -> str:
    context = normalize_console_page_context(req.pageContext)
    demo_cycle = context.get("aiopsDemoCycle")
    if isinstance(demo_cycle, Mapping) and demo_cycle.get("readOnlyOnly") is True:
        return "read-only"
    mode = str(context.get("aiopsExecutionMode") or "read-only").strip().lower()
    if mode in {"unrestricted", "dev-unrestricted", "experimental", "실험", "무제한"}:
        return "unrestricted"
    if mode in {"execute", "execution", "execution-enabled", "enabled"}:
        return "execute"
    return "read-only"


def execution_mode_allows_actions(req: ChatRequest) -> bool:
    return page_context_aiops_execution_mode(req) in {"execute", "unrestricted"}


UNRESTRICTED_COMMAND_PREFIX_RE = re.compile(
    r"(?is)^\s*(?:/exec|exec:|run:|command:|명령\s*실행:|실행:)\s+(?P<command>.+?)\s*$"
)


def parse_unrestricted_chat_command(message: str) -> str:
    match = UNRESTRICTED_COMMAND_PREFIX_RE.match(message)
    if not match:
        return ""
    command = match.group("command").strip()
    if command.startswith("```") and command.endswith("```"):
        command = re.sub(r"^```[A-Za-z0-9_-]*\s*", "", command)
        command = re.sub(r"\s*```$", "", command).strip()
    return command


def is_pod_list_request(message: str) -> bool:
    return bool(POD_LIST_REQUEST_RE.search(message))


def pod_list_namespace(req: ChatRequest) -> str:
    match = NAMESPACE_MENTION_RE.search(req.message.lower())
    if match:
        return match.group("namespace") or match.group("namespace_after") or ""
    return page_context_namespace(req)


def namespace_from_natural_action(req: ChatRequest) -> str:
    match = NAMESPACE_MENTION_RE.search(req.message.lower())
    if match:
        return match.group("namespace") or match.group("namespace_after") or ""
    shorthand_match = NAMESPACED_RESOURCE_SHORTHAND_RE.search(req.message.lower())
    if shorthand_match and shorthand_match.group("namespace") not in {"deployment", "deploy", "디플로이먼트"}:
        return shorthand_match.group("namespace")
    return page_context_namespace(req)


def first_backtick_name(message: str) -> str:
    match = BACKTICK_RESOURCE_RE.search(message)
    return match.group("name") if match else ""


def is_pod_count_query(message: str) -> bool:
    return bool(POD_COUNT_QUERY_RE.search(message))


def pod_count_query_namespace(req: ChatRequest) -> str:
    shorthand_match = NAMESPACED_RESOURCE_SHORTHAND_RE.search(req.message.lower())
    if shorthand_match and shorthand_match.group("namespace") not in {
        "deployment",
        "deploy",
        "pod",
        "pods",
        "디플로이먼트",
        "파드",
    }:
        return shorthand_match.group("namespace")
    return pod_list_namespace(req)


def is_reserved_pod_count_target(name: str) -> bool:
    return name.strip().lower() in POD_COUNT_RESERVED_TARGET_NAMES


def pod_count_query_target_name(req: ChatRequest) -> str:
    deployment_match = DEPLOYMENT_RESOURCE_RE.search(req.message)
    if deployment_match:
        return deployment_match.group("name")

    pod_match = POD_RESOURCE_RE.search(req.message)
    if pod_match:
        return pod_match.group("name")

    backtick_name = first_backtick_name(req.message)
    if backtick_name:
        return backtick_name

    shorthand_match = NAMESPACED_RESOURCE_SHORTHAND_RE.search(req.message.lower())
    if shorthand_match:
        return shorthand_match.group("name")

    before_match = POD_COUNT_TARGET_BEFORE_POD_RE.search(req.message)
    if before_match and not is_reserved_pod_count_target(before_match.group("name")):
        return before_match.group("name")

    after_match = POD_COUNT_TARGET_AFTER_POD_RE.search(req.message)
    if after_match and not is_reserved_pod_count_target(after_match.group("name")):
        return after_match.group("name")

    return page_context_resource_name(req, "Deployment") or page_context_resource_name(req, "Pod")


def parse_pod_count_query(req: ChatRequest) -> dict[str, str] | None:
    if not is_pod_count_query(req.message):
        return None

    target_name = pod_count_query_target_name(req)
    if not target_name:
        return {
            "namespace": pod_count_query_namespace(req),
            "targetName": "",
        }

    return {
        "namespace": pod_count_query_namespace(req),
        "targetName": target_name,
    }


def natural_target_name(
    req: ChatRequest,
    match: re.Match[str] | None,
    *,
    expected_kind: str = "Deployment",
) -> str:
    if expected_kind == "Pod":
        resource_match = POD_RESOURCE_RE.search(req.message)
    elif expected_kind == "HorizontalPodAutoscaler":
        resource_match = HPA_RESOURCE_RE.search(req.message)
    else:
        resource_match = DEPLOYMENT_RESOURCE_RE.search(req.message)
    if resource_match:
        return resource_match.group("name")
    backtick_name = first_backtick_name(req.message)
    if backtick_name:
        return backtick_name
    shorthand_match = NAMESPACED_RESOURCE_SHORTHAND_RE.search(req.message.lower())
    if shorthand_match:
        return shorthand_match.group("name")
    if match and "name" in match.groupdict():
        return match.group("name")
    return page_context_resource_name(req, expected_kind)


def rollback_revision_from_message(message: str) -> int | None:
    match = ROLLBACK_REVISION_RE.search(message)
    if not match:
        return None
    revision = match.group("revision") or match.group("korean_revision")
    if not revision:
        return None
    return int(revision)


def hpa_bounds_from_message(message: str) -> tuple[int, int] | None:
    min_match = HPA_MIN_RE.search(message)
    max_match = HPA_MAX_RE.search(message)
    if not min_match or not max_match:
        return None
    min_replicas = int(min_match.group("value"))
    max_replicas = int(max_match.group("value"))
    if min_replicas < 1 or max_replicas < min_replicas:
        return None
    return min_replicas, max_replicas


def is_followup_execution_request(message: str) -> bool:
    return bool(FOLLOWUP_EXECUTION_RE.search(message))


def recent_natural_action_request(req: ChatRequest) -> ChatRequest | None:
    for message in reversed(req.recentMessages):
        role = message.role.strip().lower()
        content = message.content.strip()
        if role != "user" or not content or is_followup_execution_request(content):
            continue

        candidate = ChatRequest(
            message=content,
            pageContext=req.pageContext,
            conversationId=req.conversationId,
            runId=req.runId,
        )
        if parse_natural_action_intent(candidate):
            return candidate

    return None


def parse_natural_action_intent(req: ChatRequest) -> dict[str, Any] | None:
    namespace = namespace_from_natural_action(req)

    if HPA_REQUEST_RE.search(req.message):
        bounds = hpa_bounds_from_message(req.message)
        target_name = natural_target_name(req, None, expected_kind="HorizontalPodAutoscaler")
        if bounds and namespace and target_name:
            min_replicas, max_replicas = bounds
            return {
                "apiVersion": "autoscaling/v2",
                "kind": "HorizontalPodAutoscaler",
                "toolName": "set_hpa_bounds",
                "targetName": target_name,
                "namespace": namespace,
                "parameters": {
                    "allowMaxIncrease": False,
                    "maxReplicas": max_replicas,
                    "minReplicas": min_replicas,
                },
                "summary": (
                    f"HPA `{namespace}/{target_name}` minReplicas를 `{min_replicas}`, "
                    f"maxReplicas를 `{max_replicas}`로 변경"
                ),
            }

    scale_match = SCALE_INTENT_RE.search(req.message)
    replicas_match = scale_match or SCALE_REPLICAS_RE.search(req.message)
    if replicas_match:
        target_name = natural_target_name(req, scale_match)
        replicas = int(replicas_match.group("replicas"))
        if not target_name:
            return None
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "toolName": "set_replicas_within_bounds",
            "targetName": target_name,
            "namespace": namespace,
            "parameters": {
                "hpaReviewed": False,
                "maxReplicas": max(20, replicas),
                "minReplicas": 0,
                "replicas": replicas,
            },
            "summary": f"Deployment `{namespace}/{target_name}` replicas를 `{replicas}`로 변경",
        }

    if POD_EVICTION_REQUEST_RE.search(req.message) and (
        POD_RESOURCE_RE.search(req.message)
        or page_context_resource_name(req, "Pod")
        or re.search(r"(?:pod|pods|파드)", req.message, re.IGNORECASE)
    ):
        target_name = natural_target_name(req, None, expected_kind="Pod")
        if not namespace or not target_name:
            return None
        return {
            "apiVersion": "v1",
            "kind": "Pod",
            "toolName": "evict_one_unhealthy_controller_owned_pod",
            "targetName": target_name,
            "namespace": namespace,
            "parameters": {"reason": "natural_language_unhealthy_pod_eviction"},
            "summary": f"Unhealthy controller-owned Pod `{namespace}/{target_name}` eviction",
        }

    if ROLLBACK_REQUEST_RE.search(req.message):
        target_name = natural_target_name(req, None)
        if not target_name:
            return None
        revision = rollback_revision_from_message(req.message)
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "toolName": "rollback_deployment_to_revision",
            "targetName": target_name,
            "namespace": namespace,
            "parameters": {"revision": revision},
            "summary": (
                f"Deployment `{namespace}/{target_name}` rollback"
                + (f" to revision `{revision}`" if revision else " to previous revision")
            ),
        }

    restart_match = RESTART_INTENT_RE.search(req.message)
    if restart_match or RESTART_REQUEST_RE.search(req.message):
        target_name = natural_target_name(req, restart_match)
        if not target_name:
            return None
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "toolName": "rollout_restart_deployment",
            "targetName": target_name,
            "namespace": namespace,
            "parameters": {"restartedAt": now_rfc3339()},
            "summary": f"Deployment `{namespace}/{target_name}` rollout restart",
        }

    return None


async def create_natural_action_plan(
    req: ChatRequest,
    authorization: str,
    subject: Mapping[str, Any],
    *,
    incident_id: str,
    run_id: str,
) -> dict[str, Any] | None:
    intent = parse_natural_action_intent(req)
    if not intent or not OPENSHIFT_API_URL:
        return None

    namespace = str(intent["namespace"])
    target_name = str(intent["targetName"])
    api_version = str(intent.get("apiVersion") or "apps/v1")
    kind = str(intent.get("kind") or "Deployment")

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        resolved_target = await resolve_natural_action_target(client, intent, authorization)

    if resolved_target.get("status") == "ambiguous":
        return {
            "candidates": resolved_target.get("candidates", []),
            "intent": intent,
            "status": "ambiguous",
            "summary": f"{kind} `{target_name}` 후보가 여러 namespace에서 발견되었습니다.",
        }

    if resolved_target.get("status") == "missing_namespace":
        return {
            "intent": intent,
            "status": "missing_namespace",
            "summary": f"{kind} `{target_name}` 조치에는 namespace가 필요합니다.",
        }

    live_target = resolved_target.get("target") if isinstance(resolved_target.get("target"), Mapping) else None

    if not live_target:
        return {
            "intent": intent,
            "status": "not_found",
            "summary": f"{kind} `{namespace}/{target_name}`를 찾지 못했습니다.",
        }

    metadata = live_target.get("metadata", {}) if isinstance(live_target.get("metadata"), Mapping) else {}
    namespace = str(metadata.get("namespace") or namespace)
    target_name = str(metadata.get("name") or target_name)
    intent = {
        **intent,
        "namespace": namespace,
        "targetName": target_name,
        "summary": f"{kind} `{namespace}/{target_name}` 조치",
    }
    target = ActionTarget(
        apiVersion=api_version,
        kind=kind,
        namespace=namespace,
        name=target_name,
        uid=str(metadata.get("uid") or ""),
    )
    proposal_request = ActionProposalCreate(
        incidentId=incident_id,
        runId=run_id,
        toolName=str(intent["toolName"]),
        target=target,
        parameters=dict(intent["parameters"]),
        policy={"source": "natural-language-chat"},
    )
    proposal_record = build_action_proposal_record(proposal_request, subject)
    proposal_id = str(proposal_record["metadata"]["name"])
    await bounded_put_record("actionProposals", proposal_id, proposal_record)
    increment_metric("aiops_action_proposals_total")

    plan_record = build_sealed_action_plan_record(proposal_record)
    plan_id = str(plan_record["metadata"]["name"])
    await bounded_put_record("sealedActionPlans", plan_id, plan_record)
    increment_metric("aiops_action_plans_total")

    plan = plan_record["spec"]["sealedActionPlan"]
    return {
        "intent": intent,
        "parameters": intent["parameters"],
        "planDigest": plan["digest"]["planDigest"],
        "planId": plan_id,
        "proposalId": proposal_id,
        "risk": plan["safety"]["risk"],
        "status": "planned",
        "target": target.model_dump(),
    }


def natural_action_plan_response(result: Mapping[str, Any]) -> str:
    if result.get("status") == "ambiguous":
        intent = result.get("intent") if isinstance(result.get("intent"), Mapping) else {}
        candidates = result.get("candidates") if isinstance(result.get("candidates"), list) else []
        candidate_lines = [
            f"- `{candidate.get('namespace')}/{candidate.get('name')}` ({candidate.get('kind') or intent.get('kind') or 'resource'})"
            for candidate in candidates
            if isinstance(candidate, Mapping)
        ]
        return "\n".join(
            [
                "자연어 조치 요청을 해석했지만 대상 후보가 여러 개라 실행하지 않았습니다.",
                "",
                "### 대상 후보",
                *(candidate_lines or ["- 후보를 표시할 수 없습니다."]),
                "",
                "namespace와 대상 이름을 함께 지정해 다시 요청하세요.",
            ]
        )

    if result.get("status") == "missing_namespace":
        return "\n".join(
            [
                "자연어 조치 요청을 해석했지만 namespace가 없어 실행하지 않았습니다.",
                "",
                f"- 요청 해석: {result.get('summary')}",
                "- 예: `cis 네임스페이스의 cis 파드 3개로 올려줘`",
            ]
        )

    if result.get("status") == "not_found":
        intent = result.get("intent") if isinstance(result.get("intent"), Mapping) else {}
        kind = str(intent.get("kind") or "resource")
        return "\n".join(
            [
                f"자연어 조치 요청을 해석했지만 대상 {kind} 리소스를 찾지 못했습니다.",
                "",
                f"- 요청 해석: {result.get('summary')}",
                "- namespace와 대상 이름을 확인한 뒤 다시 요청하세요.",
            ]
        )

    target = result.get("target") if isinstance(result.get("target"), Mapping) else {}
    parameters = result.get("parameters") if isinstance(result.get("parameters"), Mapping) else {}
    intent = result.get("intent") if isinstance(result.get("intent"), Mapping) else {}
    risk = str(result.get("risk") or "unknown")
    next_step = "오른쪽 `AIOps 실행 상태 > 승인·실행`에서 `승인` 후 `실행`을 누르면 실제 변경됩니다."
    if risk in {"medium", "high"}:
        next_step = (
            "이 조치는 medium/high risk로 분류될 수 있어 승인 정책상 별도 승인자가 필요할 수 있습니다. "
            "오른쪽 `AIOps 실행 상태 > 승인·실행`에서 승인 가능 여부를 확인하세요."
        )

    return "\n".join(
        [
            "자연어 조치 요청을 typed AIOps action으로 변환해 실행 계획까지 생성했습니다.",
            "",
            "### 생성된 실행 계획",
            f"- 대상: `{target.get('namespace')}/{target.get('name')}` ({target.get('kind')})",
            f"- Action: `{intent.get('toolName')}`",
            f"- Parameters: `{json.dumps(redact_sensitive(parameters), ensure_ascii=False)}`",
            f"- Proposal: `{result.get('proposalId')}`",
            f"- Plan: `{result.get('planId')}`",
            f"- Risk: `{risk}`",
            "",
            "### 다음 단계",
            f"- {next_step}",
        ]
    )


def action_plan_result_from_record(record: Mapping[str, Any]) -> dict[str, Any]:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
    sealed_plan = record.get("spec", {}).get("sealedActionPlan")
    if not isinstance(sealed_plan, Mapping):
        return {"status": "not_found"}
    action = sealed_plan.get("action") if isinstance(sealed_plan.get("action"), Mapping) else {}
    target = sealed_plan.get("target") if isinstance(sealed_plan.get("target"), Mapping) else {}
    parameters = action.get("normalizedParameters")
    parameters = parameters if isinstance(parameters, Mapping) else {}
    digest = sealed_plan.get("digest") if isinstance(sealed_plan.get("digest"), Mapping) else {}
    return {
        "intent": {
            "toolName": action.get("toolName"),
            "targetName": target.get("name"),
            "namespace": target.get("namespace"),
            "parameters": dict(parameters),
            "summary": f"{action.get('toolName')} {target.get('namespace')}/{target.get('name')}",
        },
        "parameters": dict(parameters),
        "planDigest": digest.get("planDigest"),
        "planId": metadata.get("name"),
        "proposalId": "",
        "risk": sealed_plan.get("safety", {}).get("risk") if isinstance(sealed_plan.get("safety"), Mapping) else "",
        "status": "planned",
        "target": dict(target),
    }


def plan_has_execution(plan_id: str) -> bool:
    return any(
        record.get("spec", {}).get("planId") == plan_id
        for record in EXECUTION_RECORDS.values()
        if isinstance(record.get("spec"), Mapping)
    )


def latest_pending_action_plan_result(subject: Mapping[str, Any]) -> dict[str, Any] | None:
    candidates = sorted(
        SEALED_ACTION_PLANS.values(),
        key=lambda record: str(record.get("metadata", {}).get("createdAt") or ""),
        reverse=True,
    )
    for record in candidates:
        plan_id = str(record.get("metadata", {}).get("name") or "")
        if not plan_id or plan_has_execution(plan_id):
            continue
        if not can_subject_read_record(record, subject):
            continue
        result = action_plan_result_from_record(record)
        if result.get("status") == "planned":
            return result
    return None


def no_pending_action_plan_response() -> str:
    return "\n".join(
        [
            "실행할 Gateway AIOps Action Plan이 없습니다.",
            "",
            "`승인`/`실행` 같은 후속 명령은 Gateway가 생성한 미실행 Action Plan이 있을 때만 처리합니다.",
            "대상과 namespace를 포함해서 다시 요청하세요.",
            "",
            "예: `komsco-ai-dev 네임스페이스의 aiops-two-pod-exec 파드 3개로 올려줘`",
            "예: `6:cis 파드 3개로 올려줘`",
        ]
    )


def unresolved_natural_action_response(req: ChatRequest) -> str:
    context = normalize_console_page_context(req.pageContext)
    namespace = namespace_from_natural_action(req)
    resource_name = page_context_resource_name(req)
    lines = [
        "변경 요청으로 판단했지만 실행 가능한 Gateway AIOps Action으로 확정하지 못했습니다.",
        "",
        "실제 조치를 수행하지 않았습니다.",
        "",
        "### 부족한 정보",
    ]
    if not namespace:
        lines.append("- Namespace가 명확하지 않습니다.")
    if not resource_name:
        resource_name = next(
            (
                page_context_resource_name(req, kind)
                for kind in ("Pod", "HorizontalPodAutoscaler")
                if page_context_resource_name(req, kind)
            ),
            "",
        )
    if not resource_name and not any(
        parser.search(req.message)
        for parser in (
            DEPLOYMENT_RESOURCE_RE,
            POD_RESOURCE_RE,
            HPA_RESOURCE_RE,
            NAMESPACED_RESOURCE_SHORTHAND_RE,
            BACKTICK_RESOURCE_RE,
        )
    ):
        lines.append("- 대상 리소스 이름이 명확하지 않습니다.")
    if len(lines) == 5:
        lines.append(
            "- 지원되는 조치 형태가 아닙니다. 현재 자연어 즉시 실행은 Deployment scale/restart/rollback, "
            "controller-owned unhealthy Pod eviction, HPA bounds 변경을 우선 지원합니다."
        )
    lines.extend(
        [
            "",
            "### 다시 입력 예시",
            "- `6:cis 파드 3개로 올려줘`",
            "- `6 네임스페이스의 cis 파드 3개로 올려줘`",
            "- `komsco-ai-dev:aiops-two-pod-exec 재시작해줘`",
            "- `komsco-ai-dev 네임스페이스의 pod/worker-abc 교체해줘`",
            "- `komsco-ai-dev 네임스페이스의 hpa/web-hpa 최소 2 최대 8로 변경해줘`",
        ]
    )
    if context:
        lines.extend(["", f"- 현재 콘솔 경로: `{context.get('pathname') or context.get('href') or '-'}`"])
    return "\n".join(lines)


async def execute_natural_action_plan_result(
    plan_result: Mapping[str, Any],
    authorization: str,
    subject: Mapping[str, Any],
) -> dict[str, Any]:
    if plan_result.get("status") != "planned":
        return {
            "plan": dict(plan_result),
            "status": "not_executed",
            "reason": "natural action plan was not created",
        }

    plan_id = str(plan_result.get("planId") or "")
    plan_record = SEALED_ACTION_PLANS.get(plan_id)
    if not plan_record:
        return {
            "plan": dict(plan_result),
            "status": "not_executed",
            "reason": "sealed action plan was not found",
        }

    sealed_plan = plan_record["spec"]["sealedActionPlan"]
    plan_digest = sealed_plan["digest"]["planDigest"]
    action_access_review = await fetch_action_access_review(authorization, sealed_plan)
    enforce_action_access_review(action_access_review)
    approval_request = ApprovalDecisionCreate(
        approvalScope="lab-auto-unrestricted",
        expectedPlanDigest=plan_digest,
        planId=plan_id,
    )
    approval_record = build_approval_decision_record(
        plan_record,
        approval_request,
        subject,
        action_access_review,
        allow_self_approval=True,
    )
    approval_id = str(approval_record["metadata"]["name"])
    await bounded_put_record("approvalDecisions", approval_id, approval_record)
    increment_metric("aiops_approval_decisions_total")

    approval_decision = approval_record["spec"]["approvalDecision"]
    validate_approval_is_active(approval_decision)
    validate_execution_evidence_freshness(sealed_plan)
    grant_reference = build_execution_grant_reference(approval_record, plan_record, subject)
    execution_id = f"execution-{uuid.uuid4()}"
    if MUTATIONS_ENABLED:
        executor_result = await execute_action_with_executor(sealed_plan, grant_reference)
    else:
        executor_result = {
            "mutationOutcome": {
                "status": "mutation_disabled",
                "reason": "KOMSCO_AI_ENABLE_MUTATIONS is false.",
            },
            "remediationOutcome": {"status": "not_remediated"},
            "executorTrace": {"mutationSubmitted": False},
        }

    execution_record = {
        "schemaVersion": "v1",
        "apiVersion": "aiops.komsco/v1",
        "kind": "ExecutionRecord",
        "metadata": {"name": execution_id, "createdAt": now_rfc3339()},
        "spec": {
            "executionId": execution_id,
            "approvalId": approval_id,
            "planId": plan_id,
            "planDigest": plan_digest,
            "executionGrantRef": {
                key: value for key, value in grant_reference.items() if key != "claims"
            },
            "mutationOutcome": executor_result["mutationOutcome"],
            "remediationOutcome": executor_result["remediationOutcome"],
            "executorTrace": redact_sensitive(executor_result.get("executorTrace") or {}),
            "executionAuthorization": redact_sensitive(action_access_review),
        },
        "subject": redact_sensitive(dict(subject)),
    }
    await bounded_put_record("executionRecords", execution_id, execution_record)
    approval_decision["status"] = "executed"
    approval_decision["executedAt"] = execution_record["metadata"]["createdAt"]
    await bounded_put_record("approvalDecisions", approval_id, approval_record)
    increment_metric("aiops_execution_requests_total")

    mutation_status = str(executor_result.get("mutationOutcome", {}).get("status") or "")
    if mutation_status == "mutation_succeeded":
        status = "executed"
    elif mutation_status == "mutation_disabled":
        status = "execution_disabled"
    else:
        status = "execution_failed"

    return {
        "approvalId": approval_id,
        "approval": approval_record,
        "executionId": execution_id,
        "execution": execution_record,
        "mutationOutcome": executor_result.get("mutationOutcome"),
        "plan": dict(plan_result),
        "remediationOutcome": executor_result.get("remediationOutcome"),
        "status": status,
    }


def natural_action_execution_response(result: Mapping[str, Any]) -> str:
    plan_result = result.get("plan") if isinstance(result.get("plan"), Mapping) else {}
    target = plan_result.get("target") if isinstance(plan_result.get("target"), Mapping) else {}
    intent = plan_result.get("intent") if isinstance(plan_result.get("intent"), Mapping) else {}
    parameters = plan_result.get("parameters") if isinstance(plan_result.get("parameters"), Mapping) else {}
    mutation = result.get("mutationOutcome") if isinstance(result.get("mutationOutcome"), Mapping) else {}
    remediation = result.get("remediationOutcome") if isinstance(result.get("remediationOutcome"), Mapping) else {}
    status = str(result.get("status") or "unknown")

    if status == "not_executed":
        return "\n".join(
            [
                "자연어 조치 요청을 해석했지만 실행하지 못했습니다.",
                "",
                f"- Reason: `{result.get('reason') or 'unknown'}`",
                "- namespace와 대상 이름을 확인한 뒤 다시 요청하세요.",
            ]
        )

    heading = "자연어 조치 요청을 해석해 실행까지 완료했습니다."
    if status == "execution_disabled":
        heading = "자연어 조치 요청을 해석했지만 mutation 실행은 비활성화되어 있습니다."
    elif status == "execution_failed":
        heading = "자연어 조치 요청을 해석해 실행했지만 Kubernetes 변경이 실패했습니다."

    return "\n".join(
        [
            heading,
            "",
            "### 실행 요약",
            f"- 대상: `{target.get('namespace')}/{target.get('name')}` ({target.get('kind')})",
            f"- Action: `{intent.get('toolName')}`",
            f"- Parameters: `{json.dumps(redact_sensitive(parameters), ensure_ascii=False)}`",
            f"- Plan: `{plan_result.get('planId')}`",
            f"- Approval: `{result.get('approvalId')}`",
            f"- Execution: `{result.get('executionId')}`",
            f"- Mutation: `{mutation.get('status')}` / `{mutation.get('reason')}`",
            f"- Verification: `{remediation.get('status')}` / `{remediation.get('reason')}`",
        ]
    )


def natural_action_read_only_response(intent: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "현재 AIOps 모드가 `읽기 전용`이라 실행 계획, 승인, 실행은 만들지 않고 조치 후보만 정리합니다.",
            "",
            "상태: **제안만 함 / 실행 안 함**",
            "",
            "### 요청 해석",
            f"- 대상: `{intent.get('namespace')}/{intent.get('targetName')}`",
            f"- Action: `{intent.get('toolName')}`",
            f"- Parameters: `{json.dumps(redact_sensitive(intent.get('parameters') or {}), ensure_ascii=False)}`",
            "",
            "### 선행 확인",
            "- 대상 리소스, namespace, owner, 최근 Event, 관련 Alert를 먼저 확인합니다.",
            "- 원인이 특정되지 않으면 재시작, scale, patch 같은 변경성 작업을 후보에서 제외합니다.",
            "",
            "### 안전선",
            "- 금지 동작: `oc apply`, `oc delete`, `oc patch`, `oc scale`, `oc exec`",
            "- 실제 변경은 별도 승인된 실행 모드와 Action Executor 경로에서만 가능합니다.",
        ]
    )


def decode_path_segment(segment: str | None) -> str | None:
    if not segment:
        return None

    try:
        return unquote(segment)
    except Exception:
        return segment


def normalize_aiops_demo_cycle_context(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}

    normalized = {
        key: value.get(key)
        for key in AIOPS_DEMO_CYCLE_ALLOWED_KEYS
        if value.get(key) is not None and value.get(key) != ""
    }
    target = value.get("target")
    if isinstance(target, Mapping):
        normalized_target = {
            key: target.get(key)
            for key in AIOPS_DEMO_CYCLE_TARGET_ALLOWED_KEYS
            if target.get(key) is not None and target.get(key) != ""
        }
        if normalized_target:
            normalized["target"] = normalized_target

    return normalized


def normalize_console_page_context(page_context: Mapping[str, Any] | None) -> dict[str, Any]:
    raw_context = page_context or {}
    normalized: dict[str, Any] = {}
    for key, value in raw_context.items():
        if key == "aiopsDemoCycle":
            demo_cycle = normalize_aiops_demo_cycle_context(value)
            if demo_cycle:
                normalized[key] = demo_cycle
            continue
        if key in PAGE_CONTEXT_ALLOWED_KEYS and value is not None and value != "":
            normalized[key] = value
    pathname = str(normalized.get("pathname") or "")
    segments = [segment for segment in pathname.split("/") if segment]

    route = decode_path_segment(segments[0] if segments else None)
    if route and "route" not in normalized:
        normalized["route"] = route

    if "namespace" not in normalized and "ns" in segments:
        ns_index = segments.index("ns")
        namespace = decode_path_segment(segments[ns_index + 1] if len(segments) > ns_index + 1 else None)
        if namespace:
            normalized["namespace"] = namespace

    if segments[:2] == ["k8s", "cluster"]:
        normalized.setdefault("clusterScope", True)

    ns_index = segments.index("ns") if "ns" in segments else -1
    resource_segment_index = -1
    if ns_index >= 0:
        resource_segment_index = ns_index + 2
    elif segments[:2] == ["k8s", "cluster"]:
        resource_segment_index = 2

    resource_list = decode_path_segment(
        segments[resource_segment_index] if len(segments) > resource_segment_index >= 0 else None
    )
    if resource_list:
        normalized.setdefault("resourceList", resource_list)
        resource_kind = K8S_RESOURCE_KIND_BY_ROUTE_SEGMENT.get(resource_list.lower())
        if resource_kind:
            normalized.setdefault("resourceKind", resource_kind)
            resource_name = decode_path_segment(
                segments[resource_segment_index + 1]
                if len(segments) > resource_segment_index + 1
                else None
            )
            if resource_name:
                normalized.setdefault("resourceName", resource_name)

    if route == "catalog":
        normalized.setdefault("perspective", "developer")
        normalized.setdefault("resourceKind", "Catalog")
    elif route == "topology":
        normalized.setdefault("perspective", "developer")
    elif route == "monitoring":
        normalized.setdefault("perspective", "administrator")

    return redact_sensitive(normalized)


def sse(data: Mapping[str, Any] | str) -> str:
    if isinstance(data, str):
        return f"data: {data}\n\n"

    return f"data: {json.dumps(redact_sensitive(data), ensure_ascii=False)}\n\n"


def safe_error_text(value: Any, *, limit: int = 500) -> str:
    redacted = redact_sensitive(value)
    if isinstance(redacted, str):
        text = redacted
    else:
        text = json.dumps(redacted, ensure_ascii=False, sort_keys=True)
    text = text.replace("\x00", "").strip()
    if len(text) > limit:
        return f"{text[:limit]}..."
    return text


def safe_exception_text(exc: Exception, *, limit: int = 500) -> str:
    if isinstance(exc, HTTPException):
        return safe_error_text(f"HTTP {exc.status_code}: {exc.detail}", limit=limit)
    return safe_error_text(f"{type(exc).__name__}: {exc}", limit=limit)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


async def verify_user_access(user_auth_header: str, req: ChatRequest) -> None:
    if not user_auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing OpenShift bearer token")

    if not req.message.strip() and not req.attachments:
        raise HTTPException(status_code=400, detail="Message or image attachment is required")

    enforce_rate_limit(user_auth_header)


def verify_bearer_header(user_auth_header: str | None) -> str:
    if not user_auth_header or not user_auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing OpenShift bearer token")

    token = user_auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing OpenShift bearer token")

    return f"Bearer {token}"


def validate_image_attachments(attachments: list[ImageAttachment]) -> None:
    total_size = 0
    seen_ids: set[str] = set()

    for attachment in attachments:
        if attachment.id in seen_ids:
            raise HTTPException(status_code=400, detail="Duplicate attachment id")
        seen_ids.add(attachment.id)

        if attachment.mimeType not in ALLOWED_IMAGE_MIME_TYPES:
            raise HTTPException(status_code=400, detail=f"Unsupported image type: {attachment.mimeType}")

        try:
            decoded = base64.b64decode(attachment.data, validate=True)
        except binascii.Error as exc:
            raise HTTPException(status_code=400, detail="Invalid image attachment data") from exc

        decoded_size = len(decoded)
        if decoded_size != attachment.size:
            raise HTTPException(status_code=400, detail="Image attachment size mismatch")
        if decoded_size > MAX_IMAGE_ATTACHMENT_BYTES:
            raise HTTPException(status_code=400, detail="Image attachment is too large")

        total_size += decoded_size

    if total_size > MAX_IMAGE_ATTACHMENT_TOTAL_BYTES:
        raise HTTPException(status_code=400, detail="Image attachments are too large")


def format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"

    return f"{size / (1024 * 1024):.1f} MB"


def find_condition(resource: Mapping[str, Any], condition_type: str) -> Mapping[str, Any] | None:
    conditions = resource.get("status", {}).get("conditions", [])
    if not isinstance(conditions, list):
        return None

    for condition in conditions:
        if isinstance(condition, Mapping) and condition.get("type") == condition_type:
            return condition

    return None


def condition_status(resource: Mapping[str, Any], condition_type: str) -> str | None:
    condition = find_condition(resource, condition_type)
    if not condition:
        return None

    status = condition.get("status")
    return str(status) if status is not None else None


def node_roles(node: Mapping[str, Any]) -> list[str]:
    labels = node.get("metadata", {}).get("labels", {})
    if not isinstance(labels, Mapping):
        return []

    roles = []
    for key in labels:
        prefix = "node-role.kubernetes.io/"
        if key.startswith(prefix):
            role = key[len(prefix) :] or "worker"
            roles.append(role)

    return sorted(roles) or ["worker"]


def node_metric_map(node_metrics_payload: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if not node_metrics_payload:
        return {}

    items = node_metrics_payload.get("items")
    if not isinstance(items, list):
        return {}

    metrics = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue

        name = item.get("metadata", {}).get("name")
        if isinstance(name, str):
            metrics[name] = item

    return metrics


def summarize_node(node: Mapping[str, Any], metrics: Mapping[str, Any] | None) -> dict[str, Any]:
    metadata = node.get("metadata", {}) if isinstance(node.get("metadata"), Mapping) else {}
    status = node.get("status", {}) if isinstance(node.get("status"), Mapping) else {}
    node_info = status.get("nodeInfo", {}) if isinstance(status.get("nodeInfo"), Mapping) else {}
    name = str(metadata.get("name") or "unknown-node")
    ready = condition_status(node, "Ready") == "True"
    pressures = {
        "disk": condition_status(node, "DiskPressure") == "True",
        "memory": condition_status(node, "MemoryPressure") == "True",
        "pid": condition_status(node, "PIDPressure") == "True",
    }
    usage = metrics.get("usage", {}) if isinstance(metrics, Mapping) else {}

    return {
        "name": name,
        "roles": node_roles(node),
        "ready": ready,
        "pressures": pressures,
        "kubeletVersion": node_info.get("kubeletVersion"),
        "osImage": node_info.get("osImage"),
        "usage": {
            "cpu": usage.get("cpu") if isinstance(usage, Mapping) else None,
            "memory": usage.get("memory") if isinstance(usage, Mapping) else None,
        },
    }


def summarize_operator(operator: Mapping[str, Any]) -> dict[str, Any]:
    metadata = operator.get("metadata", {}) if isinstance(operator.get("metadata"), Mapping) else {}
    name = str(metadata.get("name") or "unknown-operator")
    available = condition_status(operator, "Available") == "True"
    degraded = condition_status(operator, "Degraded") == "True"
    progressing = condition_status(operator, "Progressing") == "True"
    upgradeable = condition_status(operator, "Upgradeable")
    issue_condition = (
        find_condition(operator, "Degraded")
        if degraded
        else find_condition(operator, "Available")
        if not available
        else find_condition(operator, "Progressing")
        if progressing
        else find_condition(operator, "Upgradeable")
        if upgradeable == "False"
        else None
    )

    return {
        "name": name,
        "available": available,
        "degraded": degraded,
        "progressing": progressing,
        "upgradeable": upgradeable,
        "reason": issue_condition.get("reason") if issue_condition else None,
        "message": issue_condition.get("message") if issue_condition else None,
    }


def compute_health_score(
    nodes_summary: Mapping[str, Any],
    operators_summary: Mapping[str, Any],
    version_summary: Mapping[str, Any],
) -> int:
    score = 100
    score -= min(40, int(nodes_summary.get("notReady", 0)) * 25)
    score -= min(30, int(nodes_summary.get("pressureCount", 0)) * 10)
    score -= min(35, int(operators_summary.get("degraded", 0)) * 12)
    score -= min(35, int(operators_summary.get("unavailable", 0)) * 15)
    score -= min(15, int(operators_summary.get("progressing", 0)) * 5)
    if version_summary.get("upgradeable") is False:
        score -= 8

    return max(0, min(100, score))


def build_cluster_summary(
    nodes_payload: Mapping[str, Any],
    node_metrics_payload: Mapping[str, Any] | None,
    cluster_version_payload: Mapping[str, Any] | None,
    cluster_operators_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    node_items = nodes_payload.get("items", [])
    if not isinstance(node_items, list):
        node_items = []

    metrics_by_name = node_metric_map(node_metrics_payload)
    nodes = []
    for node in node_items:
        if not isinstance(node, Mapping):
            continue

        metadata = node.get("metadata", {}) if isinstance(node.get("metadata"), Mapping) else {}
        nodes.append(summarize_node(node, metrics_by_name.get(str(metadata.get("name")))))
    ready_nodes = [node for node in nodes if node["ready"]]
    pressure_nodes = [
        node for node in nodes if any(bool(value) for value in node.get("pressures", {}).values())
    ]
    nodes_summary = {
        "total": len(nodes),
        "ready": len(ready_nodes),
        "notReady": len(nodes) - len(ready_nodes),
        "pressureCount": len(pressure_nodes),
        "items": nodes,
        "metricsAvailable": bool(metrics_by_name),
    }

    operator_items = (
        cluster_operators_payload.get("items", [])
        if isinstance(cluster_operators_payload, Mapping)
        else []
    )
    if not isinstance(operator_items, list):
        operator_items = []

    operators = [
        summarize_operator(operator) for operator in operator_items if isinstance(operator, Mapping)
    ]
    operator_issues = [
        operator
        for operator in operators
        if not operator["available"]
        or operator["degraded"]
        or operator["progressing"]
        or operator.get("upgradeable") == "False"
    ]
    operators_summary = {
        "total": len(operators),
        "available": len([operator for operator in operators if operator["available"]]),
        "degraded": len([operator for operator in operators if operator["degraded"]]),
        "progressing": len([operator for operator in operators if operator["progressing"]]),
        "unavailable": len([operator for operator in operators if not operator["available"]]),
        "issues": operator_issues[:8],
    }

    cluster_version_status = (
        cluster_version_payload.get("status", {})
        if isinstance(cluster_version_payload, Mapping)
        else {}
    )
    desired = (
        cluster_version_status.get("desired", {})
        if isinstance(cluster_version_status.get("desired"), Mapping)
        else {}
    )
    available_updates = cluster_version_status.get("availableUpdates")
    upgradeable_condition = (
        find_condition(cluster_version_payload or {}, "Upgradeable")
        if isinstance(cluster_version_payload, Mapping)
        else None
    )
    version_summary = {
        "version": desired.get("version"),
        "channel": cluster_version_status.get("channel"),
        "updateAvailable": isinstance(available_updates, list) and len(available_updates) > 0,
        "upgradeable": upgradeable_condition.get("status") != "False"
        if upgradeable_condition
        else None,
        "upgradeableReason": upgradeable_condition.get("reason") if upgradeable_condition else None,
        "upgradeableMessage": upgradeable_condition.get("message") if upgradeable_condition else None,
    }

    return {
        "updatedAt": datetime.now(UTC).isoformat(),
        "apiUrl": OPENSHIFT_API_URL,
        "healthScore": compute_health_score(nodes_summary, operators_summary, version_summary),
        "nodes": nodes_summary,
        "operators": operators_summary,
        "version": version_summary,
    }


def data_source_status(
    *,
    label: str,
    name: str,
    path: str,
    payload: Mapping[str, Any] | None,
    required: bool = False,
    reason: str = "",
    status: str | None = None,
    http_status: int | None = None,
) -> dict[str, Any]:
    resolved_status = status or ("available" if payload is not None else "unavailable")
    item: dict[str, Any] = {
        "label": label,
        "name": name,
        "path": path,
        "required": required,
        "status": resolved_status,
    }
    if reason:
        item["reason"] = reason
    if http_status is not None:
        item["httpStatus"] = http_status
    if isinstance(payload, Mapping):
        metadata = payload.get("metadata")
        if isinstance(metadata, Mapping) and metadata.get("continue"):
            item["status"] = "partial"
            item["reason"] = "Kubernetes list response is paginated; additional pages were not fetched in this read-only summary."
            item["continueTokenPresent"] = True
    return item


async def fetch_ocp_json_observed(
    client: httpx.AsyncClient,
    path: str,
    authorization: str,
    *,
    label: str,
    name: str,
    required: bool = False,
) -> tuple[Mapping[str, Any] | None, dict[str, Any]]:
    try:
        response = await client.get(
            f"{OPENSHIFT_API_URL}{path}",
            headers={
                "Accept": "application/json",
                "Authorization": authorization,
            },
        )
    except httpx.HTTPError as exc:
        return None, data_source_status(
            label=label,
            name=name,
            path=path,
            required=required,
            reason=str(exc),
            status="error",
        )

    if response.status_code >= 400:
        return None, data_source_status(
            label=label,
            name=name,
            path=path,
            required=required,
            reason=response.text[:240],
            status="error",
            http_status=response.status_code,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        return None, data_source_status(
            label=label,
            name=name,
            path=path,
            required=required,
            reason=f"Invalid JSON response: {exc}",
            status="error",
        )

    if isinstance(payload, Mapping):
        return payload, data_source_status(
            label=label,
            name=name,
            path=path,
            payload=payload,
            required=required,
        )

    return None, data_source_status(
        label=label,
        name=name,
        path=path,
        required=required,
        reason="OpenShift API response was not a JSON object.",
        status="error",
    )


def monitoring_urls_from_config(configmap_payload: Mapping[str, Any] | None) -> dict[str, str]:
    data = configmap_payload.get("data", {}) if isinstance(configmap_payload, Mapping) else {}
    if not isinstance(data, Mapping):
        data = {}
    return {
        "alertmanager": str(data.get("alertmanagerPublicURL") or ""),
        "prometheus": str(data.get("prometheusPublicURL") or ""),
        "thanos": str(data.get("thanosPublicURL") or ""),
    }


async def query_thanos_instant(thanos_url: str, authorization: str, query: str) -> dict[str, Any]:
    if not thanos_url:
        return {
            "query": query,
            "status": "unavailable",
            "reason": "thanosPublicURL is not published in monitoring-shared-config.",
        }

    try:
        async with httpx.AsyncClient(
            verify=OPENSHIFT_API_CA_FILE,
            timeout=httpx.Timeout(10.0, connect=5.0),
        ) as client:
            response = await client.get(
                f"{thanos_url.rstrip('/')}/api/v1/query",
                headers={"Accept": "application/json", "Authorization": authorization},
                params={"query": query},
            )
    except httpx.HTTPError as exc:
        return {"query": query, "status": "error", "reason": str(exc)}

    if response.status_code >= 400:
        return {
            "httpStatus": response.status_code,
            "query": query,
            "reason": response.text[:240],
            "status": "error",
        }

    try:
        payload = response.json()
    except ValueError as exc:
        return {"query": query, "status": "error", "reason": f"Invalid JSON response: {exc}"}

    if not isinstance(payload, Mapping):
        return {"query": query, "status": "error", "reason": "Thanos response was not a JSON object."}
    prometheus_status = str(payload.get("status") or "")
    if prometheus_status and prometheus_status != "success":
        reason = (
            str(payload.get("error") or payload.get("errorType") or "Prometheus query failed")
        )
        return {"query": query, "status": "error", "reason": reason[:240]}

    data = payload.get("data", {}) if isinstance(payload, Mapping) else {}
    result = data.get("result", []) if isinstance(data, Mapping) else []
    if not isinstance(result, list):
        return {"query": query, "status": "error", "reason": "Thanos query result was not a vector list."}
    return {
        "query": query,
        "result": result[:50],
        "resultCount": len(result),
        "status": "partial" if len(result) > 50 else "available",
        **(
            {"reason": "Thanos vector result was capped at 50 series for dashboard summary."}
            if len(result) > 50
            else {}
        ),
    }


async def probe_thanos_query(thanos_url: str, authorization: str) -> dict[str, Any]:
    return await query_thanos_instant(thanos_url, authorization, "up")


def anomaly_resource(
    *,
    kind: str,
    name: str,
    namespace: str = "",
) -> dict[str, str]:
    resource = {"kind": kind, "name": name}
    if namespace:
        resource["namespace"] = namespace
    return resource


def anomaly_finding(
    *,
    candidate_cause: str,
    evidence: str,
    finding_type: str,
    priority: int,
    resource: Mapping[str, Any],
    severity: str,
    source: str,
    title: str,
    next_check: str = "",
    namespace: str = "",
    reason: str = "",
) -> dict[str, Any]:
    identity = json.dumps(
        {
            "namespace": namespace or resource.get("namespace"),
            "priority": priority,
            "resource": dict(resource),
            "source": source,
            "title": title,
            "type": finding_type,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    severity_rank = {"위험": "danger", "확인 필요": "attention", "주의": "warning"}
    finding = {
        "candidateCause": candidate_cause,
        "category": finding_type.split("_", 1)[0],
        "evidence": evidence,
        "id": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16],
        "impact": (
            "서비스 영향 또는 운영 안정성 저하 가능성이 높습니다."
            if severity == "위험"
            else "운영자가 원인 확인과 후속 관찰을 해야 합니다."
            if severity == "확인 필요"
            else "즉시 장애로 단정하지 않고 추세를 확인해야 합니다."
        ),
        "lastObservedAt": now_rfc3339(),
        "message": evidence,
        "priority": priority,
        "resource": dict(resource),
        "severity": severity,
        "source": source,
        "statusLabel": severity,
        "status": severity_rank.get(severity, "info"),
        "title": title,
        "type": finding_type,
    }
    if namespace or resource.get("namespace"):
        finding["namespace"] = namespace or str(resource.get("namespace") or "")
    if next_check:
        finding["nextCheck"] = next_check
    if reason:
        finding["reason"] = reason
    return finding


def pod_anomaly_findings(pods_payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for pod in resource_items(pods_payload):
        namespace = metadata_namespace(pod)
        pod_name = metadata_name(pod)
        status = pod.get("status", {}) if isinstance(pod.get("status"), Mapping) else {}
        phase = str(status.get("phase") or "Unknown")
        resource = anomaly_resource(kind="Pod", namespace=namespace, name=pod_name)
        owner = pod_owner_summary(pod)
        ready = pod_ready_summary(pod)

        if phase == "Pending":
            findings.append(
                anomaly_finding(
                    candidate_cause="스케줄링, PVC, 이미지 pull, node resource 중 하나가 막혔을 가능성이 있습니다. Events 확인이 우선입니다.",
                    evidence=f"Pod phase=`Pending`, ready={ready}, owner={owner}",
                    finding_type="pod_pending",
                    namespace=namespace,
                    next_check=f"oc get events -n {namespace} --field-selector involvedObject.name={pod_name}",
                    priority=25,
                    reason=phase,
                    resource=resource,
                    severity="확인 필요",
                    source="pods",
                    title=f"Pending Pod: {namespace}/{pod_name}",
                )
            )

        statuses = status.get("containerStatuses", [])
        if not isinstance(statuses, list):
            statuses = []
        for container in statuses:
            if not isinstance(container, Mapping):
                continue

            container_name = str(container.get("name") or "unknown-container")
            state = container.get("state", {}) if isinstance(container.get("state"), Mapping) else {}
            waiting = state.get("waiting") if isinstance(state.get("waiting"), Mapping) else {}
            waiting_reason = str(waiting.get("reason") or "")
            waiting_message = str(waiting.get("message") or "")
            restart_count = int(container.get("restartCount") or 0)
            last_state = container.get("lastState", {}) if isinstance(container.get("lastState"), Mapping) else {}
            last_terminated = (
                last_state.get("terminated")
                if isinstance(last_state.get("terminated"), Mapping)
                else {}
            )
            last_reason = str(last_terminated.get("reason") or "")

            if waiting_reason in {"CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull"}:
                is_pull = waiting_reason in {"ImagePullBackOff", "ErrImagePull"}
                findings.append(
                    anomaly_finding(
                        candidate_cause=(
                            "이미지 이름, registry 접근, pull secret, tag 존재 여부 확인이 우선입니다."
                            if is_pull
                            else "컨테이너 프로세스 종료, 설정/env/command 오류, 의존 서비스 연결 실패 가능성이 큽니다."
                        ),
                        evidence=(
                            f"container={container_name}, waiting.reason={waiting_reason}, "
                            f"restartCount={restart_count}, message={waiting_message[:180]}"
                        ),
                        finding_type="pod_image_pull" if is_pull else "pod_crashloop",
                        namespace=namespace,
                        next_check=(
                            f"oc describe pod {pod_name} -n {namespace}"
                            if is_pull
                            else f"oc logs {pod_name} -n {namespace} -c {container_name} --previous"
                        ),
                        priority=5 if not is_pull else 8,
                        reason=waiting_reason,
                        resource=resource,
                        severity="위험",
                        source="pods",
                        title=f"{waiting_reason}: {namespace}/{pod_name}",
                    )
                )
            elif waiting_reason and waiting_reason not in {"ContainerCreating", "PodInitializing"}:
                findings.append(
                    anomaly_finding(
                        candidate_cause="컨테이너가 정상 실행 상태로 진입하지 못했습니다. waiting reason과 Events를 같이 확인해야 합니다.",
                        evidence=f"container={container_name}, waiting.reason={waiting_reason}, message={waiting_message[:180]}",
                        finding_type="pod_waiting",
                        namespace=namespace,
                        next_check=f"oc describe pod {pod_name} -n {namespace}",
                        priority=18,
                        reason=waiting_reason,
                        resource=resource,
                        severity="확인 필요",
                        source="pods",
                        title=f"Waiting container: {namespace}/{pod_name}",
                    )
                )

            if restart_count >= 5:
                findings.append(
                    anomaly_finding(
                        candidate_cause="누적 재시작 이력이 있습니다. 현재 장애인지 최근 복구 이력인지는 lastState와 metrics 증가량 확인이 필요합니다.",
                        evidence=(
                            f"container={container_name}, restartCount={restart_count}, "
                            f"lastState.reason={last_reason or '-'}"
                        ),
                        finding_type="pod_restart_history",
                        namespace=namespace,
                        next_check=f"oc get pod {pod_name} -n {namespace} -o jsonpath='{{.status.containerStatuses}}'",
                        priority=35 if restart_count < 20 else 16,
                        reason=last_reason or "RestartCountHigh",
                        resource=resource,
                        severity="주의" if restart_count < 20 else "확인 필요",
                        source="pods",
                        title=f"Container restart history: {namespace}/{pod_name}",
                    )
                )

    return findings


def event_anomaly_findings(events_payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for event in resource_items(events_payload):
        event_type = str(event.get("type") or "")
        if event_type != "Warning":
            continue
        namespace = metadata_namespace(event)
        reason = str(event.get("reason") or "Warning")
        message = str(event.get("message") or "")
        involved = event.get("involvedObject", {}) if isinstance(event.get("involvedObject"), Mapping) else {}
        resource = anomaly_resource(
            kind=str(involved.get("kind") or "Event"),
            namespace=str(involved.get("namespace") or namespace),
            name=str(involved.get("name") or metadata_name(event)),
        )
        priority = 12 if reason in {"FailedScheduling", "FailedMount", "FailedAttachVolume"} else 28
        findings.append(
            anomaly_finding(
                candidate_cause="Kubernetes Warning Event가 발생했습니다. 해당 리소스 describe와 같은 namespace의 후속 이벤트 확인이 필요합니다.",
                evidence=f"event.reason={reason}, message={message[:220]}",
                finding_type="warning_event",
                namespace=str(resource.get("namespace") or namespace),
                next_check=f"oc describe {resource.get('kind')} {resource.get('name')} -n {resource.get('namespace')}",
                priority=priority,
                reason=reason,
                resource=resource,
                severity="확인 필요" if priority <= 20 else "주의",
                source="events",
                title=f"Warning Event: {reason}",
            )
        )
    return findings[:12]


def operator_anomaly_findings(cluster_summary_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    operators = cluster_summary_payload.get("operators", {}) if isinstance(cluster_summary_payload.get("operators"), Mapping) else {}
    issues = operators.get("issues") if isinstance(operators.get("issues"), list) else []
    findings: list[dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, Mapping):
            continue
        name = str(issue.get("name") or "unknown-operator")
        unavailable = not bool(issue.get("available"))
        degraded = bool(issue.get("degraded"))
        progressing = bool(issue.get("progressing"))
        upgradeable = str(issue.get("upgradeable") or "")
        reason = str(issue.get("reason") or "")
        message = str(issue.get("message") or "")
        severity = "위험" if unavailable or degraded else "확인 필요"
        priority = 3 if unavailable else 6 if degraded else 22
        if upgradeable == "False":
            priority = min(priority, 14)
        findings.append(
            anomaly_finding(
                candidate_cause="ClusterOperator condition이 정상 조건을 벗어났습니다. reason/message를 기준으로 관련 operand와 namespace를 확인해야 합니다.",
                evidence=(
                    f"available={issue.get('available')}, degraded={degraded}, progressing={progressing}, "
                    f"upgradeable={upgradeable or '-'}, reason={reason}, message={message[:180]}"
                ),
                finding_type="clusteroperator_condition",
                next_check=f"oc get clusteroperator {name} -o yaml",
                priority=priority,
                reason=reason or "ClusterOperatorCondition",
                resource=anomaly_resource(kind="ClusterOperator", name=name),
                severity=severity,
                source="clusteroperators",
                title=f"ClusterOperator 확인 필요: {name}",
            )
        )
    return findings


def version_anomaly_findings(cluster_summary_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    version = cluster_summary_payload.get("version", {}) if isinstance(cluster_summary_payload.get("version"), Mapping) else {}
    if version.get("upgradeable") is not False:
        return []
    return [
        anomaly_finding(
            candidate_cause="ClusterVersion Upgradeable=False 상태입니다. 업그레이드 전 차단 조건을 해소해야 합니다.",
            evidence=(
                f"version={version.get('version')}, channel={version.get('channel')}, "
                f"reason={version.get('upgradeableReason')}, message={str(version.get('upgradeableMessage') or '')[:220]}"
            ),
            finding_type="upgrade_blocked",
            next_check="oc get clusterversion version -o yaml",
            priority=20,
            reason=str(version.get("upgradeableReason") or "UpgradeableFalse"),
            resource=anomaly_resource(kind="ClusterVersion", name="version"),
            severity="확인 필요",
            source="clusterversion",
            title="Cluster upgrade blocked",
        )
    ]


def prometheus_vector_results(probe: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not isinstance(probe, Mapping):
        return []
    result = probe.get("result")
    if not isinstance(result, list):
        return []
    return [item for item in result if isinstance(item, Mapping)]


def alert_anomaly_findings(alerts_probe: Mapping[str, Any] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for item in prometheus_vector_results(alerts_probe):
        metric = item.get("metric", {}) if isinstance(item.get("metric"), Mapping) else {}
        alertname = str(metric.get("alertname") or "unknown-alert")
        severity_label = str(metric.get("severity") or metric.get("alert_severity") or "").lower()
        namespace = str(metric.get("namespace") or "")
        pod_name = str(metric.get("pod") or metric.get("pod_name") or "")
        resource_name = pod_name or str(metric.get("instance") or alertname)
        if alertname == "Watchdog":
            excluded.append({"alertname": alertname, "reason": "Watchdog is an always-firing pipeline health alert."})
            continue
        severity = "위험" if severity_label in {"critical", "error"} else "확인 필요" if severity_label in {"warning", "warn"} else "주의"
        priority = 4 if severity == "위험" else 13 if severity == "확인 필요" else 32
        findings.append(
            anomaly_finding(
                candidate_cause="Alert labels/annotations 기준의 활성 경고입니다. 관련 리소스 상세 조회로 원인을 확정해야 합니다.",
                evidence=(
                    f"alertname={alertname}, severity={severity_label or '-'}, "
                    f"namespace={namespace or '-'}, pod={pod_name or '-'}"
                ),
                finding_type="active_alert",
                namespace=namespace,
                next_check=(
                    f"oc describe pod {pod_name} -n {namespace}"
                    if pod_name and namespace
                    else "Alert labels에서 namespace/pod/resource를 확인한 뒤 관련 리소스를 describe"
                ),
                priority=priority,
                reason=alertname,
                resource=anomaly_resource(kind="Alert", namespace=namespace, name=alertname if not pod_name else pod_name),
                severity=severity,
                source="alerts",
                title=f"Active alert: {alertname}",
            )
        )
    return findings, excluded


def restart_metric_findings(restart_probe: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for item in prometheus_vector_results(restart_probe):
        metric = item.get("metric", {}) if isinstance(item.get("metric"), Mapping) else {}
        value = item.get("value")
        restart_delta = 0.0
        if isinstance(value, list) and len(value) >= 2:
            try:
                restart_delta = float(value[1])
            except (TypeError, ValueError):
                restart_delta = 0.0
        if restart_delta <= 0:
            continue
        namespace = str(metric.get("namespace") or "")
        pod_name = str(metric.get("pod") or "")
        container = str(metric.get("container") or "")
        findings.append(
            anomaly_finding(
                candidate_cause="최근 1시간 restart 증가가 관측되었습니다. 현재 CrashLoop인지 복구된 이력인지는 Pod 상태와 lastState로 확정해야 합니다.",
                evidence=f"increase(kube_pod_container_status_restarts_total[1h])={restart_delta:g}, container={container or '-'}",
                finding_type="pod_restart_spike",
                namespace=namespace,
                next_check=f"oc get pod {pod_name} -n {namespace} -o jsonpath='{{.status.containerStatuses}}'",
                priority=10,
                reason="RestartIncrease1h",
                resource=anomaly_resource(kind="Pod", namespace=namespace, name=pod_name or "unknown-pod"),
                severity="확인 필요",
                source="metrics",
                title=f"Recent restart increase: {namespace}/{pod_name or 'unknown-pod'}",
            )
        )
    return findings


def _prometheus_probe_reason(probe: Mapping[str, Any] | None) -> str:
    if not isinstance(probe, Mapping):
        return "probe payload was empty or invalid"
    return safe_error_text(probe.get("reason") or probe.get("error") or "", limit=240)


def rca_probe_event_status(probe: Mapping[str, Any] | None) -> str:
    status = str((probe or {}).get("status") or "unavailable").lower()
    if status == "available":
        return "success"
    if status == "partial":
        return "partial"
    if status == "error":
        return "error"
    return "skipped"


def build_node_status_rca_evidence(
    nodes_payload: Mapping[str, Any] | None,
    node_metrics_payload: Mapping[str, Any] | None,
    *,
    metrics_status: Mapping[str, Any] | None = None,
) -> str:
    node_items = resource_items(nodes_payload)
    if not node_items:
        return "Node status evidence unavailable: Kubernetes API `/api/v1/nodes` returned no node items."

    metrics_by_name = node_metric_map(node_metrics_payload)
    rows = []
    for node in node_items:
        metadata = node.get("metadata", {}) if isinstance(node.get("metadata"), Mapping) else {}
        summary = summarize_node(node, metrics_by_name.get(str(metadata.get("name"))))
        pressure_labels = [
            label
            for label, active in summary.get("pressures", {}).items()
            if active
        ]
        rows.append(
            {
                "cpu": summary.get("usage", {}).get("cpu") or "-",
                "memory": summary.get("usage", {}).get("memory") or "-",
                "name": summary.get("name") or "unknown-node",
                "pressures": ", ".join(pressure_labels) if pressure_labels else "-",
                "ready": "Ready" if summary.get("ready") else "NotReady",
                "roles": ",".join(summary.get("roles") or ["worker"]),
            }
        )

    ready_count = len([row for row in rows if row["ready"] == "Ready"])
    pressure_count = len([row for row in rows if row["pressures"] != "-"])
    metrics_state = str((metrics_status or {}).get("status") or "")
    metrics_reason = safe_error_text((metrics_status or {}).get("reason") or "", limit=240)
    lines = [
        "Gateway-collected Node status evidence from Kubernetes API `/api/v1/nodes` and metrics.k8s.io.",
        "EvidenceType: node",
        (
            f"Summary: total={len(rows)}, ready={ready_count}, "
            f"notReady={len(rows) - ready_count}, pressureNodes={pressure_count}, "
            f"metricsAvailable={bool(metrics_by_name)}"
        ),
    ]
    if metrics_state and metrics_state != "available":
        lines.append(
            f"Node metrics are partial/unavailable: status=`{metrics_state}`, reason={metrics_reason or '-'}"
        )
    lines.extend(
        [
            "",
            "| Node | Roles | Ready | Pressures | CPU | Memory |",
            "| :--- | :--- | :---: | :--- | :--- | :--- |",
        ]
    )
    for row in rows[:20]:
        lines.append(
            "| `{name}` | {roles} | {ready} | {pressures} | {cpu} | {memory} |".format(
                **{
                    key: markdown_table_cell(value)
                    for key, value in row.items()
                }
            )
        )
    if len(rows) > 20:
        lines.append(f"| ... | ... | ... | ... | ... | ... |")
        lines.append(f"Rows capped at 20 of {len(rows)} nodes for RCA prompt compactness.")
    return "\n".join(lines)


def build_active_alerts_rca_evidence(alerts_probe: Mapping[str, Any] | None) -> str:
    status = str((alerts_probe or {}).get("status") or "unavailable").lower()
    if status not in {"available", "partial"}:
        return (
            "Active alert evidence unavailable: "
            f"status={status}, reason={_prometheus_probe_reason(alerts_probe) or '-'}"
        )

    results = prometheus_vector_results(alerts_probe)
    active_rows: list[dict[str, str]] = []
    excluded_watchdog = 0
    for item in results:
        metric = item.get("metric", {}) if isinstance(item.get("metric"), Mapping) else {}
        alertname = str(metric.get("alertname") or "unknown-alert")
        if alertname == "Watchdog":
            excluded_watchdog += 1
            continue
        active_rows.append(
            {
                "alert": alertname,
                "severity": str(metric.get("severity") or metric.get("alert_severity") or "-"),
                "namespace": str(metric.get("namespace") or "-"),
                "pod": str(metric.get("pod") or metric.get("pod_name") or "-"),
                "instance": str(metric.get("instance") or "-"),
            }
        )

    reason = _prometheus_probe_reason(alerts_probe)
    lines = [
        'Gateway-collected Active alert evidence from Thanos query `ALERTS{alertstate="firing"}`.',
        "EvidenceType: alert",
        (
            f"Query status: `{status}`. resultCount={alerts_probe.get('resultCount', len(results))}, "
            f"nonWatchdogActiveAlerts={len(active_rows)}, excludedWatchdog={excluded_watchdog}"
        ),
    ]
    if status == "partial" or reason:
        lines.append(f"Probe note: {reason or 'partial vector result'}")
    lines.extend(
        [
            "",
            "| Alert | Severity | Namespace | Pod | Instance |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
    )
    if active_rows:
        for row in active_rows[:20]:
            lines.append(
                "| `{alert}` | {severity} | {namespace} | {pod} | {instance} |".format(
                    **{key: markdown_table_cell(value) for key, value in row.items()}
                )
            )
    else:
        lines.append("| - | - | - | - | 관련 active alert 없음. Watchdog은 pipeline health alert로 제외. |")
    if len(active_rows) > 20:
        lines.append(f"Rows capped at 20 of {len(active_rows)} non-Watchdog active alerts.")
    return "\n".join(lines)


def build_restart_metric_rca_evidence(restart_probe: Mapping[str, Any] | None) -> str:
    status = str((restart_probe or {}).get("status") or "unavailable").lower()
    query = "increase(kube_pod_container_status_restarts_total[1h]) > 0"
    if status not in {"available", "partial"}:
        return (
            "Metric RCA evidence unavailable: "
            f"status={status}, query=`{query}`, reason={_prometheus_probe_reason(restart_probe) or '-'}"
        )

    results = prometheus_vector_results(restart_probe)
    rows = []
    for item in results:
        metric = item.get("metric", {}) if isinstance(item.get("metric"), Mapping) else {}
        value = item.get("value")
        restart_delta = "-"
        if isinstance(value, list) and len(value) >= 2:
            restart_delta = str(value[1])
        rows.append(
            {
                "container": str(metric.get("container") or "-"),
                "namespace": str(metric.get("namespace") or "-"),
                "pod": str(metric.get("pod") or "-"),
                "restartDelta": restart_delta,
            }
        )

    reason = _prometheus_probe_reason(restart_probe)
    lines = [
        f"Gateway-collected Metric RCA evidence from Thanos query `{query}`.",
        "EvidenceType: metric",
        f"Query status: `{status}`. resultCount={restart_probe.get('resultCount', len(results))}, window=1h",
    ]
    if status == "partial" or reason:
        lines.append(f"Probe note: {reason or 'partial vector result'}")
    lines.extend(
        [
            "",
            "| Namespace | Pod | Container | Restart increase 1h |",
            "| :--- | :--- | :--- | ---: |",
        ]
    )
    if rows:
        for row in rows[:20]:
            lines.append(
                "| {namespace} | `{pod}` | `{container}` | {restartDelta} |".format(
                    **{key: markdown_table_cell(value) for key, value in row.items()}
                )
            )
    else:
        lines.append("| - | - | - | 0 |")
    if len(rows) > 20:
        lines.append(f"Rows capped at 20 of {len(rows)} restart metric series.")
    return "\n".join(lines)


def build_aiops_anomaly_summary(
    cluster_summary_payload: Mapping[str, Any],
    pods_payload: Mapping[str, Any] | None,
    events_payload: Mapping[str, Any] | None,
    alerts_probe: Mapping[str, Any] | None,
    restart_probe: Mapping[str, Any] | None,
    data_sources: list[Mapping[str, Any]],
) -> dict[str, Any]:
    alert_findings, excluded_alerts = alert_anomaly_findings(alerts_probe)
    source_status_by_name = {str(item.get("name") or ""): str(item.get("status") or "") for item in data_sources}
    findings = (
        operator_anomaly_findings(cluster_summary_payload)
        + version_anomaly_findings(cluster_summary_payload)
        + pod_anomaly_findings(pods_payload)
        + event_anomaly_findings(events_payload)
        + alert_findings
        + restart_metric_findings(restart_probe)
    )
    unique: dict[str, dict[str, Any]] = {}
    for finding in findings:
        unique[str(finding.get("id"))] = finding
    ordered = sorted(
        unique.values(),
        key=lambda item: (
            int(item.get("priority") or 999),
            str(item.get("source") or ""),
            str(item.get("namespace") or ""),
            str(item.get("title") or ""),
        ),
    )
    danger = sum(1 for item in ordered if item.get("severity") == "위험")
    attention = sum(1 for item in ordered if item.get("severity") == "확인 필요")
    warning = sum(1 for item in ordered if item.get("severity") == "주의")
    unavailable_sources = [item for item in data_sources if item.get("status") != "available"]
    source_errors = [
        item for item in data_sources if item.get("status") == "error" and item.get("required")
    ]

    if source_errors:
        status = "error"
        label = "필수 이상 징후 데이터 소스 확인 실패"
    elif danger:
        status = "risk"
        label = f"위험 이상 징후 {danger}건"
    elif attention:
        status = "attention"
        label = f"확인 필요 이상 징후 {attention}건"
    elif warning:
        status = "warning"
        label = f"주의 이상 징후 {warning}건"
    elif unavailable_sources:
        status = "unknown"
        label = "일부 이상 징후 데이터 소스 미확인"
    else:
        status = "normal"
        label = "현재 수집 범위에서 주요 이상 징후 없음"

    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "AIOpsAnomalySummary",
        "metadata": {"generatedAt": now_rfc3339(), "name": "kugnus-anomaly-summary"},
        "spec": {
            "dataSources": list(data_sources),
            "excludedAlerts": excluded_alerts,
            "findings": ordered[:24],
            "normalSignals": [
                signal
                for signal in [
                    "ClusterOperator issues 없음"
                    if source_status_by_name.get("clusteroperators") == "available"
                    and not operator_anomaly_findings(cluster_summary_payload)
                    else "",
                    "Pod 비정상 상태 없음"
                    if source_status_by_name.get("pods") == "available"
                    and not pod_anomaly_findings(pods_payload)
                    else "",
                    "Warning Event 없음"
                    if source_status_by_name.get("events") == "available"
                    and not event_anomaly_findings(events_payload)
                    else "",
                ]
                if signal
            ],
            "status": status,
            "statusLabel": label,
            "safety": {
                "methodsUsed": ["GET"],
                "mode": "read-only",
                "mutationsEnabled": MUTATIONS_ENABLED,
                "unrestrictedCommandsEnabled": UNRESTRICTED_COMMANDS_ENABLED,
            },
            "totals": {
                "attention": attention,
                "danger": danger,
                "total": len(ordered),
                "warning": warning,
            },
        },
    }


ACTION_CANDIDATE_FORBIDDEN_VERBS = [
    "apply",
    "attach",
    "create",
    "delete",
    "evict",
    "exec",
    "patch",
    "replace",
    "restart",
    "rollout",
    "scale",
    "update",
]


def action_candidate_target_label(resource: Mapping[str, Any]) -> str:
    kind = str(resource.get("kind") or "Resource")
    name = str(resource.get("name") or "unknown")
    namespace = str(resource.get("namespace") or "")
    return f"{namespace}/{kind}/{name}" if namespace else f"cluster/{kind}/{name}"


def read_only_check_command(resource: Mapping[str, Any], fallback: str = "관련 리소스 상태를 조회합니다.") -> str:
    kind = str(resource.get("kind") or "")
    name = str(resource.get("name") or "")
    namespace = str(resource.get("namespace") or "")
    if kind.lower() == "pod" and name and namespace:
        return f"oc describe pod {name} -n {namespace}"
    if kind.lower() == "clusteroperator" and name:
        return f"oc get clusteroperator {name} -o yaml"
    if kind.lower() == "clusterversion":
        return "oc get clusterversion version -o yaml"
    if kind and name and namespace:
        return f"oc describe {kind} {name} -n {namespace}"
    return fallback


def action_candidate_template(
    finding: Mapping[str, Any],
) -> tuple[list[str], list[str], list[str], str, str]:
    finding_type = str(finding.get("type") or "")
    resource = finding.get("resource") if isinstance(finding.get("resource"), Mapping) else {}
    target_label = action_candidate_target_label(resource)
    read_only_check = read_only_check_command(resource)

    if finding_type == "pod_crashloop":
        return (
            [
                read_only_check,
                "이전 컨테이너 로그와 Warning Event를 확인해 현재 진행 중인 CrashLoop인지 확정합니다.",
                "소유 리소스와 최근 배포 변경 이력을 확인합니다.",
            ],
            [
                "원인이 image, command, env, config, dependency 중 어디인지 분리합니다.",
                "승인 전에는 template 수정, rollback, 재시작을 실행 계획으로 만들지 않습니다.",
                "승인 후에는 단일 원인에 맞춘 변경 계획과 rollback 경로를 별도로 작성합니다.",
            ],
            [
                "대상 workload의 rollout 상태와 Ready Pod 수를 확인합니다.",
                "최근 1시간 restart 증가량이 멈췄는지 Thanos 지표로 재확인합니다.",
            ],
            f"{target_label} 회복 가능성이 있지만 잘못된 변경은 재시작 또는 서비스 영향으로 이어질 수 있습니다.",
            "high",
        )
    if finding_type == "pod_image_pull":
        return (
            [
                read_only_check,
                "이미지 이름, tag, registry 접근성, imagePullSecret 참조를 확인합니다.",
                "동일 namespace의 Secret과 ServiceAccount 연결 상태를 확인합니다.",
            ],
            [
                "이미지/tag 오타, registry 권한, pull secret 누락 중 하나로 원인을 좁힙니다.",
                "승인 전에는 image 또는 secret 변경을 실행하지 않습니다.",
                "승인 후에는 변경 범위와 영향받는 workload를 명시한 계획을 작성합니다.",
            ],
            [
                "Pod Events에서 pull 실패 메시지가 사라졌는지 확인합니다.",
                "새 Pod가 ImagePullBackOff 없이 Running/Ready로 진입했는지 확인합니다.",
            ],
            f"{target_label} 기동 차단을 해소할 수 있으나 image/secret 변경은 배포 범위 전체에 영향이 날 수 있습니다.",
            "high",
        )
    if finding_type in {"pod_pending", "warning_event"}:
        return (
            [
                read_only_check,
                "동일 namespace의 최근 Event를 시간순으로 확인합니다.",
                "PVC, quota, node resource, scheduling constraint 중 차단 지점을 분리합니다.",
            ],
            [
                "스케줄링 실패 사유가 quota/PVC/node/affinity 중 무엇인지 확정합니다.",
                "승인 전에는 resource request, PVC, node selector, affinity를 변경하지 않습니다.",
                "승인 후에는 최소 변경 단위와 되돌림 방법을 포함한 계획을 작성합니다.",
            ],
            [
                "Pending Pod가 Running/Ready로 바뀌었는지 확인합니다.",
                "동일 reason의 Warning Event가 계속 증가하지 않는지 확인합니다.",
            ],
            f"{target_label} 배치 지연을 해소할 수 있으나 quota나 scheduling 변경은 다른 workload에 영향을 줄 수 있습니다.",
            "medium",
        )
    if finding_type == "clusteroperator_condition":
        return (
            [
                read_only_check,
                "Operator condition의 reason/message와 관련 operand namespace를 확인합니다.",
                "ClusterVersion과 다른 ClusterOperator의 연쇄 영향을 확인합니다.",
            ],
            [
                "Operator 자체 문제인지 operand 문제인지 분리합니다.",
                "승인 전에는 ClusterOperator, Subscription, operand 리소스를 변경하지 않습니다.",
                "승인 후에는 벤더/운영 절차에 맞는 복구 계획을 별도로 작성합니다.",
            ],
            [
                "해당 ClusterOperator의 Available/Degraded/Progressing 조건을 재확인합니다.",
                "콘솔과 경고 상태가 동시에 회복되었는지 확인합니다.",
            ],
            f"{target_label} 정상화는 클러스터 기능 전체에 영향이 있으므로 변경 전 승인과 영향 범위 확인이 필요합니다.",
            "high",
        )
    if finding_type == "upgrade_blocked":
        return (
            [
                read_only_check,
                "Upgradeable=False reason과 AdminAck 또는 차단 조건을 확인합니다.",
                "관련 ClusterOperator 조건과 업데이트 채널 상태를 함께 확인합니다.",
            ],
            [
                "업그레이드 차단 조건을 문서화하고 필요한 승인 절차를 정리합니다.",
                "승인 전에는 upgrade ack, 채널 변경, 업데이트 진행을 수행하지 않습니다.",
                "승인 후에는 maintenance window와 rollback 판단 기준을 포함합니다.",
            ],
            [
                "Upgradeable 조건이 True로 회복되었는지 확인합니다.",
                "업그레이드 전 필수 ClusterOperator가 안정 상태인지 확인합니다.",
            ],
            "업그레이드 차단 해소는 클러스터 전체 운영 계획과 연결되므로 사전 승인 없이는 실행하지 않습니다.",
            "high",
        )
    if finding_type in {"active_alert", "pod_restart_spike", "pod_restart_history"}:
        return (
            [
                read_only_check,
                "Alert label, Pod 상태, 최근 restart 지표가 같은 대상을 가리키는지 확인합니다.",
                "현재 장애인지 복구된 이력인지 lastState와 시간 범위로 분리합니다.",
            ],
            [
                "경고와 지표의 공통 원인을 RCA 후보로 고정합니다.",
                "승인 전에는 재시작, scale, patch 같은 증상 제거 작업을 실행하지 않습니다.",
                "승인 후에는 원인별 수정과 검증 순서를 나눈 계획을 작성합니다.",
            ],
            [
                "Alert firing 상태가 해소되었는지 확인합니다.",
                "restart 증가량과 Ready 상태가 안정화되었는지 확인합니다.",
            ],
            f"{target_label}의 경고/재시작 신호를 줄일 수 있으나 원인 확정 전 실행은 재발 가능성이 높습니다.",
            "medium",
        )
    return (
        [
            read_only_check,
            "관련 리소스의 현재 상태, Event, owner 관계를 먼저 확인합니다.",
            "데이터 소스 실패가 있으면 후보 신뢰도를 낮춰 판단합니다.",
        ],
        [
            "근거가 충분할 때만 수정 후보를 하나로 좁힙니다.",
            "승인 전에는 변경성 작업을 실행하지 않습니다.",
            "승인 후에는 영향 범위와 되돌림 기준을 포함한 계획을 작성합니다.",
        ],
        [
            "같은 이상 징후가 더 이상 증가하지 않는지 확인합니다.",
            "대상 리소스와 상위 workload의 정상 상태를 함께 확인합니다.",
        ],
        f"{target_label}의 운영 리스크를 낮출 수 있으나 원인 확정 전 실행은 금지됩니다.",
        "medium",
    )


def build_aiops_action_candidates(
    anomaly_summary: Mapping[str, Any] | None,
    data_sources: list[Mapping[str, Any]],
) -> dict[str, Any]:
    anomaly_spec = (
        anomaly_summary.get("spec", {})
        if isinstance(anomaly_summary, Mapping) and isinstance(anomaly_summary.get("spec"), Mapping)
        else {}
    )
    findings = anomaly_spec.get("findings") if isinstance(anomaly_spec.get("findings"), list) else []
    required_gaps = [
        item
        for item in data_sources
        if item.get("required") and item.get("status") != "available"
    ]
    candidates: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, Mapping):
            continue
        prerequisite_checks, recommendation_steps, verification_checks, expected_impact, risk_level = (
            action_candidate_template(finding)
        )
        source_id = str(
            finding.get("id")
            or hashlib.sha256(json.dumps(finding, sort_keys=True, default=str).encode()).hexdigest()[:16]
        )
        blocked_reasons = ["read-only-mode", "mutation-disabled", "approval-required"]
        if required_gaps:
            blocked_reasons.append("required-data-source-gap")
        candidates.append(
            {
                "approvalRequired": True,
                "blockedActions": list(ACTION_CANDIDATE_FORBIDDEN_VERBS),
                "blockedReasons": blocked_reasons,
                "confidence": "limited" if required_gaps else "medium",
                "evidence": str(finding.get("evidence") or finding.get("message") or "근거 수집 중"),
                "evidenceRefs": [
                    {
                        "evidenceType": str(finding.get("source") or "anomaly"),
                        "findingId": source_id,
                        "sourceType": str(finding.get("type") or "unknown"),
                        "status": "collected",
                    }
                ],
                "executable": False,
                "executionPolicy": {
                    "executionEnabled": False,
                    "mode": "read-only",
                    "mutationVerbsDisabled": True,
                    "proposalOnly": True,
                },
                "expectedImpact": expected_impact,
                "id": f"action-candidate-{source_id}",
                "mutationSubmitted": False,
                "priority": int(finding.get("priority") or 999),
                "prerequisiteChecks": prerequisite_checks,
                "recommendationSteps": recommendation_steps,
                "riskLevel": risk_level,
                "riskLabel": "높음" if risk_level == "high" else "중간",
                "severity": str(finding.get("severity") or "확인 필요"),
                "sourceFindingId": source_id,
                "sourceType": str(finding.get("type") or "unknown"),
                "statusLabel": "제안만 함 / 실행 안 함",
                "target": dict(finding.get("resource") if isinstance(finding.get("resource"), Mapping) else {}),
                "title": f"{finding.get('title') or '이상 징후'} 조치 후보",
                "verificationChecks": verification_checks,
            }
        )

    candidates = sorted(candidates, key=lambda item: (item["priority"], item["sourceType"], item["id"]))
    if required_gaps:
        status = "blocked"
        status_label = "필수 데이터 소스 실패로 조치 후보 신뢰 제한"
    elif candidates:
        status = "candidates"
        status_label = f"read-only 조치 후보 {len(candidates)}건"
    elif anomaly_spec.get("status") == "normal":
        status = "normal"
        status_label = "현재 수집 범위에서 제안할 조치 후보 없음"
    else:
        status = "unknown"
        status_label = "조치 후보 생성을 위한 이상 징후 데이터 확인 중"

    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "AIOpsActionCandidateSummary",
        "metadata": {"generatedAt": now_rfc3339(), "name": "kugnus-read-only-action-candidates"},
        "spec": {
            "candidates": candidates[:8],
            "dataSources": list(data_sources),
            "safety": {
                "forbiddenMutationVerbs": list(ACTION_CANDIDATE_FORBIDDEN_VERBS),
                "methodsUsed": ["GET"],
                "mode": "read-only",
                "mutationsEnabled": MUTATIONS_ENABLED,
                "proposalOnly": True,
                "unrestrictedCommandsEnabled": UNRESTRICTED_COMMANDS_ENABLED,
            },
            "source": {
                "anomalySummaryName": str(
                    (anomaly_summary or {}).get("metadata", {}).get("name")
                    if isinstance((anomaly_summary or {}).get("metadata"), Mapping)
                    else "kugnus-anomaly-summary"
                ),
                "requiredDataSourceGaps": required_gaps,
            },
            "status": status,
            "statusLabel": status_label,
            "totals": {
                "approvalRequired": len(candidates),
                "blockedByRequiredSourceGap": len(required_gaps),
                "highRisk": len([candidate for candidate in candidates if candidate.get("riskLevel") == "high"]),
                "shown": min(len(candidates), 8),
                "total": len(candidates),
            },
        },
    }


def build_aiops_overview(
    cluster_summary_payload: Mapping[str, Any],
    data_sources: list[Mapping[str, Any]],
    monitoring_urls: Mapping[str, str],
    monitoring_probe: Mapping[str, Any],
    anomaly_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    health_score = int(cluster_summary_payload.get("healthScore") or 0)
    nodes = cluster_summary_payload.get("nodes", {}) if isinstance(cluster_summary_payload.get("nodes"), Mapping) else {}
    operators = (
        cluster_summary_payload.get("operators", {})
        if isinstance(cluster_summary_payload.get("operators"), Mapping)
        else {}
    )
    required_errors = [
        item
        for item in data_sources
        if item.get("required") and item.get("status") != "available"
    ]
    attention_count = (
        int(nodes.get("notReady") or 0)
        + int(nodes.get("pressureCount") or 0)
        + int(operators.get("degraded") or 0)
        + int(operators.get("unavailable") or 0)
        + int(operators.get("progressing") or 0)
    )
    if required_errors:
        tower_status = "error"
        tower_label = "필수 데이터 소스 확인 실패"
    elif health_score >= 90 and attention_count == 0:
        tower_status = "healthy"
        tower_label = "회사 OCP 읽기 전용 관제 정상"
    elif health_score >= 65:
        tower_status = "attention"
        tower_label = "운영 확인 필요"
    else:
        tower_status = "risk"
        tower_label = "즉시 확인 필요"

    anomaly_spec = (
        anomaly_summary.get("spec", {})
        if isinstance(anomaly_summary, Mapping) and isinstance(anomaly_summary.get("spec"), Mapping)
        else {}
    )
    anomaly_status = str(anomaly_spec.get("status") or "")
    anomaly_totals = (
        anomaly_spec.get("totals", {}) if isinstance(anomaly_spec.get("totals"), Mapping) else {}
    )
    anomaly_total = int(anomaly_totals.get("total") or 0)
    if anomaly_status in {"error", "unknown"}:
        tower_status = "error"
        tower_label = str(anomaly_spec.get("statusLabel") or "이상 징후 데이터 소스 확인 필요")
    elif anomaly_status == "risk":
        tower_status = "risk"
        tower_label = str(anomaly_spec.get("statusLabel") or "위험 이상 징후 확인 필요")
    elif anomaly_status in {"attention", "warning"} and tower_status == "healthy":
        tower_status = "attention"
        tower_label = str(anomaly_spec.get("statusLabel") or "이상 징후 확인 필요")
    action_candidates = build_aiops_action_candidates(anomaly_summary, data_sources)

    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "AIOpsOverview",
        "metadata": {"generatedAt": now_rfc3339(), "name": "kugnus-control-tower"},
        "spec": {
            "clusterSummary": cluster_summary_payload,
            "controlTower": {
                "name": "Cywell AI 관제탑",
                "mode": "read-only",
                "status": tower_status,
                "statusLabel": tower_label,
                "attentionCount": attention_count + anomaly_total,
                "healthScore": health_score,
                "target": cluster_summary_payload.get("apiUrl") or OPENSHIFT_API_URL,
            },
            "dataSources": list(data_sources),
            "anomalies": dict(anomaly_summary or {}),
            "actionCandidates": action_candidates,
            "monitoring": {
                "probe": dict(monitoring_probe),
                "urls": {
                    "alertmanagerConfigured": bool(monitoring_urls.get("alertmanager")),
                    "prometheusConfigured": bool(monitoring_urls.get("prometheus")),
                    "thanosConfigured": bool(monitoring_urls.get("thanos")),
                },
            },
            "safety": {
                "mutationsEnabled": MUTATIONS_ENABLED,
                "readOnlyDefault": not MUTATIONS_ENABLED,
                "unrestrictedCommandsEnabled": UNRESTRICTED_COMMANDS_ENABLED,
            },
        },
    }


def build_attachment_context(
    attachments: list[ImageAttachment],
    image_analysis: str | None = None,
    *,
    forwarded_to_ols: bool = False,
) -> str:
    if not attachments:
        return "첨부 이미지 없음"

    lines = [
        "첨부 이미지는 Gateway에서 수신 및 검증했습니다.",
    ]
    if image_analysis:
        lines.append("Gateway 비전 분석 결과:")
        lines.append(image_analysis)
    elif forwarded_to_ols:
        lines.append("이미지 원본은 Lightspeed attachments로 전달했습니다.")
    else:
        lines.append(
            "현재 Gateway 비전 분석과 OLS image attachment 전달이 비활성화되어 있습니다. "
            "답변에는 첨부 파일 메타데이터, 사용자 설명, 도구 조회 결과만 근거로 사용하세요."
        )

    lines.append("첨부 파일 메타데이터:")

    for index, attachment in enumerate(attachments, start=1):
        lines.append(
            f"{index}. {attachment.name} ({attachment.mimeType}, {format_bytes(attachment.size)})"
        )

    return "\n".join(lines)


def build_ols_attachments(attachments: list[ImageAttachment]) -> list[dict[str, str]]:
    return [
        {
            "attachment_type": "image",
            "content_type": attachment.mimeType,
            "content": attachment.data,
        }
        for attachment in attachments
    ]


def build_ols_gateway_context(
    *,
    tool_plan: Mapping[str, Any],
    rca_context: Mapping[str, Any],
    safety_contract: Mapping[str, Any],
    policy: Mapping[str, Any],
    gateway_evidence: str | None = None,
) -> dict[str, Any]:
    rca_evidence = rca_context.get("evidence", {}) if isinstance(rca_context.get("evidence"), Mapping) else {}
    missing_evidence = rca_evidence.get("missing", []) if isinstance(rca_evidence, Mapping) else []
    context = {
        "apiVersion": "aiops.komsco/v1alpha1",
        "kind": "GatewayContext",
        "metadata": {
            "generatedAt": now_rfc3339(),
            "source": "komsco-ai-gateway",
            "version": "0.1.3",
            "rcaContextDigest": rca_context.get("metadata", {}).get("digest")
            if isinstance(rca_context.get("metadata"), Mapping)
            else "",
        },
        "toolPlan": redact_sensitive(dict(tool_plan)),
        "evidenceSummary": redact_sensitive(rca_evidence.get("summary", {}) if isinstance(rca_evidence, Mapping) else {}),
        "missingEvidence": redact_sensitive(missing_evidence if isinstance(missing_evidence, list) else []),
        "rcaContext": redact_sensitive(dict(rca_context)),
        "safetyContract": redact_sensitive(dict(safety_contract)),
        "policy": redact_sensitive(dict(policy)),
        "gatewayEvidenceDigest": canonical_digest(redact_sensitive(gateway_evidence or "")) if gateway_evidence else "",
    }
    context["metadata"]["digest"] = canonical_digest(redact_sensitive(context))
    return context


def build_ols_payload(
    query: str,
    conversation_id: str | None,
    attachments: list[ImageAttachment],
    *,
    forward_image_attachments: bool = False,
    gateway_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"query": query}
    if conversation_id:
        payload["conversation_id"] = conversation_id

    if gateway_context:
        payload["gateway_context"] = redact_sensitive(dict(gateway_context))

    ols_attachments = build_ols_attachments(attachments) if forward_image_attachments else []
    if ols_attachments:
        payload["attachments"] = ols_attachments

    return payload


def read_secret_value(value: str | None, file_path: str | None) -> str | None:
    if value:
        return value
    if not file_path:
        return None

    try:
        with open(file_path, encoding="utf-8") as secret_file:
            return secret_file.read().strip()
    except OSError:
        return None


def should_forward_image_attachments_to_ols() -> bool:
    return parse_bool(os.getenv("KOMSCO_AI_FORWARD_IMAGE_ATTACHMENTS_TO_OLS"), default=False)


def get_vision_config() -> dict[str, str] | None:
    base_url = os.getenv("KOMSCO_AI_VISION_BASE_URL", "").rstrip("/")
    model = os.getenv("KOMSCO_AI_VISION_MODEL", "").strip()
    api_key = read_secret_value(
        os.getenv("KOMSCO_AI_VISION_API_KEY"),
        os.getenv("KOMSCO_AI_VISION_API_KEY_FILE"),
    )

    if not base_url or not model:
        return None

    config = {"base_url": base_url, "model": model}
    if api_key:
        config["api_key"] = api_key

    return config


def truncate_detail(value: str, limit: int = MAX_TOOL_DETAIL_CHARS) -> str:
    if len(value) <= limit:
        return value

    return f"{value[:limit]}\n... truncated ..."


def dump_tool_detail(value: Any) -> str:
    if isinstance(value, str):
        return truncate_detail(value)

    try:
        return truncate_detail(json.dumps(value, ensure_ascii=False, indent=2))
    except TypeError:
        return truncate_detail(str(value))


def summarize_resource_args(args: Any) -> str | None:
    if not isinstance(args, Mapping):
        return None

    kind = args.get("kind")
    name = args.get("name")
    namespace = args.get("namespace")
    if not kind or not name:
        return None

    resource_name = f"{namespace}/{name}" if namespace else str(name)
    return f"{kind} {resource_name}"


def summarize_resource_content(content: str) -> str | None:
    kind_match = re.search(r"(?m)^kind:\s*([A-Za-z0-9_.-]+)\s*$", content)
    name_match = re.search(r"(?m)^\s{2}name:\s*([A-Za-z0-9_.-]+)\s*$", content)
    namespace_match = re.search(r"(?m)^\s{2}namespace:\s*([A-Za-z0-9_.-]+)\s*$", content)
    if not kind_match or not name_match:
        return None

    resource_name = (
        f"{namespace_match.group(1)}/{name_match.group(1)}"
        if namespace_match
        else name_match.group(1)
    )
    return f"{kind_match.group(1)} {resource_name}"


def summarize_tool_payload(event_type: str, payload: Mapping[str, Any]) -> str:
    tool_name = payload.get("name") or payload.get("tool_name")
    if event_type == "tool_call":
        if tool_name == "resources_get":
            resource_ref = summarize_resource_args(payload.get("args"))
            if resource_ref:
                return f"{resource_ref} 상세 조회"

        server_name = payload.get("server_name") or payload.get("serverName")
        if server_name:
            return f"{server_name} 도구 호출"

        return "도구 호출"

    status = payload.get("status")
    content = payload.get("content")
    if status and str(status).lower() in {"error", "failed", "failure"}:
        if isinstance(content, str) and content.strip():
            first_line = content.strip().splitlines()[0]
            return f"조회 실패: {truncate_detail(first_line, 80)}"

        return f"상태: {status}"

    if isinstance(content, str):
        if tool_name == "resources_get":
            resource_ref = summarize_resource_content(content)
            if resource_ref:
                return f"{resource_ref} 조회 완료"

        try:
            parsed_content = json.loads(content)
        except json.JSONDecodeError:
            parsed_content = None

        if isinstance(parsed_content, Mapping):
            alerts = parsed_content.get("alerts")
            if isinstance(alerts, list):
                return f"경고 {len(alerts)}건 조회"

    if status:
        return f"상태: {status}"

    return "도구 실행 완료"


def summarize_alerts_detail(alerts: list[Any]) -> str:
    lines = [f"조회 경고: {len(alerts)}건"]
    for alert in alerts[:10]:
        if not isinstance(alert, Mapping):
            continue

        labels = alert.get("labels") if isinstance(alert.get("labels"), Mapping) else {}
        annotations = (
            alert.get("annotations") if isinstance(alert.get("annotations"), Mapping) else {}
        )
        parts = [
            str(labels.get("severity") or "unknown"),
            str(labels.get("alertname") or "unknown-alert"),
        ]
        namespace = labels.get("namespace")
        pod = labels.get("pod")
        if namespace:
            parts.append(f"namespace={namespace}")
        if pod:
            parts.append(f"pod={pod}")

        lines.append(f"- {' / '.join(parts)}")
        summary = annotations.get("summary")
        if summary:
            lines.append(f"  {summary}")

    if len(alerts) > 10:
        lines.append(f"... {len(alerts) - 10}건 더 있음")

    return "\n".join(lines)


def build_tool_detail(event_type: str, payload: Mapping[str, Any]) -> str:
    if event_type == "tool_call":
        lines = []
        server_name = payload.get("server_name") or payload.get("serverName")
        args = payload.get("args")
        if server_name:
            lines.append(f"도구 서버: {server_name}")
        if args is not None:
            lines.append(f"요청 인자:\n{dump_tool_detail(args)}")

        return "\n".join(lines) or dump_tool_detail(payload)

    lines = []
    status = payload.get("status")
    if status:
        lines.append(f"상태: {status}")

    content = payload.get("content")
    if isinstance(content, str):
        try:
            parsed_content = json.loads(content)
        except json.JSONDecodeError:
            parsed_content = None

        if isinstance(parsed_content, Mapping):
            alerts = parsed_content.get("alerts")
            if isinstance(alerts, list):
                lines.append(summarize_alerts_detail(alerts))
                return truncate_detail("\n".join(lines))

            lines.append(dump_tool_detail(parsed_content))
            return truncate_detail("\n".join(lines))

        lines.append(truncate_detail(content))
        return truncate_detail("\n".join(lines))

    result = payload.get("result")
    if result is not None:
        lines.append(dump_tool_detail(result))
        return truncate_detail("\n".join(lines))

    return dump_tool_detail(payload)


def normalize_tool_event(event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "type": event_type,
        "name": payload.get("name") or payload.get("tool_name") or "unknown_tool",
        "summary": summarize_tool_payload(event_type, payload),
        "detail": build_tool_detail(event_type, payload),
    }

    for source_key, target_key in (
        ("id", "id"),
        ("args", "args"),
        ("status", "status"),
        ("server_name", "serverName"),
        ("serverName", "serverName"),
        ("round", "round"),
    ):
        value = payload.get(source_key)
        if value is not None:
            normalized[target_key] = value

    return normalized


def parse_tool_text_line(line: str) -> dict[str, Any] | None:
    stripped = line.strip()
    for prefix, event_type in TOOL_LINE_PREFIXES:
        if not stripped.startswith(prefix):
            continue

        raw_payload = stripped[len(prefix) :].strip()
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            return {
                "type": event_type,
                "name": "unknown_tool",
                "summary": "도구 이벤트 수신",
                "detail": truncate_detail(raw_payload),
            }

        if isinstance(payload, Mapping):
            return normalize_tool_event(event_type, payload)

        return {
            "type": event_type,
            "name": "unknown_tool",
            "summary": "도구 이벤트 수신",
            "detail": dump_tool_detail(payload),
        }

    return None


async def split_plain_text_events(chunks: AsyncIterator[str]) -> AsyncIterator[dict[str, Any]]:
    pending = ""

    async for chunk in chunks:
        if not chunk:
            continue

        pending += chunk
        while pending:
            if any(prefix.startswith(pending) for prefix, _ in TOOL_LINE_PREFIXES):
                break

            matched_prefix = next(
                (prefix for prefix, _ in TOOL_LINE_PREFIXES if pending.startswith(prefix)),
                None,
            )
            if matched_prefix:
                line_end = pending.find("\n")
                if line_end == -1:
                    break

                line = pending[:line_end]
                pending = pending[line_end + 1 :]
                tool_event = parse_tool_text_line(line)
                if tool_event:
                    yield tool_event
                continue

            line_end = pending.find("\n")
            if line_end == -1:
                yield {"type": "text", "content": pending}
                pending = ""
                continue

            yield {"type": "text", "content": pending[: line_end + 1]}
            pending = pending[line_end + 1 :]

    if pending:
        tool_event = parse_tool_text_line(pending)
        if tool_event:
            yield tool_event
        else:
            yield {"type": "text", "content": pending}


def should_collect_pod_status_evidence(message: str) -> bool:
    return bool(
        POD_STATUS_ANALYSIS_RE.search(message)
        or POD_COUNT_QUERY_RE.search(message)
        or CLUSTER_OPERATOR_ANALYSIS_RE.search(message)
    )


def should_collect_cronjob_activity_evidence(
    message: str,
    image_analysis: str | None = None,
) -> bool:
    combined = f"{message}\n{image_analysis or ''}".strip()
    return bool(combined and CRONJOB_ACTIVITY_ANALYSIS_RE.search(combined))


def should_collect_rca_signal_evidence(message: str) -> bool:
    return bool(
        should_collect_pod_status_evidence(message)
        or CLUSTER_OPERATOR_ANALYSIS_RE.search(message)
        or RCA_SIGNAL_ANALYSIS_RE.search(message)
    )


def append_gateway_evidence(current: str | None, new_evidence: str) -> str:
    if not current:
        return new_evidence

    return f"{current}\n\n{new_evidence}"


def normalize_pod_restart_language(text: str) -> str:
    normalized = text
    for source, replacement in POD_RESTART_LANGUAGE_REPLACEMENTS:
        normalized = normalized.replace(source, replacement)
    return normalized


def state_summary(container_status: Mapping[str, Any]) -> str:
    state = container_status.get("state")
    if not isinstance(state, Mapping):
        return "unknown"

    if isinstance(state.get("waiting"), Mapping):
        waiting = state["waiting"]
        reason = waiting.get("reason") or "Waiting"
        return f"waiting:{reason}"

    if isinstance(state.get("running"), Mapping):
        running = state["running"]
        started_at = running.get("startedAt")
        return f"running since {started_at}" if started_at else "running"

    if isinstance(state.get("terminated"), Mapping):
        terminated = state["terminated"]
        reason = terminated.get("reason") or "Terminated"
        exit_code = terminated.get("exitCode")
        return f"terminated:{reason}/{exit_code}"

    return "unknown"


def last_termination_summary(container_status: Mapping[str, Any]) -> tuple[str, str]:
    last_state = container_status.get("lastState")
    if not isinstance(last_state, Mapping):
        return "-", ""

    terminated = last_state.get("terminated")
    if not isinstance(terminated, Mapping):
        return "-", ""

    reason = terminated.get("reason") or "Terminated"
    exit_code = terminated.get("exitCode")
    finished_at = str(terminated.get("finishedAt") or "")
    return f"{reason}/{exit_code}", finished_at


def pod_ready_summary(pod: Mapping[str, Any]) -> str:
    statuses = pod.get("status", {}).get("containerStatuses", [])
    if not isinstance(statuses, list):
        return "0/0"

    total = len(statuses)
    ready = sum(1 for item in statuses if isinstance(item, Mapping) and item.get("ready"))
    return f"{ready}/{total}"


def pod_display_state(pod: Mapping[str, Any]) -> str:
    status = pod.get("status", {}) if isinstance(pod.get("status"), Mapping) else {}
    phase = str(status.get("phase") or "Unknown")
    statuses = status.get("containerStatuses", [])
    if not isinstance(statuses, list):
        return phase

    waiting_reasons = []
    for item in statuses:
        if not isinstance(item, Mapping):
            continue
        state = item.get("state")
        waiting = state.get("waiting") if isinstance(state, Mapping) else None
        if isinstance(waiting, Mapping):
            waiting_reasons.append(str(waiting.get("reason") or "Waiting"))

    if waiting_reasons:
        return f"{phase} ({', '.join(sorted(set(waiting_reasons)))})"

    return phase


def pod_owner_summary(pod: Mapping[str, Any]) -> str:
    owners = pod.get("metadata", {}).get("ownerReferences", [])
    if not isinstance(owners, list) or not owners:
        return "-"

    owner = owners[0]
    if not isinstance(owner, Mapping):
        return "-"

    kind = owner.get("kind") or "Owner"
    name = owner.get("name") or "unknown"
    return f"{kind}/{name}"


def markdown_table_cell(value: Any, *, max_length: int = 180) -> str:
    text = str(redact_sensitive(value)).replace("\n", " ").replace("\r", " ").strip()
    text = text.replace("|", "\\|")
    if not text:
        return "-"
    if len(text) > max_length:
        return f"{text[: max_length - 1]}..."
    return text


def json_list_summary(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "-"
    return json.dumps(redact_sensitive(value), ensure_ascii=False)


def pod_label_summary(pod: Mapping[str, Any]) -> str:
    metadata = pod.get("metadata", {}) if isinstance(pod.get("metadata"), Mapping) else {}
    labels = metadata.get("labels")
    if not isinstance(labels, Mapping) or not labels:
        return "-"

    priority_keys = [
        "app",
        "app.kubernetes.io/name",
        "app.kubernetes.io/component",
        "aiops.komsco/scenario",
        "aiops.komsco/scenario-type",
        "pod-template-hash",
    ]
    ordered_keys = [key for key in priority_keys if key in labels]
    ordered_keys.extend(sorted(str(key) for key in labels if str(key) not in ordered_keys))
    parts = [f"{key}={labels.get(key)}" for key in ordered_keys[:8]]
    if len(labels) > len(parts):
        parts.append(f"+{len(labels) - len(parts)} more")
    return ", ".join(parts)


def resource_items(payload: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not payload:
        return []
    items = payload.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, Mapping)]


def metadata_name(resource: Mapping[str, Any]) -> str:
    metadata = resource.get("metadata", {}) if isinstance(resource.get("metadata"), Mapping) else {}
    return str(metadata.get("name") or "")


def metadata_namespace(resource: Mapping[str, Any]) -> str:
    metadata = resource.get("metadata", {}) if isinstance(resource.get("metadata"), Mapping) else {}
    return str(metadata.get("namespace") or "")


def resource_labels(resource: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = resource.get("metadata", {}) if isinstance(resource.get("metadata"), Mapping) else {}
    labels = metadata.get("labels")
    return labels if isinstance(labels, Mapping) else {}


def selector_matches_labels(selector: Mapping[str, Any], labels: Mapping[str, Any]) -> bool:
    matched_any_selector = False
    match_labels = selector.get("matchLabels")
    if isinstance(match_labels, Mapping):
        for key, value in match_labels.items():
            matched_any_selector = True
            if str(labels.get(str(key)) or "") != str(value):
                return False

    expressions = selector.get("matchExpressions")
    if isinstance(expressions, list):
        for expression in expressions:
            if not isinstance(expression, Mapping):
                return False
            key = str(expression.get("key") or "")
            operator = str(expression.get("operator") or "")
            values = expression.get("values")
            value_set = {str(value) for value in values} if isinstance(values, list) else set()
            label_exists = key in labels
            label_value = str(labels.get(key) or "")
            matched_any_selector = True
            if operator == "In" and label_value not in value_set:
                return False
            if operator == "NotIn" and label_exists and label_value in value_set:
                return False
            if operator == "Exists" and not label_exists:
                return False
            if operator == "DoesNotExist" and label_exists:
                return False
            if operator not in {"In", "NotIn", "Exists", "DoesNotExist"}:
                return False

    return matched_any_selector


def pod_matches_deployment_selector(pod: Mapping[str, Any], deployment: Mapping[str, Any]) -> bool:
    if metadata_namespace(pod) != metadata_namespace(deployment):
        return False
    spec = deployment.get("spec", {}) if isinstance(deployment.get("spec"), Mapping) else {}
    selector = spec.get("selector")
    if not isinstance(selector, Mapping):
        return False
    return selector_matches_labels(selector, resource_labels(pod))


def pod_ready_numbers(pod: Mapping[str, Any]) -> tuple[int, int]:
    statuses = pod.get("status", {}).get("containerStatuses", [])
    if not isinstance(statuses, list):
        return 0, 0
    total = len(statuses)
    ready = sum(1 for item in statuses if isinstance(item, Mapping) and item.get("ready"))
    return ready, total


def pod_is_fully_ready(pod: Mapping[str, Any]) -> bool:
    ready, total = pod_ready_numbers(pod)
    return total > 0 and ready == total


def pod_restart_total(pod: Mapping[str, Any]) -> int:
    statuses = pod.get("status", {}).get("containerStatuses", [])
    if not isinstance(statuses, list):
        return 0
    return sum(int(item.get("restartCount") or 0) for item in statuses if isinstance(item, Mapping))


def pod_is_terminating(pod: Mapping[str, Any]) -> bool:
    metadata = pod.get("metadata", {}) if isinstance(pod.get("metadata"), Mapping) else {}
    return bool(metadata.get("deletionTimestamp"))


def pod_matches_target_fallback(pod: Mapping[str, Any], target_name: str, namespace: str = "") -> bool:
    if namespace and metadata_namespace(pod) != namespace:
        return False

    pod_name = metadata_name(pod)
    if pod_name == target_name or pod_name.startswith(f"{target_name}-"):
        return True

    labels = resource_labels(pod)
    standard_identity_labels = (
        "app",
        "app.kubernetes.io/name",
        "app.kubernetes.io/instance",
        "deployment",
        "deploymentconfig",
        "name",
    )
    return any(str(labels.get(key) or "") == target_name for key in standard_identity_labels)


def deployment_matches_identity(deployment: Mapping[str, Any], target_name: str) -> bool:
    if metadata_name(deployment) == target_name:
        return True

    standard_identity_labels = (
        "app",
        "app.kubernetes.io/name",
        "app.kubernetes.io/instance",
        "deployment",
        "deploymentconfig",
        "name",
    )
    metadata_labels = resource_labels(deployment)
    if any(str(metadata_labels.get(key) or "") == target_name for key in standard_identity_labels):
        return True

    spec = deployment.get("spec", {}) if isinstance(deployment.get("spec"), Mapping) else {}
    template = spec.get("template") if isinstance(spec.get("template"), Mapping) else {}
    template_metadata = template.get("metadata") if isinstance(template.get("metadata"), Mapping) else {}
    template_labels = template_metadata.get("labels") if isinstance(template_metadata.get("labels"), Mapping) else {}
    return any(str(template_labels.get(key) or "") == target_name for key in standard_identity_labels)


def choose_single_natural_action_target(
    candidates: list[Mapping[str, Any]],
    *,
    target_name: str,
) -> dict[str, Any]:
    if not candidates:
        return {"status": "not_found"}

    exact = [candidate for candidate in candidates if metadata_name(candidate) == target_name]
    narrowed = exact or candidates
    unique_by_namespace_name = {
        (metadata_namespace(candidate), metadata_name(candidate)): candidate for candidate in narrowed
    }
    unique_candidates = list(unique_by_namespace_name.values())
    if len(unique_candidates) == 1:
        return {"status": "found", "target": unique_candidates[0]}

    return {
        "candidates": [
            {
                "kind": str(candidate.get("kind") or ""),
                "name": metadata_name(candidate),
                "namespace": metadata_namespace(candidate),
            }
            for candidate in sorted(unique_candidates, key=lambda item: (metadata_namespace(item), metadata_name(item)))[:10]
        ],
        "status": "ambiguous",
    }


async def resolve_natural_action_target(
    client: httpx.AsyncClient,
    intent: Mapping[str, Any],
    authorization: str,
) -> dict[str, Any]:
    namespace = str(intent.get("namespace") or "")
    target_name = str(intent.get("targetName") or "")
    api_version = str(intent.get("apiVersion") or "apps/v1")
    kind = str(intent.get("kind") or "Deployment")
    lookup_target = {
        "apiVersion": api_version,
        "kind": kind,
        "namespace": namespace,
        "name": target_name,
    }

    if namespace:
        live_target = await fetch_ocp_json(client, target_path(lookup_target), authorization)
        return {"status": "found", "target": live_target} if live_target else {"status": "not_found"}

    if kind != "Deployment" or api_version != "apps/v1":
        return {"status": "missing_namespace"}

    deployments_payload = await fetch_ocp_json(client, "/apis/apps/v1/deployments", authorization)
    deployments = resource_items(deployments_payload)
    identity_matches = [
        deployment for deployment in deployments if deployment_matches_identity(deployment, target_name)
    ]
    identity_result = choose_single_natural_action_target(identity_matches, target_name=target_name)
    if identity_result["status"] in {"found", "ambiguous"}:
        return identity_result

    pods_payload = await fetch_ocp_json(client, "/api/v1/pods", authorization)
    matched_pods = [
        pod for pod in resource_items(pods_payload) if pod_matches_target_fallback(pod, target_name)
    ]
    selector_matches = [
        deployment
        for deployment in deployments
        if any(pod_matches_deployment_selector(pod, deployment) for pod in matched_pods)
    ]
    selector_result = choose_single_natural_action_target(selector_matches, target_name=target_name)
    if selector_result["status"] == "found":
        selector_result["matchStrategy"] = "pod_name_or_standard_labels_to_deployment_selector"
    return selector_result


def summarize_counted_pods(pods: list[Mapping[str, Any]]) -> dict[str, Any]:
    phase_counts: dict[str, int] = {}
    for pod in pods:
        status = pod.get("status", {}) if isinstance(pod.get("status"), Mapping) else {}
        phase = str(status.get("phase") or "Unknown")
        phase_counts[phase] = phase_counts.get(phase, 0) + 1

    pod_details = [
        {
            "name": metadata_name(pod),
            "phase": pod_display_state(pod),
            "ready": pod_ready_summary(pod),
            "restarts": pod_restart_total(pod),
            "terminating": pod_is_terminating(pod),
        }
        for pod in sorted(pods, key=lambda item: metadata_name(item))
    ]
    running = sum(
        1
        for pod in pods
        if (pod.get("status", {}) if isinstance(pod.get("status"), Mapping) else {}).get("phase") == "Running"
    )
    ready = sum(1 for pod in pods if pod_is_fully_ready(pod))
    terminating = sum(1 for pod in pods if pod_is_terminating(pod))
    return {
        "phaseCounts": phase_counts,
        "podDetails": pod_details,
        "readyPods": ready,
        "runningPods": running,
        "terminatingPods": terminating,
        "totalPods": len(pods),
        "unhealthyPods": sum(
            1
            for pod in pods
            if not pod_is_fully_ready(pod)
            or (pod.get("status", {}) if isinstance(pod.get("status"), Mapping) else {}).get("phase") != "Running"
        ),
    }


def build_pod_count_investigation(
    query: Mapping[str, str],
    deployments_payload: Mapping[str, Any] | None,
    pods_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    target_name = str(query.get("targetName") or "")
    namespace = str(query.get("namespace") or "")
    if not target_name:
        return {
            "namespace": namespace,
            "reason": "target_name_missing",
            "status": "missing_target",
        }

    deployments = resource_items(deployments_payload)
    pods = resource_items(pods_payload)
    matched_deployments = [
        deployment
        for deployment in deployments
        if metadata_name(deployment) == target_name
        and (not namespace or metadata_namespace(deployment) == namespace)
    ]

    rows: list[dict[str, Any]] = []
    if matched_deployments:
        for deployment in sorted(
            matched_deployments,
            key=lambda item: (metadata_namespace(item), metadata_name(item)),
        ):
            spec = deployment.get("spec", {}) if isinstance(deployment.get("spec"), Mapping) else {}
            status = deployment.get("status", {}) if isinstance(deployment.get("status"), Mapping) else {}
            matched_pods = [
                pod for pod in pods if pod_matches_deployment_selector(pod, deployment)
            ]
            pod_summary = summarize_counted_pods(matched_pods)
            rows.append(
                {
                    **pod_summary,
                    "availableReplicas": int(status.get("availableReplicas") or 0),
                    "desiredReplicas": int(spec.get("replicas") or 0),
                    "kind": "Deployment",
                    "namespace": metadata_namespace(deployment),
                    "observedGeneration": status.get("observedGeneration"),
                    "readyReplicas": int(status.get("readyReplicas") or 0),
                    "targetName": target_name,
                    "updatedReplicas": int(status.get("updatedReplicas") or 0),
                }
            )
        return {
            "matchStrategy": "deployment_selector",
            "namespace": namespace,
            "rows": rows,
            "status": "found",
            "targetName": target_name,
        }

    matched_pods = [
        pod for pod in pods if pod_matches_target_fallback(pod, target_name, namespace=namespace)
    ]
    if matched_pods:
        grouped: dict[str, list[Mapping[str, Any]]] = {}
        for pod in matched_pods:
            grouped.setdefault(metadata_namespace(pod), []).append(pod)
        for pod_namespace, namespace_pods in sorted(grouped.items()):
            pod_summary = summarize_counted_pods(namespace_pods)
            rows.append(
                {
                    **pod_summary,
                    "availableReplicas": "-",
                    "desiredReplicas": "-",
                    "kind": "PodSelector",
                    "namespace": pod_namespace,
                    "readyReplicas": "-",
                    "targetName": target_name,
                    "updatedReplicas": "-",
                }
            )
        return {
            "matchStrategy": "pod_name_or_standard_labels",
            "namespace": namespace,
            "rows": rows,
            "status": "found",
            "targetName": target_name,
        }

    return {
        "matchStrategy": "deployment_then_pod_fallback",
        "namespace": namespace,
        "rows": [],
        "status": "not_found",
        "targetName": target_name,
    }


def pod_count_investigation_response(result: Mapping[str, Any]) -> str:
    status = str(result.get("status") or "unknown")
    target_name = str(result.get("targetName") or "")
    namespace = str(result.get("namespace") or "")
    scope = f"namespace `{namespace}`" if namespace else "접근 가능한 전체 namespace"

    if status == "unavailable":
        return "\n".join(
            [
                "Pod 개수 직접 조회를 수행하지 못했습니다.",
                "",
                f"- 사유: {result.get('reason')}",
                f"- 조회 범위: {scope}",
            ]
        )

    if status == "missing_target":
        return "\n".join(
            [
                "Pod 개수를 직접 조회하려면 대상 Deployment 또는 Pod 이름이 필요합니다.",
                "",
                f"- 조회 범위: {scope}",
                "- 예: `komsco-ai-dev 네임스페이스의 web-api 파드 몇 개 떠있어?`",
            ]
        )

    if status == "not_found":
        return "\n".join(
            [
                f"`{target_name}` 기준으로 직접 Kubernetes API를 조회했지만 매칭되는 Deployment 또는 Pod를 찾지 못했습니다.",
                "",
                f"- 조회 범위: {scope}",
                f"- 매칭 방식: `{result.get('matchStrategy')}`",
                "- 대상 이름 또는 namespace를 확인하세요.",
            ]
        )

    rows = result.get("rows")
    result_rows = [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []
    if not result_rows:
        return f"`{target_name}` 기준 조회 결과가 비어 있습니다. 조회 범위: {scope}"

    first_row = result_rows[0]
    if len(result_rows) == 1:
        lead = (
            f"`{first_row.get('namespace')}/{target_name}` 기준 현재 Pod는 총 "
            f"{first_row.get('totalPods')}개이며, Running {first_row.get('runningPods')}개, "
            f"Ready {first_row.get('readyPods')}/{first_row.get('totalPods')}개입니다."
        )
    else:
        total_pods = sum(int(row.get("totalPods") or 0) for row in result_rows)
        running_pods = sum(int(row.get("runningPods") or 0) for row in result_rows)
        ready_pods = sum(int(row.get("readyPods") or 0) for row in result_rows)
        lead = (
            f"`{target_name}` 이름이 여러 namespace에서 매칭되었습니다. 합계는 총 {total_pods}개, "
            f"Running {running_pods}개, Ready {ready_pods}/{total_pods}개입니다."
        )

    lines = [
        lead,
        "",
        "직접 Kubernetes API로 조회했으며 실행/변경 조치는 수행하지 않았습니다.",
        "",
        "| Namespace | Target | Desired | Current Pods | Running | Ready | Terminating | Pod details |",
        "| :--- | :--- | ---: | ---: | ---: | :---: | ---: | :--- |",
    ]
    for row in result_rows:
        pod_details = row.get("podDetails")
        detail_items = []
        if isinstance(pod_details, list):
            for pod in pod_details[:8]:
                if not isinstance(pod, Mapping):
                    continue
                terminating = ", terminating" if pod.get("terminating") else ""
                detail_items.append(
                    f"{pod.get('name')}({pod.get('phase')}, ready {pod.get('ready')}, restarts {pod.get('restarts')}{terminating})"
                )
            if len(pod_details) > len(detail_items):
                detail_items.append(f"+{len(pod_details) - len(detail_items)} more")

        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_table_cell(row.get("namespace")),
                    markdown_table_cell(f"{row.get('kind')}/{row.get('targetName')}"),
                    markdown_table_cell(row.get("desiredReplicas")),
                    markdown_table_cell(row.get("totalPods")),
                    markdown_table_cell(row.get("runningPods")),
                    markdown_table_cell(f"{row.get('readyPods')}/{row.get('totalPods')}"),
                    markdown_table_cell(row.get("terminatingPods")),
                    markdown_table_cell(", ".join(detail_items) or "-", max_length=800),
                ]
            )
            + " |"
        )

    return "\n".join(lines)


def container_spec_index(pod: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    spec = pod.get("spec", {}) if isinstance(pod.get("spec"), Mapping) else {}
    containers = spec.get("containers")
    if not isinstance(containers, list):
        return {}

    indexed: dict[str, Mapping[str, Any]] = {}
    for container in containers:
        if not isinstance(container, Mapping):
            continue
        name = str(container.get("name") or "")
        if name:
            indexed[name] = container
    return indexed


def replicaset_owner_index(replicasets_payload: Mapping[str, Any] | None) -> dict[tuple[str, str], str]:
    if not replicasets_payload:
        return {}
    items = replicasets_payload.get("items")
    if not isinstance(items, list):
        return {}

    indexed: dict[tuple[str, str], str] = {}
    for replicaset in items:
        if not isinstance(replicaset, Mapping):
            continue
        metadata = replicaset.get("metadata", {}) if isinstance(replicaset.get("metadata"), Mapping) else {}
        namespace = str(metadata.get("namespace") or "")
        name = str(metadata.get("name") or "")
        owner = pod_owner_summary(replicaset)
        if namespace and name and owner != "-":
            indexed[(namespace, name)] = owner
    return indexed


def pod_owner_chain_summary(
    pod: Mapping[str, Any],
    replicaset_owners: Mapping[tuple[str, str], str],
) -> str:
    metadata = pod.get("metadata", {}) if isinstance(pod.get("metadata"), Mapping) else {}
    namespace = str(metadata.get("namespace") or "")
    owner = pod_owner_summary(pod)
    if owner == "-" or not owner.startswith("ReplicaSet/"):
        return owner

    replicaset_name = owner.split("/", 1)[1]
    parent_owner = replicaset_owners.get((namespace, replicaset_name))
    if not parent_owner:
        return owner
    return f"{owner} -> {parent_owner}"


def build_pod_status_evidence(
    pods_payload: Mapping[str, Any],
    replicasets_payload: Mapping[str, Any] | None = None,
    *,
    include_pod_list: bool = False,
    list_namespace: str = "",
) -> str:
    items = pods_payload.get("items")
    if not isinstance(items, list):
        return "Pod status evidence unavailable: API response did not include an items list."

    replicaset_owners = replicaset_owner_index(replicasets_payload)
    rows: list[dict[str, Any]] = []
    unhealthy_rows: list[dict[str, Any]] = []
    for pod in items:
        if not isinstance(pod, Mapping):
            continue

        metadata = pod.get("metadata", {}) if isinstance(pod.get("metadata"), Mapping) else {}
        status = pod.get("status", {}) if isinstance(pod.get("status"), Mapping) else {}
        namespace = str(metadata.get("namespace") or "unknown")
        pod_name = str(metadata.get("name") or "unknown")
        phase = str(status.get("phase") or "Unknown")
        pod_start_time = str(status.get("startTime") or "-")
        ready = pod_ready_summary(pod)
        pod_state = pod_display_state(pod)
        owner = pod_owner_summary(pod)
        owner_chain = pod_owner_chain_summary(pod, replicaset_owners)
        label_summary = pod_label_summary(pod)
        specs_by_name = container_spec_index(pod)
        statuses = status.get("containerStatuses", [])
        regular_statuses = statuses if isinstance(statuses, list) else []
        expected_ready = f"{len(regular_statuses)}/{len(regular_statuses)}"
        is_unhealthy = phase not in {"Running", "Succeeded"} or ready != expected_ready

        for container in regular_statuses:
            if not isinstance(container, Mapping):
                continue

            last_state, last_finished_at = last_termination_summary(container)
            container_name = str(container.get("name") or "unknown")
            container_spec = specs_by_name.get(container_name, {})
            row = {
                "namespace": namespace,
                "pod": pod_name,
                "container": container_name,
                "phase": pod_state,
                "podStartTime": pod_start_time,
                "ready": ready,
                "state": state_summary(container),
                "restartCount": int(container.get("restartCount") or 0),
                "lastState": last_state,
                "lastFinishedAt": last_finished_at or "-",
                "lastFinishedSort": parse_rfc3339(last_finished_at)
                or datetime.min.replace(tzinfo=UTC),
                "owner": owner,
                "ownerChain": owner_chain,
                "image": markdown_table_cell(container_spec.get("image") or "-"),
                "command": markdown_table_cell(json_list_summary(container_spec.get("command"))),
                "args": markdown_table_cell(json_list_summary(container_spec.get("args"))),
                "labels": markdown_table_cell(label_summary),
            }
            rows.append(row)
            if is_unhealthy or row["state"].startswith("waiting:"):
                unhealthy_rows.append(row)

    top_restart_rows = sorted(
        rows,
        key=lambda item: (item["restartCount"], item["lastFinishedSort"]),
        reverse=True,
    )[:15]
    top_unhealthy_rows = sorted(
        unhealthy_rows,
        key=lambda item: (item["restartCount"], item["lastFinishedSort"]),
        reverse=True,
    )[:10]
    list_rows = sorted(
        [
            row
            for row in rows
            if not list_namespace or str(row.get("namespace") or "") == list_namespace
        ],
        key=lambda item: (str(item["namespace"]), str(item["pod"]), str(item["container"])),
    )

    lines = [
        "Gateway-collected Pod status evidence from Kubernetes API `/api/v1/pods`.",
        "Use this as primary evidence for cluster-wide Pod restart/status analysis.",
        "Restart counts below are cumulative container-level counts, not Pod-level rates.",
        "Pod phase/startTime indicate the current Pod object state; old Failed pods can be historical artifacts.",
        "Do not infer current control-plane or service impact from Failed pods alone; correlate with owner/controller/operator status.",
        "",
        "Top container restart counts:",
        "| Namespace | Pod | Container | Current State | Pod Start | Ready | Restarts | Last State/Exit | Last Finished | Owner |",
        "| :--- | :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- | :--- |",
    ]
    if top_restart_rows:
        for row in top_restart_rows:
            lines.append(
                "| {namespace} | `{pod}` | `{container}` | {phase} / {state} | {podStartTime} | {ready} | {restartCount} | {lastState} | {lastFinishedAt} | {owner} |".format(
                    **row
                )
            )
    else:
        lines.append("| - | - | - | - | - | - | 0 | - | - | - |")

    lines.extend(
        [
            "",
            "Currently non-healthy or waiting container evidence:",
            "| Namespace | Pod | Container | Current State | Pod Start | Ready | Restarts | Last State/Exit | Owner |",
            "| :--- | :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- |",
        ]
    )
    if top_unhealthy_rows:
        for row in top_unhealthy_rows:
            lines.append(
                "| {namespace} | `{pod}` | `{container}` | {phase} / {state} | {podStartTime} | {ready} | {restartCount} | {lastState} | {owner} |".format(
                    **row
                )
            )
    else:
        lines.append(
            "| - | - | - | 현재 non-healthy/waiting container가 evidence 상위권에 없음 | - | - | 0 | - | - |"
        )

    if include_pod_list:
        shown_list_rows = list_rows[:200]
        namespace_label = list_namespace or "all-accessible-namespaces"
        lines.extend(
            [
                "",
                "Current Pod list evidence:",
                f"Namespace filter: `{namespace_label}`",
                f"Rows shown: {len(shown_list_rows)} / {len(list_rows)}",
                "| Namespace | Pod | Container | Current State | Pod Start | Ready | Restarts | Last State/Exit | Owner |",
                "| :--- | :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- |",
            ]
        )
        if shown_list_rows:
            for row in shown_list_rows:
                lines.append(
                    "| {namespace} | `{pod}` | `{container}` | {phase} / {state} | {podStartTime} | {ready} | {restartCount} | {lastState} | {owner} |".format(
                        **row
                    )
                )
        else:
            lines.append("| - | - | - | 조회된 Pod 없음 | - | - | 0 | - | - |")

    lines.extend(
        [
            "",
            "Spec evidence for currently non-healthy or waiting containers:",
            "Use command/args/image/labels below as concrete evidence for root-cause and remediation planning; do not replace these values with generic guesses.",
            "| Namespace | Pod | Container | Image | Command | Args | Pod Labels | Owner Chain |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
    )
    if top_unhealthy_rows:
        for row in top_unhealthy_rows:
            lines.append(
                "| {namespace} | `{pod}` | `{container}` | {image} | {command} | {args} | {labels} | {ownerChain} |".format(
                    **row
                )
            )
    else:
        lines.append("| - | - | - | - | - | - | - | - |")

    return "\n".join(lines)


def build_deployment_rollout_evidence(
    deployments_payload: Mapping[str, Any] | None,
    replicasets_payload: Mapping[str, Any] | None,
    pods_payload: Mapping[str, Any],
) -> str:
    deployments = deployments_payload.get("items") if isinstance(deployments_payload, Mapping) else None
    if not isinstance(deployments, list):
        return "Deployment rollout evidence unavailable: deployments API response did not include an items list."

    replicasets = replicasets_payload.get("items") if isinstance(replicasets_payload, Mapping) else []
    pods = pods_payload.get("items") if isinstance(pods_payload.get("items"), list) else []
    rs_by_deployment_uid: dict[str, list[Mapping[str, Any]]] = {}
    if isinstance(replicasets, list):
        for replicaset in replicasets:
            if not isinstance(replicaset, Mapping):
                continue
            for owner in replicaset.get("metadata", {}).get("ownerReferences", []) or []:
                if isinstance(owner, Mapping) and owner.get("kind") == "Deployment":
                    rs_by_deployment_uid.setdefault(str(owner.get("uid") or ""), []).append(replicaset)

    pod_rows_by_selector: dict[tuple[str, str], list[str]] = {}
    if isinstance(pods, list):
        for pod in pods:
            if not isinstance(pod, Mapping):
                continue
            metadata = pod.get("metadata", {}) if isinstance(pod.get("metadata"), Mapping) else {}
            labels = metadata.get("labels") if isinstance(metadata.get("labels"), Mapping) else {}
            namespace = str(metadata.get("namespace") or "")
            app = str(labels.get("app") or "")
            if not namespace or not app:
                continue
            hash_value = str(labels.get("pod-template-hash") or "-")
            name = str(metadata.get("name") or "unknown")
            start_time = str(pod.get("status", {}).get("startTime") or "-")
            pod_rows_by_selector.setdefault((namespace, app), []).append(f"{name} hash={hash_value} start={start_time}")

    rows: list[dict[str, Any]] = []
    for deployment in deployments:
        if not isinstance(deployment, Mapping):
            continue
        metadata = deployment.get("metadata", {}) if isinstance(deployment.get("metadata"), Mapping) else {}
        spec = deployment.get("spec", {}) if isinstance(deployment.get("spec"), Mapping) else {}
        status = deployment.get("status", {}) if isinstance(deployment.get("status"), Mapping) else {}
        namespace = str(metadata.get("namespace") or "unknown")
        name = str(metadata.get("name") or "unknown")
        annotations = metadata.get("annotations") if isinstance(metadata.get("annotations"), Mapping) else {}
        template_metadata = (
            spec.get("template", {}).get("metadata", {})
            if isinstance(spec.get("template"), Mapping)
            else {}
        )
        template_annotations = (
            template_metadata.get("annotations")
            if isinstance(template_metadata.get("annotations"), Mapping)
            else {}
        )
        labels = template_metadata.get("labels") if isinstance(template_metadata.get("labels"), Mapping) else {}
        app_label = str(labels.get("app") or "")
        deployment_uid = str(metadata.get("uid") or "")
        owned_rs = sorted(
            rs_by_deployment_uid.get(deployment_uid, []),
            key=lambda item: str(item.get("metadata", {}).get("creationTimestamp") or ""),
        )
        rs_summary = []
        for replicaset in owned_rs[-4:]:
            rs_meta = replicaset.get("metadata", {}) if isinstance(replicaset.get("metadata"), Mapping) else {}
            rs_status = replicaset.get("status", {}) if isinstance(replicaset.get("status"), Mapping) else {}
            rs_spec = replicaset.get("spec", {}) if isinstance(replicaset.get("spec"), Mapping) else {}
            rs_annotations = rs_meta.get("annotations") if isinstance(rs_meta.get("annotations"), Mapping) else {}
            rs_summary.append(
                "{name}(rev={rev},desired={desired},ready={ready})".format(
                    name=str(rs_meta.get("name") or "unknown"),
                    rev=str(rs_annotations.get("deployment.kubernetes.io/revision") or "-"),
                    desired=str(rs_spec.get("replicas", 0)),
                    ready=str(rs_status.get("readyReplicas", 0)),
                )
            )
        pod_summary = pod_rows_by_selector.get((namespace, app_label), [])
        rows.append(
            {
                "namespace": namespace,
                "name": name,
                "revision": markdown_table_cell(annotations.get("deployment.kubernetes.io/revision") or "-"),
                "restartedAt": markdown_table_cell(
                    template_annotations.get("kubectl.kubernetes.io/restartedAt") or "-"
                ),
                "observedGeneration": markdown_table_cell(status.get("observedGeneration") or "-"),
                "ready": f"{status.get('readyReplicas', 0)}/{spec.get('replicas', 0)}",
                "updated": markdown_table_cell(status.get("updatedReplicas", 0)),
                "replicaSets": markdown_table_cell("; ".join(rs_summary) or "-"),
                "pods": markdown_table_cell("; ".join(sorted(pod_summary)) or "-"),
            }
        )

    lines = [
        "Deployment rollout/replacement evidence from Kubernetes APIs.",
        "Ready replicas only prove current availability. Do not say Pods were replaced unless restart annotation, Deployment revision/ReplicaSet transition, ExecutionRecord, or before/after Pod identity comparison proves it.",
        "| Namespace | Deployment | Revision | RestartedAt | ObservedGeneration | Ready | Updated | Recent ReplicaSets | Current Pods |",
        "| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :--- | :--- |",
    ]
    for row in sorted(rows, key=lambda item: (str(item["namespace"]), str(item["name"])))[:40]:
        lines.append(
            "| {namespace} | `{name}` | {revision} | {restartedAt} | {observedGeneration} | {ready} | {updated} | {replicaSets} | {pods} |".format(
                **row
            )
        )
    if not rows:
        lines.append("| - | - | - | - | - | - | - | - | - |")
    return "\n".join(lines)


def cluster_operator_condition(
    operator: Mapping[str, Any],
    condition_type: str,
) -> tuple[str, str, str]:
    conditions = operator.get("status", {}).get("conditions", [])
    if not isinstance(conditions, list):
        return "-", "-", "-"

    for condition in conditions:
        if not isinstance(condition, Mapping) or condition.get("type") != condition_type:
            continue
        return (
            str(condition.get("status") or "-"),
            str(condition.get("reason") or "-"),
            str(condition.get("message") or "-"),
        )

    return "-", "-", "-"


def build_cluster_operator_status_evidence(cluster_operators_payload: Mapping[str, Any]) -> str:
    items = cluster_operators_payload.get("items")
    if not isinstance(items, list):
        return "ClusterOperator evidence unavailable: API response did not include an items list."

    rows: list[dict[str, str]] = []
    for operator in items:
        if not isinstance(operator, Mapping):
            continue

        metadata = operator.get("metadata", {}) if isinstance(operator.get("metadata"), Mapping) else {}
        status = operator.get("status", {}) if isinstance(operator.get("status"), Mapping) else {}
        available, available_reason, available_message = cluster_operator_condition(
            operator,
            "Available",
        )
        degraded, degraded_reason, degraded_message = cluster_operator_condition(
            operator,
            "Degraded",
        )
        progressing, progressing_reason, progressing_message = cluster_operator_condition(
            operator,
            "Progressing",
        )
        rows.append(
            {
                "name": str(metadata.get("name") or "unknown"),
                "version": str(status.get("versions", [{}])[0].get("version") or "-")
                if isinstance(status.get("versions"), list) and status.get("versions")
                else "-",
                "available": available,
                "degraded": degraded,
                "progressing": progressing,
                "reason": next(
                    (
                        value
                        for value in [
                            degraded_reason if degraded == "True" else "",
                            progressing_reason if progressing == "True" else "",
                            available_reason if available != "True" else "",
                        ]
                        if value and value != "-"
                    ),
                    "-",
                ),
                "message": truncate_detail(
                    next(
                        (
                            value
                            for value in [
                                degraded_message if degraded == "True" else "",
                                progressing_message if progressing == "True" else "",
                                available_message if available != "True" else "",
                            ]
                            if value and value != "-"
                        ),
                        "-",
                    ),
                    300,
                ),
            }
        )

    issue_rows = [
        row
        for row in rows
        if row["available"] != "True" or row["degraded"] == "True" or row["progressing"] == "True"
    ]
    selected_rows = issue_rows or rows[:10]
    lines = [
        "Gateway-collected ClusterOperator status evidence from Kubernetes API `/apis/config.openshift.io/v1/clusteroperators`.",
        "Use this to avoid treating historical Failed control-plane/operator installer pods as current outages when operators are healthy.",
        "| ClusterOperator | Version | Available | Degraded | Progressing | Reason | Message |",
        "| :--- | :--- | :---: | :---: | :---: | :--- | :--- |",
    ]
    for row in selected_rows[:15]:
        lines.append(
            "| {name} | {version} | {available} | {degraded} | {progressing} | {reason} | {message} |".format(
                **row
            )
        )
    if not selected_rows:
        lines.append("| - | - | - | - | - | - | - |")

    return "\n".join(lines)


def cron_minute_interval(schedule: str) -> int | None:
    fields = schedule.split()
    if len(fields) < 5:
        return None

    minute_field = fields[0]
    match = re.fullmatch(r"(?:\*|0)/(\d+)", minute_field)
    if not match:
        return None

    interval = int(match.group(1))
    return interval if interval > 0 else None


def requested_minute_interval(context_text: str) -> int | None:
    cron_match = re.search(r"(?:\*|0)/(\d+)", context_text)
    if cron_match:
        interval = int(cron_match.group(1))
        return interval if interval > 0 else None

    minute_match = re.search(r"(?i)(\d+)\s*(분|minute|min)", context_text)
    if minute_match:
        interval = int(minute_match.group(1))
        return interval if interval > 0 else None

    return None


def schedule_interval_summary(schedule: str) -> str:
    interval = cron_minute_interval(schedule)
    if interval is None:
        return "-"

    return f"{interval}분마다"


def format_seconds_duration(value: str) -> str:
    try:
        seconds = int(value)
    except ValueError:
        return value

    if seconds <= 0:
        return f"{seconds}초"
    if seconds % 86400 == 0:
        days = seconds // 86400
        return f"{seconds}초 ({days}일)"
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return f"{seconds}초 ({hours}시간)"
    if seconds % 60 == 0:
        minutes = seconds // 60
        return f"{seconds}초 ({minutes}분)"

    return f"{seconds}초"


def safe_env_value(env_item: Mapping[str, Any]) -> str:
    name = str(env_item.get("name") or "")
    if SECRET_ENV_RE.search(name):
        return "[REDACTED]"

    value = env_item.get("value")
    if value is not None:
        return str(value)

    value_from = env_item.get("valueFrom")
    if isinstance(value_from, Mapping):
        if "secretKeyRef" in value_from:
            return "[REDACTED:valueFrom.secretKeyRef]"
        return f"valueFrom.{next(iter(value_from.keys()), 'unknown')}"

    return "-"


def cronjob_container_summary(cronjob: Mapping[str, Any]) -> tuple[str, list[Mapping[str, Any]]]:
    containers = (
        cronjob.get("spec", {})
        .get("jobTemplate", {})
        .get("spec", {})
        .get("template", {})
        .get("spec", {})
        .get("containers", [])
    )
    if not isinstance(containers, list):
        return "-", []

    images = []
    env_items: list[Mapping[str, Any]] = []
    for container in containers:
        if not isinstance(container, Mapping):
            continue
        image = container.get("image")
        if image:
            images.append(str(image))
        env = container.get("env", [])
        if isinstance(env, list):
            env_items.extend(item for item in env if isinstance(item, Mapping))

    return ", ".join(images) if images else "-", env_items


def cronjob_matches_context(cronjob: Mapping[str, Any], context_text: str) -> bool:
    metadata = cronjob.get("metadata", {}) if isinstance(cronjob.get("metadata"), Mapping) else {}
    spec = cronjob.get("spec", {}) if isinstance(cronjob.get("spec"), Mapping) else {}
    name = str(metadata.get("name") or "")
    namespace = str(metadata.get("namespace") or "")
    schedule = str(spec.get("schedule") or "")
    context = context_text.lower()
    requested_interval = requested_minute_interval(context_text)

    if name and name.lower() in context:
        return True
    if namespace and namespace.lower() in context and ("cron" in context or "크론" in context):
        return True
    if requested_interval is not None and cron_minute_interval(schedule) == requested_interval:
        return True
    if cron_minute_interval(schedule) is not None and re.search(
        r"(?i)(주기|반복|활동|이벤트|activity|schedule|스케줄)",
        context_text,
    ):
        return True

    return False


def build_cronjob_activity_evidence(
    cronjobs_payload: Mapping[str, Any],
    jobs_payload: Mapping[str, Any] | None = None,
    *,
    context_text: str = "",
) -> str:
    cronjobs = cronjobs_payload.get("items")
    if not isinstance(cronjobs, list):
        return "CronJob activity evidence unavailable: API response did not include an items list."

    matched: list[Mapping[str, Any]] = [
        item for item in cronjobs if isinstance(item, Mapping) and cronjob_matches_context(item, context_text)
    ]
    if not matched:
        requested_interval = requested_minute_interval(context_text)
        matched = [
            item
            for item in cronjobs
            if isinstance(item, Mapping)
            and requested_interval is not None
            and cron_minute_interval(str(item.get("spec", {}).get("schedule") or ""))
            == requested_interval
        ]
    if not matched:
        matched = [item for item in cronjobs if isinstance(item, Mapping)][:10]

    matched = sorted(
        matched,
        key=lambda item: (
            str(item.get("metadata", {}).get("namespace") or ""),
            str(item.get("metadata", {}).get("name") or ""),
        ),
    )[:10]
    matched_keys = {
        (
            str(item.get("metadata", {}).get("namespace") or ""),
            str(item.get("metadata", {}).get("name") or ""),
        )
        for item in matched
    }

    lines = [
        "Gateway-collected CronJob activity evidence from Kubernetes API `/apis/batch/v1/cronjobs`.",
        "Use this as primary evidence for scheduled Activity/CronJob questions.",
        "If a matched CronJob uses an interval schedule, answer first whether the observed interval is expected by configuration.",
        "Do not overstate intent from the name alone; use env/settings as policy hints and say when behavior needs log confirmation.",
        "Env seconds are threshold values only; do not infer created-time or idle-time basis unless logs or source confirm it.",
        "",
        "Matched CronJobs:",
        "| Namespace | CronJob | Schedule | Derived interval | Concurrency | Suspend | Successful history | Failed history | Image |",
        "| :--- | :--- | :--- | :--- | :--- | :---: | ---: | ---: | :--- |",
    ]

    policy_env_rows: list[str] = []
    for cronjob in matched:
        metadata = cronjob.get("metadata", {}) if isinstance(cronjob.get("metadata"), Mapping) else {}
        spec = cronjob.get("spec", {}) if isinstance(cronjob.get("spec"), Mapping) else {}
        namespace = str(metadata.get("namespace") or "unknown")
        name = str(metadata.get("name") or "unknown")
        schedule = str(spec.get("schedule") or "-")
        concurrency_policy = str(spec.get("concurrencyPolicy") or "-")
        suspend = str(spec.get("suspend", False))
        success_history = str(spec.get("successfulJobsHistoryLimit", "-"))
        failed_history = str(spec.get("failedJobsHistoryLimit", "-"))
        image_summary, env_items = cronjob_container_summary(cronjob)
        interval_summary = schedule_interval_summary(schedule)
        lines.append(
            f"| {namespace} | `{name}` | `{schedule}` | {interval_summary} | "
            f"{concurrency_policy} | {suspend} | {success_history} | {failed_history} | "
            f"`{image_summary}` |"
        )

        for env_item in env_items:
            env_name = str(env_item.get("name") or "")
            if not CRONJOB_POLICY_ENV_RE.search(env_name):
                continue
            raw_value = safe_env_value(env_item)
            interpreted = format_seconds_duration(raw_value) if raw_value.isdigit() else raw_value
            policy_env_rows.append(f"| {namespace} | `{name}` | `{env_name}` | `{raw_value}` | {interpreted} |")

    lines.extend(
        [
            "",
            "Policy-related environment hints:",
            "| Namespace | CronJob | Env | Raw value | Interpreted value |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
    )
    lines.extend(policy_env_rows or ["| - | - | - | - | 관련 env 힌트 없음 |"])

    jobs = jobs_payload.get("items") if isinstance(jobs_payload, Mapping) else None
    recent_job_rows: list[dict[str, Any]] = []
    if isinstance(jobs, list):
        for job in jobs:
            if not isinstance(job, Mapping):
                continue
            metadata = job.get("metadata", {}) if isinstance(job.get("metadata"), Mapping) else {}
            status = job.get("status", {}) if isinstance(job.get("status"), Mapping) else {}
            namespace = str(metadata.get("namespace") or "")
            owner_name = "-"
            owners = metadata.get("ownerReferences", [])
            if isinstance(owners, list):
                for owner in owners:
                    if isinstance(owner, Mapping) and owner.get("kind") == "CronJob":
                        owner_name = str(owner.get("name") or "-")
                        break
            if (namespace, owner_name) not in matched_keys:
                continue

            created_at = str(metadata.get("creationTimestamp") or "")
            recent_job_rows.append(
                {
                    "namespace": namespace,
                    "name": str(metadata.get("name") or "unknown"),
                    "owner": owner_name,
                    "createdAt": created_at,
                    "startTime": str(status.get("startTime") or "-"),
                    "completionTime": str(status.get("completionTime") or "-"),
                    "succeeded": int(status.get("succeeded") or 0),
                    "failed": int(status.get("failed") or 0),
                    "active": int(status.get("active") or 0),
                    "createdSort": parse_rfc3339(created_at) or datetime.min.replace(tzinfo=UTC),
                }
            )

    lines.extend(
        [
            "",
            "Recent Jobs owned by matched CronJobs:",
            "| Namespace | Job | Owner CronJob | Created | Started | Completed | Succeeded | Failed | Active |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: |",
        ]
    )
    for row in sorted(recent_job_rows, key=lambda item: item["createdSort"], reverse=True)[:10]:
        lines.append(
            "| {namespace} | `{name}` | `{owner}` | {createdAt} | {startTime} | {completionTime} | "
            "{succeeded} | {failed} | {active} |".format(**row)
        )
    if not recent_job_rows:
        lines.append("| - | - | - | - | - | - | 0 | 0 | 0 |")

    return "\n".join(lines)


def build_ols_query(
    req: ChatRequest,
    image_analysis: str | None = None,
    *,
    policy: Mapping[str, Any] | None = None,
    subject: Mapping[str, Any] | None = None,
    gateway_evidence: str | None = None,
) -> str:
    page_context = normalize_console_page_context(req.pageContext)
    forwarded_to_ols = should_forward_image_attachments_to_ols()
    effective_policy = policy or classify_request_policy(req.message)
    subject_metadata = subject or safe_subject(None)
    query = f"""
[Gateway 보안 경계]
{build_gateway_guardrail(effective_policy)}

[Gateway 정책 결정]
{json.dumps(redact_sensitive(effective_policy), ensure_ascii=False)}

[API 서버 관찰 주체]
{json.dumps(redact_sensitive(subject_metadata), ensure_ascii=False)}

[사용자 질문]
{redact_sensitive(req.message)}

[현재 콘솔 컨텍스트]
{json.dumps(redact_sensitive(page_context), ensure_ascii=False)}

[첨부 이미지]
{build_attachment_context(req.attachments, redact_sensitive(image_analysis) if image_analysis else None, forwarded_to_ols=forwarded_to_ols)}

[Gateway 선조회 증거]
{redact_sensitive(gateway_evidence) if gateway_evidence else "Gateway 선조회 증거 없음"}

[CrashLoopBackOff 시연 답변 계약]
{crashloop_demo_prompt_answer_contract(req)}

이미지/화면 컨텍스트 처리:
- [첨부 이미지]가 `첨부 이미지 없음`이면 현재 콘솔 페이지의 스크린샷이나 이미지가 전달된 것이 아닙니다. 이 경우 답변에 "이미지를 직접 판독할 수 없다", "스크린샷을 볼 수 없다" 같은 문장을 쓰지 말고 [현재 콘솔 컨텍스트]의 `pathname`/`href`와 필요한 OpenShift 도구 조회 결과만 근거로 답하세요.
- [현재 콘솔 컨텍스트]는 URL, namespace, resource metadata입니다. 화면의 시각적 내용 자체라고 단정하지 말고, `/catalog/ns/<namespace>` 같은 경로가 있으면 "경로 기준으로는 Catalog 페이지로 보입니다"처럼 근거 범위를 분리하세요.
- [첨부 이미지]에 Gateway 비전 분석 결과가 없으면 이미지 내부 텍스트, 색상, 표 항목을 보았다고 말하지 마세요. 필요한 경우 이미지 첨부 또는 비전 분석 설정이 필요하다는 점을 별도 전제로만 짧게 표시하세요.

AIOps 리소스 원인분석 라우팅:
- 이 프롬프트에서 "Gateway"는 KOMSCO AI Gateway/BFF 보안 경계를 뜻합니다. 사용자가 Kubernetes Gateway API를 명시적으로 묻지 않았다면 `gateway.networking.k8s.io`, `Gateway`, `GatewayClass` 문서 링크를 추가하지 마세요.
- 사용자가 namespace와 리소스/워크로드 이름을 언급하고 "왜", "원인", "안 떠", "Pending", "CrashLoop", "ImagePull", "Ready", "Secret", "ConfigMap", "PVC", "HPA", "스케일", "지난주 이슈", "최근 운영 이슈"처럼 장애 원인 분석을 묻는 경우 active alert 조회를 우선하지 말고 해당 namespace의 Kubernetes 리소스 조회를 먼저 수행하세요.
- alert 조회는 사용자가 "경고", "alert", "알람"을 명시했거나, 리소스 상태 조회 후 관련 경고를 보강할 때 사용하세요. "활성 alert에 없음"은 HPA, Pod, PVC, Job 장애가 없다는 뜻이 아닙니다.
- HPA/스케일아웃 질문은 `HorizontalPodAutoscaler` 목록 또는 상세를 먼저 조회하고, `TARGETS`, `currentMetrics`, `desiredReplicas`, `currentReplicas`, `minReplicas`, `maxReplicas`, 관련 Deployment/Pod 상태를 근거로 설명하세요.
- Pod/Deployment/워크로드 이름이 주어졌지만 정확한 Pod 이름이 아니면 namespace의 Pod 목록을 먼저 조회하고, `metadata.name`, `labels.app`, ownerReferences가 질문 대상과 맞는 Pod를 선택해 상세 조회하세요.
- 사용자가 정확한 Pod 이름 또는 Pod 목록 evidence에 있는 Pod를 지목했다면, Gateway 선조회 Pod 요약만으로 원인/조치 계획을 끝내지 말고 `apiVersion: v1`, `kind: Pod`, `namespace`, `name` 상세를 조회하세요. command/args/env/image/ownerReferences/labels/events 근거가 필요한 질문에서는 상세 조회 결과가 없다는 점을 명시하고 일반론으로 단정하지 마세요.
- Pod 상세의 owner가 ReplicaSet이면 해당 ReplicaSet 상세를 조회해 상위 Deployment 이름을 확인하세요. Deployment 이름을 확인하지 못한 경우에는 추정한 Deployment 이름으로 조치 명령을 만들지 말고 owner chain 조회가 필요하다고 쓰세요.
- 사용자가 Pod 재시작, rollout restart, delete pod, scale 같은 변경 요청을 했지만 대상 namespace 또는 리소스 이름이 없으면 임의로 Gateway API나 다른 동음이의어 리소스로 해석하지 마세요. "대상 미지정"으로 표시하고 `namespace`, `Pod 또는 관리 객체 이름`, 장애 증상만 요청하세요.
- `CreateContainerConfigError`는 Pod의 `status.containerStatuses[*].state.waiting.message`, `envFrom.configMapRef`, `envFrom.secretRef`, volume secret/configMap 참조를 근거로 원인을 설명하세요. Secret 값은 조회하거나 출력하지 마세요.
- PVC/Pending 질문은 PVC 상세와 관련 Pod의 `volumes[*].persistentVolumeClaim`, `status.conditions`, 이벤트 메시지를 근거로 설명하고, 존재하지 않는 StorageClass/Provisioner/BindingMode를 구분하세요.
- namespace 전체의 "최근/지난주/운영 이슈" 요약 질문은 먼저 Pod 목록, HPA 목록, PVC 목록, Job 목록을 확인하고, 비정상 리소스의 대표 상세만 조회해 우선순위를 작성하세요. 최종 답변은 반드시 분석 요약과 조치 항목을 먼저 쓰고, 참고 링크만 단독으로 출력하지 마세요.

CronJob/Activity 분석 프로토콜:
- 사용자가 콘솔 Activity, 반복 실행, CronJob, Job, schedule, 특정 분 단위 주기를 묻는 경우에는 CronJob `spec.schedule`, `spec.concurrencyPolicy`, `successfulJobsHistoryLimit`, `failedJobsHistoryLimit`, container image, lifecycle/retention 관련 env, 최근 Job 실행 이력을 근거로 답하세요.
- `spec.schedule`에서 분 단위 interval이 확인되면 첫 문장에 "네, 설정상 의도된 <N>분 주기입니다"처럼 정상 여부를 먼저 명확히 답하세요.
- 이름만 보고 작업 목적을 단정하지 말고, env 이름에 hibernate/suspend/sleep/idle/delete/ttl/expire/cleanup/retention/prune/archive/max_age/timeout 같은 lifecycle/retention 신호가 확인된 경우에만 해당 정책으로 보인다고 쓰세요.
- 초 단위 env는 사람이 읽는 값으로 같이 풀어 쓰되 "기준값"으로만 표현하세요. 예: `1800`은 30분, `1209600`은 14일입니다. 로그나 소스 근거 없이 생성 후/마지막 사용 후/유휴 시간 기준인지 단정하지 마세요.
- `concurrencyPolicy: Forbid`는 이전 실행이 끝나지 않았을 때 중복 실행을 막는 설정으로 설명하고, `successfulJobsHistoryLimit`는 콘솔에 남는 성공 Job 이력 수를 설명할 때만 사용하세요.
- 실제로 어떤 리소스를 처리했는지는 CronJob 설정만으로 단정하지 말고 최근 Job 로그 확인이 필요하다고 분리하세요.
- 로그 확인 명령은 가능하면 `oc -n <namespace> logs job/<job-name>` 형태로 제시하고, 최근 Job 이름 확인 명령은 `oc -n <namespace> get jobs --sort-by=.metadata.creationTimestamp | grep <cronjob-name>` 형태를 우선 제시하세요.

Pod 상태/재시작 분석 프로토콜:
- Pod 상태 또는 재시작 이력 질문은 현재 상태와 과거 재시작 이력을 먼저 분리하세요. 현재 상태는 `status.phase`, `Ready` condition, `status.containerStatuses[*].ready`, `status.containerStatuses[*].state`를 기준으로 표현하세요.
- `restartCount`만 보고 현재 `CrashLoopBackOff`, "현재 진행 중", "지속 오류"라고 단정하지 마세요. 현재 `state.waiting.reason` 또는 `oc get pods` STATUS가 `CrashLoopBackOff`인 경우에만 현재 CrashLoopBackOff라고 쓰세요.
- `restartCount`는 Pod 단위가 아니라 container 단위입니다. 멀티컨테이너 Pod는 반드시 container 이름별로 `restartCount`, `lastState.terminated.reason`, `exitCode`, `finishedAt`, 현재 `state`를 구분해 쓰세요.
- `restartCount`는 누적 카운터입니다. 특정 시간 구간의 증가량이나 여러 종료 시각이 확인되지 않았다면 "빈번", "빈도", "계속 발생"이라고 표현하지 말고 "재시작 이력/누적 재시작 횟수"라고 쓰세요.
- `oc get pods -A --sort-by=.status.containerStatuses[0].restartCount`는 첫 번째 컨테이너 기준이라 멀티컨테이너 Pod의 재시작을 놓칠 수 있습니다. 가능하면 JSON 결과의 모든 `containerStatuses[*]`를 기준으로 상위 항목을 판단하세요.
- `Running` 및 `Ready=True`이면서 restartCount가 높은 Pod는 "현재 CrashLoop"가 아니라 "과거 또는 최근 재시작 이력/최근 복구됨"으로 표현하고, 마지막 종료 시각과 현재 startedAt을 같이 제시하세요.
- `status.phase=Failed`이고 현재 `state.terminated`인 Pod는 현재 재시작 중인 Pod가 아니라 종료된 Pod 객체일 수 있습니다. `startTime`, `finishedAt`, owner/controller/operator 상태를 함께 보고 "과거 실패 이력"과 "현재 장애"를 분리하세요.
- OpenShift 관리 namespace의 installer/revisioner/pruner 같은 단발성 작업 Pod가 Failed로 남아 있더라도 관련 ClusterOperator가 `Available=True`, `Degraded=False`, `Progressing=False`이면 현재 제어면 장애라고 단정하지 마세요. "과거 실패 Pod 이력, 현재 Operator 상태는 정상"처럼 표현하세요.
- `Last State`가 `Error`와 exit code만 제공되면 일반적인 원인을 나열하기 전에 `--previous` 로그 또는 이벤트 근거를 확인하세요. `exitCode=137`은 OOMKilled일 수 있지만 `reason`이 `OOMKilled`가 아니면 단정하지 말고 "강제 종료 가능성, 추가 확인 필요"로 표현하세요.
- 이전 종료 원인을 볼 때는 `oc logs <pod> -n <namespace> -c <container> --previous --tail=120`처럼 컨테이너명을 포함하세요. 단일 컨테이너 Pod도 컨테이너명을 명시하면 근거가 더 명확합니다.
- 우선순위는 1) 현재 `Pending`, `NotReady`, `CrashLoopBackOff`, `ImagePullBackOff` 등 비정상 상태, 2) 현재 Running/Ready지만 최근에 재시작된 컨테이너, 3) 오래된 재시작 이력 순으로 정리하세요.
- `ImagePullBackOff` 또는 `ErrImagePull`은 `status.containerStatuses[*].state.waiting.message`와 Events를 최우선 근거로 삼고, catalog/marketplace 성격의 Pod라면 관련 `CatalogSource` 상태와 image registry 접근성도 확인 항목에 포함하세요.
- 최종 답변 표에는 가능한 경우 `Namespace`, `Pod`, `Container`, `현재 상태`, `Ready`, `Restart Count`, `Last State/Exit`, `마지막 종료 시각`, `근거`를 포함하세요.

Pod 조치/복구 계획 프로토콜:
- Pod가 controller-owned이면 `metadata.ownerReferences`를 따라 관리 객체를 먼저 식별하세요. `Pod -> ReplicaSet -> Deployment` 관계가 확인되면 최종 관리 객체는 Deployment로 표현하고, 조치 명령에는 확인된 정확한 `deployment/<name>`을 사용하세요.
- 정확한 관리 객체 이름이 증거에 있는데 `<deployment-name>`, `<pod-name>` 같은 placeholder를 남기지 마세요. 이름이 없을 때만 조회 명령을 먼저 제시하세요.
- selector/label 기반 검증 명령도 placeholder로 남기지 마세요. Pod/Deployment 상세의 `metadata.labels` 또는 Deployment selector가 확인되면 `-l app=<value>`처럼 실제 값을 쓰고, label/selector가 확인되지 않았다면 `oc get pod -n <namespace> --show-labels`로 먼저 확인하라고 쓰세요.
- Deployment가 관리하는 Pod의 복구 계획에서 ReplicaSet 직접 수정은 권장하지 마세요. ReplicaSet은 현재 template의 산출물로 보고, 수정/롤백/rollout restart 대상은 상위 Deployment로 잡으세요.
- `spec.containers[*].command` 또는 `args`가 즉시 종료 명령, `exit`, 실패하는 헬스 체크용 명령, 명시적 예외 발생처럼 컨테이너 종료를 직접 유발하는 증거라면 원인을 "컨테이너 실행 명령/애플리케이션 프로세스가 즉시 종료됨"으로 우선 설명하세요. OOMKilled, probe 실패, 노드 문제 같은 일반 원인은 해당 field나 event 근거가 있을 때만 후보로 제시하세요.
- Pod spec의 command/args를 조회하지 못했다면 "실행 명령 오류가 확인됨"이라고 쓰지 말고 "확인 필요"로 표현하세요. 반대로 command/args가 확인되면 설정값/외부 서비스/DB 같은 일반 후보보다 그 값을 먼저 근거로 제시하세요.
- `CrashLoopBackOff`에서 단순 `oc delete pod` 또는 `oc rollout restart`는 template/image/config 문제가 그대로면 해결책이 아니라고 분리하세요. 영구 조치는 Deployment template의 command/image/env/config 수정 또는 정상 revision으로 rollback입니다.
- 사용자가 "조치 계획"을 요청하면 `원인 확인`, `수정 또는 rollback`, `rollout 검증`, `재발 방지 확인` 순서로 쓰고, 검증에는 `oc rollout status deployment/<name> -n <namespace>`와 selector 기반 `oc get pod` 확인을 포함하세요.
- 리소스 label/annotation/name에 test, e2e, scenario, sandbox, demo, sample 같은 비운영 신호가 있고 사용자의 문맥도 테스트/검증이면 "서비스 복구"와 별도로 "테스트 리소스 정리" 선택지를 제시하세요. 이때도 확인된 namespace와 관리 객체 이름을 사용하고, 특정 테스트 이름을 임의로 만들지 마세요.
- 로그가 이미 없거나 `--previous` 조회가 실패해도 Pod spec의 command/args, current state, lastState, events가 원인을 충분히 설명하면 그 근거를 우선 사용하세요. 로그 확인은 보조 검증으로만 표시하세요.

Deployment rollout/Pod 교체 판정 프로토콜:
- `replicas=2`, `Ready 2/2`, Pod 2개 존재, Pod Age만으로 "교체 완료", "rollout 완료", "새 Pod가 자리 잡음"이라고 쓰지 마세요. 이는 현재 가용성 증거일 뿐 실행/교체 증거가 아닙니다.
- rollout restart 실행 여부는 `spec.template.metadata.annotations["kubectl.kubernetes.io/restartedAt"]`, Deployment revision 증가, 새 ReplicaSet 생성 및 old/new ReplicaSet replica 전환, ExecutionRecord의 `mutation_succeeded`, 또는 질문 전에 수집한 Pod 이름과 현재 Pod 이름의 before/after 비교가 있을 때만 확인됐다고 쓰세요.
- 위 증거가 없고 현재 Pod가 질문 전부터 존재하던 동일 이름/동일 `pod-template-hash`라면 "아직 실행 전 또는 교체 증거 없음"으로 답하세요.
- 사용자가 "Pod가 교체됐는지" 물으면 현재 Pod 목록뿐 아니라 Deployment rollout evidence의 `RestartedAt`, `Revision`, `Recent ReplicaSets`, `Current Pods`를 근거로 판단하세요.
- 교체를 보여주기 위한 테스트 시나리오에서는 실행 전 Pod 이름과 실행 후 Pod 이름/hash/revision을 나란히 비교하세요.

OpenShift 경고 분석 프로토콜:
- 사용자가 "최근 경고", "alert", "우선 확인 항목"을 묻는 경우 먼저 active alert 목록을 조회하세요.
- 주요 alert별 상세 조사는 아래 순서를 따르세요. 해당 상세 조회가 실패하면 실패 사실과 이유를 답변에 포함하고, 확인하지 못한 원인은 추정으로만 표현하세요.
- 상태 표현은 엄격히 구분하세요.
  - "상세 확인됨": 관련 리소스 상세 조회를 수행했고, 답변에 쓰는 field path가 그 결과에 존재하는 경우에만 사용하세요.
  - "Alert 근거 확인": active alert의 labels/annotations만 근거로 삼은 경우에 사용하세요.
  - "추가 확인 필요": 상세 조회를 하지 않았거나 도구가 실패한 경우에 사용하세요.
- 상세 조회를 실제로 호출하지 않은 리소스의 `status.conditions`, `containerStatuses`, `events`, Secret/ConfigMap 존재 여부를 확인했다고 쓰지 마세요.
- KubePodNotReady:
  1. alert label의 namespace/pod 값으로 `resources_get`을 사용해 `apiVersion: v1`, `kind: Pod`, `namespace`, `name`을 조회하세요.
  2. Pod의 `status.conditions`, `status.containerStatuses[*].state.waiting.reason/message`, `spec.containers[*].image`, ownerReferences를 근거로 원인을 작성하세요.
  3. 이벤트 조회 도구가 있으면 해당 namespace/pod의 events도 조회하세요. 이벤트 도구가 없거나 실패하면 events는 추가 확인 명령으로만 제시하세요.
  4. container가 시작하지 못한 상태(ImagePullBackOff, ErrImagePull 등)이면 `oc logs`를 원인 확인의 첫 명령으로 제시하지 마세요.
- ClusterNotUpgradeable:
  1. `resources_get`으로 `apiVersion: config.openshift.io/v1`, `kind: ClusterVersion`, `name: version`을 조회하세요.
  2. `status.conditions[type=Upgradeable]`의 status/reason/message를 최우선 근거로 사용하세요.
  3. `ClusterOperator` 문제라고 쓰려면 ClusterOperator 상세나 요약에서 실제 Degraded/Unavailable/Progressing이 확인된 경우에만 그렇게 표현하세요.
- AlertmanagerReceiversNotConfigured:
  1. alert 결과만으로 ConfigMap 또는 Secret 이름을 만들어 조회하지 마세요.
  2. Secret 내용은 권한 또는 보안 정책상 직접 조회가 제한될 수 있으므로, 조회 시도 대신 "설정 리소스 확인은 권한상 제한될 수 있음"으로 표현하고 사용자가 확인할 안전한 명령을 제시하세요.
- etcdDatabaseHighFragmentationRatio:
  1. alert annotation의 비율/instance/pod를 근거로 설명하세요.
  2. defrag는 즉시 실행 지시가 아니라 상태 확인, 영향도 판단, 공식 절차 검토, 승인 후 수행으로 표현하세요.
- Watchdog:
  1. Alertmanager 경로 확인용 상시 경고로 분류하고 우선 조치 대상에서 제외하세요.

답변 지침:
- 최종 답변은 일반 문장 나열이 아니라 `## RCA 보고서` 형식으로 작성하세요.
- 가능한 경우 아래 섹션을 순서대로 포함하세요: `### 우선 판단`, `### 수집 근거`, `### 원인 후보`, `### 확인 불가`, `### 다음 확인 명령`, `### 우선순위`.
- 근거가 부족한 항목은 `확인 불가`에 넣고, 확인한 사실과 원인 후보를 섞지 마세요.
- 실시간 클러스터 상태(경고, 이벤트, Pod, Node, 리소스, 메트릭, 로그)가 필요한 질문이면 OpenShift MCP 도구를 먼저 사용하세요.
- 도구 결과에 없는 alert, pod, node, namespace, resource 이름이나 상태를 만들지 마세요.
- 도구를 사용할 수 없거나 결과가 부족하면 확인하지 못했다고 말하고 사용자가 확인할 명령을 제시하세요.
- 참고 링크는 사용자가 문서를 요청했거나 답변의 대상 리소스와 직접 관련된 경우에만 제시하세요. KOMSCO AI Gateway 보안 경계를 설명하면서 Kubernetes Gateway API 또는 GatewayClass 문서를 붙이지 마세요.
- 참고 링크가 필요한 경우에도 답변의 근거가 된 리소스/경고와 직접 관련된 문서만 1-2개로 제한하세요. Pod 상태 분석 답변 끝에 `Extension APIs`, `Admission plugins`, `TokenReview`, `ClusterRole`처럼 분석 대상과 무관한 API 색인 링크를 붙이지 마세요.
- alert 이름이나 summary만으로 원인을 단정하지 마세요. 원인, 영향, 조치 우선순위는 관련 리소스 상세 조회 결과가 있을 때만 "확인됨"으로 표현하세요.
- 도구 결과로 확인한 사실과 추가 확인이 필요한 추정을 분리해서 작성하세요. 최종 답변에는 각 주요 항목마다 "근거"를 짧게 포함하세요.
- 도구 실패나 권한 제한이 있으면 숨기지 말고 "조회 실패/권한 제한" 항목으로 짧게 표시하세요.
- 사용자가 실행 가능한 조치와 근거를 함께 제시하세요.
- Secret, token, password, private key는 절대 출력하지 마세요.
- etcd defrag, 리소스 삭제, 재시작, 설정 변경 같은 위험 작업은 "즉시 수행"으로 단정하지 말고 상태 확인, 영향 판단, 공식 절차 검토, 승인 후 수행 순서로 표현하세요.
- 대상이 특정되지 않은 재시작 요청에는 `oc get pods -A`를 기본 제안하지 마세요. 현재 콘솔 컨텍스트 namespace가 있으면 `oc get pods -n <namespace>`를 제시하고, namespace도 없으면 namespace와 Pod/Deployment/StatefulSet/DaemonSet 이름을 먼저 요청하세요.
- `oc delete pod`는 기본 재시작 방법으로 제시하지 마세요. ownerReferences, replica 수, PDB, 현재 rollout 상태를 확인했고 승인 단계가 있다는 조건을 명시한 경우에만 보조 선택지로 언급하세요. Deployment가 확인되면 승인 후 계획의 기본 후보는 `oc rollout restart deployment/<name> -n <namespace>`입니다.
- KubePodNotReady는 대상 Pod의 status.containerStatuses와 events를 확인하기 전까지 원인을 단정하지 마세요. container가 시작하지 못한 상태면 oc logs를 우선 명령으로 제시하지 말고 oc describe pod/events를 먼저 제시하세요.
- KubePodNotReady가 openshift-marketplace의 catalog Pod라면 이미지 풀, registry, CatalogSource/PackageManifest 영향 범위를 먼저 확인하고 일반 업무 서비스 장애로 단정하지 마세요.
- ClusterNotUpgradeable는 ClusterOperator 장애로 단정하지 마세요. ClusterVersion conditions 또는 oc adm upgrade 상당 결과의 reason/message를 확인하고, ClusterOperator가 실제 Degraded/Unavailable/Progressing일 때만 Operator 문제라고 표현하세요.
- AlertmanagerReceiversNotConfigured는 alert 결과만으로 특정 ConfigMap/Secret 이름을 만들지 말고, 권한상 직접 확인이 제한될 수 있음을 표시하세요.
- Watchdog alert는 Alertmanager 경로 확인용 상시 경고임을 설명하고 우선 조치 대상에서 제외하세요.
- Markdown은 GitHub Flavored Markdown으로 작성하고, 코드블록은 반드시 삼중 백틱으로 열고 삼중 백틱으로 닫으세요.
- 코드블록 안에는 실행 가능한 명령만 넣고, "Pod 로그 확인" 같은 설명 문장은 코드블록 밖에 작성하세요.
- OpenShift 관점에서 설명하세요.
"""
    return redact_sensitive(query)


async def analyze_image_attachments(
    attachments: list[ImageAttachment],
    user_message: str,
) -> str | None:
    if not attachments:
        return None

    config = get_vision_config()
    if not config:
        return None

    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"{VISION_SYSTEM_PROMPT}\n\n"
                f"User request: {user_message.strip() or 'Analyze the attached OpenShift image.'}"
            ),
        }
    ]
    for attachment in attachments:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{attachment.mimeType};base64,{attachment.data}",
                },
            }
        )

    headers = {"Content-Type": "application/json"}
    api_key = config.get("api_key")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": config["model"],
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
        "max_tokens": 800,
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0)) as client:
        response = await client.post(
            f"{config['base_url']}/chat/completions",
            headers=headers,
            json=payload,
        )
        if response.status_code >= 400:
            body = response.text[:500]
            return f"비전 분석 실패: provider returned HTTP {response.status_code}: {body}"

        result = response.json()

    choices = result.get("choices") if isinstance(result, Mapping) else None
    if not isinstance(choices, list) or not choices:
        return "비전 분석 실패: provider response did not include choices"

    first_choice = choices[0]
    if not isinstance(first_choice, Mapping):
        return "비전 분석 실패: provider response choice format is invalid"

    message = first_choice.get("message")
    if not isinstance(message, Mapping):
        return "비전 분석 실패: provider response message format is invalid"

    content_text = message.get("content")
    if isinstance(content_text, str) and content_text.strip():
        return content_text.strip()

    return "비전 분석 실패: provider response content is empty"


async def stream_with_heartbeats(
    events: AsyncIterator[dict[str, Any]],
    run_id: str,
) -> AsyncIterator[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any] | BaseException | None] = asyncio.Queue()
    started_at = time.monotonic()

    async def produce() -> None:
        try:
            async for event in events:
                await queue.put(event)
        except BaseException as exc:
            await queue.put(exc)
        finally:
            await queue.put(None)

    producer = asyncio.create_task(produce())

    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=RUN_HEARTBEAT_SECONDS)
            except TimeoutError:
                yield {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": "waiting",
                    "message": "Lightspeed 응답 스트림 대기 중",
                    "elapsedMs": int((time.monotonic() - started_at) * 1000),
                }
                continue

            if item is None:
                break

            if isinstance(item, BaseException):
                raise item

            yield item
    finally:
        if not producer.done():
            producer.cancel()


def update_ols_stream_status(
    status: str,
    *,
    context_digest: str = "",
    fallback_active: bool = False,
    reason: str = "",
) -> None:
    global OLS_STREAM_STATUS
    now = now_rfc3339()
    previous_started_at = str(OLS_STREAM_STATUS.get("lastStartedAt") or "")
    safe_reason = safe_error_text(reason, limit=500) if reason else ""
    OLS_STREAM_STATUS = {
        "streamProbe": status,
        "lastStatus": status,
        "lastContextDigest": context_digest,
        "lastStartedAt": now if status == "started" else previous_started_at,
        "lastCompletedAt": now if status in {"succeeded", "failed", "dev_echo", "not_configured"} else "",
        "lastError": safe_reason if status in {"failed", "not_configured", "dev_echo"} else "",
        "fallbackActive": fallback_active,
    }


async def call_ols_stream(
    user_auth_header: str,
    query: str,
    conversation_id: str | None,
    attachments: list[ImageAttachment],
    gateway_context: Mapping[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    context_digest = (
        str(gateway_context.get("metadata", {}).get("digest") or "")
        if isinstance(gateway_context, Mapping) and isinstance(gateway_context.get("metadata"), Mapping)
        else ""
    )
    if DEV_ECHO or not OLS_BASE_URL:
        fallback_status = "dev_echo" if DEV_ECHO else "not_configured"
        fallback_reason = "DEV_ECHO enabled" if DEV_ECHO else "OLS_BASE_URL is not configured"
        update_ols_stream_status(
            fallback_status,
            context_digest=context_digest,
            fallback_active=True,
            reason=fallback_reason,
        )
        yield {
            "type": "text",
            "content": "DEV_ECHO: Gateway is running. Configure OLS_BASE_URL for Lightspeed streaming.\n\n",
            "source": "gateway_fallback",
            "fallbackAnswer": True,
            "gatewayContextDigest": context_digest,
            "streamProbe": fallback_status,
        }
        yield {
            "type": "text",
            "content": query[:1200],
            "source": "gateway_fallback",
            "fallbackAnswer": True,
            "gatewayContextDigest": context_digest,
            "streamProbe": fallback_status,
        }
        yield {"type": "end", "conversationId": conversation_id}
        return

    payload = build_ols_payload(
        query,
        conversation_id,
        attachments,
        forward_image_attachments=should_forward_image_attachments_to_ols(),
        gateway_context=gateway_context,
    )
    update_ols_stream_status("started", context_digest=context_digest)

    try:
        async with httpx.AsyncClient(
            verify=OLS_CA_FILE,
            timeout=httpx.Timeout(300.0, connect=10.0),
        ) as client:
            async with client.stream(
                "POST",
                f"{OLS_BASE_URL}/v1/streaming_query",
                headers={
                    "Accept": "text/event-stream",
                    "Authorization": user_auth_header,
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    detail = body.decode("utf-8", errors="replace")
                    safe_detail = safe_error_text(detail, limit=1000)
                    update_ols_stream_status(
                        "failed",
                        context_digest=context_digest,
                        fallback_active=True,
                        reason=f"HTTP {response.status_code}: {safe_detail}",
                    )
                    raise HTTPException(status_code=response.status_code, detail=safe_detail)

                content_type = response.headers.get("content-type", "")
                if "text/event-stream" not in content_type:
                    async for event in split_plain_text_events(response.aiter_text()):
                        yield event
                    update_ols_stream_status("succeeded", context_digest=context_digest)
                    return

                buffer = ""
                async for chunk in response.aiter_text():
                    if not chunk:
                        continue

                    buffer += chunk
                    frames = buffer.split("\n\n")
                    buffer = frames.pop() or ""

                    for frame in frames:
                        data_lines = [
                            line[len("data:") :].strip()
                            for line in frame.splitlines()
                            if line.startswith("data:")
                        ]
                        if not data_lines:
                            continue

                        raw = "\n".join(data_lines)
                        if not raw or raw == "[DONE]":
                            continue

                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            tool_event = parse_tool_text_line(raw)
                            if tool_event:
                                yield tool_event
                            else:
                                yield {"type": "text", "content": raw}
                            continue

                        yield event

                if buffer.strip() and not buffer.lstrip().startswith("data:"):
                    async def iter_buffer() -> AsyncIterator[str]:
                        yield buffer

                    async for event in split_plain_text_events(iter_buffer()):
                        yield event
                update_ols_stream_status("succeeded", context_digest=context_digest)
    except Exception as exc:
        if OLS_STREAM_STATUS.get("lastStatus") != "failed":
            update_ols_stream_status(
                "failed",
                context_digest=context_digest,
                fallback_active=True,
                reason=safe_exception_text(exc),
            )
        raise


def normalize_ols_event(event: dict[str, Any]) -> dict[str, Any]:
    event_type = event.get("event") or event.get("type")

    if event_type == "text":
        normalized = {
            "type": "text",
            "content": event.get("data") or event.get("content") or "",
        }
        for key in ("fallbackAnswer", "gatewayContextDigest", "source", "streamProbe"):
            if key in event:
                normalized[key] = event[key]
        return normalized

    if event_type == "end":
        return {"type": "end", "conversationId": event.get("conversation_id")}

    if event_type in {"tool_call", "tool_result"}:
        if event.get("detail") is not None and event.get("summary") is not None:
            return event

        return normalize_tool_event(event_type, event)

    return event


def should_filter_gateway_api_references(message: str) -> bool:
    return not bool(EXPLICIT_KUBERNETES_GATEWAY_API_RE.search(message))


def should_filter_low_signal_references(message: str) -> bool:
    return not bool(EXPLICIT_OPENSHIFT_DOC_REFERENCE_RE.search(message))


def is_disallowed_gateway_api_reference(line: str) -> bool:
    return bool(DISALLOWED_GATEWAY_API_REFERENCE_RE.search(line))


def is_low_signal_reference(line: str) -> bool:
    return bool(LOW_SIGNAL_REFERENCE_RE.search(line))


class TextReferenceFilter:
    def __init__(
        self,
        *,
        filter_gateway_api_references: bool,
        filter_low_signal_references: bool = False,
        normalize_restart_language: bool = False,
    ) -> None:
        self.filter_gateway_api_references = filter_gateway_api_references
        self.filter_low_signal_references = filter_low_signal_references
        self.normalize_restart_language = normalize_restart_language
        self.pending = ""
        self.held_lines: list[str] = []

    def filter(self, content: str, *, final: bool = False) -> str:
        if (
            not self.filter_gateway_api_references
            and not self.filter_low_signal_references
            and not self.normalize_restart_language
        ):
            return content

        text = f"{self.pending}{content}"
        if final:
            complete = text
            self.pending = ""
        else:
            last_newline = text.rfind("\n")
            if last_newline == -1:
                self.pending = text
                return ""

            complete = text[: last_newline + 1]
            self.pending = text[last_newline + 1 :]

        if self.normalize_restart_language:
            complete = normalize_pod_restart_language(complete)

        lines = complete.splitlines(keepends=True)
        filtered_lines: list[str] = []
        for line in lines:
            if self.is_disallowed_reference(line):
                self.held_lines = []
                continue

            if self.held_lines:
                if not line.strip():
                    self.held_lines.append(line)
                    continue

                filtered_lines.extend(self.held_lines)
                self.held_lines = []

            if line.strip() == "---":
                self.held_lines = [line]
                continue

            filtered_lines.append(line)

        return "".join(filtered_lines)

    def is_disallowed_reference(self, line: str) -> bool:
        return (
            self.filter_gateway_api_references
            and is_disallowed_gateway_api_reference(line)
        ) or (
            self.filter_low_signal_references
            and is_low_signal_reference(line)
        )

    def flush(self) -> str:
        filtered = self.filter("", final=True)
        if self.held_lines:
            filtered = f"{filtered}{''.join(self.held_lines)}"
            self.held_lines = []
        return filtered


async def fetch_ocp_json(
    client: httpx.AsyncClient,
    path: str,
    authorization: str,
    *,
    required: bool = False,
) -> Mapping[str, Any] | None:
    response = await client.get(
        f"{OPENSHIFT_API_URL}{path}",
        headers={
            "Accept": "application/json",
            "Authorization": authorization,
        },
    )
    if response.status_code >= 400:
        if required:
            body = response.text[:500]
            raise HTTPException(
                status_code=response.status_code,
                detail=f"OpenShift API request failed for {path}: {body}",
            )

        return None

    payload = response.json()
    if isinstance(payload, Mapping):
        return payload

    return None


def crashloop_demo_target_from_request(req: ChatRequest) -> dict[str, str]:
    context = normalize_console_page_context(req.pageContext)
    demo_cycle = context.get("aiopsDemoCycle")
    if not isinstance(demo_cycle, Mapping) or demo_cycle.get("scenarioId") not in {
        "crashloop",
        "evidence-rca-scene",
    }:
        return {}

    target = demo_cycle.get("target")
    if not isinstance(target, Mapping):
        return {}

    kind = str(target.get("kind") or "")
    namespace = str(target.get("namespace") or "")
    name = str(target.get("name") or "")
    if kind.lower() != "pod" or not namespace or not name:
        return {}

    return {
        "kind": "Pod",
        "name": name,
        "namespace": namespace,
    }


def crashloop_demo_prompt_answer_contract(req: ChatRequest) -> str:
    target = crashloop_demo_target_from_request(req)
    if not target:
        return "적용 없음"

    return "\n".join(
        [
            "이 요청은 Ver.0.1.3 공식 Evidence 기반 Pod 재시작 RCA 시연 사이클입니다.",
            "최종 답변에는 아래 5개 섹션명을 이 순서 그대로 포함하세요.",
            "1. `### 확인된 근거`",
            "2. `### 가능한 원인 후보`",
            "3. `### 추가 확인 필요`",
            "4. `### Read-only 확인 순서`",
            "5. `### 금지 작업`",
            "로그 원문이나 Event message 원문을 출력하지 말고, 수집 여부/상태/digest 중심으로 말하세요.",
            "원인을 확정하지 말고 collected/partial/missing evidence에 맞춰 확인됨과 추정을 분리하세요.",
            "로그 분석은 `grep_tool`의 오류 패턴/digest 결과로 설명하고, 코드블록에 raw `oc logs` 덤프 명령을 넣지 마세요.",
            "공식 최종 답변에는 `RCA`, `즉시 조치`, `재발 방지책`, `참고 증적` 관점을 포함하세요.",
            "`oc apply/delete/patch/scale/exec/rollout restart/replace/create`는 코드블록에 넣지 말고 금지 작업 섹션에서만 언급하세요.",
        ]
    )


def container_status_rows(pod_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    status = pod_payload.get("status") if isinstance(pod_payload.get("status"), Mapping) else {}
    statuses = status.get("containerStatuses")
    rows: list[dict[str, Any]] = []
    for item in statuses if isinstance(statuses, list) else []:
        if not isinstance(item, Mapping):
            continue
        state = item.get("state") if isinstance(item.get("state"), Mapping) else {}
        waiting = state.get("waiting") if isinstance(state.get("waiting"), Mapping) else {}
        terminated = state.get("terminated") if isinstance(state.get("terminated"), Mapping) else {}
        last_state = item.get("lastState") if isinstance(item.get("lastState"), Mapping) else {}
        last_terminated = (
            last_state.get("terminated")
            if isinstance(last_state.get("terminated"), Mapping)
            else {}
        )
        rows.append(
            {
                "container": str(item.get("name") or "unknown"),
                "lastReason": str(last_terminated.get("reason") or ""),
                "ready": bool(item.get("ready")),
                "restartCount": int(item.get("restartCount") or 0),
                "stateReason": str(waiting.get("reason") or terminated.get("reason") or ""),
            }
        )
    return rows


def crashloop_container_name(pod_payload: Mapping[str, Any]) -> str:
    rows = container_status_rows(pod_payload)
    waiting_crashloop = [
        row
        for row in rows
        if "crashloop" in str(row.get("stateReason") or "").lower()
    ]
    if waiting_crashloop:
        return str(waiting_crashloop[0].get("container") or "")
    if rows:
        return str(sorted(rows, key=lambda row: int(row.get("restartCount") or 0), reverse=True)[0].get("container") or "")
    return ""


def summarize_pod_event_availability(events_payload: Mapping[str, Any] | None) -> tuple[str, int]:
    items = events_payload.get("items") if isinstance(events_payload, Mapping) else []
    warning_reasons: dict[str, int] = {}
    total = 0
    for event in items if isinstance(items, list) else []:
        if not isinstance(event, Mapping):
            continue
        total += 1
        if str(event.get("type") or "") != "Warning":
            continue
        reason = str(event.get("reason") or "Warning")
        warning_reasons[reason] = warning_reasons.get(reason, 0) + 1

    reason_summary = ", ".join(
        f"{reason}={count}"
        for reason, count in sorted(warning_reasons.items(), key=lambda item: (-item[1], item[0]))[:5]
    )
    if reason_summary:
        return f"events={total}; warningReasons={reason_summary}; raw event messages omitted", total
    return f"events={total}; warningReasons=none; raw event messages omitted", total


async def fetch_ocp_text_status(
    client: httpx.AsyncClient,
    path: str,
    authorization: str,
) -> dict[str, Any]:
    response = await client.get(
        f"{OPENSHIFT_API_URL}{path}",
        headers={
            "Accept": "text/plain",
            "Authorization": authorization,
        },
    )
    if response.status_code >= 400:
        return {
            "byteCount": 0,
            "httpStatus": response.status_code,
            "lineCount": 0,
            "reason": f"HTTP {response.status_code}",
            "status": "skipped",
        }
    return {
        "byteCount": len(response.content or b""),
        "httpStatus": response.status_code,
        "lineCount": len(response.text.splitlines()),
        "reason": "",
        "status": "success",
    }


def build_resource_access_review_request(resource_attributes: Mapping[str, Any]) -> dict[str, Any]:
    clean_attributes = {
        key: value
        for key, value in dict(resource_attributes).items()
        if value is not None and value != ""
    }
    return {
        "apiVersion": "authorization.k8s.io/v1",
        "kind": "SelfSubjectAccessReview",
        "spec": {"resourceAttributes": clean_attributes},
    }


async def fetch_resource_access_review(
    client: httpx.AsyncClient,
    user_auth_header: str,
    resource_attributes: Mapping[str, Any],
) -> dict[str, Any]:
    review_request = build_resource_access_review_request(resource_attributes)
    response = await client.post(
        f"{OPENSHIFT_API_URL}/apis/authorization.k8s.io/v1/selfsubjectaccessreviews",
        headers={
            "Accept": "application/json",
            "Authorization": user_auth_header,
            "Content-Type": "application/json",
        },
        json=review_request,
    )
    if response.status_code >= 400:
        return {
            "allowed": False,
            "evaluationError": safe_error_text(response.text, limit=300),
            "reason": f"SelfSubjectAccessReview failed with HTTP {response.status_code}",
            "resourceAttributes": review_request["spec"]["resourceAttributes"],
        }

    payload = response.json()
    status_payload = payload.get("status", {}) if isinstance(payload, Mapping) else {}
    status_map = status_payload if isinstance(status_payload, Mapping) else {}
    return {
        "allowed": bool(status_map.get("allowed")),
        "denied": bool(status_map.get("denied")),
        "evaluationError": status_map.get("evaluationError") or "",
        "reason": status_map.get("reason") or "",
        "resourceAttributes": review_request["spec"]["resourceAttributes"],
    }


async def fetch_crashloop_demo_access_reviews(
    client: httpx.AsyncClient,
    user_auth_header: str,
    target: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    namespace = str(target.get("namespace") or "")
    pod_name = str(target.get("name") or "")
    return {
        "eventsList": await fetch_resource_access_review(
            client,
            user_auth_header,
            {
                "namespace": namespace,
                "resource": "events",
                "verb": "list",
            },
        ),
        "podGet": await fetch_resource_access_review(
            client,
            user_auth_header,
            {
                "namespace": namespace,
                "name": pod_name,
                "resource": "pods",
                "verb": "get",
            },
        ),
        "podLogGet": await fetch_resource_access_review(
            client,
            user_auth_header,
            {
                "namespace": namespace,
                "name": pod_name,
                "resource": "pods",
                "subresource": "log",
                "verb": "get",
            },
        ),
    }


def crashloop_demo_skipped_evidence_events(
    *,
    request_id: str,
    target: Mapping[str, str],
    reason: str,
    detail: str = "",
) -> list[dict[str, Any]]:
    safe_detail = safe_error_text(detail or reason, limit=700)
    return [
        {
            "type": "tool_result",
            "detail": safe_detail,
            "evidenceType": "event",
            "id": f"{request_id}-crashloop-event-evidence",
            "missingReason": reason,
            "name": "crashloop_event_evidence",
            "sourcePath": "",
            "status": "skipped",
            "summary": "CrashLoop Event 증거 수집 생략",
            "target": dict(target),
        },
        {
            "type": "tool_result",
            "detail": safe_detail,
            "evidenceType": "pod_log",
            "id": f"{request_id}-crashloop-log-availability",
            "missingReason": reason,
            "name": "crashloop_log_availability",
            "sourcePath": "",
            "status": "skipped",
            "summary": "CrashLoop 이전 로그 가용성 확인 생략",
            "target": dict(target),
        },
        {
            "type": "tool_result",
            "detail": safe_detail,
            "evidenceType": "snapshot",
            "id": f"{request_id}-crashloop-pod-snapshot",
            "missingReason": reason,
            "name": "crashloop_pod_snapshot",
            "sourcePath": "",
            "status": "skipped",
            "summary": "CrashLoop Pod snapshot 증거 수집 생략",
            "target": dict(target),
        },
    ]


async def collect_crashloop_demo_evidence_events(
    user_auth_header: str,
    target: Mapping[str, str],
    request_id: str,
) -> list[dict[str, Any]]:
    if not OPENSHIFT_API_URL:
        return [
            {
                "type": "tool_result",
                "detail": "CrashLoop event evidence unavailable: OPENSHIFT_API_URL is not configured.",
                "evidenceType": "event",
                "id": f"{request_id}-crashloop-event-evidence",
                "missingReason": "OPENSHIFT_API_URL is not configured",
                "name": "crashloop_event_evidence",
                "sourcePath": "",
                "status": "skipped",
                "summary": "CrashLoop Event 증거 수집 생략",
            },
            {
                "type": "tool_result",
                "detail": "CrashLoop previous log availability unavailable: OPENSHIFT_API_URL is not configured.",
                "evidenceType": "pod_log",
                "id": f"{request_id}-crashloop-log-availability",
                "missingReason": "OPENSHIFT_API_URL is not configured",
                "name": "crashloop_log_availability",
                "sourcePath": "",
                "status": "skipped",
                "summary": "CrashLoop 이전 로그 가용성 확인 생략",
            },
            {
                "type": "tool_result",
                "detail": "CrashLoop Pod snapshot unavailable: OPENSHIFT_API_URL is not configured.",
                "evidenceType": "snapshot",
                "id": f"{request_id}-crashloop-pod-snapshot",
                "missingReason": "OPENSHIFT_API_URL is not configured",
                "name": "crashloop_pod_snapshot",
                "sourcePath": "",
                "status": "skipped",
                "summary": "CrashLoop Pod snapshot 증거 수집 생략",
            },
        ]

    namespace = str(target.get("namespace") or "")
    pod_name = str(target.get("name") or "")
    if not namespace or not pod_name:
        return crashloop_demo_skipped_evidence_events(
            request_id=request_id,
            target=target,
            reason="CrashLoop demo target is incomplete.",
        )

    if namespace not in DEMO_NAMESPACE_ALLOWLIST:
        return crashloop_demo_skipped_evidence_events(
            request_id=request_id,
            target=target,
            reason=f"Namespace {namespace} is not allowlisted for CrashLoop demo evidence collection.",
            detail=json.dumps(
                {
                    "allowlist": sorted(DEMO_NAMESPACE_ALLOWLIST),
                    "namespace": namespace,
                    "target": dict(target),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )

    pod_path = f"/api/v1/namespaces/{path_segment(namespace)}/pods/{path_segment(pod_name)}"
    events_path = (
        f"/api/v1/namespaces/{path_segment(namespace)}/events"
        f"?fieldSelector=involvedObject.name={path_segment(pod_name)}&limit=50"
    )

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        access_reviews = await fetch_crashloop_demo_access_reviews(client, user_auth_header, target)
        denied_reviews = {
            key: value
            for key, value in access_reviews.items()
            if value.get("allowed") is not True
        }
        if denied_reviews:
            return crashloop_demo_skipped_evidence_events(
                request_id=request_id,
                target=target,
                reason="Exact SelfSubjectAccessReview denied CrashLoop demo evidence collection.",
                detail=json.dumps(
                    {
                        "deniedReviews": redact_sensitive(denied_reviews),
                        "target": dict(target),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )

        pod_payload = await fetch_ocp_json(client, pod_path, user_auth_header)
        events_payload = await fetch_ocp_json(client, events_path, user_auth_header)
        container_name = crashloop_container_name(pod_payload or {})
        log_path = (
            f"/api/v1/namespaces/{path_segment(namespace)}/pods/{path_segment(pod_name)}/log"
            f"?previous=true&tailLines=1&limitBytes=1"
        )
        if container_name:
            log_path = f"{log_path}&container={path_segment(container_name)}"
        log_status = await fetch_ocp_text_status(client, log_path, user_auth_header)

    container_rows = container_status_rows(pod_payload or {})
    event_summary, event_count = summarize_pod_event_availability(events_payload)
    event_status = "success" if events_payload is not None else "skipped"
    event_missing = "" if event_status == "success" else "Pod-specific events were not returned by Kubernetes API."
    log_probe_status = str(log_status.get("status") or "skipped")
    log_evidence_status = "partial"
    log_missing = (
        "availability checked only; raw logs intentionally withheld"
        if log_probe_status == "success"
        else (
            "previous log endpoint probe did not return log content; "
            f"raw logs intentionally withheld; probeStatus={log_status.get('reason') or 'unknown'}"
        )
    )
    pod_summary = {
        "containers": container_rows,
        "phase": str((pod_payload or {}).get("status", {}).get("phase") or "Unknown")
        if isinstance((pod_payload or {}).get("status"), Mapping)
        else "Unknown",
        "target": dict(target),
    }
    return [
        {
            "type": "tool_result",
            "detail": safe_error_text(
                json.dumps(
                    {
                        "eventAvailability": event_summary,
                        "eventCount": event_count,
                        "pod": pod_summary,
                        "rawEventMessages": "omitted",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                limit=1200,
            ),
            "evidenceType": "event",
            "id": f"{request_id}-crashloop-event-evidence",
            "missingReason": event_missing,
            "name": "crashloop_event_evidence",
            "sourcePath": events_path,
            "status": event_status,
            "summary": _evidence_summary("CrashLoop Pod Event 증거", event_status),
        },
        {
            "type": "tool_result",
            "detail": safe_error_text(
                json.dumps(
                    {
                        "byteCount": log_status.get("byteCount"),
                        "container": container_name,
                        "httpStatus": log_status.get("httpStatus"),
                        "lineCount": log_status.get("lineCount"),
                        "probeLimitBytes": 1,
                        "rawLogDisclosure": False,
                        "target": dict(target),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                limit=1200,
            ),
            "evidenceType": "pod_log",
            "id": f"{request_id}-crashloop-log-availability",
            "missingReason": log_missing,
            "name": "crashloop_log_availability",
            "sourcePath": log_path,
            "status": log_evidence_status,
            "summary": _evidence_summary("CrashLoop 이전 로그 가용성", log_evidence_status),
        },
        {
            "type": "tool_result",
            "detail": safe_error_text(
                json.dumps(
                    {
                        "pod": pod_summary,
                        "snapshotSource": "pod.status.containerStatuses",
                        "target": dict(target),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                limit=1200,
            ),
            "evidenceType": "snapshot",
            "id": f"{request_id}-crashloop-pod-snapshot",
            "missingReason": "" if pod_payload is not None else "Pod payload was not returned by Kubernetes API.",
            "name": "crashloop_pod_snapshot",
            "sourcePath": pod_path,
            "status": "success" if pod_payload is not None else "skipped",
            "summary": _evidence_summary(
                "CrashLoop Pod snapshot 증거",
                "success" if pod_payload is not None else "skipped",
            ),
        },
    ]


def official_namespace_restart_namespace(runtime_tool_plan: Mapping[str, Any] | None) -> str:
    if not isinstance(runtime_tool_plan, Mapping):
        return ""
    if str(runtime_tool_plan.get("task_type") or "") != "pod_restart_rca":
        return ""
    target = runtime_tool_plan.get("target")
    if not isinstance(target, Mapping):
        return ""
    namespace = str(target.get("namespace") or "").strip()
    if not namespace or namespace == "all-accessible-namespaces":
        return ""
    return namespace


def namespace_restart_candidate_rows(
    pods_payload: Mapping[str, Any] | None,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pod in resource_items(pods_payload):
        container_rows = container_status_rows(pod)
        restart_count = sum(int(row.get("restartCount") or 0) for row in container_rows)
        reasons = sorted(
            {
                str(row.get("stateReason") or row.get("lastReason") or "")
                for row in container_rows
                if row.get("stateReason") or row.get("lastReason")
            }
        )
        status = pod.get("status") if isinstance(pod.get("status"), Mapping) else {}
        phase = str(status.get("phase") or "Unknown")
        if restart_count <= 0 and not reasons and phase in {"Running", "Succeeded"}:
            continue
        rows.append(
            {
                "containers": container_rows[:4],
                "name": metadata_name(pod),
                "namespace": metadata_namespace(pod),
                "phase": phase,
                "restartCount": restart_count,
                "stateReasons": reasons,
            }
        )

    return sorted(
        rows,
        key=lambda row: (-int(row.get("restartCount") or 0), str(row.get("name") or "")),
    )[:limit]


def summarize_namespace_restart_events(
    events_payload: Mapping[str, Any] | None,
    *,
    candidate_names: set[str],
) -> dict[str, Any]:
    items = resource_items(events_payload)
    warning_reasons: dict[str, int] = {}
    candidate_hits: dict[str, int] = {}
    involved_kinds: dict[str, int] = {}
    restart_reason_hints = {"BackOff", "Killing", "OOMKilled", "Evicted", "Unhealthy", "Failed"}

    for event in items:
        involved = event.get("involvedObject") if isinstance(event.get("involvedObject"), Mapping) else {}
        involved_name = str(involved.get("name") or "")
        involved_kind = str(involved.get("kind") or "unknown")
        if involved_kind:
            involved_kinds[involved_kind] = involved_kinds.get(involved_kind, 0) + 1
        if candidate_names and involved_name in candidate_names:
            candidate_hits[involved_name] = candidate_hits.get(involved_name, 0) + 1
        if str(event.get("type") or "") != "Warning":
            continue
        reason = str(event.get("reason") or "Warning")
        warning_reasons[reason] = warning_reasons.get(reason, 0) + 1

    restart_hints = {
        reason: count
        for reason, count in warning_reasons.items()
        if reason in restart_reason_hints or "back" in reason.lower() or "kill" in reason.lower()
    }
    return {
        "candidateEventHits": dict(sorted(candidate_hits.items())[:8]),
        "eventCount": len(items),
        "involvedKinds": dict(sorted(involved_kinds.items())[:8]),
        "rawEventMessages": "omitted",
        "restartReasonHints": dict(sorted(restart_hints.items(), key=lambda item: (-item[1], item[0]))[:8]),
        "warningReasons": dict(sorted(warning_reasons.items(), key=lambda item: (-item[1], item[0]))[:8]),
    }


async def fetch_ocp_log_pattern_probe(
    client: httpx.AsyncClient,
    path: str,
    authorization: str,
) -> dict[str, Any]:
    response = await client.get(
        f"{OPENSHIFT_API_URL}{path}",
        headers={
            "Accept": "text/plain",
            "Authorization": authorization,
        },
    )
    if response.status_code >= 400:
        return {
            "byteCount": 0,
            "httpStatus": response.status_code,
            "lineCount": 0,
            "matchedPatternIds": [],
            "patternCounts": {},
            "rawLogDisclosure": False,
            "reason": f"HTTP {response.status_code}",
            "status": "skipped",
        }

    text = response.text or ""
    patterns = {
        "Back-off": r"back[- ]off|crashloopbackoff",
        "Exception": r"exception|traceback|panic|error|failed",
        "OOMKilled": r"oomkilled|out of memory|killed process",
    }
    counts = {
        name: len(re.findall(pattern, text, flags=re.IGNORECASE))
        for name, pattern in patterns.items()
    }
    return {
        "byteCount": len(response.content or b""),
        "httpStatus": response.status_code,
        "lineCount": len(text.splitlines()),
        "matchedPatternIds": [name for name, count in counts.items() if count > 0],
        "patternCounts": counts,
        "rawLogDisclosure": False,
        "reason": "",
        "status": "success",
    }


def official_namespace_restart_skipped_evidence_events(
    *,
    namespace: str,
    request_id: str,
    reason: str,
    detail: str = "",
) -> list[dict[str, Any]]:
    safe_detail = safe_error_text(detail or reason, limit=900)
    target = {"kind": "Namespace", "namespace": namespace}
    return [
        {
            "type": "tool_result",
            "detail": safe_detail,
            "evidenceType": "event",
            "id": f"{request_id}-official-namespace-restart-events",
            "missingReason": reason,
            "name": "official_namespace_restart_event_evidence",
            "sourcePath": "",
            "status": "skipped",
            "summary": "공식 Pod 재시작 namespace Event 증거 수집 생략",
            "target": target,
        },
        {
            "type": "tool_result",
            "detail": safe_detail,
            "evidenceType": "snapshot",
            "id": f"{request_id}-official-namespace-restart-snapshot",
            "missingReason": reason,
            "name": "official_namespace_restart_snapshot",
            "sourcePath": "",
            "status": "skipped",
            "summary": "공식 Pod 재시작 namespace snapshot 증거 수집 생략",
            "target": target,
        },
        {
            "type": "tool_result",
            "detail": safe_detail,
            "evidenceType": "pod_log",
            "id": f"{request_id}-official-namespace-restart-log-patterns",
            "missingReason": reason,
            "name": "official_namespace_restart_log_pattern_probe",
            "sourcePath": "",
            "status": "skipped",
            "summary": "공식 Pod 재시작 log pattern 증거 수집 생략",
            "target": target,
        },
    ]


async def collect_official_namespace_restart_evidence_events(
    user_auth_header: str,
    namespace: str,
    request_id: str,
) -> list[dict[str, Any]]:
    namespace = namespace.strip()
    if not OPENSHIFT_API_URL:
        return official_namespace_restart_skipped_evidence_events(
            namespace=namespace,
            request_id=request_id,
            reason="OPENSHIFT_API_URL is not configured",
        )
    if not namespace:
        return official_namespace_restart_skipped_evidence_events(
            namespace=namespace,
            request_id=request_id,
            reason="namespace target is empty",
        )
    if namespace not in DEMO_NAMESPACE_ALLOWLIST:
        return official_namespace_restart_skipped_evidence_events(
            namespace=namespace,
            request_id=request_id,
            reason=f"Namespace {namespace} is not allowlisted for official Evidence RCA collection.",
            detail=json.dumps(
                {"allowlist": sorted(DEMO_NAMESPACE_ALLOWLIST), "namespace": namespace},
                ensure_ascii=False,
                sort_keys=True,
            ),
        )

    pods_path = f"/api/v1/namespaces/{path_segment(namespace)}/pods?limit=200"
    events_path = f"/api/v1/namespaces/{path_segment(namespace)}/events?limit=200"
    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        access_reviews = {
            "eventsList": await fetch_resource_access_review(
                client,
                user_auth_header,
                {"namespace": namespace, "resource": "events", "verb": "list"},
            ),
            "podsList": await fetch_resource_access_review(
                client,
                user_auth_header,
                {"namespace": namespace, "resource": "pods", "verb": "list"},
            ),
        }
        denied_reviews = {
            key: value
            for key, value in access_reviews.items()
            if value.get("allowed") is not True
        }
        if denied_reviews:
            return official_namespace_restart_skipped_evidence_events(
                namespace=namespace,
                request_id=request_id,
                reason="SelfSubjectAccessReview denied namespace Evidence RCA collection.",
                detail=json.dumps(
                    {"deniedReviews": redact_sensitive(denied_reviews), "namespace": namespace},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )

        pods_payload = await fetch_ocp_json(client, pods_path, user_auth_header)
        events_payload = await fetch_ocp_json(client, events_path, user_auth_header)
        candidates = namespace_restart_candidate_rows(pods_payload)
        top_candidate = candidates[0] if candidates else {}
        container_name = ""
        log_probe: dict[str, Any] = {
            "byteCount": 0,
            "lineCount": 0,
            "matchedPatternIds": [],
            "patternCounts": {},
            "rawLogDisclosure": False,
            "reason": "No restart candidate pod found in namespace snapshot.",
            "status": "skipped",
        }
        log_path = ""
        if top_candidate.get("name"):
            pod_payload = next(
                (
                    pod
                    for pod in resource_items(pods_payload)
                    if metadata_name(pod) == top_candidate.get("name")
                ),
                {},
            )
            container_name = crashloop_container_name(pod_payload)
            log_path = (
                f"/api/v1/namespaces/{path_segment(namespace)}/pods/"
                f"{path_segment(str(top_candidate.get('name') or ''))}/log"
                "?previous=true&tailLines=80&limitBytes=20000"
            )
            if container_name:
                log_path = f"{log_path}&container={path_segment(container_name)}"
            log_probe = await fetch_ocp_log_pattern_probe(client, log_path, user_auth_header)

    candidate_names = {str(candidate.get("name") or "") for candidate in candidates if candidate.get("name")}
    event_summary = summarize_namespace_restart_events(events_payload, candidate_names=candidate_names)
    event_status = "success" if events_payload is not None else "skipped"
    snapshot_status = "success" if pods_payload is not None else "skipped"
    log_status = "partial" if log_probe.get("status") == "success" else "skipped"
    log_missing = (
        "raw logs withheld; pattern probe executed"
        if log_probe.get("status") == "success"
        else str(log_probe.get("reason") or "Pod previous log pattern probe did not run")
    )

    return [
        {
            "type": "tool_result",
            "detail": safe_error_text(
                json.dumps(
                    {
                        "namespace": namespace,
                        "summary": event_summary,
                        "targetCandidateNames": sorted(candidate_names),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                limit=1600,
            ),
            "evidenceType": "event",
            "id": f"{request_id}-official-namespace-restart-events",
            "missingReason": "" if event_status == "success" else "Namespace events were not returned by Kubernetes API.",
            "name": "official_namespace_restart_event_evidence",
            "sourcePath": events_path,
            "status": event_status,
            "summary": _evidence_summary("공식 Pod 재시작 namespace Event 증거", event_status),
        },
        {
            "type": "tool_result",
            "detail": safe_error_text(
                json.dumps(
                    {
                        "candidatePods": candidates,
                        "namespace": namespace,
                        "snapshotSource": "namespace pods.status.containerStatuses",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                limit=1600,
            ),
            "evidenceType": "snapshot",
            "id": f"{request_id}-official-namespace-restart-snapshot",
            "missingReason": "" if snapshot_status == "success" else "Namespace pods were not returned by Kubernetes API.",
            "name": "official_namespace_restart_snapshot",
            "sourcePath": pods_path,
            "status": snapshot_status,
            "summary": _evidence_summary("공식 Pod 재시작 namespace snapshot 증거", snapshot_status),
        },
        {
            "type": "tool_result",
            "detail": safe_error_text(
                json.dumps(
                    {
                        "container": container_name,
                        "namespace": namespace,
                        "probe": log_probe,
                        "rawLogDisclosure": False,
                        "targetPod": top_candidate.get("name") or "",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                limit=1600,
            ),
            "evidenceType": "pod_log",
            "id": f"{request_id}-official-namespace-restart-log-patterns",
            "lineCount": log_probe.get("lineCount"),
            "matchedPatternIds": log_probe.get("matchedPatternIds"),
            "missingReason": log_missing,
            "name": "official_namespace_restart_log_pattern_probe",
            "patternCounts": log_probe.get("patternCounts"),
            "rawLogDisclosure": False,
            "sourcePath": log_path,
            "status": log_status,
            "summary": _evidence_summary("공식 Pod 재시작 log pattern 증거", log_status),
        },
    ]


async def collect_pod_status_evidence(
    user_auth_header: str,
    *,
    include_pod_list: bool = False,
    list_namespace: str = "",
) -> str:
    if not OPENSHIFT_API_URL:
        return "Pod status evidence unavailable: OPENSHIFT_API_URL is not configured."

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        pods_payload = await fetch_ocp_json(client, "/api/v1/pods", user_auth_header)
        deployments_payload = await fetch_ocp_json(
            client,
            "/apis/apps/v1/deployments",
            user_auth_header,
        )
        replicasets_payload = await fetch_ocp_json(
            client,
            "/apis/apps/v1/replicasets",
            user_auth_header,
        )
        cluster_operators_payload = await fetch_ocp_json(
            client,
            "/apis/config.openshift.io/v1/clusteroperators",
            user_auth_header,
        )

    if not pods_payload:
        return (
            "Pod status evidence unavailable: Kubernetes API pod list was not returned. "
            "This may be a permission or API availability issue."
        )

    evidence = build_pod_status_evidence(
        pods_payload,
        replicasets_payload,
        include_pod_list=include_pod_list,
        list_namespace=list_namespace,
    )
    if deployments_payload:
        evidence = append_gateway_evidence(
            evidence,
            build_deployment_rollout_evidence(deployments_payload, replicasets_payload, pods_payload),
        )
    if cluster_operators_payload:
        evidence = append_gateway_evidence(
            evidence,
            build_cluster_operator_status_evidence(cluster_operators_payload),
        )

    return evidence


async def collect_pod_count_investigation(
    user_auth_header: str,
    query: Mapping[str, str],
) -> dict[str, Any]:
    namespace = str(query.get("namespace") or "")
    if not OPENSHIFT_API_URL:
        return {
            "namespace": namespace,
            "reason": "OPENSHIFT_API_URL is not configured",
            "status": "unavailable",
            "targetName": str(query.get("targetName") or ""),
        }

    if namespace:
        deployments_path = f"/apis/apps/v1/namespaces/{path_segment(namespace)}/deployments"
        pods_path = f"/api/v1/namespaces/{path_segment(namespace)}/pods"
    else:
        deployments_path = "/apis/apps/v1/deployments"
        pods_path = "/api/v1/pods"

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        deployments_payload = await fetch_ocp_json(client, deployments_path, user_auth_header)
        pods_payload = await fetch_ocp_json(client, pods_path, user_auth_header)

    if not pods_payload:
        return {
            "namespace": namespace,
            "reason": f"Kubernetes API pod list was not returned for {pods_path}",
            "status": "unavailable",
            "targetName": str(query.get("targetName") or ""),
        }

    return build_pod_count_investigation(query, deployments_payload, pods_payload)


async def collect_cronjob_activity_evidence(user_auth_header: str, context_text: str) -> str:
    if not OPENSHIFT_API_URL:
        return "CronJob activity evidence unavailable: OPENSHIFT_API_URL is not configured."

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        cronjobs_payload = await fetch_ocp_json(client, "/apis/batch/v1/cronjobs", user_auth_header)
        jobs_payload = await fetch_ocp_json(client, "/apis/batch/v1/jobs?limit=500", user_auth_header)

    if not cronjobs_payload:
        return (
            "CronJob activity evidence unavailable: Kubernetes API CronJob list was not returned. "
            "This may be a permission or API availability issue."
        )

    return build_cronjob_activity_evidence(
        cronjobs_payload,
        jobs_payload,
        context_text=context_text,
    )


def _data_source_event_status(source: Mapping[str, Any] | None) -> str:
    status = str((source or {}).get("status") or "unavailable").lower()
    if status == "available":
        return "success"
    if status == "partial":
        return "partial"
    if status == "error":
        return "error"
    return "skipped"


def _evidence_summary(label: str, status: str) -> str:
    if status == "success":
        return f"{label} 수집 완료"
    if status == "partial":
        return f"{label} 부분 수집"
    return f"{label} 수집 불가"


async def _monitoring_urls_for_rca(user_auth_header: str) -> tuple[dict[str, str], dict[str, Any]]:
    if not OPENSHIFT_API_URL:
        return {}, data_source_status(
            label="Monitoring public URLs",
            name="monitoring-shared-config",
            path="/api/v1/namespaces/openshift-config-managed/configmaps/monitoring-shared-config",
            reason="OPENSHIFT_API_URL is not configured.",
            status="unavailable",
        )

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        monitoring_config_payload, monitoring_config_status = await fetch_ocp_json_observed(
            client,
            "/api/v1/namespaces/openshift-config-managed/configmaps/monitoring-shared-config",
            user_auth_header,
            label="Monitoring public URLs",
            name="monitoring-shared-config",
        )

    return monitoring_urls_from_config(monitoring_config_payload), monitoring_config_status


async def collect_node_status_rca_evidence(user_auth_header: str) -> dict[str, Any]:
    source_path = "/api/v1/nodes"
    metrics_path = "/apis/metrics.k8s.io/v1beta1/nodes"
    if not OPENSHIFT_API_URL:
        reason = "OPENSHIFT_API_URL is not configured."
        return {
            "detail": f"Node status evidence unavailable: {reason}",
            "evidenceType": "node",
            "missingReason": reason,
            "sourcePath": source_path,
            "status": "skipped",
            "summary": _evidence_summary("Node 상태 RCA 증거", "skipped"),
        }

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        nodes_payload, nodes_status = await fetch_ocp_json_observed(
            client,
            source_path,
            user_auth_header,
            label="RCA Node status",
            name="nodes",
            required=True,
        )
        node_metrics_payload, metrics_status = await fetch_ocp_json_observed(
            client,
            metrics_path,
            user_auth_header,
            label="RCA Node metrics",
            name="metrics.k8s.io",
        )

    if not nodes_payload:
        reason = safe_error_text(nodes_status.get("reason") or "Kubernetes API node list was not returned.")
        status = _data_source_event_status(nodes_status)
        return {
            "detail": f"Node status evidence unavailable: {reason}",
            "evidenceType": "node",
            "missingReason": reason,
            "sourcePath": source_path,
            "status": status,
            "summary": _evidence_summary("Node 상태 RCA 증거", status),
        }

    metrics_event_status = _data_source_event_status(metrics_status)
    status = "partial" if metrics_event_status != "success" else "success"
    detail = build_node_status_rca_evidence(
        nodes_payload,
        node_metrics_payload,
        metrics_status=metrics_status,
    )
    return {
        "detail": detail,
        "evidenceType": "node",
        "missingReason": safe_error_text(metrics_status.get("reason") or "", limit=240)
        if status == "partial"
        else "",
        "sourcePath": f"{source_path},{metrics_path}",
        "status": status,
        "summary": _evidence_summary("Node 상태 RCA 증거", status),
    }


async def collect_active_alerts_rca_evidence(user_auth_header: str) -> dict[str, Any]:
    monitoring_urls, monitoring_status = await _monitoring_urls_for_rca(user_auth_header)
    alerts_probe = await query_thanos_instant(
        monitoring_urls.get("thanos", ""),
        user_auth_header,
        'ALERTS{alertstate="firing"}',
    )
    status = rca_probe_event_status(alerts_probe)
    detail = build_active_alerts_rca_evidence(alerts_probe)
    if status == "skipped" and _data_source_event_status(monitoring_status) == "error":
        status = "error"
    reason = _prometheus_probe_reason(alerts_probe)
    return {
        "detail": detail,
        "evidenceType": "alert",
        "missingReason": reason if status != "success" else "",
        "sourcePath": '/api/v1/query?query=ALERTS{alertstate="firing"}',
        "status": status,
        "summary": _evidence_summary("Active Alert RCA 증거", status),
    }


async def collect_restart_metric_rca_evidence(user_auth_header: str) -> dict[str, Any]:
    query = "increase(kube_pod_container_status_restarts_total[1h]) > 0"
    monitoring_urls, monitoring_status = await _monitoring_urls_for_rca(user_auth_header)
    restart_probe = await query_thanos_instant(
        monitoring_urls.get("thanos", ""),
        user_auth_header,
        query,
    )
    status = rca_probe_event_status(restart_probe)
    detail = build_restart_metric_rca_evidence(restart_probe)
    if status == "skipped" and _data_source_event_status(monitoring_status) == "error":
        status = "error"
    reason = _prometheus_probe_reason(restart_probe)
    return {
        "detail": detail,
        "evidenceType": "metric",
        "missingReason": reason if status != "success" else "",
        "sourcePath": f"/api/v1/query?query={query}",
        "status": status,
        "summary": _evidence_summary("Restart metric RCA 증거", status),
    }


def log_audit_record(record: Mapping[str, Any]) -> None:
    safe_record = redact_sensitive(dict(record))
    audit_id = str(safe_record.get("auditId") or f"audit-{uuid.uuid4().hex[:16]}")
    bounded_put(AUDIT_RECORDS, audit_id, safe_record, AUDIT_MAX_RECORDS)
    increment_metric("aiops_audit_records_total")
    print(
        json.dumps({"aiopsAudit": safe_record}, ensure_ascii=False),
        flush=True,
    )


def log_break_glass_audit_record(record: Mapping[str, Any]) -> None:
    print(
        json.dumps({"aiopsBreakGlassAudit": redact_sensitive(dict(record))}, ensure_ascii=False),
        flush=True,
    )


def build_evidence_reference_events(
    *,
    event: Mapping[str, Any],
    incident_id: str,
    run_id: str,
    source_type: str,
    subject: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    evidence_ref = build_evidence_reference(
        event=event,
        incident_id=incident_id,
        run_id=run_id,
        source_type=source_type,
        subject=subject,
    )
    event_status = str(event.get("status") or "unknown")
    evidence_type = event.get("evidenceType") or event.get("evidence_type")
    enriched_ref = {
        **evidence_ref,
        "eventName": event.get("name"),
        "eventStatus": event_status,
        "evidenceType": evidence_type,
        "missingReason": event.get("missingReason"),
        "sourcePath": event.get("sourcePath"),
    }
    enriched_ref = {
        key: value
        for key, value in enriched_ref.items()
        if value is not None and value != ""
    }
    evidence_record = {
        **enriched_ref,
        "detail": redact_sensitive(event.get("detail") or event.get("result") or ""),
    }
    bounded_put(
        EVIDENCE_RECORDS,
        str(evidence_ref["evidenceId"]),
        evidence_record,
        EVIDENCE_MAX_RECORDS,
    )
    increment_metric("aiops_evidence_records_total")
    return [
        {
            "type": "tool_call",
            "id": enriched_ref["evidenceId"],
            "name": "evidence_ref",
            "summary": "증거 참조 생성",
        },
        {
            "type": "tool_result",
            "detail": json.dumps(redact_sensitive(enriched_ref), ensure_ascii=False, indent=2),
            "id": enriched_ref["evidenceId"],
            "name": "evidence_ref",
            "result": enriched_ref,
            "status": "success",
            "summary": f"{enriched_ref['evidenceId']} 기록",
        },
    ]


def evidence_refs_for_run(run_id: str) -> list[dict[str, Any]]:
    refs = [
        redact_sensitive(dict(record))
        for record in EVIDENCE_RECORDS.values()
        if str(record.get("runId") or "") == run_id
    ]
    return sorted(
        refs,
        key=lambda item: str(item.get("collectedAt") or item.get("evidenceId") or ""),
    )


def evidence_ref_bucket(ref: Mapping[str, Any]) -> str:
    status = str(ref.get("eventStatus") or ref.get("status") or "").lower()
    if status in {"recorded", "success", "succeeded", "ok", "completed", "collected"}:
        return "collected"
    if status == "partial":
        return "partial"
    return "missing"


def evidence_type_from_record(ref: Mapping[str, Any]) -> str:
    return str(ref.get("evidenceType") or ref.get("type") or "").lower()


def evidence_contract_line(refs: list[Mapping[str, Any]], evidence_type: str, label: str) -> str:
    typed_refs = [ref for ref in refs if evidence_type_from_record(ref) == evidence_type]
    if not typed_refs:
        return f"- {label}: 확인 불가. 해당 evidence reference가 없습니다."
    preferred = sorted(
        typed_refs,
        key=lambda ref: {"collected": 0, "partial": 1}.get(evidence_ref_bucket(ref), 2),
    )[0]
    bucket = evidence_ref_bucket(preferred)
    digest = str(preferred.get("contentDigest") or "")
    short_digest = digest[:24] if digest else "digest 없음"
    reason = str(preferred.get("missingReason") or preferred.get("summary") or "")
    if bucket == "collected":
        return f"- {label}: 수집됨. evidence `{preferred.get('evidenceId')}`, digest `{short_digest}`."
    if bucket == "partial":
        return (
            f"- {label}: 부분 확인. evidence `{preferred.get('evidenceId')}`, "
            f"digest `{short_digest}`. {safe_error_text(reason, limit=160)}"
        )
    return (
        f"- {label}: 확인 불가. evidence `{preferred.get('evidenceId')}`, "
        f"상태 `{preferred.get('eventStatus') or preferred.get('status') or 'unknown'}`. "
        f"{safe_error_text(reason, limit=160)}"
    )


def build_crashloop_demo_answer_contract_text(req: ChatRequest, run_id: str) -> str:
    target = crashloop_demo_target_from_request(req)
    if not target:
        return ""

    refs = evidence_refs_for_run(run_id)
    namespace = target["namespace"]
    pod_name = target["name"]
    forbidden = ", ".join(ACTION_CANDIDATE_FORBIDDEN_VERBS)
    evidence_lines = [
        evidence_contract_line(refs, "pod_status", "Pod 상태와 재시작 근거"),
        evidence_contract_line(refs, "event", "Pod Event 근거"),
        evidence_contract_line(refs, "pod_log", "이전 로그 가용성"),
        evidence_contract_line(refs, "metric", "Restart/운영 메트릭"),
    ]
    return "\n".join(
        [
            "",
            "## RCA 계약 요약",
            "",
            "### 확인된 근거",
            *evidence_lines,
            "",
            "### 가능한 원인 후보",
            "- 현재 시연 컨텍스트는 공식 Evidence RCA 대상 Pod 재시작 질문에 묶여 있습니다.",
            "- 컨테이너 프로세스 반복 종료, 잘못된 command/args, 설정/env 참조, 이미지 또는 애플리케이션 초기화 실패가 후보입니다.",
            "- 이 후보는 수집된 상태/event/메트릭과 이전 로그 가용성 기준의 후보이며, 로그 원문을 근거로 확정하지 않습니다.",
            "",
            "### RCA",
            "- 공식 시연 기준 RCA는 Event, grep/log-pattern, Metric, Snapshot evidence를 함께 묶어 판단합니다.",
            "- 현재 답변은 수집된 evidence와 누락 evidence를 분리한 원인 후보 분석이며, 단일 원인 확정이 아닙니다.",
            "",
            "### 즉시 조치",
            "- 즉시 실행이 아니라 read-only 확인 순서와 승인 필요 여부를 먼저 제시합니다.",
            "- 영향도가 큰 변경은 action candidate로만 남기고 실행하지 않습니다.",
            "",
            "### 재발 방지책",
            "- restart 추세, resource request/limit, readiness/liveness 설정, 배포 변경 이력, runbook 보완 여부를 후속 점검합니다.",
            "",
            "### 참고 증적",
            "- Pod/Event/Metric/Snapshot evidence의 수집 상태와 digest를 기준으로 참고 증적을 표시합니다.",
            "",
            "### 추가 확인 필요",
            "- Pod log 원문은 민감정보 가능성이 있어 gateway evidence에는 저장하거나 출력하지 않았습니다.",
            "- grep_tool은 로그 원문이 아니라 OOMKilled, Eviction, stack-trace, error 같은 패턴과 digest만 근거화해야 합니다.",
            "- ClusterOperator 및 runbook/RAG 근거는 현재 사이클에서 미수집 상태로 남을 수 있습니다.",
            "- 원인을 확정하려면 승인된 운영 절차 안에서 이벤트 상세, Pod spec, 이전 로그를 추가 확인해야 합니다.",
            "",
            "### Read-only 확인 순서",
            "```bash",
            f"oc describe pod {pod_name} -n {namespace}",
            f"oc get events -n {namespace} --field-selector involvedObject.name={pod_name} --sort-by=.lastTimestamp",
            f"oc get pod {pod_name} -n {namespace} -o yaml",
            "```",
            "",
            "### 금지 작업",
            f"- 이 사이클은 read-only 전용입니다. `{forbidden}` 계열 작업은 실행하지 않습니다.",
            "- action candidate는 제안만 하며, 승인 전 `apply/delete/patch/scale/exec/rollout/restart`를 수행하지 않습니다.",
        ]
    )


def build_rca_context_stream_event(
    *,
    req: "ChatRequest",
    runtime_tool_plan: Mapping[str, Any],
    run_id: str,
    incident_id: str,
    phase: str,
) -> dict[str, Any]:
    context = redact_sensitive(
        build_rca_context(
            message=req.message,
            tool_plan=runtime_tool_plan,
            evidence_refs=evidence_refs_for_run(run_id),
            page_context=normalize_console_page_context(req.pageContext),
            run_id=run_id,
            incident_id=incident_id,
            phase=phase,
        )
    )
    contract = build_runtime_safety_contract(
        mutations_enabled=MUTATIONS_ENABLED,
        unrestricted_commands_enabled=UNRESTRICTED_COMMANDS_ENABLED,
        diagnostics_enabled=DIAGNOSTICS_ENABLED,
        record_store_enabled=RECORD_STORE_ENABLED,
        diagnostics_controller_configured=bool(HOST_DIAGNOSTICS_CONTROLLER_URL),
        lightspeed_status=redact_sensitive(dict(OLS_STREAM_STATUS)),
        latest_runtime_tool_plan=runtime_tool_plan,
        latest_rca_context=context,
    )
    return {
        "type": "rca_context",
        "context": context,
        "evidenceStatus": contract["evidenceStatus"],
        "phase": phase,
        "runId": run_id,
        "status": "success",
    }


def build_product_access_review_request() -> dict[str, Any]:
    resource_attributes: dict[str, Any] = {
        "resource": PRODUCT_ACCESS_REVIEW_RESOURCE,
        "verb": PRODUCT_ACCESS_REVIEW_VERB,
    }
    if PRODUCT_ACCESS_REVIEW_GROUP:
        resource_attributes["group"] = PRODUCT_ACCESS_REVIEW_GROUP
    if PRODUCT_ACCESS_REVIEW_NAME:
        resource_attributes["name"] = PRODUCT_ACCESS_REVIEW_NAME

    return {
        "apiVersion": "authorization.k8s.io/v1",
        "kind": "SelfSubjectAccessReview",
        "spec": {"resourceAttributes": resource_attributes},
    }


def build_action_access_review_request(plan: Mapping[str, Any]) -> dict[str, Any]:
    action = plan.get("action") if isinstance(plan.get("action"), Mapping) else {}
    target = plan.get("target") if isinstance(plan.get("target"), Mapping) else {}
    authorization = action.get("authorization") if isinstance(action.get("authorization"), Mapping) else {}
    resource_attributes: dict[str, Any] = {
        "group": authorization.get("apiGroup") or "",
        "resource": authorization.get("resource") or "",
        "subresource": authorization.get("subresource") or "",
        "verb": authorization.get("verb") or "",
        "namespace": target.get("namespace") or "",
        "name": target.get("name") or "",
    }
    if not resource_attributes["group"]:
        resource_attributes.pop("group", None)
    if not resource_attributes["subresource"]:
        resource_attributes.pop("subresource", None)
    return {
        "apiVersion": "authorization.k8s.io/v1",
        "kind": "SelfSubjectAccessReview",
        "spec": {"resourceAttributes": resource_attributes},
    }


async def fetch_action_access_review(user_auth_header: str, plan: Mapping[str, Any]) -> dict[str, Any]:
    review_request = build_action_access_review_request(plan)
    if not OPENSHIFT_API_URL:
        return {
            "allowed": not MUTATIONS_ENABLED,
            "enabled": True,
            "resourceAttributes": review_request["spec"]["resourceAttributes"],
            "skipped": True,
            "reason": "OPENSHIFT_API_URL is not configured",
        }

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(10.0, connect=5.0),
    ) as client:
        response = await client.post(
            f"{OPENSHIFT_API_URL}/apis/authorization.k8s.io/v1/selfsubjectaccessreviews",
            headers={
                "Accept": "application/json",
                "Authorization": user_auth_header,
                "Content-Type": "application/json",
            },
            json=review_request,
        )

    if response.status_code >= 400:
        return {
            "allowed": False,
            "enabled": True,
            "resourceAttributes": review_request["spec"]["resourceAttributes"],
            "reason": f"SelfSubjectAccessReview failed with HTTP {response.status_code}",
            "evaluationError": response.text[:500],
        }

    payload = response.json()
    status_payload = payload.get("status", {}) if isinstance(payload, Mapping) else {}
    status_map = status_payload if isinstance(status_payload, Mapping) else {}
    return {
        "allowed": bool(status_map.get("allowed")),
        "denied": bool(status_map.get("denied")),
        "enabled": True,
        "evaluationError": status_map.get("evaluationError") or "",
        "reason": status_map.get("reason") or "",
        "resourceAttributes": review_request["spec"]["resourceAttributes"],
        "skipped": False,
    }


def enforce_action_access_review(review: Mapping[str, Any]) -> None:
    if review.get("allowed") is True:
        return
    raise HTTPException(
        status_code=403,
        detail={
            "reason": "action_authorization_denied",
            "message": "Approver is not authorized for the exact Kubernetes action.",
            "review": redact_sensitive(dict(review)),
        },
    )


async def fetch_product_access_review(user_auth_header: str) -> dict[str, Any]:
    if not PRODUCT_ACCESS_REVIEW_ENABLED:
        return {
            "allowed": True,
            "enabled": False,
            "required": PRODUCT_ACCESS_REVIEW_REQUIRED,
            "skipped": True,
            "reason": "product access review disabled",
        }

    review_request = build_product_access_review_request()
    if not OPENSHIFT_API_URL:
        return {
            "allowed": not PRODUCT_ACCESS_REVIEW_REQUIRED,
            "enabled": True,
            "required": PRODUCT_ACCESS_REVIEW_REQUIRED,
            "resourceAttributes": review_request["spec"]["resourceAttributes"],
            "skipped": True,
            "reason": "OPENSHIFT_API_URL is not configured",
        }

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(10.0, connect=5.0),
    ) as client:
        response = await client.post(
            f"{OPENSHIFT_API_URL}/apis/authorization.k8s.io/v1/selfsubjectaccessreviews",
            headers={
                "Accept": "application/json",
                "Authorization": user_auth_header,
                "Content-Type": "application/json",
            },
            json=review_request,
        )

    if response.status_code >= 400:
        return {
            "allowed": False,
            "enabled": True,
            "required": PRODUCT_ACCESS_REVIEW_REQUIRED,
            "resourceAttributes": review_request["spec"]["resourceAttributes"],
            "reason": f"SelfSubjectAccessReview failed with HTTP {response.status_code}",
            "evaluationError": response.text[:500],
        }

    payload = response.json()
    status_payload = payload.get("status", {}) if isinstance(payload, Mapping) else {}
    status_map = status_payload if isinstance(status_payload, Mapping) else {}
    return {
        "allowed": bool(status_map.get("allowed")),
        "denied": bool(status_map.get("denied")),
        "enabled": True,
        "evaluationError": status_map.get("evaluationError") or "",
        "reason": status_map.get("reason") or "",
        "required": PRODUCT_ACCESS_REVIEW_REQUIRED,
        "resourceAttributes": review_request["spec"]["resourceAttributes"],
        "skipped": False,
    }


def product_access_review_status(review: Mapping[str, Any]) -> str:
    if review.get("skipped"):
        return "skipped"
    if review.get("allowed") is True:
        return "success"
    if review.get("required") is True:
        return "error"
    return "warning"


def summarize_product_access_review(review: Mapping[str, Any]) -> str:
    if review.get("enabled") is False:
        return "Product access SSAR is disabled by configuration."

    attributes = review.get("resourceAttributes")
    attributes_text = json.dumps(redact_sensitive(attributes), ensure_ascii=False)
    return "\n".join(
        [
            f"enabled: {review.get('enabled')}",
            f"required: {review.get('required')}",
            f"allowed: {review.get('allowed')}",
            f"denied: {review.get('denied', False)}",
            f"resourceAttributes: {attributes_text}",
            f"reason: {review.get('reason') or '-'}",
            f"evaluationError: {review.get('evaluationError') or '-'}",
        ]
    )


def enforce_product_access_review(review: Mapping[str, Any]) -> None:
    if review.get("required") is True and review.get("allowed") is not True:
        reason = review.get("reason") or review.get("evaluationError") or "product access denied"
        raise HTTPException(status_code=403, detail=f"KOMSCO AI product access denied: {reason}")


OPENSHIFT_USER_AUTH_FAILURE_MESSAGE = (
    "OpenShift 사용자 인증이 만료되었거나 Gateway로 전달된 사용자 토큰이 유효하지 않습니다. "
    "OpenShift 콘솔을 새로고침하거나 다시 로그인한 뒤 요청을 재시도하세요."
)


def build_openshift_user_auth_failure_detail(status_code: int, body: str) -> dict[str, Any]:
    upstream_reason = ""
    try:
        payload = json.loads(body)
        if isinstance(payload, Mapping):
            upstream_reason = str(payload.get("reason") or payload.get("message") or "")
    except json.JSONDecodeError:
        upstream_reason = body[:120]
    return {
        "code": "openshift_user_auth_failed",
        "message": OPENSHIFT_USER_AUTH_FAILURE_MESSAGE,
        "remediation": "OpenShift 콘솔 세션을 갱신한 뒤 AIOps 요청을 다시 실행하세요.",
        "upstreamStatus": status_code,
        "upstreamReason": redact_sensitive(upstream_reason),
    }


def http_exception_message(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, Mapping):
        message = detail.get("message")
        if message:
            return str(message)
        return json.dumps(redact_sensitive(detail), ensure_ascii=False)
    return str(detail) or exc.__class__.__name__


def is_openshift_user_auth_failure(exc: HTTPException) -> bool:
    detail = exc.detail
    return (
        exc.status_code == 401
        and isinstance(detail, Mapping)
        and detail.get("code") == "openshift_user_auth_failed"
    )


async def fetch_self_subject_review(user_auth_header: str) -> dict[str, Any]:
    if not OPENSHIFT_API_URL:
        return safe_subject(None)

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(10.0, connect=5.0),
    ) as client:
        response = await client.post(
            f"{OPENSHIFT_API_URL}/apis/authentication.k8s.io/v1/selfsubjectreviews",
            headers={
                "Accept": "application/json",
                "Authorization": user_auth_header,
                "Content-Type": "application/json",
            },
            json={
                "apiVersion": "authentication.k8s.io/v1",
                "kind": "SelfSubjectReview",
            },
        )

    if response.status_code >= 400:
        body = response.text[:500]
        if response.status_code == 401:
            raise HTTPException(
                status_code=401,
                detail=build_openshift_user_auth_failure_detail(response.status_code, body),
            )
        raise HTTPException(
            status_code=response.status_code,
            detail=f"OpenShift subject review failed: {body}",
        )

    payload = response.json()
    user_info = payload.get("status", {}).get("userInfo", {}) if isinstance(payload, Mapping) else {}
    return safe_subject(user_info if isinstance(user_info, Mapping) else None)


def summarize_policy_detail(policy: Mapping[str, Any]) -> str:
    decision = str(policy.get("decision") or "")
    if decision == "action_proposal_only":
        decision_label = "조치 요청은 Action Plan 경로로 처리"
        decision_explanation = "변경 가능성이 있는 요청이므로 직접 변경하지 않고 조치 계획/승인/실행 경로로 넘깁니다."
    elif decision == "allow_read_only_evidence":
        decision_label = "조회/증거 수집 허용"
        decision_explanation = "클러스터 상태 조회와 근거 수집은 허용하며 리소스 변경은 수행하지 않습니다."
    else:
        decision_label = "정책 결정 확인 필요"
        decision_explanation = str(policy.get("reason") or "-")

    risk_label = {
        "low": "낮음",
        "approval_required": "승인 필요",
        "unrestricted": "실험 무제한",
    }.get(str(policy.get("risk") or ""), str(policy.get("risk") or "-"))
    mutation_allowed = "예" if policy.get("mutationAllowed") else "아니오"
    return "\n".join(
        [
            f"정책 결정: {decision_label}",
            f"내부 결정값: {decision or '-'}",
            f"위험도: {risk_label}",
            f"변경 실행 허용: {mutation_allowed}",
            f"설명: {decision_explanation}",
        ]
    )


def policy_check_summary(policy: Mapping[str, Any]) -> str:
    if policy.get("decision") == "action_proposal_only":
        return "조치 요청은 Action Plan 경로로 처리"
    if policy.get("decision") == "allow_read_only_evidence":
        return "조회/증거 수집 허용"
    return "정책 결정 확인 필요"


def summarize_subject_detail(subject: Mapping[str, Any], *, live_review: bool) -> str:
    if not live_review:
        return "OPENSHIFT_API_URL 미설정: bearer 형식만 확인했고 live SelfSubjectReview는 건너뜀"

    return "\n".join(
        [
            f"username: {subject.get('username')}",
            f"uid: {subject.get('uid')}",
            f"groupsDigest: {subject.get('groupsDigest')}",
            f"authenticatedByCluster: {subject.get('authenticatedByCluster')}",
        ]
    )


def build_action_proposal_fallback(req: ChatRequest, policy: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "현재 요청은 변경/재시작/삭제/스케일/패치 계열 작업으로 분류되었습니다.",
            "",
            "### 조치 제안",
            f"- 요청: {redact_sensitive(req.message.strip()) or '미지정'}",
            "- 현재 단계: Gateway Phase 5 Action Execution",
            f"- 정책 결정: `{policy.get('decision')}`",
            "- 실행 가능 범위: 자연어 요청을 typed ActionProposal/SealedActionPlan으로 변환 후 승인된 Action Executor에서 실행",
            "",
            "### 승인 필요 여부",
            "- 필요함. 실제 mutation 실행은 Approval API와 Action Executor 경로에서만 허용됩니다.",
            "",
            "### 추가로 필요한 대상 정보",
            "- namespace",
            "- Pod 또는 관리 객체(Deployment/StatefulSet/DaemonSet 등) 이름",
            "- 원하는 작업이 단순 재시작인지, 장애 원인 분석 후 조치인지",
        ]
    )


def parse_markdown_table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    cells = [cell.strip().replace("\\|", "|") for cell in stripped.strip("|").split("|")]
    if not cells or all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
        return []
    if cells[0].lower() == "namespace":
        return []
    return [cell.strip("`") for cell in cells]


def parse_gateway_pod_evidence_rows(gateway_evidence: str | None) -> list[dict[str, str]]:
    if not gateway_evidence:
        return []

    section = ""
    rows: dict[tuple[str, str, str], dict[str, str]] = {}
    for line in gateway_evidence.splitlines():
        if line.startswith("Top container restart counts:"):
            section = "status_with_finished"
            continue
        if line.startswith("Currently non-healthy or waiting container evidence:"):
            section = "status"
            continue
        if line.startswith("Current Pod list evidence:"):
            section = "pod_list"
            continue
        if line.startswith("Spec evidence for currently non-healthy or waiting containers:"):
            section = "spec"
            continue

        cells = parse_markdown_table_cells(line)
        if not cells:
            continue

        if section == "status_with_finished" and len(cells) >= 10:
            namespace, pod, container = cells[0], cells[1], cells[2]
            key = (namespace, pod, container)
            rows.setdefault(key, {"namespace": namespace, "pod": pod, "container": container}).update(
                {
                    "currentState": cells[3],
                    "podStart": cells[4],
                    "ready": cells[5],
                    "restarts": cells[6],
                    "lastState": cells[7],
                    "lastFinished": cells[8],
                    "owner": cells[9],
                }
            )
            continue

        if section == "status" and len(cells) >= 9:
            namespace, pod, container = cells[0], cells[1], cells[2]
            key = (namespace, pod, container)
            rows.setdefault(key, {"namespace": namespace, "pod": pod, "container": container}).update(
                {
                    "currentState": cells[3],
                    "podStart": cells[4],
                    "ready": cells[5],
                    "restarts": cells[6],
                    "lastState": cells[7],
                    "owner": cells[8],
                }
            )
            continue

        if section == "pod_list" and len(cells) >= 9:
            namespace, pod, container = cells[0], cells[1], cells[2]
            key = (namespace, pod, container)
            rows.setdefault(key, {"namespace": namespace, "pod": pod, "container": container}).update(
                {
                    "currentState": cells[3],
                    "podStart": cells[4],
                    "ready": cells[5],
                    "restarts": cells[6],
                    "lastState": cells[7],
                    "owner": cells[8],
                }
            )
            continue

        if section == "spec" and len(cells) >= 8:
            namespace, pod, container = cells[0], cells[1], cells[2]
            key = (namespace, pod, container)
            rows.setdefault(key, {"namespace": namespace, "pod": pod, "container": container}).update(
                {
                    "image": cells[3],
                    "command": cells[4],
                    "args": cells[5],
                    "labels": cells[6],
                    "ownerChain": cells[7],
                }
            )

    return list(rows.values())


def parse_gateway_current_pod_list_rows(gateway_evidence: str | None) -> tuple[list[dict[str, str]], str, str]:
    if not gateway_evidence:
        return [], "", ""

    section = ""
    namespace_filter = ""
    rows_shown = ""
    rows: list[dict[str, str]] = []
    for line in gateway_evidence.splitlines():
        if line.startswith("Current Pod list evidence:"):
            section = "pod_list"
            continue
        if section == "pod_list" and line.startswith("Namespace filter:"):
            namespace_filter = line.split(":", 1)[1].strip().strip("`")
            continue
        if section == "pod_list" and line.startswith("Rows shown:"):
            rows_shown = line.split(":", 1)[1].strip()
            continue
        if section == "pod_list" and line.startswith("Spec evidence for currently non-healthy or waiting containers:"):
            section = ""
            continue

        cells = parse_markdown_table_cells(line)
        if section != "pod_list" or len(cells) < 9:
            continue

        rows.append(
            {
                "namespace": cells[0],
                "pod": cells[1],
                "container": cells[2],
                "currentState": cells[3],
                "podStart": cells[4],
                "ready": cells[5],
                "restarts": cells[6],
                "lastState": cells[7],
                "owner": cells[8],
            }
        )

    return rows, namespace_filter, rows_shown


def kubernetes_name_terms(message: str) -> list[str]:
    ignored = {
        "namespace",
        "deployment",
        "statefulset",
        "daemonset",
        "crashloopbackoff",
        "openshift",
    }
    terms: list[str] = []
    for match in re.finditer(r"\b[a-z0-9](?:[-a-z0-9]{2,61}[a-z0-9])?\b", message.lower()):
        term = match.group(0)
        if len(term) < 4 or term in ignored:
            continue
        if term not in terms:
            terms.append(term)
    return terms


def score_gateway_pod_row(row: Mapping[str, str], message: str) -> int:
    message_lower = message.lower()
    haystack = " ".join(str(row.get(key, "")).lower() for key in row)
    score = 0
    if row.get("namespace", "").lower() in message_lower:
        score += 3
    if row.get("pod", "").lower() in message_lower:
        score += 30
    if row.get("container", "").lower() in message_lower:
        score += 5
    for term in kubernetes_name_terms(message):
        if term and term in haystack:
            score += 10
    if "crash" in message_lower and "crashloopbackoff" in haystack:
        score += 5
    if "waiting:" in row.get("currentState", "").lower() or "crashloopbackoff" in haystack:
        score += 2
    return score


def choose_gateway_pod_row(rows: list[dict[str, str]], message: str) -> dict[str, str] | None:
    if not rows:
        return None
    scored = sorted(
        ((score_gateway_pod_row(row, message), index, row) for index, row in enumerate(rows)),
        key=lambda item: (item[0], -item[1]),
        reverse=True,
    )
    if scored[0][0] > 0:
        return scored[0][2]
    for row in rows:
        if "crashloopbackoff" in " ".join(row.values()).lower() or "waiting:" in row.get("currentState", "").lower():
            return row
    return rows[0]


def deployment_from_owner_chain(owner_chain: str) -> str | None:
    match = re.search(r"Deployment/([A-Za-z0-9._-]+)", owner_chain)
    return match.group(1) if match else None


def app_label_from_labels(labels: str) -> str | None:
    match = re.search(r"(?:^|,\s*)app=([^,\s]+)", labels)
    return match.group(1) if match else None


def looks_non_production_context(row: Mapping[str, str]) -> bool:
    text = " ".join(
        [
            row.get("pod", ""),
            row.get("labels", ""),
            row.get("ownerChain", ""),
        ]
    ).lower()
    return bool(re.search(r"\b(test|e2e|scenario|sandbox|demo|sample)\b", text))


def command_suggests_immediate_exit(command: str, args: str) -> bool:
    text = f"{command} {args}".lower()
    return any(marker in text for marker in ["systemexit", "raise ", "exit ", "exit(", "false", "sys.exit"])


def ready_summary_is_full(ready: str) -> bool:
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", ready)
    return bool(match and match.group(1) == match.group(2))


def build_pod_list_fallback(req: ChatRequest, gateway_evidence: str | None) -> str | None:
    if not is_pod_list_request(req.message):
        return None

    rows, namespace_filter, rows_shown = parse_gateway_current_pod_list_rows(gateway_evidence)
    evidence_scope = "Current Pod list evidence"
    if not rows:
        rows = parse_gateway_pod_evidence_rows(gateway_evidence)
        evidence_scope = "Pod status evidence 상위 항목"

    namespace = pod_list_namespace(req) or namespace_filter or "all-accessible-namespaces"
    if namespace and namespace != "all-accessible-namespaces":
        rows = [row for row in rows if row.get("namespace") == namespace]

    if not rows:
        return "\n".join(
            [
                "## RCA 보고서",
                "",
                "Gateway가 수집한 Kubernetes 증거 기준으로 Pod 목록을 조회했습니다.",
                "",
                "### 우선 판단",
                f"- Namespace: `{namespace}`",
                "- 조회된 Pod가 없습니다.",
                "- 현재 수집 범위에서는 Pod 장애를 확인하지 못했습니다.",
                "",
                "### 수집 근거",
                f"- Evidence 범위: `Current Pod list evidence`",
                "",
                "### 원인 후보",
                "- 조회 범위가 맞지 않거나, 현재 접근 권한/namespace 기준으로 대상 Pod가 없을 수 있습니다.",
                "",
                "### 확인 불가",
                "- Pod 상세, Event, 로그는 대상 Pod가 식별되지 않아 확인하지 못했습니다.",
                "",
                "### 확인 명령",
                "```bash",
                f"oc get pods -n {namespace}" if namespace != "all-accessible-namespaces" else "oc get pods -A",
                "```",
                "",
                "### 우선순위",
                "1. namespace와 대상 워크로드 이름을 먼저 확정합니다.",
            ]
        )

    total_rows = len(rows)
    not_ready_rows = [row for row in rows if not ready_summary_is_full(str(row.get("ready") or ""))]
    problem_rows = [
        row
        for row in rows
        if re.search(
            r"(?i)(crashloopbackoff|imagepullbackoff|errimagepull|error|failed|pending|waiting:)",
            " ".join(str(row.get(key, "")) for key in ("currentState", "lastState")),
        )
    ]

    lines = [
        "## RCA 보고서",
        "",
        "Gateway가 수집한 Kubernetes 증거 기준으로 Pod 목록을 조회했습니다.",
        "",
        "### 우선 판단",
        f"- Namespace: `{namespace}`",
        f"- Evidence 범위: `{evidence_scope}`",
        f"- 표시 Pod/Container row: `{total_rows}`" + (f" (수집 표시: `{rows_shown}`)" if rows_shown else ""),
        f"- Ready 아님: `{len(not_ready_rows)}`",
        f"- Warning/Error 계열 상태: `{len(problem_rows)}`",
        "",
        "### 수집 근거",
        "- Pod phase, container ready, restart count, lastState, owner 기준으로 목록을 정리했습니다.",
        "",
        "### 원인 후보",
        (
            "- Warning/Error 계열 상태가 있는 Pod부터 현재 장애 가능성을 확인해야 합니다."
            if problem_rows
            else "- 현재 목록 근거만으로는 즉시 장애 원인을 특정할 신호가 없습니다."
        ),
        "",
        "### 확인 불가",
        "- 개별 Pod 상세, Event, 이전 로그는 이 목록 요약만으로 확정하지 않습니다.",
        "",
        "### Pod 목록",
        "| Namespace | Pod | Container | Current State | Ready | Restarts | Last State/Exit | Owner |",
        "| :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- |",
    ]
    for row in rows:
        lines.append(
            "| {namespace} | `{pod}` | `{container}` | {currentState} | {ready} | {restarts} | {lastState} | {owner} |".format(
                namespace=row.get("namespace") or "-",
                pod=row.get("pod") or "-",
                container=row.get("container") or "-",
                currentState=row.get("currentState") or "-",
                ready=row.get("ready") or "-",
                restarts=row.get("restarts") or "0",
                lastState=row.get("lastState") or "-",
                owner=row.get("owner") or "-",
            )
        )

    lines.extend(
        [
            "",
            "### 확인 명령",
            "```bash",
            f"oc get pods -n {namespace}" if namespace != "all-accessible-namespaces" else "oc get pods -A",
            "```",
            "",
            "### 우선순위",
            "1. Warning/Error 계열 Pod의 상세와 Event를 먼저 확인합니다.",
            "2. Ready 아님 상태가 계속되는 Pod는 owner/controller 상태를 확인합니다.",
            "3. restart count는 누적값이므로 최근 증가 여부는 metric 또는 lastState 시간으로 따로 확인합니다.",
        ]
    )
    return "\n".join(lines)


def build_pod_evidence_fallback(req: ChatRequest, gateway_evidence: str | None) -> str | None:
    rows = parse_gateway_pod_evidence_rows(gateway_evidence)
    row = choose_gateway_pod_row(rows, req.message)
    if not row:
        return None

    namespace = row.get("namespace") or "unknown"
    pod = row.get("pod") or "unknown"
    container = row.get("container") or "unknown"
    state = row.get("currentState") or "-"
    ready = row.get("ready") or "-"
    restarts = row.get("restarts") or "-"
    last_state = row.get("lastState") or "-"
    last_finished = row.get("lastFinished") or "-"
    image = row.get("image") or "-"
    command = row.get("command") or "-"
    args = row.get("args") or "-"
    labels = row.get("labels") or "-"
    owner_chain = row.get("ownerChain") or row.get("owner") or "-"
    deployment = deployment_from_owner_chain(owner_chain)
    app_label = app_label_from_labels(labels)

    cause = "컨테이너가 `CrashLoopBackOff`/waiting 상태이며 마지막 종료 상태와 restart count가 확인됩니다."
    if command != "-" and command_suggests_immediate_exit(command, args):
        cause = "컨테이너 실행 명령/args가 프로세스의 즉시 종료를 유발하는 형태로 확인됩니다."

    lines = [
        "## RCA 보고서",
        "",
        "Gateway가 수집한 Kubernetes 증거 기준으로 대상 Pod를 우선 분석했습니다.",
        "",
        "### 우선 판단",
        f"- 대상: `{namespace}` / Pod `{pod}` / Container `{container}`",
        f"- 현재 상태: {state}, Ready `{ready}`, restart count `{restarts}`",
        f"- 마지막 종료: `{last_state}`" + (f", `{last_finished}`" if last_finished != "-" else ""),
        "",
        "### 수집 근거",
        f"- 원인 근거: {cause}",
        f"- 이미지: `{image}`",
        f"- Command: `{command}`",
        f"- Args: `{args}`",
        f"- 관리 객체: `{owner_chain}`",
        "",
        "### 원인 후보",
        f"- 1순위 후보: {cause}",
        "- 로그, Event, resource limit, image pull 세부 원인은 추가 근거가 있어야 확정할 수 있습니다.",
        "",
        "### 확인 불가",
        "- 이 fallback은 Gateway 사전 수집 표 기반입니다. Pod 상세/Event/previous log 조회가 실패했거나 아직 수행되지 않은 항목은 확정하지 않습니다.",
    ]

    lines.extend(["", "### 조치 후보"])
    if deployment:
        lines.append(
            f"- 단순 Pod 삭제나 rollout restart만으로는 같은 template이 다시 실행되어 재발할 수 있습니다. "
            f"`deployment/{deployment}`의 command/args/image/env/config 또는 정상 revision을 수정 후보로 잡으세요. 이 단계에서는 실행하지 않습니다."
        )
    else:
        lines.append(
            "- 상위 Deployment가 Gateway evidence에서 확정되지 않았습니다. Pod owner chain을 먼저 확인한 뒤 관리 객체를 대상으로 수정하세요."
        )
    if looks_non_production_context(row) and deployment:
        lines.append(
            "- 테스트/시나리오 리소스라면 정리 여부를 별도 조치 후보로 검토하세요. "
            "Stage 3 RCA 답변에서는 삭제 명령을 실행하거나 제시하지 않습니다."
        )

    lines.extend(["", "### 검증 명령"])
    if deployment:
        lines.append("```bash")
        lines.append(f"oc rollout status deployment/{deployment} -n {namespace}")
        if app_label:
            lines.append(f"oc get pod -n {namespace} -l app={app_label}")
        else:
            lines.append(f"oc get pod -n {namespace} --show-labels")
        lines.append(f"oc logs {pod} -n {namespace} -c {container} --previous --tail=120")
        lines.append("```")
    else:
        lines.append("```bash")
        lines.append(f"oc get pod {pod} -n {namespace} -o yaml")
        lines.append(f"oc get rs -n {namespace} --show-labels")
        lines.append("```")

    lines.extend(
        [
            "",
            "### 우선순위",
            "1. 현재 상태와 Event를 확인해 현재 장애인지 과거 이력인지 분리합니다.",
            "2. command/args/image/env/config처럼 template에 남는 원인을 먼저 수정 후보로 봅니다.",
            "3. 실행 조치는 별도 승인 전까지 제안만 유지합니다.",
        ]
    )

    return "\n".join(lines)


def build_empty_answer_fallback(
    req: ChatRequest,
    policy: Mapping[str, Any],
    tool_results: list[Mapping[str, Any]],
    gateway_evidence: str | None = None,
) -> str:
    if policy.get("decision") == "action_proposal_only":
        return build_action_proposal_fallback(req, policy)

    pod_list_fallback = build_pod_list_fallback(req, gateway_evidence)
    if pod_list_fallback:
        return pod_list_fallback

    pod_fallback = build_pod_evidence_fallback(req, gateway_evidence)
    if pod_fallback:
        return pod_fallback

    lines = [
        "## RCA 보고서",
        "",
        "Gateway가 수집한 증거 기준으로 안전한 요약을 생성했습니다.",
        "",
        "### 우선 판단",
        f"- 질문: {redact_sensitive(req.message.strip()) or '미지정'}",
        "- 현재 답변은 read-only Gateway 증거와 도구 결과만 근거로 합니다.",
    ]
    if tool_results:
        lines.extend(["", "### 수집 근거"])
        for index, event in enumerate(tool_results[-3:], start=1):
            name = event.get("name") or "tool_result"
            status_text = event.get("status") or "-"
            summary = event.get("summary") or event.get("detail") or "-"
            lines.append(f"{index}. `{name}` status={status_text}: {truncate_detail(str(summary), 500)}")
    if gateway_evidence:
        lines.extend(
            [
                "",
                "### Gateway 사전 수집 증거 요약",
                truncate_detail(gateway_evidence, 1800),
            ]
        )
    if not tool_results and not gateway_evidence:
        lines.extend(["", "### 수집 근거", "- 도구 결과가 없어 현재 답변은 추가 조회가 필요합니다."])

    lines.extend(
        [
            "",
            "### 원인 후보",
            "- 수집된 근거만으로 확정 원인을 단정하지 않습니다. 위 도구 결과의 status와 detail을 기준으로 후보를 좁혀야 합니다.",
            "",
            "### 확인 불가",
            "- 근거에 없는 리소스 상태, 로그 내용, Event 원인은 확인하지 못했습니다.",
        ]
    )

    lines.extend(
        [
            "",
            "### 다음 확인 명령",
            "```bash",
            "oc get events -A --sort-by=.lastTimestamp",
            "oc get co",
            "oc get pods -A",
            "```",
            "",
            "### 우선순위",
            "1. 실패하거나 누락된 evidence source를 먼저 복구합니다.",
            "2. 질문 대상 namespace/resource를 좁힙니다.",
            "3. 관련 Pod/Event/Operator/Metric 근거를 모아 원인 후보를 재평가합니다.",
        ]
    )
    return "\n".join(lines)


def truncate_unrestricted_output(value: bytes) -> tuple[str, bool]:
    truncated = len(value) > UNRESTRICTED_COMMAND_MAX_OUTPUT_BYTES
    if truncated:
        value = value[:UNRESTRICTED_COMMAND_MAX_OUTPUT_BYTES]
    text = value.decode("utf-8", errors="replace")
    return redact_sensitive(text), truncated


def unrestricted_command_timeout(requested_timeout: int | None) -> int:
    default_timeout = max(1, min(UNRESTRICTED_COMMAND_TIMEOUT_SECONDS, 3600))
    if requested_timeout is None:
        return default_timeout
    return max(1, min(int(requested_timeout), 3600))


def unrestricted_command_cwd(requested_cwd: str | None = None) -> str:
    cwd = requested_cwd or UNRESTRICTED_COMMAND_CWD or os.getcwd()
    return os.path.abspath(os.path.expanduser(cwd))


async def execute_unrestricted_command_request(
    req: UnrestrictedCommandExecuteCreate,
    subject: Mapping[str, Any],
    *,
    request_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    if not UNRESTRICTED_COMMANDS_ENABLED:
        raise HTTPException(status_code=403, detail="Experimental unrestricted command execution is disabled")

    command = req.command.strip()
    if not command:
        raise HTTPException(status_code=400, detail="Command is empty")

    cwd = unrestricted_command_cwd(req.cwd)
    if not os.path.isdir(cwd):
        raise HTTPException(status_code=400, detail=f"Command cwd does not exist: {cwd}")
    timeout_seconds = unrestricted_command_timeout(req.timeoutSeconds)
    started_at = time.monotonic()
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=cwd,
        executable="/bin/bash",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    timed_out = False
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        timed_out = True
        proc.kill()
        stdout_bytes, stderr_bytes = await proc.communicate()

    duration_ms = int((time.monotonic() - started_at) * 1000)
    stdout_text, stdout_truncated = truncate_unrestricted_output(stdout_bytes)
    stderr_text, stderr_truncated = truncate_unrestricted_output(stderr_bytes)
    exit_code = proc.returncode if proc.returncode is not None else -1
    result = {
        "apiVersion": "aiops.komsco/v1",
        "kind": "UnrestrictedCommandExecution",
        "metadata": {
            "name": f"unrestricted-command-{uuid.uuid4().hex[:16]}",
            "createdAt": now_rfc3339(),
        },
        "spec": {
            "command": redact_sensitive(command),
            "cwd": cwd,
            "durationMs": duration_ms,
            "exitCode": exit_code,
            "requestId": request_id or "",
            "runId": run_id or "",
            "stderr": stderr_text,
            "stderrTruncated": stderr_truncated,
            "stdout": stdout_text,
            "stdoutTruncated": stdout_truncated,
            "subject": redact_sensitive(dict(subject)),
            "timedOut": timed_out,
            "timeoutSeconds": timeout_seconds,
            "warning": "Experimental dev-only unrestricted command execution ran with Gateway local process privileges.",
        },
    }
    log_audit_record(
        build_trace_record(
            action="unrestricted_command_executed",
            incident_id="dev-unrestricted",
            policy={
                "schemaVersion": "v1",
                "phase": "experimental-unrestricted-command",
                "decision": "executed",
                "mutationAllowed": True,
                "risk": "unrestricted",
                "reason": "User selected experimental unrestricted mode.",
            },
            request_id=request_id or f"req-{uuid.uuid4()}",
            run_id=run_id or f"run-{uuid.uuid4()}",
            subject=subject,
            target={
                "command": redact_sensitive(command),
                "cwd": cwd,
                "durationMs": duration_ms,
                "exitCode": exit_code,
                "timedOut": timed_out,
            },
        )
    )
    return result


def unrestricted_command_response(result: Mapping[str, Any]) -> str:
    spec = result.get("spec") if isinstance(result.get("spec"), Mapping) else {}
    stdout_text = str(spec.get("stdout") or "")
    stderr_text = str(spec.get("stderr") or "")
    lines = [
        "실험용 무제한 명령 실행 결과입니다.",
        "",
        f"- Command: `{spec.get('command') or ''}`",
        f"- CWD: `{spec.get('cwd') or ''}`",
        f"- Exit code: `{spec.get('exitCode')}`",
        f"- Duration: `{spec.get('durationMs')}ms`",
        f"- Timed out: `{spec.get('timedOut')}`",
        "",
        "### stdout",
        "```text",
        stdout_text or "(empty)",
        "```",
    ]
    if stderr_text:
        lines.extend(["", "### stderr", "```text", stderr_text, "```"])
    return "\n".join(lines)


def append_query(path: str, query: Mapping[str, str]) -> str:
    separator = "&" if "?" in path else "?"
    encoded = "&".join(f"{key}={value}" for key, value in query.items())
    return f"{path}{separator}{encoded}"


def executor_auth_header() -> str:
    token = read_secret_value(
        os.getenv("KOMSCO_AI_ACTION_EXECUTOR_BEARER_TOKEN"),
        ACTION_EXECUTOR_TOKEN_FILE,
    )
    if not token:
        raise HTTPException(status_code=503, detail="Action Executor service account token is not configured")
    return f"Bearer {token}"


async def fetch_executor_live_state(
    client: httpx.AsyncClient,
    authorization: str,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    target = target_from_plan(plan)
    action = action_from_plan(plan)
    live_target = await fetch_ocp_json(
        client,
        target_path(target),
        authorization,
        required=True,
    )
    live_state: dict[str, Any] = {"target": live_target or {}}
    namespace = str(target.get("namespace") or "")
    tool_name = str(action.get("toolName") or "")
    if tool_name == "set_replicas_within_bounds":
        hpas = await fetch_ocp_json(
            client,
            f"/apis/autoscaling/v2/namespaces/{namespace}/horizontalpodautoscalers",
            authorization,
        )
        items = hpas.get("items") if isinstance(hpas, Mapping) else []
        live_state["hpas"] = [item for item in items if isinstance(item, Mapping)] if isinstance(items, list) else []
    if tool_name == "rollback_deployment_to_revision":
        replica_sets = await fetch_ocp_json(
            client,
            f"/apis/apps/v1/namespaces/{namespace}/replicasets",
            authorization,
        )
        items = replica_sets.get("items") if isinstance(replica_sets, Mapping) else []
        live_state["replicaSets"] = (
            [item for item in items if isinstance(item, Mapping)] if isinstance(items, list) else []
        )
    return live_state


async def submit_ocp_request(
    client: httpx.AsyncClient,
    authorization: str,
    *,
    method: str,
    path: str,
    content_type: str,
    body: Mapping[str, Any],
) -> httpx.Response:
    return await client.request(
        method,
        f"{OPENSHIFT_API_URL}{path}",
        headers={
            "Accept": "application/json",
            "Authorization": authorization,
            "Content-Type": content_type,
        },
        json=body,
    )


async def verify_typed_action_postcondition(
    client: httpx.AsyncClient,
    authorization: str,
    sealed_plan: Mapping[str, Any],
) -> dict[str, Any]:
    action = action_from_plan(sealed_plan)
    target = target_from_plan(sealed_plan)
    parameters = parameters_from_plan(sealed_plan)
    tool_name = str(action.get("toolName") or "")
    target_resource = await fetch_ocp_json(client, target_path(target), authorization)

    if tool_name == "evict_one_unhealthy_controller_owned_pod":
        if target_resource is None:
            return {"status": "verified", "reason": "target_pod_removed"}
        deletion_timestamp = target_resource.get("metadata", {}).get("deletionTimestamp")
        if deletion_timestamp:
            return {
                "status": "verified",
                "reason": "target_pod_deleting",
                "deletionTimestamp": deletion_timestamp,
            }
        observed_uid = str(target_resource.get("metadata", {}).get("uid") or "")
        if observed_uid != str(target.get("uid") or ""):
            return {"status": "verified", "reason": "target_pod_replaced"}
        return {"status": "verification_failed", "reason": "target_pod_still_present"}

    if target_resource is None:
        return {"status": "verification_failed", "reason": "target_resource_unavailable"}

    if tool_name == "rollout_restart_deployment":
        annotations = (
            target_resource.get("spec", {})
            .get("template", {})
            .get("metadata", {})
            .get("annotations", {})
        )
        restarted_at = str(parameters.get("restartedAt") or "")
        if isinstance(annotations, Mapping) and annotations.get("kubectl.kubernetes.io/restartedAt") == restarted_at:
            return {"status": "verified", "reason": "restart_annotation_observed"}
        return {"status": "verification_failed", "reason": "restart_annotation_not_observed"}

    if tool_name == "set_replicas_within_bounds":
        scale = await fetch_ocp_json(client, deployment_scale_path(target), authorization)
        replicas = parameters.get("replicas")
        observed = scale.get("spec", {}).get("replicas") if isinstance(scale, Mapping) else None
        if observed == replicas:
            return {"status": "verified", "reason": "scale_spec_matches", "observedReplicas": observed}
        return {
            "status": "verification_failed",
            "reason": "scale_spec_mismatch",
            "observedReplicas": observed,
        }

    if tool_name == "rollback_deployment_to_revision":
        annotations = (
            target_resource.get("spec", {})
            .get("template", {})
            .get("metadata", {})
            .get("annotations", {})
        )
        if isinstance(annotations, Mapping) and annotations.get("aiops.komsco/rollback-revision"):
            return {
                "status": "verified",
                "reason": "rollback_template_annotation_observed",
                "rollbackRevision": annotations.get("aiops.komsco/rollback-revision"),
            }
        return {"status": "verification_failed", "reason": "rollback_annotation_not_observed"}

    if tool_name == "set_hpa_bounds":
        spec = target_resource.get("spec", {}) if isinstance(target_resource.get("spec"), Mapping) else {}
        if spec.get("minReplicas") == parameters.get("minReplicas") and spec.get("maxReplicas") == parameters.get("maxReplicas"):
            return {"status": "verified", "reason": "hpa_bounds_match"}
        return {
            "status": "verification_failed",
            "reason": "hpa_bounds_mismatch",
            "observed": {
                "minReplicas": spec.get("minReplicas"),
                "maxReplicas": spec.get("maxReplicas"),
            },
        }

    return {"status": "inconclusive", "reason": "no_postcondition_for_tool"}


async def execute_typed_action_plan(sealed_plan: Mapping[str, Any]) -> dict[str, Any]:
    if not OPENSHIFT_API_URL:
        raise HTTPException(status_code=503, detail="OPENSHIFT_API_URL is not configured")

    executor_auth = executor_auth_header()
    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(30.0, connect=5.0),
    ) as client:
        live_state = await fetch_executor_live_state(client, executor_auth, sealed_plan)
        try:
            mutation = build_mutation_request(
                sealed_plan,
                live_target=live_state["target"],
                hpas=live_state.get("hpas") or (),
                replica_sets=live_state.get("replicaSets") or (),
            )
        except AiopsCoreError as exc:
            raise HTTPException(status_code=409, detail={"reason": exc.reason, "message": str(exc)}) from exc

        dry_run_path = append_query(
            mutation.path,
            {
                "dryRun": "All",
                "fieldManager": ACTION_EXECUTOR_FIELD_MANAGER,
            },
        )
        dry_run_response = await submit_ocp_request(
            client,
            executor_auth,
            method=mutation.method,
            path=dry_run_path,
            content_type=mutation.content_type,
            body=mutation.body,
        )
        increment_metric("aiops_execution_dry_run_total")
        if dry_run_response.status_code not in mutation.expected_statuses:
            return {
                "mutationOutcome": {
                    "status": "mutation_failed",
                    "reason": "server_side_dry_run_failed",
                    "httpStatus": dry_run_response.status_code,
                    "body": dry_run_response.text[:1000],
                },
                "remediationOutcome": {"status": "mutation_failed"},
                "executorTrace": {"dryRunPath": dry_run_path, "mutationSubmitted": False},
            }

        mutate_path = append_query(
            mutation.path,
            {
                "fieldManager": ACTION_EXECUTOR_FIELD_MANAGER,
            },
        )
        mutation_response = await submit_ocp_request(
            client,
            executor_auth,
            method=mutation.method,
            path=mutate_path,
            content_type=mutation.content_type,
            body=mutation.body,
        )
        if mutation_response.status_code not in mutation.expected_statuses:
            increment_metric("aiops_execution_mutation_failed_total")
            return {
                "mutationOutcome": {
                    "status": "mutation_failed",
                    "reason": "kubernetes_api_request_failed",
                    "httpStatus": mutation_response.status_code,
                    "body": mutation_response.text[:1000],
                },
                "remediationOutcome": {"status": "mutation_failed"},
                "executorTrace": {
                    "dryRunPath": dry_run_path,
                    "mutationPath": mutate_path,
                    "mutationSubmitted": True,
                },
            }

        postcondition = await verify_typed_action_postcondition(client, executor_auth, sealed_plan)
        increment_metric("aiops_execution_mutation_succeeded_total")
        return {
            "mutationOutcome": {
                "status": "mutation_succeeded",
                "reason": "typed_action_executed",
                "httpStatus": mutation_response.status_code,
            },
            "remediationOutcome": postcondition,
            "executorTrace": {
                "dryRunPath": dry_run_path,
                "mutationPath": mutate_path,
                "mutationSubmitted": True,
                "toolName": action_from_plan(sealed_plan).get("toolName"),
                "target": target_from_plan(sealed_plan),
            },
        }


async def execute_action_with_executor(
    sealed_plan: Mapping[str, Any],
    grant_reference: Mapping[str, Any],
) -> dict[str, Any]:
    if not ACTION_EXECUTOR_URL:
        return await execute_typed_action_plan(sealed_plan)

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if ACTION_EXECUTOR_SHARED_TOKEN:
        headers["Authorization"] = f"Bearer {ACTION_EXECUTOR_SHARED_TOKEN}"

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
        response = await client.post(
            f"{ACTION_EXECUTOR_URL}/v1/executor/actions/execute",
            headers=headers,
            json={
                "sealedActionPlan": redact_sensitive(dict(sealed_plan)),
                "executionGrantRef": redact_sensitive(dict(grant_reference)),
            },
        )

    if response.status_code >= 400:
        return {
            "mutationOutcome": {
                "status": "mutation_failed",
                "reason": "action_executor_request_failed",
                "httpStatus": response.status_code,
                "body": response.text[:1000],
            },
            "remediationOutcome": {"status": "mutation_failed"},
            "executorTrace": {
                "executorUrlConfigured": True,
                "mutationSubmitted": False,
            },
        }

    payload = response.json()
    spec = payload.get("spec") if isinstance(payload, Mapping) else {}
    if isinstance(spec, Mapping):
        return dict(spec)

    return {
        "mutationOutcome": {
            "status": "indeterminate",
            "reason": "action_executor_response_invalid",
        },
        "remediationOutcome": {"status": "inconclusive"},
        "executorTrace": {
            "executorUrlConfigured": True,
            "mutationSubmitted": True,
        },
    }


@app.get("/v1/cluster/summary")
async def cluster_summary(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    if not OPENSHIFT_API_URL:
        raise HTTPException(status_code=503, detail="OPENSHIFT_API_URL is not configured")

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        nodes_payload = await fetch_ocp_json(
            client,
            "/api/v1/nodes",
            user_auth_header,
            required=True,
        )
        node_metrics_payload = await fetch_ocp_json(
            client,
            "/apis/metrics.k8s.io/v1beta1/nodes",
            user_auth_header,
        )
        cluster_version_payload = await fetch_ocp_json(
            client,
            "/apis/config.openshift.io/v1/clusterversions/version",
            user_auth_header,
        )
        cluster_operators_payload = await fetch_ocp_json(
            client,
            "/apis/config.openshift.io/v1/clusteroperators",
            user_auth_header,
        )

    return build_cluster_summary(
        nodes_payload or {"items": []},
        node_metrics_payload,
        cluster_version_payload,
        cluster_operators_payload,
    )


@app.get("/v1/aiops/overview")
async def aiops_overview(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    if not OPENSHIFT_API_URL:
        raise HTTPException(status_code=503, detail="OPENSHIFT_API_URL is not configured")

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        nodes_payload, nodes_status = await fetch_ocp_json_observed(
            client,
            "/api/v1/nodes",
            user_auth_header,
            label="Node inventory",
            name="nodes",
            required=True,
        )
        node_metrics_payload, metrics_status = await fetch_ocp_json_observed(
            client,
            "/apis/metrics.k8s.io/v1beta1/nodes",
            user_auth_header,
            label="Node metrics",
            name="metrics.k8s.io",
        )
        cluster_version_payload, version_status = await fetch_ocp_json_observed(
            client,
            "/apis/config.openshift.io/v1/clusterversions/version",
            user_auth_header,
            label="Cluster version",
            name="clusterversion",
        )
        cluster_operators_payload, operators_status = await fetch_ocp_json_observed(
            client,
            "/apis/config.openshift.io/v1/clusteroperators",
            user_auth_header,
            label="Cluster operators",
            name="clusteroperators",
        )
        monitoring_config_payload, monitoring_config_status = await fetch_ocp_json_observed(
            client,
            "/api/v1/namespaces/openshift-config-managed/configmaps/monitoring-shared-config",
            user_auth_header,
            label="Monitoring public URLs",
            name="monitoring-shared-config",
        )
        pods_payload, pods_status = await fetch_ocp_json_observed(
            client,
            "/api/v1/pods?limit=500",
            user_auth_header,
            label="Pod anomaly signals",
            name="pods",
            required=True,
        )
        events_payload, events_status = await fetch_ocp_json_observed(
            client,
            "/api/v1/events?limit=500",
            user_auth_header,
            label="Warning events",
            name="events",
            required=True,
        )

    monitoring_urls = monitoring_urls_from_config(monitoring_config_payload)
    monitoring_probe = await probe_thanos_query(monitoring_urls.get("thanos", ""), user_auth_header)
    alerts_probe = await query_thanos_instant(
        monitoring_urls.get("thanos", ""),
        user_auth_header,
        'ALERTS{alertstate="firing"}',
    )
    restart_probe = await query_thanos_instant(
        monitoring_urls.get("thanos", ""),
        user_auth_header,
        "increase(kube_pod_container_status_restarts_total[1h]) > 0",
    )
    monitoring_probe_status = data_source_status(
        label="Thanos query probe",
        name="thanos-query",
        path="/api/v1/query?query=up",
        payload=monitoring_probe if monitoring_probe.get("status") == "available" else None,
        reason=str(monitoring_probe.get("reason") or ""),
        status=str(monitoring_probe.get("status") or "unavailable"),
        http_status=monitoring_probe.get("httpStatus")
        if isinstance(monitoring_probe.get("httpStatus"), int)
        else None,
    )
    alerts_probe_status = data_source_status(
        label="Active alerts",
        name="alerts",
        path='/api/v1/query?query=ALERTS{alertstate="firing"}',
        payload=alerts_probe if alerts_probe.get("status") == "available" else None,
        reason=str(alerts_probe.get("reason") or ""),
        status=str(alerts_probe.get("status") or "unavailable"),
        http_status=alerts_probe.get("httpStatus")
        if isinstance(alerts_probe.get("httpStatus"), int)
        else None,
    )
    restart_probe_status = data_source_status(
        label="Restart increase metric",
        name="restart-metrics",
        path="/api/v1/query?query=increase(kube_pod_container_status_restarts_total[1h]) > 0",
        payload=restart_probe if restart_probe.get("status") == "available" else None,
        reason=str(restart_probe.get("reason") or ""),
        status=str(restart_probe.get("status") or "unavailable"),
        http_status=restart_probe.get("httpStatus")
        if isinstance(restart_probe.get("httpStatus"), int)
        else None,
    )

    summary = build_cluster_summary(
        nodes_payload or {"items": []},
        node_metrics_payload,
        cluster_version_payload,
        cluster_operators_payload,
    )
    data_sources = [
        nodes_status,
        metrics_status,
        version_status,
        operators_status,
        monitoring_config_status,
        monitoring_probe_status,
        pods_status,
        events_status,
        alerts_probe_status,
        restart_probe_status,
    ]
    anomaly_summary = build_aiops_anomaly_summary(
        summary,
        pods_payload,
        events_payload,
        alerts_probe,
        restart_probe,
        data_sources,
    )

    return build_aiops_overview(
        summary,
        data_sources,
        monitoring_urls,
        monitoring_probe,
        anomaly_summary,
    )


@app.get("/v1/aiops/anomalies")
async def aiops_anomalies(
    authorization: str | None = Header(default=None),
    namespace: str | None = Query(default=None),
    since_minutes: int = Query(default=60, alias="sinceMinutes", ge=1, le=1440),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    overview = await aiops_overview(authorization)
    anomalies = overview.get("spec", {}).get("anomalies")
    if not isinstance(anomalies, dict):
        return {}

    filtered = dict(anomalies)
    spec = dict(filtered.get("spec", {})) if isinstance(filtered.get("spec"), Mapping) else {}
    findings = spec.get("findings") if isinstance(spec.get("findings"), list) else []
    if namespace:
        findings = [
            finding
            for finding in findings
            if isinstance(finding, Mapping)
            and (
                finding.get("namespace") == namespace
                or not finding.get("namespace")
                or str(finding.get("namespace")) == "cluster-scoped"
            )
        ]
    spec["findings"] = findings[:limit]
    spec["query"] = {
        "limit": limit,
        "namespace": namespace or "",
        "sinceMinutes": since_minutes,
    }
    filtered["spec"] = spec
    return filtered


@app.get("/v1/aiops/action-candidates")
async def aiops_action_candidates(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    overview = await aiops_overview(authorization)
    action_candidates = overview.get("spec", {}).get("actionCandidates")
    if not isinstance(action_candidates, dict):
        return {}
    return action_candidates


@app.get("/v1/auth/subject")
async def auth_subject(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    return await fetch_self_subject_review(user_auth_header)


@app.get("/v1/evidence")
async def list_evidence(
    authorization: str | None = Header(default=None),
    incident_id: str | None = Query(default=None, alias="incidentId"),
    run_id: str | None = Query(default=None, alias="runId"),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    items = []
    for record in EVIDENCE_RECORDS.values():
        if incident_id and record.get("incidentId") != incident_id:
            continue
        if run_id and record.get("runId") != run_id:
            continue
        if not can_subject_read_record(record, subject):
            continue
        items.append({key: value for key, value in record.items() if key != "detail"})

    return {
        "apiVersion": "aiops.komsco/v1",
        "items": items,
        "kind": "EvidenceReferenceList",
    }


@app.get("/v1/evidence/{evidence_id}")
async def get_evidence(
    evidence_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = EVIDENCE_RECORDS.get(evidence_id)
    if not record or not can_subject_read_record(record, subject):
        raise HTTPException(status_code=404, detail="Evidence not found")

    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "Evidence",
        "metadata": {"name": evidence_id},
        "spec": record,
    }


@app.get("/v1/workflows/{run_id}")
async def get_workflow(
    run_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = WORKFLOW_RECORDS.get(run_id)
    if not record or not can_subject_read_record(record, subject):
        raise HTTPException(status_code=404, detail="Workflow not found")

    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "Workflow",
        "metadata": {"name": run_id},
        "spec": record,
    }


@app.get("/v1/diagnostics/collectors")
async def get_diagnostic_collectors(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    verify_bearer_header(authorization)
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "HostDiagnosticCollectorRegistry",
        "metadata": {
            "name": "host-diagnostic-collector-registry",
            "version": HOST_DIAGNOSTIC_COLLECTOR_VERSION,
        },
        "spec": {
            "digest": HOST_DIAGNOSTIC_COLLECTOR_DIGEST,
            "diagnosticsEnabled": DIAGNOSTICS_ENABLED,
            "controllerConfigured": bool(HOST_DIAGNOSTICS_CONTROLLER_URL),
            "collectors": list(HOST_DIAGNOSTIC_COLLECTORS.values()),
        },
    }


@app.post("/v1/diagnostics/requests")
async def create_diagnostic_request(
    req: DiagnosticRequestCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = build_diagnostic_request_record(req, subject)
    record = await submit_diagnostic_request_to_controller(record)
    request_id = str(record["metadata"]["name"])
    await bounded_put_record("diagnosticRequests", request_id, record)
    increment_metric("aiops_diagnostic_requests_total")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "DiagnosticRequest",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.get("/v1/diagnostics/requests/{request_id}")
async def get_diagnostic_request(
    request_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = DIAGNOSTIC_REQUESTS.get(request_id)
    if not record or not can_subject_read_record(record, subject):
        raise HTTPException(status_code=404, detail="Diagnostic request not found")
    record = await refresh_diagnostic_request_from_controller(record)
    await bounded_put_record("diagnosticRequests", request_id, record)

    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "DiagnosticRequest",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


def latest_readable_records(
    store: Mapping[str, dict[str, Any]],
    subject: Mapping[str, Any],
    *,
    product_access_allowed: bool = False,
    limit: int = 8,
) -> list[dict[str, Any]]:
    records = [
        record
        for record in store.values()
        if product_access_allowed or can_subject_read_record(record, subject)
    ]
    records.sort(
        key=lambda record: str(record.get("metadata", {}).get("createdAt") or ""),
        reverse=True,
    )
    return [
        {
            "metadata": record.get("metadata", {}),
            "kind": record.get("kind"),
            "spec": record.get("spec", {}),
        }
        for record in records[:limit]
    ]


def latest_readable_audit_records(
    subject: Mapping[str, Any],
    *,
    product_access_allowed: bool = False,
    limit: int = 12,
) -> list[dict[str, Any]]:
    records = [
        record
        for record in AUDIT_RECORDS.values()
        if product_access_allowed or can_subject_read_record(record, subject)
    ]
    records.sort(key=lambda record: str(record.get("timestamp") or ""), reverse=True)
    return [
        {
            "kind": "AuditRecord",
            "metadata": {
                "createdAt": record.get("timestamp"),
                "name": record.get("auditId"),
            },
            "spec": {
                "action": record.get("action"),
                "incidentId": record.get("incidentId"),
                "policy": record.get("policy", {}),
                "requestId": record.get("requestId"),
                "runId": record.get("runId"),
                "target": record.get("target", {}),
            },
        }
        for record in records[:limit]
    ]



RAG_DEMO_RUNBOOKS: tuple[dict[str, Any], ...] = (
    {
        "chunkId": "komsco-runbook-pod-restart-oom-v1:chunk:0",
        "documentId": "komsco-runbook-pod-restart-oom-v1",
        "title": "Pod restart / OOMKilled RCA runbook",
        "sourceUri": "docs/Ver.0.1.3/Komsco_ai_agent_final.converted.md#pod-restart-rca",
        "sourceType": "runbook",
        "customer": "komsco",
        "namespace": "default",
        "version": "v0.1.3",
        "aclGroups": ["cluster-admins", "aiops-admins"],
        "labels": {"scenario": "pod_restart_rca", "severity": "warning", "domain": "openshift"},
        "content": (
            "Pod 재시작 RCA는 Event, previous container log, restart metric, Pod snapshot 순서로 근거를 수집한다. "
            "OOMKilled, Evicted, CrashLoopBackOff, readiness/liveness probe 실패를 구분하고, 메모리 limit 변경과 배포 변경 이력을 확인한다. "
            "답변은 RCA, 즉시 조치, 재발 방지책, 참고 증적 순서로 작성한다."
        ),
    },
    {
        "chunkId": "komsco-runbook-image-pull-v1:chunk:0",
        "documentId": "komsco-runbook-image-pull-v1",
        "title": "ImagePullBackOff triage runbook",
        "sourceUri": "docs/Ver.0.1.3/Komsco_ai_agent_final.converted.md#image-pull",
        "sourceType": "runbook",
        "customer": "komsco",
        "namespace": "openshift-marketplace",
        "version": "v0.1.3",
        "aclGroups": ["cluster-admins", "aiops-admins"],
        "labels": {"scenario": "image_pull", "severity": "warning", "domain": "openshift"},
        "content": (
            "ImagePullBackOff는 image 경로, tag 존재 여부, registry 연결성, pull secret, mirror registry 정책을 확인한다. "
            "CatalogSource 또는 marketplace Pod라면 관련 CatalogSource, Pod event, registry route 상태를 함께 본다."
        ),
    },
    {
        "chunkId": "komsco-runbook-etcd-fragmentation-v1:chunk:0",
        "documentId": "komsco-runbook-etcd-fragmentation-v1",
        "title": "etcd high fragmentation review runbook",
        "sourceUri": "docs/Ver.0.1.3/Komsco_ai_agent_final.converted.md#etcd-fragmentation",
        "sourceType": "runbook",
        "customer": "komsco",
        "namespace": "openshift-etcd",
        "version": "v0.1.3",
        "aclGroups": ["cluster-admins", "aiops-admins"],
        "labels": {"scenario": "etcd_fragmentation", "severity": "warning", "domain": "openshift"},
        "content": (
            "etcdDatabaseHighFragmentationRatio 경고는 즉시 defrag를 실행하지 않는다. "
            "먼저 etcd member 상태, leader, DB size, fragmentation ratio, backup 상태, 운영 영향도를 확인하고 승인된 절차로만 defrag를 수행한다."
        ),
    },
    {
        "chunkId": "komsco-runbook-operator-degraded-v1:chunk:0",
        "documentId": "komsco-runbook-operator-degraded-v1",
        "title": "ClusterOperator degraded RCA runbook",
        "sourceUri": "docs/Ver.0.1.3/Komsco_ai_agent_final.converted.md#operator",
        "sourceType": "runbook",
        "customer": "komsco",
        "namespace": "cluster-scoped",
        "version": "v0.1.3",
        "aclGroups": ["cluster-admins", "aiops-admins"],
        "labels": {"scenario": "operator_degraded", "severity": "warning", "domain": "openshift"},
        "content": (
            "ClusterOperator degraded/progressing/unavailable 상태는 ClusterOperator condition, relatedObjects, 최근 Warning event, operand Pod 상태를 함께 확인한다. "
            "Upgradeable=False 또는 AdminAckRequired는 장애와 업데이트 정책 신호를 분리해서 설명한다."
        ),
    },
    {
        "chunkId": "komsco-runbook-bounded-action-v1:chunk:0",
        "documentId": "komsco-runbook-bounded-action-v1",
        "title": "Approved bounded action runbook",
        "sourceUri": "docs/Ver.0.1.1/rag-storage-contract.md#runbook-plan",
        "sourceType": "sop",
        "customer": "komsco",
        "namespace": "komsco-ai-dev",
        "version": "v0.1.3",
        "aclGroups": ["cluster-admins", "aiops-admins"],
        "labels": {"scenario": "approved_action", "severity": "controlled", "domain": "execution"},
        "content": (
            "실행 가능한 조치는 자연어에서 직접 patch/delete/scale을 수행하지 않는다. "
            "Gateway는 ActionProposal, SealedActionPlan, Approval, Action Executor 순서로 처리하고, 실행 전 fresh evidence와 namespace/owner/HPA/PDB 정책을 확인한다."
        ),
    },
)


def split_rag_upload_chunks(content: str, *, max_chars: int | None = None) -> list[str]:
    limit = max_chars or RAG_UPLOAD_MAX_CHUNK_CHARS
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", content) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs or [content.strip()]:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= limit:
            current = paragraph
            continue
        for start in range(0, len(paragraph), limit):
            chunk = paragraph[start : start + limit].strip()
            if chunk:
                chunks.append(chunk)
        current = ""
    if current:
        chunks.append(current)
    return chunks[:RAG_UPLOAD_MAX_CHUNKS]


def sanitize_rag_upload_text(content: str) -> str:
    """Remove control characters that cannot be persisted as PostgreSQL text."""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", content)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{4,}", "\n\n\n", cleaned)
    return cleaned.strip()


def xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def xml_text_content(node: ET.Element) -> str:
    parts = [
        str(element.text or "").strip()
        for element in node.iter()
        if xml_local_name(str(element.tag)) == "t" and str(element.text or "").strip()
    ]
    return " ".join(parts).strip()


def parse_rag_upload_form_labels(raw_labels: str | None) -> dict[str, str]:
    if not raw_labels or not raw_labels.strip():
        return {}

    try:
        parsed = json.loads(raw_labels)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="RAG upload labels must be a JSON object") from exc

    if not isinstance(parsed, Mapping):
        raise HTTPException(status_code=400, detail="RAG upload labels must be a JSON object")

    return {
        str(key)[:80]: str(value)[:240]
        for key, value in parsed.items()
        if str(key).strip()
    }


def detect_rag_upload_file_format(name: str, mime_type: str, raw: bytes) -> str:
    suffix = os.path.splitext(name.lower())[1]
    normalized_mime = mime_type.lower()
    if raw.startswith(b"%PDF-") or suffix == ".pdf" or normalized_mime == "application/pdf":
        return "pdf"
    if suffix == ".docx" or normalized_mime.endswith("wordprocessingml.document"):
        return "docx"
    if suffix == ".pptx" or normalized_mime.endswith("presentationml.presentation"):
        return "pptx"
    if suffix == ".xlsx" or normalized_mime.endswith("spreadsheetml.sheet"):
        return "xlsx"
    if normalized_mime.startswith("text/") or suffix in {".md", ".markdown", ".txt", ".yaml", ".yml", ".log"}:
        return "text"
    if suffix == ".json" or normalized_mime == "application/json":
        return "text"
    return "unknown"


def extract_pdf_text(raw: bytes) -> tuple[str, dict[str, Any]]:
    if PdfReader is None:
        raise HTTPException(status_code=503, detail="PDF upload parser dependency is not installed")

    try:
        reader = PdfReader(io.BytesIO(raw))
        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=400, detail="Encrypted PDF uploads are not supported") from exc

        pages: list[str] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = str(page.extract_text() or "").strip()
            if text:
                pages.append(f"<!-- page: {page_number} -->\n{text}")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"PDF text extraction failed: {type(exc).__name__}") from exc

    content = "\n\n".join(pages).strip()
    if not content:
        raise HTTPException(status_code=400, detail="PDF text extraction produced no text")
    return content, {"parser": "pypdf", "documentFormat": "pdf", "pageCount": len(pages)}


def extract_docx_text(raw: bytes) -> tuple[str, dict[str, Any]]:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            xml_bytes = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise HTTPException(status_code=400, detail="DOCX text extraction failed") from exc

    root = ET.fromstring(xml_bytes)
    paragraphs = [xml_text_content(node) for node in root.iter() if xml_local_name(str(node.tag)) == "p"]
    content = "\n\n".join(part for part in paragraphs if part).strip()
    if not content:
        raise HTTPException(status_code=400, detail="DOCX text extraction produced no text")
    return content, {"parser": "office-xml", "documentFormat": "docx", "paragraphCount": len(paragraphs)}


def extract_pptx_text(raw: bytes) -> tuple[str, dict[str, Any]]:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            slide_names = sorted(
                name for name in archive.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", name)
            )
            slides: list[str] = []
            for slide_number, name in enumerate(slide_names, start=1):
                root = ET.fromstring(archive.read(name))
                texts = [
                    str(element.text or "").strip()
                    for element in root.iter()
                    if xml_local_name(str(element.tag)) == "t" and str(element.text or "").strip()
                ]
                if texts:
                    slides.append(f"<!-- slide: {slide_number} -->\n" + "\n".join(texts))
    except (zipfile.BadZipFile, ET.ParseError) as exc:
        raise HTTPException(status_code=400, detail="PPTX text extraction failed") from exc

    content = "\n\n".join(slides).strip()
    if not content:
        raise HTTPException(status_code=400, detail="PPTX text extraction produced no text")
    return content, {"parser": "office-xml", "documentFormat": "pptx", "slideCount": len(slides)}


def extract_xlsx_text(raw: bytes) -> tuple[str, dict[str, Any]]:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                shared_strings = [
                    xml_text_content(item)
                    for item in shared_root.iter()
                    if xml_local_name(str(item.tag)) == "si"
                ]

            sheet_names = sorted(
                name for name in archive.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", name)
            )
            sheets: list[str] = []
            for sheet_number, name in enumerate(sheet_names, start=1):
                root = ET.fromstring(archive.read(name))
                values: list[str] = []
                for cell in (node for node in root.iter() if xml_local_name(str(node.tag)) == "c"):
                    cell_type = str(cell.attrib.get("t") or "")
                    raw_value = ""
                    for child in cell:
                        if xml_local_name(str(child.tag)) == "v":
                            raw_value = str(child.text or "").strip()
                            break
                    if not raw_value:
                        continue
                    if cell_type == "s":
                        try:
                            values.append(shared_strings[int(raw_value)])
                        except (ValueError, IndexError):
                            values.append(raw_value)
                    else:
                        values.append(raw_value)
                if values:
                    sheets.append(f"<!-- sheet: {sheet_number} -->\n" + "\n".join(values))
    except (zipfile.BadZipFile, ET.ParseError) as exc:
        raise HTTPException(status_code=400, detail="XLSX text extraction failed") from exc

    content = "\n\n".join(sheets).strip()
    if not content:
        raise HTTPException(status_code=400, detail="XLSX text extraction produced no text")
    return content, {"parser": "office-xml", "documentFormat": "xlsx", "sheetCount": len(sheets)}


def extract_rag_upload_file_content(name: str, mime_type: str, raw: bytes) -> tuple[str, dict[str, Any]]:
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(raw) > RAG_UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=413, detail="RAG upload file is too large")

    document_format = detect_rag_upload_file_format(name, mime_type, raw)
    if document_format == "pdf":
        content, report = extract_pdf_text(raw)
    elif document_format == "docx":
        content, report = extract_docx_text(raw)
    elif document_format == "pptx":
        content, report = extract_pptx_text(raw)
    elif document_format == "xlsx":
        content, report = extract_xlsx_text(raw)
    elif document_format == "text":
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="Text upload must be UTF-8 encoded") from exc
        report = {"parser": "utf-8-text", "documentFormat": "text"}
    else:
        guessed = mimetypes.guess_type(name)[0] or mime_type or "application/octet-stream"
        raise HTTPException(status_code=400, detail=f"Unsupported RAG upload file type: {guessed}")

    content = sanitize_rag_upload_text(content)
    if not content:
        raise HTTPException(status_code=400, detail="RAG upload parser produced empty content")

    truncated = False
    if len(content) > RAG_UPLOAD_MAX_CHARS:
        content = content[:RAG_UPLOAD_MAX_CHARS].rstrip()
        truncated = True

    report.update(
        {
            "originalFileName": name,
            "originalMimeType": mime_type or "application/octet-stream",
            "originalBytes": len(raw),
            "extractedChars": len(content),
            "truncated": truncated,
        }
    )
    return content, report


def decode_rag_upload_content(req: RagDocumentUploadCreate) -> str:
    if req.content and req.data:
        raise HTTPException(status_code=400, detail="Provide either content or base64 data, not both")
    if req.content is not None:
        content = req.content
        byte_size = len(content.encode("utf-8"))
    elif req.data is not None:
        try:
            raw = base64.b64decode(req.data, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Invalid upload base64 data") from exc
        byte_size = len(raw)
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="Only UTF-8 text/markdown uploads are supported in Ver.0.1.4") from exc
    else:
        raise HTTPException(status_code=400, detail="Upload content is required")

    if byte_size > RAG_UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=413, detail="RAG upload is too large")
    if not content.strip():
        raise HTTPException(status_code=400, detail="Upload content is empty")
    return content


def subject_acl_principals(subject: Mapping[str, Any]) -> set[str]:
    principals: set[str] = set()
    groups = subject.get("groups")
    if isinstance(groups, list):
        principals.update(
            str(group).strip()
            for group in groups
            if str(group).strip() and str(group).strip() not in RAG_BROAD_SYSTEM_GROUPS
        )

    username = str(subject.get("username") or "")
    uid = str(subject.get("uid") or "")
    if username and username != "unknown":
        principals.add(f"user:{username}")
    if uid and uid != "unknown":
        principals.add(f"uid:{uid}")
    return principals


def upload_acl_groups_for_subject(req: RagDocumentUploadCreate, subject: Mapping[str, Any]) -> list[str]:
    principals = subject_acl_principals(subject)
    if not principals:
        raise HTTPException(status_code=403, detail="Authenticated subject has no usable RAG ACL principals")

    if req.aclGroups:
        requested = {str(group) for group in req.aclGroups if str(group).strip()}
        allowed = sorted(requested.intersection(principals))
        if not allowed:
            raise HTTPException(status_code=403, detail="Requested RAG ACL groups are not owned by the current subject")
        return allowed

    return sorted(principals)


def classify_rag_upload_safety(content: str, labels: Mapping[str, str]) -> str:
    if RAG_DANGEROUS_CONTENT_RE.search(content):
        return "dangerous"

    requested = str(labels.get("safetyClass") or labels.get("safety_class") or "").strip()
    if requested in {"read-only", "approved-exec", "dangerous"}:
        return requested
    return "read-only"


def classify_rag_upload_freshness(labels: Mapping[str, str]) -> str:
    requested = str(labels.get("freshness") or "").strip()
    if requested in {"fresh", "stale", "unknown"}:
        return requested
    return "fresh"


def build_rag_upload_document(req: RagDocumentUploadCreate, subject: Mapping[str, Any]) -> dict[str, Any]:
    content = sanitize_rag_upload_text(decode_rag_upload_content(req))
    redacted_content = redact_sensitive(content)
    if not isinstance(redacted_content, str):
        redacted_content = str(redacted_content)
    chunks = split_rag_upload_chunks(redacted_content)
    if not chunks:
        raise HTTPException(status_code=400, detail="No upload chunks were produced")

    checksum = canonical_digest(content)
    document_id = f"user-upload:{checksum.removeprefix('sha256:')[:16]}"
    generated_at = now_rfc3339()
    safety_class = classify_rag_upload_safety(redacted_content, req.labels)
    freshness = classify_rag_upload_freshness(req.labels)
    labels = {
        "source": "user-upload",
        "version": req.version,
        **req.labels,
        "freshness": freshness,
        "safetyClass": safety_class,
    }
    source_uri = req.sourceUri or f"upload://{document_id}/{req.name}"
    acl_groups = upload_acl_groups_for_subject(req, subject)
    return {
        "document": {
            "documentId": document_id,
            "name": req.name,
            "title": req.name,
            "mimeType": req.mimeType,
            "sourceUri": source_uri,
            "sourceType": req.sourceType,
            "customer": req.customer,
            "namespace": req.namespace,
            "version": req.version,
            "aclGroups": acl_groups,
            "labels": labels,
            "checksum": checksum,
            "contentBytes": len(content.encode("utf-8")),
            "chunkCount": len(chunks),
            "ingestedAt": generated_at,
            "uploadedBy": str(subject.get("username") or "unknown"),
            "runId": req.runId or "",
        },
        "chunks": [
            {
                "chunkId": f"{document_id}:chunk:{index}",
                "documentId": document_id,
                "chunkIndex": index,
                "title": req.name,
                "sourceUri": f"{source_uri}#chunk-{index}",
                "sourceType": req.sourceType,
                "customer": req.customer,
                "namespace": req.namespace,
                "version": req.version,
                "aclGroups": acl_groups,
                "labels": {**labels, "chunkIndex": str(index)},
                "content": chunk,
                "textHash": canonical_digest(chunk),
                "checksum": canonical_digest({"documentId": document_id, "chunkIndex": index, "content": chunk}),
            }
            for index, chunk in enumerate(chunks)
        ],
    }


def rag_tokenize(value: str) -> list[str]:
    return re.findall(r"[0-9a-zA-Z가-힣_./:-]+", value.lower())


def build_rag_embedding(value: str, dimensions: int | None = None) -> list[float]:
    size = int(dimensions or RAG_EFFECTIVE_VECTOR_DIMENSIONS or 64)
    vector = [0.0 for _ in range(size)]
    tokens = rag_tokenize(value)
    if not tokens:
        return vector
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % size
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(item * item for item in vector)) or 1.0
    return [round(item / norm, 6) for item in vector]


def pgvector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{item:.6f}" for item in vector) + "]"


def ensure_pgvector_schema(conn: Any) -> None:
    dimensions = int(RAG_EFFECTIVE_VECTOR_DIMENSIONS or 64)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS aiops_rag_documents (
          document_id text PRIMARY KEY,
          collection text NOT NULL,
          title text NOT NULL,
          source_uri text NOT NULL,
          source_type text NOT NULL,
          customer text NOT NULL,
          namespace text NOT NULL,
          version text NOT NULL,
          mime_type text NOT NULL DEFAULT 'text/plain',
          acl_groups text[] NOT NULL,
          labels jsonb NOT NULL DEFAULT '{}'::jsonb,
          checksum text NOT NULL,
          chunk_count integer NOT NULL DEFAULT 0,
          content_bytes integer NOT NULL DEFAULT 0,
          uploaded_by text NOT NULL DEFAULT 'unknown',
          run_id text NOT NULL DEFAULT '',
          lifecycle text NOT NULL DEFAULT 'active',
          ingested_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS aiops_rag_chunks (
          chunk_id text PRIMARY KEY,
          collection text NOT NULL,
          document_id text NOT NULL,
          title text NOT NULL,
          source_uri text NOT NULL,
          source_type text NOT NULL,
          customer text NOT NULL,
          namespace text NOT NULL,
          version text NOT NULL,
          acl_groups text[] NOT NULL,
          labels jsonb NOT NULL DEFAULT '{{}}'::jsonb,
          lifecycle text NOT NULL DEFAULT 'active',
          content_redacted text NOT NULL,
          text_hash text NOT NULL,
          checksum text NOT NULL,
          embedding vector({dimensions}) NOT NULL,
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def seed_pgvector_runbooks(conn: Any) -> None:
    if not RAG_DEMO_SEED_ENABLED:
        return
    for doc in RAG_DEMO_RUNBOOKS:
        content = str(doc["content"])
        embedding = pgvector_literal(build_rag_embedding(f"{doc['title']} {content}"))
        text_hash = canonical_digest(content)
        checksum = canonical_digest({"chunkId": doc["chunkId"], "content": content, "version": doc["version"]})
        conn.execute(
            """
            INSERT INTO aiops_rag_chunks (
              chunk_id, collection, document_id, title, source_uri, source_type, customer,
              namespace, version, acl_groups, labels, lifecycle, content_redacted,
              text_hash, checksum, embedding, updated_at
            ) VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active', %s, %s, %s, %s::vector, now()
            )
            ON CONFLICT (chunk_id) DO UPDATE SET
              collection = EXCLUDED.collection,
              title = EXCLUDED.title,
              source_uri = EXCLUDED.source_uri,
              source_type = EXCLUDED.source_type,
              customer = EXCLUDED.customer,
              namespace = EXCLUDED.namespace,
              version = EXCLUDED.version,
              acl_groups = EXCLUDED.acl_groups,
              labels = EXCLUDED.labels,
              lifecycle = EXCLUDED.lifecycle,
              content_redacted = EXCLUDED.content_redacted,
              text_hash = EXCLUDED.text_hash,
              checksum = EXCLUDED.checksum,
              embedding = EXCLUDED.embedding,
              updated_at = now()
            """,
            (
                doc["chunkId"],
                RAG_COLLECTION,
                doc["documentId"],
                doc["title"],
                doc["sourceUri"],
                doc["sourceType"],
                doc["customer"],
                doc["namespace"],
                doc["version"],
                doc["aclGroups"],
                Jsonb(doc["labels"]) if Jsonb else json.dumps(doc["labels"]),
                content,
                text_hash,
                checksum,
                embedding,
            ),
        )


def persist_rag_upload_document(record: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    if not RAG_BACKEND_URL:
        return (
            "not_configured",
            "KOMSCO_AI_RAG_BACKEND_URL is not configured; upload ingestion was validated but not persisted.",
            {},
        )
    if psycopg is None or dict_row is None:
        return ("unavailable", "psycopg is not installed in the Gateway runtime.", {})

    document = record["document"]
    try:
        with psycopg.connect(RAG_BACKEND_URL, row_factory=dict_row) as conn:
            ensure_pgvector_schema(conn)
            conn.execute(
                """
                INSERT INTO aiops_rag_documents (
                  document_id, collection, title, source_uri, source_type, customer, namespace,
                  version, mime_type, acl_groups, labels, checksum, chunk_count, content_bytes,
                  uploaded_by, run_id, lifecycle, ingested_at, updated_at
                ) VALUES (
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active', now(), now()
                )
                ON CONFLICT (document_id) DO UPDATE SET
                  title = EXCLUDED.title,
                  source_uri = EXCLUDED.source_uri,
                  source_type = EXCLUDED.source_type,
                  customer = EXCLUDED.customer,
                  namespace = EXCLUDED.namespace,
                  version = EXCLUDED.version,
                  mime_type = EXCLUDED.mime_type,
                  acl_groups = EXCLUDED.acl_groups,
                  labels = EXCLUDED.labels,
                  checksum = EXCLUDED.checksum,
                  chunk_count = EXCLUDED.chunk_count,
                  content_bytes = EXCLUDED.content_bytes,
                  uploaded_by = EXCLUDED.uploaded_by,
                  run_id = EXCLUDED.run_id,
                  lifecycle = EXCLUDED.lifecycle,
                  updated_at = now()
                """,
                (
                    document["documentId"],
                    RAG_COLLECTION,
                    document["title"],
                    document["sourceUri"],
                    document["sourceType"],
                    document["customer"],
                    document["namespace"],
                    document["version"],
                    document["mimeType"],
                    document["aclGroups"],
                    Jsonb(document["labels"]) if Jsonb else json.dumps(document["labels"]),
                    document["checksum"],
                    document["chunkCount"],
                    document["contentBytes"],
                    document["uploadedBy"],
                    document["runId"],
                ),
            )
            for chunk in record["chunks"]:
                embedding = pgvector_literal(build_rag_embedding(f"{chunk['title']} {chunk['content']}"))
                conn.execute(
                    """
                    INSERT INTO aiops_rag_chunks (
                      chunk_id, collection, document_id, title, source_uri, source_type, customer,
                      namespace, version, acl_groups, labels, lifecycle, content_redacted,
                      text_hash, checksum, embedding, updated_at
                    ) VALUES (
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active', %s, %s, %s, %s::vector, now()
                    )
                    ON CONFLICT (chunk_id) DO UPDATE SET
                      collection = EXCLUDED.collection,
                      title = EXCLUDED.title,
                      source_uri = EXCLUDED.source_uri,
                      source_type = EXCLUDED.source_type,
                      customer = EXCLUDED.customer,
                      namespace = EXCLUDED.namespace,
                      version = EXCLUDED.version,
                      acl_groups = EXCLUDED.acl_groups,
                      labels = EXCLUDED.labels,
                      lifecycle = EXCLUDED.lifecycle,
                      content_redacted = EXCLUDED.content_redacted,
                      text_hash = EXCLUDED.text_hash,
                      checksum = EXCLUDED.checksum,
                      embedding = EXCLUDED.embedding,
                      updated_at = now()
                    """,
                    (
                        chunk["chunkId"],
                        RAG_COLLECTION,
                        chunk["documentId"],
                        chunk["title"],
                        chunk["sourceUri"],
                        chunk["sourceType"],
                        chunk["customer"],
                        chunk["namespace"],
                        chunk["version"],
                        chunk["aclGroups"],
                        Jsonb(chunk["labels"]) if Jsonb else json.dumps(chunk["labels"]),
                        chunk["content"],
                        chunk["textHash"],
                        chunk["checksum"],
                        embedding,
                    ),
                )
        return ("persisted", "Uploaded document chunks were persisted to pgvector.", document)
    except Exception as exc:
        return ("unavailable", f"pgvector upload ingestion failed: {exc}", {})


def list_pgvector_upload_documents(subject: Mapping[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    if not RAG_BACKEND_URL:
        return ("not_configured", "KOMSCO_AI_RAG_BACKEND_URL is not configured.", [])
    if psycopg is None or dict_row is None:
        return ("unavailable", "psycopg is not installed in the Gateway runtime.", [])
    subject_principals = subject_acl_principals(subject)
    if not subject_principals:
        return ("empty", "Current subject has no RAG ACL principals.", [])
    try:
        with psycopg.connect(RAG_BACKEND_URL, row_factory=dict_row) as conn:
            ensure_pgvector_schema(conn)
            rows = conn.execute(
                """
                SELECT
                  document_id, title, source_uri, source_type, customer, namespace, version,
                  mime_type, acl_groups, labels, checksum, chunk_count, content_bytes,
                  uploaded_by, run_id, lifecycle, ingested_at, updated_at
                FROM aiops_rag_documents
                WHERE collection = %s
                  AND source_type = 'user-upload'
                  AND lifecycle = 'active'
                  AND acl_groups && %s::text[]
                ORDER BY updated_at DESC
                LIMIT 50
                """,
                (RAG_COLLECTION, sorted(subject_principals)),
            ).fetchall()
    except Exception as exc:
        return ("unavailable", f"pgvector upload list failed: {exc}", [])

    documents = [
        redact_sensitive(
            {
                "documentId": row.get("document_id"),
                "title": row.get("title"),
                "sourceUri": row.get("source_uri"),
                "sourceType": row.get("source_type"),
                "customer": row.get("customer"),
                "namespace": row.get("namespace"),
                "version": row.get("version"),
                "mimeType": row.get("mime_type"),
                "aclGroups": row.get("acl_groups") or [],
                "labels": row.get("labels") or {},
                "checksum": row.get("checksum"),
                "chunkCount": row.get("chunk_count"),
                "contentBytes": row.get("content_bytes"),
                "uploadedBy": row.get("uploaded_by"),
                "runId": row.get("run_id"),
                "ingestedAt": row.get("ingested_at").isoformat() if row.get("ingested_at") else "",
                "updatedAt": row.get("updated_at").isoformat() if row.get("updated_at") else "",
            }
        )
        for row in rows
        if set(row.get("acl_groups") or []).intersection(subject_principals)
    ]
    return ("collected" if documents else "empty", "Uploaded RAG documents retrieved from pgvector.", documents)


def row_matches_rag_filters(
    row: Mapping[str, Any],
    filters: RagSearchFilters,
    subject_principals: set[str],
) -> bool:
    if filters.sourceTypes and row.get("source_type") not in filters.sourceTypes:
        return False
    if filters.namespaces and row.get("namespace") not in filters.namespaces:
        return False
    if filters.customers and row.get("customer") not in filters.customers:
        return False
    if filters.runbookIds and row.get("document_id") not in filters.runbookIds:
        return False
    if filters.versions and row.get("version") not in filters.versions:
        return False
    acl_groups = set(row.get("acl_groups") or [])
    if not acl_groups.intersection(subject_principals):
        return False
    if filters.aclGroups and not set(filters.aclGroups).intersection(acl_groups.intersection(subject_principals)):
        return False
    labels = row.get("labels") if isinstance(row.get("labels"), Mapping) else {}
    for key, expected in filters.labels.items():
        if str(labels.get(key) or "") != str(expected):
            return False
    if labels.get("safetyClass") == "dangerous" and filters.labels.get("safetyClass") != "dangerous":
        return False
    if labels.get("freshness") == "stale" and filters.labels.get("freshness") != "stale":
        return False
    return bool(acl_groups)


def search_pgvector_runbooks(
    req: RagSearchCreate,
    subject: Mapping[str, Any] | None = None,
) -> tuple[str, str, list[dict[str, Any]]]:
    if not RAG_BACKEND_URL:
        return (
            "not_configured",
            "KOMSCO_AI_RAG_BACKEND_URL is not configured; search returns no retrieved runbook evidence.",
            [],
        )
    if psycopg is None or dict_row is None:
        return ("unavailable", "psycopg is not installed in the Gateway runtime.", [])

    subject_principals = subject_acl_principals(subject or safe_subject(None))
    if not subject_principals:
        return ("empty", "Current subject has no RAG ACL principals.", [])

    query_vector = pgvector_literal(build_rag_embedding(req.query))
    try:
        with psycopg.connect(RAG_BACKEND_URL, row_factory=dict_row) as conn:
            ensure_pgvector_schema(conn)
            seed_pgvector_runbooks(conn)
            rows = conn.execute(
                """
                SELECT
                  chunk_id, document_id, title, source_uri, source_type, customer, namespace,
                  version, acl_groups, labels, content_redacted, text_hash, checksum,
                  1 - (embedding <=> %s::vector) AS score
                FROM aiops_rag_chunks
                WHERE collection = %s
                  AND lifecycle = 'active'
                  AND acl_groups && %s::text[]
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (query_vector, RAG_COLLECTION, sorted(subject_principals), query_vector, max(req.topK * 4, 20)),
            ).fetchall()
    except Exception as exc:  # pragma: no cover - depends on local DB state
        return ("unavailable", f"pgvector search failed: {exc}", [])

    results: list[dict[str, Any]] = []
    for row in rows:
        if not row_matches_rag_filters(row, req.filters, subject_principals):
            continue
        content = str(row.get("content_redacted") or "")
        result = {
            "id": row.get("chunk_id"),
            "documentId": row.get("document_id"),
            "title": row.get("title"),
            "score": round(float(row.get("score") or 0.0), 6),
            "sourceUri": row.get("source_uri"),
            "sourceType": row.get("source_type"),
            "customer": row.get("customer"),
            "namespace": row.get("namespace"),
            "version": row.get("version"),
            "contentPreview": content[:260],
            "content": content if req.includeContent else "",
            "metadata": row.get("labels") or {},
            "safety": {
                "freshness": (row.get("labels") or {}).get("freshness", "unknown"),
                "safetyClass": (row.get("labels") or {}).get("safetyClass", "unknown"),
            },
            "evidenceRef": {
                "type": "runbook",
                "evidenceType": "runbook",
                "status": "collected",
                "summary": row.get("title"),
                "sourceUri": row.get("source_uri"),
                "checksum": row.get("checksum"),
                "freshness": (row.get("labels") or {}).get("freshness", "unknown"),
                "safetyClass": (row.get("labels") or {}).get("safetyClass", "unknown"),
            },
        }
        results.append(redact_sensitive(result))
        if len(results) >= req.topK:
            break

    if results:
        return ("collected", "pgvector runbook evidence retrieved from local Gateway-controlled backend.", results)
    return ("empty", "pgvector backend is configured but no runbook matched the query and filters.", [])


def build_rag_context_detail(results: Sequence[Mapping[str, Any]], reason: str) -> str:
    if not results:
        return f"RAG evidence unavailable: {reason}"

    lines = [
        "Gateway-collected RAG evidence from `/v1/rag/search`.",
        "Use these retrieved sources as citation candidates; do not invent document contents that are not present in the previews.",
        "",
        "| Source | Type | Score | Preview |",
        "| - | - | - | - |",
    ]
    for result in results[:5]:
        title = str(result.get("title") or result.get("documentId") or "untitled")
        source_type = str(result.get("sourceType") or "runbook")
        score = result.get("score")
        preview = str(result.get("contentPreview") or result.get("content") or "").replace("\n", " ")
        source_uri = str(result.get("sourceUri") or result.get("documentId") or "")
        lines.append(f"| {title} ({source_uri}) | {source_type} | {score} | {preview[:180]} |")
    return "\n".join(lines)


def build_rag_answer_citation_text(results: Sequence[Mapping[str, Any]]) -> str:
    if not results:
        return ""

    lines = ["\n\n[ RAG 근거 ]"]
    for index, result in enumerate(results[:3], start=1):
        title = str(result.get("title") or result.get("documentId") or "untitled")
        source_uri = str(result.get("sourceUri") or result.get("documentId") or "")
        source_type = str(result.get("sourceType") or "runbook")
        score = result.get("score")
        lines.append(f"{index}. {title} ({source_type}, score={score})")
        if source_uri:
            lines.append(f"   - source: {source_uri}")
    return "\n".join(lines)


def build_rag_backend_status() -> dict[str, Any]:
    backend_configured = bool(RAG_BACKEND_URL)
    return {
        "status": "configured" if backend_configured else "not_configured",
        "backendType": RAG_BACKEND_TYPE,
        "collection": RAG_COLLECTION,
        "endpointConfigured": backend_configured,
        "embeddingModel": RAG_EMBEDDING_MODEL if backend_configured else "not_configured",
        "vectorDimensions": RAG_EFFECTIVE_VECTOR_DIMENSIONS if backend_configured else RAG_VECTOR_DIMENSIONS,
        "accessPath": "gateway-only",
        "directDatabaseAccess": False,
        "aclRequired": True,
        "demoSeedEnabled": RAG_DEMO_SEED_ENABLED,
        "requiredMetadata": [
            "documentId",
            "sourceUri",
            "sourceType",
            "customer",
            "namespace",
            "checksum",
            "version",
            "aclGroups",
            "ingestedAt",
        ],
        "reason": ""
        if backend_configured
        else "KOMSCO_AI_RAG_BACKEND_URL is not configured; search returns no retrieved runbook evidence.",
    }


@app.get("/v1/aiops/status")
async def get_aiops_status(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    product_access_review = await fetch_product_access_review(user_auth_header)
    product_access_allowed = bool(product_access_review.get("allowed"))
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "AIOpsRuntimeStatus",
        "metadata": {
            "name": "runtime-status",
            "generatedAt": now_rfc3339(),
        },
        "spec": {
            "capabilities": {
                "mutationsEnabled": MUTATIONS_ENABLED,
                "diagnosticsEnabled": DIAGNOSTICS_ENABLED,
                "diagnosticsControllerConfigured": bool(HOST_DIAGNOSTICS_CONTROLLER_URL),
                "actionExecutorConfigured": bool(ACTION_EXECUTOR_URL),
                "unrestrictedCommandsEnabled": UNRESTRICTED_COMMANDS_ENABLED,
                "recordStoreEnabled": RECORD_STORE_ENABLED,
                "recordStoreConfigMap": RECORD_STORE_CONFIGMAP if RECORD_STORE_ENABLED else "",
                "rag": build_rag_backend_status(),
            },
            "safetyContract": build_runtime_safety_contract(
                mutations_enabled=MUTATIONS_ENABLED,
                unrestricted_commands_enabled=UNRESTRICTED_COMMANDS_ENABLED,
                diagnostics_enabled=DIAGNOSTICS_ENABLED,
                record_store_enabled=RECORD_STORE_ENABLED,
                diagnostics_controller_configured=bool(HOST_DIAGNOSTICS_CONTROLLER_URL),
                lightspeed_status=redact_sensitive(dict(OLS_STREAM_STATUS)),
                latest_runtime_tool_plan=LAST_RUNTIME_TOOL_PLAN,
                latest_rca_context=LAST_RCA_CONTEXT,
            ),
            "productAccessReview": redact_sensitive(product_access_review),
            "subject": redact_sensitive(dict(subject)),
            "records": {
                "auditRecords": latest_readable_audit_records(
                    subject,
                    product_access_allowed=product_access_allowed,
                ),
                "diagnosticRequests": latest_readable_records(
                    DIAGNOSTIC_REQUESTS,
                    subject,
                    product_access_allowed=product_access_allowed,
                ),
                "actionProposals": latest_readable_records(
                    ACTION_PROPOSALS,
                    subject,
                    product_access_allowed=product_access_allowed,
                ),
                "sealedActionPlans": latest_readable_records(
                    SEALED_ACTION_PLANS,
                    subject,
                    product_access_allowed=product_access_allowed,
                ),
                "approvalDecisions": latest_readable_records(
                    APPROVAL_DECISIONS,
                    subject,
                    product_access_allowed=product_access_allowed,
                ),
                "executionRecords": latest_readable_records(
                    EXECUTION_RECORDS,
                    subject,
                    product_access_allowed=product_access_allowed,
                ),
            },
        },
    }


@app.get("/v1/actions/registry")
async def get_action_registry(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    verify_bearer_header(authorization)
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "ActionRegistry",
        "metadata": {
            "name": "mutation-action-registry",
            "version": ACTION_REGISTRY_VERSION,
        },
        "spec": {
            "digest": ACTION_REGISTRY_DIGEST,
            "mutationsEnabled": MUTATIONS_ENABLED,
            "entries": list(ACTION_REGISTRY_ENTRIES.values()),
        },
    }


@app.post("/v1/actions/proposals")
async def create_action_proposal(
    req: ActionProposalCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = build_action_proposal_record(req, subject)
    proposal_id = str(record["metadata"]["name"])
    await bounded_put_record("actionProposals", proposal_id, record)
    increment_metric("aiops_action_proposals_total")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "ActionProposal",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.get("/v1/actions/proposals/{proposal_id}")
async def get_action_proposal(
    proposal_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = ACTION_PROPOSALS.get(proposal_id)
    if not record or not can_subject_read_record(record, subject):
        raise HTTPException(status_code=404, detail="Action proposal not found")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "ActionProposal",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.post("/v1/actions/plans")
async def create_action_plan(
    req: SealedActionPlanCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    proposal = ACTION_PROPOSALS.get(req.proposalId)
    if not proposal or not can_subject_read_record(proposal, subject):
        raise HTTPException(status_code=404, detail="Action proposal not found")
    record = build_sealed_action_plan_record(proposal)
    plan_id = str(record["metadata"]["name"])
    await bounded_put_record("sealedActionPlans", plan_id, record)
    increment_metric("aiops_action_plans_total")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "SealedActionPlan",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.get("/v1/actions/plans/{plan_id}")
async def get_action_plan(
    plan_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = SEALED_ACTION_PLANS.get(plan_id)
    if not record or not can_subject_read_record(record, subject):
        raise HTTPException(status_code=404, detail="Sealed action plan not found")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "SealedActionPlan",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.post("/v1/actions/approvals")
async def create_approval_decision(
    req: ApprovalDecisionCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    product_access_review = await fetch_product_access_review(user_auth_header)
    if APPROVAL_ACCESS_REVIEW_REQUIRED:
        enforce_product_access_review(
            {
                **product_access_review,
                "required": True,
            }
        )
    plan = SEALED_ACTION_PLANS.get(req.planId)
    if not plan:
        raise HTTPException(status_code=404, detail="Sealed action plan not found")
    if not can_subject_read_record(plan, subject) and product_access_review.get("allowed") is not True:
        raise HTTPException(status_code=404, detail="Sealed action plan not found")
    action_access_review = await fetch_action_access_review(
        user_auth_header,
        plan["spec"]["sealedActionPlan"],
    )
    enforce_action_access_review(action_access_review)
    record = build_approval_decision_record(plan, req, subject, action_access_review)
    approval_id = str(record["metadata"]["name"])
    await bounded_put_record("approvalDecisions", approval_id, record)
    increment_metric("aiops_approval_decisions_total")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "ApprovalDecision",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.post("/v1/actions/execute")
async def execute_action(
    req: ActionExecutionCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    product_access_review = await fetch_product_access_review(user_auth_header)
    product_access_allowed = bool(product_access_review.get("allowed"))
    plan = SEALED_ACTION_PLANS.get(req.planId)
    approval = APPROVAL_DECISIONS.get(req.approvalId)
    if not plan or (
        not can_subject_read_record(plan, subject) and not product_access_allowed
    ):
        raise HTTPException(status_code=404, detail="Sealed action plan not found")
    if not approval or (
        not can_subject_read_record(approval, subject) and not product_access_allowed
    ):
        raise HTTPException(status_code=404, detail="Approval decision not found")

    sealed_plan = plan["spec"]["sealedActionPlan"]
    plan_digest = sealed_plan["digest"]["planDigest"]
    approval_decision = approval["spec"]["approvalDecision"]
    if req.expectedPlanDigest != plan_digest or approval_decision["planDigest"] != plan_digest:
        raise HTTPException(status_code=409, detail="Execution request is stale for this sealed plan")
    if approval_decision["status"] != "approved":
        raise HTTPException(status_code=409, detail="Approval decision is not approved")
    validate_approval_is_active(approval_decision)
    if approval_already_executed(req.approvalId):
        raise HTTPException(status_code=409, detail="Approval decision has already been used for execution")
    execution_access_review = await fetch_action_access_review(user_auth_header, sealed_plan)
    enforce_action_access_review(execution_access_review)
    validate_execution_evidence_freshness(sealed_plan)

    grant_reference = build_execution_grant_reference(approval, plan, subject)
    execution_id = f"execution-{uuid.uuid4()}"
    if MUTATIONS_ENABLED:
        executor_result = await execute_action_with_executor(sealed_plan, grant_reference)
    else:
        executor_result = {
            "mutationOutcome": {
                "status": "mutation_disabled",
                "reason": "KOMSCO_AI_ENABLE_MUTATIONS is false.",
            },
            "remediationOutcome": {"status": "not_remediated"},
            "executorTrace": {"mutationSubmitted": False},
        }
    record = {
        "schemaVersion": "v1",
        "apiVersion": "aiops.komsco/v1",
        "kind": "ExecutionRecord",
        "metadata": {"name": execution_id, "createdAt": now_rfc3339()},
        "spec": {
            "executionId": execution_id,
            "approvalId": req.approvalId,
            "planId": req.planId,
            "planDigest": plan_digest,
            "executionGrantRef": {
                key: value for key, value in grant_reference.items() if key != "claims"
            },
            "mutationOutcome": executor_result["mutationOutcome"],
            "remediationOutcome": executor_result["remediationOutcome"],
            "executorTrace": redact_sensitive(executor_result.get("executorTrace") or {}),
            "executionAuthorization": redact_sensitive(execution_access_review),
        },
        "subject": redact_sensitive(dict(subject)),
    }
    await bounded_put_record("executionRecords", execution_id, record)
    approval_decision["status"] = "executed"
    approval_decision["executedAt"] = record["metadata"]["createdAt"]
    await bounded_put_record("approvalDecisions", req.approvalId, approval)
    increment_metric("aiops_execution_requests_total")
    if not MUTATIONS_ENABLED:
        raise HTTPException(status_code=403, detail=record["spec"])
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "ExecutionRecord",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.post("/v1/dev/commands/execute")
async def execute_unrestricted_command(
    req: UnrestrictedCommandExecuteCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    return await execute_unrestricted_command_request(req, subject)


@app.get("/v1/runbooks/registry")
async def get_runbook_registry(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    verify_bearer_header(authorization)
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "RunbookRegistry",
        "metadata": {"name": "restricted-runbook-registry", "version": RUNBOOK_REGISTRY_VERSION},
        "spec": {
            "digest": RUNBOOK_REGISTRY_DIGEST,
            "entries": list(RUNBOOK_REGISTRY_ENTRIES.values()),
            "preapprovedPatchFieldDigest": PREAPPROVED_PATCH_FIELD_DIGEST,
            "preapprovedPatchFieldSchemas": list(PREAPPROVED_PATCH_FIELD_SCHEMAS.values()),
        },
    }


@app.get("/v1/rag/uploads")
async def list_rag_uploads(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    status, reason, documents = list_pgvector_upload_documents(subject)
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "RagUploadedDocumentList",
        "metadata": {"name": "uploaded-rag-documents", "generatedAt": now_rfc3339()},
        "spec": {
            "status": status,
            "reason": reason,
            "backend": build_rag_backend_status(),
            "documents": documents,
            "totals": {"documents": len(documents)},
            "safety": {
                "gatewayOnly": True,
                "directDatabaseAccessAllowed": False,
                "rawContentReturned": False,
            },
        },
    }


@app.post("/v1/rag/uploads")
async def create_rag_upload(
    req: RagDocumentUploadCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = build_rag_upload_document(req, subject)
    status, reason, document = persist_rag_upload_document(record)
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "RagUploadIngestionResult",
        "metadata": {"name": record["document"]["documentId"], "generatedAt": now_rfc3339()},
        "spec": {
            "status": status,
            "reason": reason,
            "backend": build_rag_backend_status(),
            "document": document or record["document"],
            "chunks": [
                {
                    "chunkId": chunk["chunkId"],
                    "chunkIndex": chunk["chunkIndex"],
                    "textHash": chunk["textHash"],
                    "checksum": chunk["checksum"],
                    "charLength": len(chunk["content"]),
                    "sourceUri": chunk["sourceUri"],
                }
                for chunk in record["chunks"]
            ],
            "safety": {
                "gatewayOnly": True,
                "directDatabaseAccessAllowed": False,
                "rawContentReturned": False,
                "redactionAppliedBeforeChunking": True,
            },
        },
    }


@app.post("/v1/rag/uploads/file")
async def create_rag_upload_file(
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
    labels: str = Form(default="{}"),
    customer: str = Form(default="komsco"),
    namespace: str = Form(default="komsco-ai-kugnus"),
    run_id: str | None = Form(default=None),
    source_type: str = Form(default="user-upload"),
    source_uri: str | None = Form(default=None),
    version: str = Form(default="v0.1.5"),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    filename = os.path.basename(file.filename or "upload").strip() or "upload"
    mime_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    raw = await file.read()
    content, parser_report = extract_rag_upload_file_content(filename, mime_type, raw)
    requested_labels = parse_rag_upload_form_labels(labels)
    parser_labels = {
        key: str(value).lower() if isinstance(value, bool) else str(value)
        for key, value in parser_report.items()
        if value is not None
    }
    req = RagDocumentUploadCreate(
        name=filename,
        mimeType=mime_type,
        content=content,
        sourceUri=source_uri,
        sourceType=source_type,
        customer=customer,
        namespace=namespace,
        version=version,
        labels={
            **requested_labels,
            **parser_labels,
            "source": requested_labels.get("source", "chat-attachment"),
        },
        runId=run_id,
    )
    record = build_rag_upload_document(req, subject)
    status, reason, document = persist_rag_upload_document(record)
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "RagUploadIngestionResult",
        "metadata": {"name": record["document"]["documentId"], "generatedAt": now_rfc3339()},
        "spec": {
            "status": status,
            "reason": reason,
            "backend": build_rag_backend_status(),
            "document": document or record["document"],
            "ingestionReport": parser_report,
            "chunks": [
                {
                    "chunkId": chunk["chunkId"],
                    "chunkIndex": chunk["chunkIndex"],
                    "textHash": chunk["textHash"],
                    "checksum": chunk["checksum"],
                    "charLength": len(chunk["content"]),
                    "sourceUri": chunk["sourceUri"],
                }
                for chunk in record["chunks"]
            ],
            "safety": {
                "gatewayOnly": True,
                "directDatabaseAccessAllowed": False,
                "rawContentReturned": False,
                "redactionAppliedBeforeChunking": True,
                "parserBoundary": "gateway-multipart-upload",
            },
        },
    }


@app.post("/v1/rag/search")
async def search_rag_runbooks(
    req: RagSearchCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    backend = build_rag_backend_status()
    request_id = f"rag-search-{uuid.uuid4()}"
    increment_metric("aiops_rag_search_requests_total")
    search_status, reason, results = search_pgvector_runbooks(req, subject=subject)
    evidence_status = "collected" if results else ("missing" if search_status == "not_configured" else search_status)
    collected_refs = [result.get("evidenceRef", {}) for result in results if isinstance(result.get("evidenceRef"), Mapping)]
    missing = [] if collected_refs else [{"type": "runbook", "reason": reason}]
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "RagSearchResult",
        "metadata": {
            "name": request_id,
            "generatedAt": now_rfc3339(),
        },
        "spec": {
            "query": req.query,
            "topK": req.topK,
            "filters": req.filters.model_dump(),
            "includeContent": req.includeContent,
            "runId": req.runId or request_id,
            "status": search_status,
            "reason": reason,
            "backend": backend,
            "results": results,
            "evidence": {
                "type": "runbook",
                "status": evidence_status,
                "reason": reason,
                "collectedRefs": collected_refs,
                "missing": missing,
            },
            "safety": {
                "gatewayOnly": True,
                "directDatabaseAccessAllowed": False,
                "aclRequired": True,
                "mockResultsAreProductionEvidence": False,
            },
        },
    }


@app.post("/v1/runbooks/plans")
async def create_runbook_plan(
    req: RunbookPlanCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = build_runbook_plan_record(req, subject)
    plan_id = str(record["metadata"]["name"])
    await bounded_put_record("runbookPlans", plan_id, record)
    increment_metric("aiops_runbook_plans_total")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "RunbookPlan",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.get("/v1/runbooks/plans/{plan_id}")
async def get_runbook_plan(
    plan_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = RUNBOOK_PLANS.get(plan_id)
    if not record or not can_subject_read_record(record, subject):
        raise HTTPException(status_code=404, detail="Runbook plan not found")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "RunbookPlan",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.post("/v1/runbooks/patch-preapproved-field")
async def create_preapproved_patch_request(
    req: PatchPreapprovedFieldCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = build_preapproved_patch_record(req, subject)
    request_id = str(record["metadata"]["name"])
    await bounded_put_record("preapprovedPatchRequests", request_id, record)
    increment_metric("aiops_preapproved_patch_requests_total")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "PatchPreapprovedFieldRequest",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.get("/v1/runbooks/patch-preapproved-field/{request_id}")
async def get_preapproved_patch_request(
    request_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = PREAPPROVED_PATCH_REQUESTS.get(request_id)
    if not record or not can_subject_read_record(record, subject):
        raise HTTPException(status_code=404, detail="Preapproved patch request not found")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "PatchPreapprovedFieldRequest",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.get("/v1/breakglass/profiles")
async def get_break_glass_profiles(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    verify_bearer_header(authorization)
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "BreakGlassProfileRegistry",
        "metadata": {"name": "break-glass-profile-registry", "version": BREAK_GLASS_PROFILE_VERSION},
        "spec": {
            "enabled": BREAK_GLASS_ENABLED,
            "digest": BREAK_GLASS_PROFILE_DIGEST,
            "profiles": list(BREAK_GLASS_PROFILES.values()),
        },
    }


@app.post("/v1/breakglass/requests")
async def create_break_glass_request(
    req: BreakGlassRequestCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = build_break_glass_request_record(req, subject)
    request_id = str(record["metadata"]["name"])
    await bounded_put_record("breakGlassRequests", request_id, record)
    increment_metric("aiops_break_glass_requests_total")
    log_break_glass_audit_record(
        build_trace_record(
            action="break_glass_request_recorded",
            incident_id=req.incidentId or request_id,
            policy=record["spec"]["policy"],
            request_id=request_id,
            run_id=req.runId or request_id,
            subject=subject,
            target={
                "profileId": req.profileId,
                "targetNode": req.targetNode.model_dump(),
                "phase": record["spec"]["status"]["phase"],
                "jobSubmitted": False,
            },
        )
    )
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "BreakGlassRequest",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.get("/v1/breakglass/requests/{request_id}")
async def get_break_glass_request(
    request_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = BREAK_GLASS_REQUESTS.get(request_id)
    if not record or not can_subject_read_record(record, subject):
        raise HTTPException(status_code=404, detail="Break-glass request not found")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "BreakGlassRequest",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> str:
    lines = []
    for name in sorted(METRICS):
        lines.append(f"# TYPE {name} counter")
        lines.append(f"{name} {METRICS[name]}")
    lines.append("# TYPE aiops_audit_records gauge")
    lines.append(f"aiops_audit_records {len(AUDIT_RECORDS)}")
    lines.append("# TYPE aiops_evidence_records gauge")
    lines.append(f"aiops_evidence_records {len(EVIDENCE_RECORDS)}")
    lines.append("# TYPE aiops_workflow_records gauge")
    lines.append(f"aiops_workflow_records {len(WORKFLOW_RECORDS)}")
    lines.append("# TYPE aiops_diagnostic_request_records gauge")
    lines.append(f"aiops_diagnostic_request_records {len(DIAGNOSTIC_REQUESTS)}")
    lines.append("# TYPE aiops_action_proposal_records gauge")
    lines.append(f"aiops_action_proposal_records {len(ACTION_PROPOSALS)}")
    lines.append("# TYPE aiops_sealed_action_plan_records gauge")
    lines.append(f"aiops_sealed_action_plan_records {len(SEALED_ACTION_PLANS)}")
    lines.append("# TYPE aiops_approval_decision_records gauge")
    lines.append(f"aiops_approval_decision_records {len(APPROVAL_DECISIONS)}")
    lines.append("# TYPE aiops_execution_records gauge")
    lines.append(f"aiops_execution_records {len(EXECUTION_RECORDS)}")
    lines.append("# TYPE aiops_runbook_plan_records gauge")
    lines.append(f"aiops_runbook_plan_records {len(RUNBOOK_PLANS)}")
    lines.append("# TYPE aiops_preapproved_patch_request_records gauge")
    lines.append(f"aiops_preapproved_patch_request_records {len(PREAPPROVED_PATCH_REQUESTS)}")
    lines.append("# TYPE aiops_break_glass_request_records gauge")
    lines.append(f"aiops_break_glass_request_records {len(BREAK_GLASS_REQUESTS)}")
    return "\n".join(lines) + "\n"


@app.post("/v1/chat/stream")
async def chat_stream(
    req: ChatRequest,
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing OpenShift bearer token")

    async def generate() -> AsyncIterator[str]:
        global LAST_RCA_CONTEXT, LAST_RUNTIME_TOOL_PLAN

        run_id = req.runId or f"run-{uuid.uuid4()}"
        request_id = f"req-{uuid.uuid4()}"
        incident_id = req.conversationId or f"inc-{uuid.uuid4()}"
        policy = classify_request_policy(req.message)
        subject = safe_subject(None)
        product_access_review: dict[str, Any] | None = None
        gateway_evidence: str | None = None
        rag_answer_citation_text = ""
        text_reference_filter = TextReferenceFilter(
            filter_gateway_api_references=should_filter_gateway_api_references(req.message),
            filter_low_signal_references=should_filter_low_signal_references(req.message),
            normalize_restart_language=should_collect_pod_status_evidence(req.message),
        )
        runtime_tool_plan: dict[str, Any] | None = None
        increment_metric("aiops_chat_requests_total")
        record_workflow(
            run_id=run_id,
            incident_id=incident_id,
            policy=policy,
            request_id=request_id,
            stage="started",
            status="running",
            subject=subject,
            target={
                "attachments": len(req.attachments),
                "messageLength": len(req.message),
                "pageContext": normalize_console_page_context(req.pageContext),
            },
        )

        try:
            yield sse(
                {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": "started",
                    "message": "Gateway 실행 루프 시작",
                    "elapsedMs": 0,
                }
            )
            yield sse(
                {
                    "type": "tool_call",
                    "id": f"{request_id}-security-boundary",
                    "name": "security_boundary",
                    "summary": "Phase 5 Action Execution 보안 경계 적용",
                }
            )
            yield sse(
                {
                    "type": "tool_result",
                    "detail": (
                        "UserToken은 Gateway 내부와 OLS forwarding에만 사용합니다.\n"
                        "Agent/Model prompt, audit payload, evidence event에는 redacted metadata만 전달합니다.\n"
                        "Mutation은 Approval API와 Action Executor 경로에서만 실행합니다.\n"
                        "실험용 무제한 모드는 KOMSCO_AI_ENABLE_UNRESTRICTED_COMMANDS=true이고 UI가 unrestricted 모드일 때만 동작합니다.\n"
                        "이 모드에서는 `/exec` 셸 명령과 지원되는 자연어 AIOps 조치를 즉시 실행할 수 있습니다."
                    ),
                    "id": f"{request_id}-security-boundary",
                    "name": "security_boundary",
                    "status": "success",
                    "summary": "Gateway credential boundary 확인",
                }
            )
            yield sse({"type": "tool_call", "name": "access_check"})
            await verify_user_access(authorization, req)
            validate_image_attachments(req.attachments)
            yield sse({"type": "tool_result", "name": "access_check", "result": "ok"})

            yield sse(
                {
                    "type": "tool_call",
                    "id": f"{request_id}-subject-review",
                    "name": "subject_review",
                    "summary": "API 서버 관찰 주체 확인",
                }
            )
            subject = await fetch_self_subject_review(authorization)
            live_review = bool(OPENSHIFT_API_URL)
            yield sse(
                {
                    "type": "tool_result",
                    "detail": summarize_subject_detail(subject, live_review=live_review),
                    "id": f"{request_id}-subject-review",
                    "name": "subject_review",
                    "result": subject,
                    "status": "success" if live_review else "skipped",
                    "summary": "주체 확인 완료" if live_review else "주체 확인 생략",
                }
            )

            yield sse(
                {
                    "type": "tool_call",
                    "id": f"{request_id}-product-access-review",
                    "name": "product_access_review",
                    "summary": "제품 접근 SelfSubjectAccessReview 확인",
                }
            )
            product_access_review = await fetch_product_access_review(authorization)
            increment_metric("aiops_product_access_reviews_total")
            yield sse(
                {
                    "type": "tool_result",
                    "detail": summarize_product_access_review(product_access_review),
                    "id": f"{request_id}-product-access-review",
                    "name": "product_access_review",
                    "result": product_access_review,
                    "status": product_access_review_status(product_access_review),
                    "summary": "제품 접근 확인 완료",
                }
            )
            enforce_product_access_review(product_access_review)
            record_workflow(
                run_id=run_id,
                incident_id=incident_id,
                policy=policy,
                request_id=request_id,
                stage="authorized",
                status="running",
                subject=subject,
                target={
                    "attachments": len(req.attachments),
                    "messageLength": len(req.message),
                    "pageContext": normalize_console_page_context(req.pageContext),
                    "productAccessReview": product_access_review,
                },
            )

            yield sse(
                {
                    "type": "tool_call",
                    "id": f"{request_id}-policy-check",
                    "name": "policy_check",
                    "summary": "요청 정책 분류",
                }
            )
            yield sse(
                {
                    "type": "tool_result",
                    "detail": summarize_policy_detail(policy),
                    "id": f"{request_id}-policy-check",
                    "name": "policy_check",
                    "result": policy,
                    "status": "success",
                    "summary": policy_check_summary(policy),
                }
            )
            runtime_tool_plan = build_runtime_tool_plan(
                req.message,
                page_context=normalize_console_page_context(req.pageContext),
                execution_mode=page_context_aiops_execution_mode(req),
            )
            LAST_RUNTIME_TOOL_PLAN = runtime_tool_plan
            def current_rca_context_event(phase: str) -> dict[str, Any]:
                return build_rca_context_stream_event(
                    req=req,
                    runtime_tool_plan=runtime_tool_plan or {},
                    run_id=run_id,
                    incident_id=incident_id,
                    phase=phase,
                )

            yield sse(
                {
                    "type": "tool_call",
                    "id": f"{request_id}-runtime-tool-plan",
                    "name": "runtime_tool_plan",
                    "summary": f"질문별 Tool Plan 생성: {runtime_tool_plan.get('task_type')}",
                }
            )
            yield sse(
                {
                    "type": "tool_plan",
                    "plan": redact_sensitive(runtime_tool_plan),
                    "runId": run_id,
                    "status": (
                        "success"
                        if runtime_tool_plan.get("validation", {}).get("ok")
                        else "failed"
                    ),
                }
            )
            yield sse(
                {
                    "type": "tool_result",
                    "detail": json.dumps(
                        redact_sensitive(runtime_tool_plan),
                        ensure_ascii=False,
                        indent=2,
                    ),
                    "id": f"{request_id}-runtime-tool-plan",
                    "name": "runtime_tool_plan",
                    "result": redact_sensitive(runtime_tool_plan),
                    "status": (
                        "success"
                        if runtime_tool_plan.get("validation", {}).get("ok")
                        else "failed"
                    ),
                    "summary": "read-only Tool Plan 검증 완료",
                }
            )
            rca_context_event = current_rca_context_event("plan_ready")
            LAST_RCA_CONTEXT = rca_context_event["context"]
            yield sse(rca_context_event)
            accepted_audit_record = build_trace_record(
                action="chat_request_accepted",
                incident_id=incident_id,
                policy=policy,
                request_id=request_id,
                run_id=run_id,
                subject=subject,
                target={
                    "attachments": len(req.attachments),
                    "messageLength": len(req.message),
                    "pageContext": normalize_console_page_context(req.pageContext),
                    "productAccessReview": product_access_review,
                },
            )
            log_audit_record(accepted_audit_record)
            yield sse(
                {
                    "type": "tool_result",
                    "detail": json.dumps(
                        redact_sensitive(accepted_audit_record),
                        ensure_ascii=False,
                        indent=2,
                    ),
                    "id": accepted_audit_record["auditId"],
                    "name": "audit_record",
                    "status": "success",
                    "summary": "감사 레코드 기록",
                }
            )

            unrestricted_command = parse_unrestricted_chat_command(req.message)
            if page_context_aiops_execution_mode(req) == "unrestricted" and unrestricted_command:
                yield sse(
                    {
                        "type": "tool_call",
                        "id": f"{request_id}-unrestricted-command",
                        "name": "unrestricted_command",
                        "summary": "실험용 무제한 명령 실행",
                    }
                )
                command_result = await execute_unrestricted_command_request(
                    UnrestrictedCommandExecuteCreate(command=unrestricted_command),
                    subject,
                    request_id=request_id,
                    run_id=run_id,
                )
                spec = command_result["spec"]
                yield sse(
                    {
                        "type": "tool_result",
                        "detail": json.dumps(redact_sensitive(spec), ensure_ascii=False, indent=2),
                        "id": f"{request_id}-unrestricted-command",
                        "name": "unrestricted_command",
                        "result": command_result,
                        "status": "failed" if spec.get("exitCode") else "success",
                        "summary": f"명령 종료 코드 {spec.get('exitCode')}",
                    }
                )
                rca_context_event = current_rca_context_event("post_answer")
                LAST_RCA_CONTEXT = rca_context_event["context"]
                yield sse(rca_context_event)
                yield sse({"type": "text", "content": unrestricted_command_response(command_result)})
                yield sse(
                    {
                        "type": "run_status",
                        "runId": run_id,
                        "stage": "completed",
                        "message": "Gateway 실험용 명령 실행 완료",
                    }
                )
                yield sse("[DONE]")
                return

            pod_count_query = parse_pod_count_query(req)
            if pod_count_query and not crashloop_demo_target_from_request(req):
                target_name = str(pod_count_query.get("targetName") or "")
                namespace = str(pod_count_query.get("namespace") or "")
                scope_summary = (
                    f"namespace `{namespace}` 범위에서 조회"
                    if namespace
                    else "접근 가능한 전체 namespace에서 조회"
                )
                yield sse(
                    {
                        "type": "tool_call",
                        "id": f"{request_id}-pod-count-scope",
                        "name": "pod_count_scope_resolve",
                        "summary": "요청에서 대상 이름과 namespace 범위 해석",
                    }
                )
                yield sse(
                    {
                        "type": "tool_result",
                        "detail": json.dumps(
                            {
                                "namespace": namespace or "all-accessible-namespaces",
                                "scope": scope_summary,
                                "targetName": target_name or "missing",
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        "id": f"{request_id}-pod-count-scope",
                        "name": "pod_count_scope_resolve",
                        "result": pod_count_query,
                        "status": "success" if target_name else "skipped",
                        "summary": (
                            f"대상 `{target_name}`, {scope_summary}"
                            if target_name
                            else f"대상 이름 미확인, {scope_summary}"
                        ),
                    }
                )
                if namespace:
                    deployments_path = f"/apis/apps/v1/namespaces/{path_segment(namespace)}/deployments"
                    pods_path = f"/api/v1/namespaces/{path_segment(namespace)}/pods"
                else:
                    deployments_path = "/apis/apps/v1/deployments"
                    pods_path = "/api/v1/pods"

                deployments_payload: Mapping[str, Any] | None = None
                pods_payload: Mapping[str, Any] | None = None
                pod_count_result: dict[str, Any] | None = None
                if not target_name:
                    pod_count_result = build_pod_count_investigation(
                        pod_count_query,
                        deployments_payload,
                        pods_payload,
                    )
                elif not OPENSHIFT_API_URL:
                    pod_count_result = {
                        "namespace": namespace,
                        "reason": "OPENSHIFT_API_URL is not configured",
                        "status": "unavailable",
                        "targetName": target_name,
                    }
                else:
                    async with httpx.AsyncClient(
                        verify=OPENSHIFT_API_CA_FILE,
                        timeout=httpx.Timeout(20.0, connect=5.0),
                    ) as client:
                        yield sse(
                            {
                                "type": "tool_call",
                                "id": f"{request_id}-pod-count-deployments",
                                "name": "pod_count_deployment_lookup",
                                "summary": f"Deployment 목록 조회: `{deployments_path}`",
                            }
                        )
                        deployments_payload = await fetch_ocp_json(
                            client,
                            deployments_path,
                            authorization,
                        )
                        matched_deployment_count = sum(
                            1
                            for deployment in resource_items(deployments_payload)
                            if metadata_name(deployment) == target_name
                            and (not namespace or metadata_namespace(deployment) == namespace)
                        )
                        deployment_status = "success" if deployments_payload else "skipped"
                        yield sse(
                            {
                                "type": "tool_result",
                                "detail": json.dumps(
                                    {
                                        "matchedDeployments": matched_deployment_count,
                                        "path": deployments_path,
                                        "receivedItems": len(resource_items(deployments_payload)),
                                        "targetName": target_name,
                                    },
                                    ensure_ascii=False,
                                    indent=2,
                                ),
                                "id": f"{request_id}-pod-count-deployments",
                                "name": "pod_count_deployment_lookup",
                                "result": {
                                    "matchedDeployments": matched_deployment_count,
                                    "path": deployments_path,
                                },
                                "status": deployment_status,
                                "summary": (
                                    f"Deployment `{target_name}` 후보 {matched_deployment_count}건 확인"
                                    if deployments_payload
                                    else "Deployment 목록을 받지 못해 Pod fallback 조회 준비"
                                ),
                            }
                        )

                        yield sse(
                            {
                                "type": "tool_call",
                                "id": f"{request_id}-pod-count-pods",
                                "name": "pod_count_pod_lookup",
                                "summary": f"Pod 목록 조회: `{pods_path}`",
                            }
                        )
                        pods_payload = await fetch_ocp_json(client, pods_path, authorization)
                        pod_items = resource_items(pods_payload)
                        yield sse(
                            {
                                "type": "tool_result",
                                "detail": json.dumps(
                                    {
                                        "path": pods_path,
                                        "receivedItems": len(pod_items),
                                        "targetName": target_name,
                                    },
                                    ensure_ascii=False,
                                    indent=2,
                                ),
                                "id": f"{request_id}-pod-count-pods",
                                "name": "pod_count_pod_lookup",
                                "result": {"path": pods_path, "receivedItems": len(pod_items)},
                                "status": "success" if pods_payload else "skipped",
                                "summary": (
                                    f"Pod 목록 {len(pod_items)}건 수신"
                                    if pods_payload
                                    else "Pod 목록을 받지 못함"
                                ),
                            }
                        )

                    if not pods_payload:
                        pod_count_result = {
                            "namespace": namespace,
                            "reason": f"Kubernetes API pod list was not returned for {pods_path}",
                            "status": "unavailable",
                            "targetName": target_name,
                        }
                    else:
                        yield sse(
                            {
                                "type": "tool_call",
                                "id": f"{request_id}-pod-count-match",
                                "name": "pod_count_selector_match",
                                "summary": "Deployment selector와 Pod label/name 매칭",
                            }
                        )
                        pod_count_result = build_pod_count_investigation(
                            pod_count_query,
                            deployments_payload,
                            pods_payload,
                        )
                        result_rows = pod_count_result.get("rows")
                        matched_pods = sum(
                            int(row.get("totalPods") or 0)
                            for row in (result_rows if isinstance(result_rows, list) else [])
                            if isinstance(row, Mapping)
                        )
                        match_strategy = str(pod_count_result.get("matchStrategy") or "none")
                        yield sse(
                            {
                                "type": "tool_result",
                                "detail": json.dumps(
                                    redact_sensitive(pod_count_result),
                                    ensure_ascii=False,
                                    indent=2,
                                ),
                                "id": f"{request_id}-pod-count-match",
                                "name": "pod_count_selector_match",
                                "result": {
                                    "matchedPods": matched_pods,
                                    "matchStrategy": match_strategy,
                                    "status": pod_count_result.get("status"),
                                },
                                "status": (
                                    "success"
                                    if pod_count_result.get("status") == "found"
                                    else "skipped"
                                ),
                                "summary": (
                                    f"`{match_strategy}` 방식으로 Pod {matched_pods}개 매칭"
                                    if pod_count_result.get("status") == "found"
                                    else "매칭되는 Deployment/Pod 없음"
                                ),
                            }
                        )

                yield sse(
                    {
                        "type": "tool_call",
                        "id": f"{request_id}-pod-count-investigation",
                        "name": "pod_count_investigation",
                        "summary": "Pod 개수 조회 결과 정리",
                    }
                )
                pod_count_result = pod_count_result or {
                    "namespace": namespace,
                    "reason": "Pod count investigation did not produce a result",
                    "status": "unavailable",
                    "targetName": target_name,
                }
                pod_count_text = pod_count_investigation_response(pod_count_result)
                result_status = str(pod_count_result.get("status") or "")
                pod_count_event = {
                    "type": "tool_result",
                    "detail": pod_count_text,
                    "id": f"{request_id}-pod-count-investigation",
                    "name": "pod_count_investigation",
                    "result": pod_count_result,
                    "status": "success" if result_status == "found" else "skipped",
                    "summary": "Pod 개수 직접 조회 완료",
                }
                yield sse(pod_count_event)
                for evidence_event in build_evidence_reference_events(
                    event=pod_count_event,
                    incident_id=incident_id,
                    run_id=run_id,
                    source_type="gateway-direct-evidence",
                    subject=subject,
                ):
                    yield sse(evidence_event)
                rca_context_event = current_rca_context_event("post_answer")
                LAST_RCA_CONTEXT = rca_context_event["context"]
                yield sse(rca_context_event)
                yield sse({"type": "text", "content": pod_count_text})
                yield sse(
                    {
                        "type": "run_status",
                        "runId": run_id,
                        "stage": "completed",
                        "message": "Gateway Pod 개수 직접 조회 완료",
                    }
                )
                yield sse("[DONE]")
                return

            if (
                page_context_aiops_execution_mode(req) == "unrestricted"
                and is_followup_execution_request(req.message)
            ):
                pending_plan_result = latest_pending_action_plan_result(subject)
                if not pending_plan_result:
                    contextual_request = recent_natural_action_request(req)
                    if contextual_request:
                        contextual_plan_result = await create_natural_action_plan(
                            contextual_request,
                            authorization,
                            subject,
                            incident_id=incident_id,
                            run_id=run_id,
                        )
                        if contextual_plan_result:
                            if contextual_plan_result.get("status") == "planned":
                                yield sse(
                                    {
                                        "type": "tool_call",
                                        "id": f"{request_id}-natural-action-followup",
                                        "name": "natural_action_followup",
                                        "summary": "최근 대화의 AIOps 조치 요청 후속 실행",
                                    }
                                )
                                followup_execution_result = await execute_natural_action_plan_result(
                                    contextual_plan_result,
                                    authorization,
                                    subject,
                                )
                                yield sse(
                                    {
                                        "type": "tool_result",
                                        "detail": json.dumps(
                                            redact_sensitive(followup_execution_result),
                                            ensure_ascii=False,
                                            indent=2,
                                        ),
                                        "id": f"{request_id}-natural-action-followup",
                                        "name": "natural_action_followup",
                                        "result": followup_execution_result,
                                        "status": (
                                            "success"
                                            if followup_execution_result.get("status") == "executed"
                                            else "failed"
                                        ),
                                        "summary": "최근 대화의 AIOps 조치 후속 실행 완료",
                                    }
                                )
                                yield sse(
                                    {
                                        "type": "text",
                                        "content": natural_action_execution_response(
                                            followup_execution_result
                                        ),
                                    }
                                )
                                yield sse(
                                    {
                                        "type": "run_status",
                                        "runId": run_id,
                                        "stage": "completed",
                                        "message": "Gateway 최근 맥락 조치 실행 완료",
                                    }
                                )
                                rca_context_event = current_rca_context_event("post_answer")
                                LAST_RCA_CONTEXT = rca_context_event["context"]
                                yield sse(rca_context_event)
                                yield sse("[DONE]")
                                return

                            yield sse(
                                {
                                    "type": "tool_result",
                                    "detail": json.dumps(
                                        redact_sensitive(contextual_plan_result),
                                        ensure_ascii=False,
                                        indent=2,
                                    ),
                                    "id": f"{request_id}-natural-action-followup",
                                    "name": "natural_action_followup",
                                    "result": contextual_plan_result,
                                    "status": "failed",
                                    "summary": "최근 대화의 AIOps 조치 대상 확인 실패",
                                }
                            )
                            yield sse(
                                {
                                    "type": "text",
                                    "content": natural_action_plan_response(contextual_plan_result),
                                }
                            )
                            rca_context_event = current_rca_context_event("post_answer")
                            LAST_RCA_CONTEXT = rca_context_event["context"]
                            yield sse(rca_context_event)
                            yield sse(
                                {
                                    "type": "run_status",
                                    "runId": run_id,
                                    "stage": "completed",
                                    "message": "Gateway 최근 맥락 조치 대상 확인 실패",
                                }
                            )
                            yield sse("[DONE]")
                            return

                    yield sse(
                        {
                            "type": "tool_result",
                            "detail": json.dumps(
                                {"status": "not_found", "reason": "no_pending_action_plan"},
                                ensure_ascii=False,
                                indent=2,
                            ),
                            "id": f"{request_id}-natural-action-followup",
                            "name": "natural_action_followup",
                            "result": {"status": "not_found", "reason": "no_pending_action_plan"},
                            "status": "skipped",
                            "summary": "실행할 Gateway Action Plan 없음",
                        }
                    )
                    yield sse({"type": "text", "content": no_pending_action_plan_response()})
                    rca_context_event = current_rca_context_event("post_answer")
                    LAST_RCA_CONTEXT = rca_context_event["context"]
                    yield sse(rca_context_event)
                    yield sse(
                        {
                            "type": "run_status",
                            "runId": run_id,
                            "stage": "completed",
                            "message": "Gateway 후속 실행 대상 없음",
                        }
                    )
                    yield sse("[DONE]")
                    return

                yield sse(
                    {
                        "type": "tool_call",
                        "id": f"{request_id}-natural-action-followup",
                        "name": "natural_action_followup",
                        "summary": "최근 AIOps Action Plan 후속 실행",
                    }
                )
                followup_execution_result = await execute_natural_action_plan_result(
                    pending_plan_result,
                    authorization,
                    subject,
                )
                yield sse(
                    {
                        "type": "tool_result",
                        "detail": json.dumps(
                            redact_sensitive(followup_execution_result),
                            ensure_ascii=False,
                            indent=2,
                        ),
                        "id": f"{request_id}-natural-action-followup",
                        "name": "natural_action_followup",
                        "result": followup_execution_result,
                        "status": (
                            "success"
                            if followup_execution_result.get("status") == "executed"
                            else "failed"
                        ),
                        "summary": "최근 AIOps Action Plan 후속 실행 완료",
                    }
                )
                yield sse(
                    {
                        "type": "text",
                        "content": natural_action_execution_response(followup_execution_result),
                    }
                )
                yield sse(
                    {
                        "type": "run_status",
                        "runId": run_id,
                        "stage": "completed",
                        "message": "Gateway 후속 조치 실행 완료",
                    }
                )
                rca_context_event = current_rca_context_event("post_answer")
                LAST_RCA_CONTEXT = rca_context_event["context"]
                yield sse(rca_context_event)
                yield sse("[DONE]")
                return

            if (
                policy.get("decision") == "action_proposal_only"
                and not crashloop_demo_target_from_request(req)
            ):
                natural_action_intent = parse_natural_action_intent(req)
                if not natural_action_intent:
                    unresolved_result = {
                        "executionMode": page_context_aiops_execution_mode(req),
                        "message": req.message,
                        "status": "unresolved",
                    }
                    yield sse(
                        {
                            "type": "tool_result",
                            "detail": json.dumps(
                                redact_sensitive(unresolved_result),
                                ensure_ascii=False,
                                indent=2,
                            ),
                            "id": f"{request_id}-natural-action-unresolved",
                            "name": "natural_action_unresolved",
                            "result": unresolved_result,
                            "status": "skipped",
                            "summary": "변경 요청 대상 해석 실패",
                        }
                    )
                    yield sse({"type": "text", "content": unresolved_natural_action_response(req)})
                    rca_context_event = current_rca_context_event("post_answer")
                    LAST_RCA_CONTEXT = rca_context_event["context"]
                    yield sse(rca_context_event)
                    yield sse(
                        {
                            "type": "run_status",
                            "runId": run_id,
                            "stage": "completed",
                            "message": "Gateway 변경 요청 해석 실패",
                        }
                    )
                    yield sse("[DONE]")
                    return

                if natural_action_intent and not execution_mode_allows_actions(req):
                    yield sse(
                        {
                            "type": "tool_result",
                            "detail": json.dumps(
                                redact_sensitive(
                                    {
                                        "executionMode": "read-only",
                                        "intent": natural_action_intent,
                                        "status": "skipped",
                                    }
                                ),
                                ensure_ascii=False,
                                indent=2,
                            ),
                            "id": f"{request_id}-natural-action-read-only",
                            "name": "natural_action_plan",
                            "result": {
                                "executionMode": "read-only",
                                "intent": natural_action_intent,
                                "status": "skipped",
                            },
                            "status": "skipped",
                            "summary": "읽기 전용 모드로 조치 계획 생성 생략",
                        }
                    )
                    yield sse({"type": "text", "content": natural_action_read_only_response(natural_action_intent)})
                    rca_context_event = current_rca_context_event("post_answer")
                    LAST_RCA_CONTEXT = rca_context_event["context"]
                    yield sse(rca_context_event)
                    yield sse(
                        {
                            "type": "run_status",
                            "runId": run_id,
                            "stage": "completed",
                            "message": "Gateway 읽기 전용 모드 안내 완료",
                        }
                    )
                    yield sse("[DONE]")
                    return

                natural_action_result = await create_natural_action_plan(
                    req,
                    authorization,
                    subject,
                    incident_id=incident_id,
                    run_id=run_id,
                )
                if natural_action_result:
                    yield sse(
                        {
                            "type": "tool_result",
                            "detail": json.dumps(
                                redact_sensitive(natural_action_result),
                                ensure_ascii=False,
                                indent=2,
                            ),
                            "id": f"{request_id}-natural-action-plan",
                            "name": "natural_action_plan",
                            "result": natural_action_result,
                            "status": (
                                "success"
                                if natural_action_result.get("status") == "planned"
                                else "failed"
                            ),
                            "summary": "자연어 조치 요청을 Action Plan으로 변환",
                        }
                    )
                    if (
                        page_context_aiops_execution_mode(req) == "unrestricted"
                        and natural_action_result.get("status") == "planned"
                    ):
                        yield sse(
                            {
                                "type": "tool_call",
                                "id": f"{request_id}-natural-action-execute",
                                "name": "natural_action_execute",
                                "summary": "실험용 자연어 AIOps 조치 즉시 실행",
                            }
                        )
                        natural_execution_result = await execute_natural_action_plan_result(
                            natural_action_result,
                            authorization,
                            subject,
                        )
                        yield sse(
                            {
                                "type": "tool_result",
                                "detail": json.dumps(
                                    redact_sensitive(natural_execution_result),
                                    ensure_ascii=False,
                                    indent=2,
                                ),
                                "id": f"{request_id}-natural-action-execute",
                                "name": "natural_action_execute",
                                "result": natural_execution_result,
                                "status": (
                                    "success"
                                    if natural_execution_result.get("status") == "executed"
                                    else "failed"
                                ),
                                "summary": "자연어 AIOps 조치 실행 완료",
                            }
                        )
                        yield sse(
                            {
                                "type": "text",
                                "content": natural_action_execution_response(natural_execution_result),
                            }
                        )
                        yield sse(
                            {
                                "type": "run_status",
                                "runId": run_id,
                                "stage": "completed",
                                "message": "Gateway 자연어 조치 실행 완료",
                            }
                        )
                        rca_context_event = current_rca_context_event("post_answer")
                        LAST_RCA_CONTEXT = rca_context_event["context"]
                        yield sse(rca_context_event)
                        yield sse("[DONE]")
                        return

                    yield sse({"type": "text", "content": natural_action_plan_response(natural_action_result)})
                    yield sse(
                        {
                            "type": "run_status",
                            "runId": run_id,
                            "stage": "completed",
                            "message": "Gateway 자연어 조치 계획 생성 완료",
                        }
                    )
                    rca_context_event = current_rca_context_event("post_answer")
                    LAST_RCA_CONTEXT = rca_context_event["context"]
                    yield sse(rca_context_event)
                    yield sse("[DONE]")
                    return

            if req.attachments:
                yield sse({"type": "tool_call", "name": "attachment_check"})
                yield sse(
                    {
                        "type": "tool_result",
                        "name": "attachment_check",
                        "result": {
                            "images": len(req.attachments),
                            "totalBytes": sum(item.size for item in req.attachments),
                        },
                    }
                )

            image_analysis = None
            if req.attachments:
                yield sse({"type": "tool_call", "name": "vision_analysis"})
                image_analysis = await analyze_image_attachments(req.attachments, req.message)
                yield sse(
                    {
                        "type": "tool_result",
                        "name": "vision_analysis",
                        "result": "ok" if image_analysis else "not_configured",
                    }
                )

            if should_collect_cronjob_activity_evidence(req.message, image_analysis):
                yield sse(
                    {
                        "type": "tool_call",
                        "id": f"{request_id}-cronjob-activity-evidence",
                        "name": "cronjob_activity_evidence",
                        "summary": "CronJob/Activity 주기 증거 수집",
                    }
                )
                try:
                    cronjob_context = "\n".join(
                        item for item in [req.message, image_analysis] if item
                    )
                    cronjob_evidence = await collect_cronjob_activity_evidence(
                        authorization,
                        cronjob_context,
                    )
                    evidence_status = (
                        "skipped"
                        if cronjob_evidence.startswith("CronJob activity evidence unavailable:")
                        else "success"
                    )
                    gateway_evidence = append_gateway_evidence(gateway_evidence, cronjob_evidence)
                    cronjob_event = {
                        "type": "tool_result",
                        "detail": cronjob_evidence,
                        "evidenceType": "cronjob",
                        "id": f"{request_id}-cronjob-activity-evidence",
                        "missingReason": cronjob_evidence
                        if evidence_status != "success"
                        else "",
                        "name": "cronjob_activity_evidence",
                        "sourcePath": "/apis/batch/v1/cronjobs,/apis/batch/v1/jobs?limit=500",
                        "status": evidence_status,
                        "summary": _evidence_summary(
                            "CronJob/Activity 주기 증거",
                            evidence_status,
                        ),
                    }
                    yield sse(cronjob_event)
                    for evidence_event in build_evidence_reference_events(
                        event=cronjob_event,
                        incident_id=incident_id,
                        run_id=run_id,
                        source_type="gateway-preflight-evidence",
                        subject=subject,
                    ):
                        yield sse(evidence_event)
                except Exception as exc:
                    cronjob_evidence = f"CronJob activity evidence unavailable: {safe_exception_text(exc)}"
                    gateway_evidence = append_gateway_evidence(gateway_evidence, cronjob_evidence)
                    cronjob_event = {
                        "type": "tool_result",
                        "detail": cronjob_evidence,
                        "id": f"{request_id}-cronjob-activity-evidence",
                        "name": "cronjob_activity_evidence",
                        "evidenceType": "cronjob",
                        "missingReason": safe_exception_text(exc),
                        "status": "error",
                        "summary": "CronJob/Activity 주기 증거 수집 실패",
                    }
                    yield sse(cronjob_event)
                    for evidence_event in build_evidence_reference_events(
                        event=cronjob_event,
                        incident_id=incident_id,
                        run_id=run_id,
                        source_type="gateway-preflight-evidence",
                        subject=subject,
                    ):
                        yield sse(evidence_event)

            if should_collect_pod_status_evidence(req.message):
                yield sse(
                    {
                        "type": "tool_call",
                        "id": f"{request_id}-pod-status-evidence",
                        "name": "pod_status_evidence",
                        "summary": "Pod 상태/재시작 증거 수집",
                    }
                )
                try:
                    pod_list_requested = is_pod_list_request(req.message)
                    pod_evidence = await collect_pod_status_evidence(
                        authorization,
                        include_pod_list=pod_list_requested,
                        list_namespace=pod_list_namespace(req) if pod_list_requested else "",
                    )
                    evidence_status = (
                        "skipped"
                        if pod_evidence.startswith("Pod status evidence unavailable:")
                        else "success"
                    )
                    gateway_evidence = append_gateway_evidence(gateway_evidence, pod_evidence)
                    pod_event = {
                        "type": "tool_result",
                        "detail": pod_evidence,
                        "evidenceType": "pod_status",
                        "id": f"{request_id}-pod-status-evidence",
                        "missingReason": pod_evidence if evidence_status != "success" else "",
                        "name": "pod_status_evidence",
                        "sourcePath": "/api/v1/pods,/apis/apps/v1/deployments,/apis/config.openshift.io/v1/clusteroperators",
                        "status": evidence_status,
                        "summary": _evidence_summary("Pod 상태/재시작 증거", evidence_status),
                    }
                    pod_snapshot_event = {
                        "type": "tool_result",
                        "detail": pod_evidence,
                        "evidenceType": "snapshot",
                        "id": f"{request_id}-pod-snapshot-evidence",
                        "missingReason": pod_evidence if evidence_status != "success" else "",
                        "name": "pod_snapshot_evidence",
                        "sourcePath": "/api/v1/pods,/apis/apps/v1/deployments,/apis/config.openshift.io/v1/clusteroperators",
                        "status": evidence_status,
                        "summary": _evidence_summary("Pod snapshot 증거", evidence_status),
                    }
                    yield sse(pod_event)
                    for evidence_event in build_evidence_reference_events(
                        event=pod_event,
                        incident_id=incident_id,
                        run_id=run_id,
                        source_type="gateway-preflight-evidence",
                        subject=subject,
                    ):
                        yield sse(evidence_event)
                    yield sse(pod_snapshot_event)
                    for evidence_event in build_evidence_reference_events(
                        event=pod_snapshot_event,
                        incident_id=incident_id,
                        run_id=run_id,
                        source_type="gateway-preflight-evidence",
                        subject=subject,
                    ):
                        yield sse(evidence_event)
                except Exception as exc:
                    pod_evidence = f"Pod status evidence unavailable: {safe_exception_text(exc)}"
                    gateway_evidence = append_gateway_evidence(gateway_evidence, pod_evidence)
                    pod_event = {
                        "type": "tool_result",
                        "detail": pod_evidence,
                        "id": f"{request_id}-pod-status-evidence",
                        "name": "pod_status_evidence",
                        "evidenceType": "pod_status",
                        "missingReason": safe_exception_text(exc),
                        "status": "error",
                        "summary": "Pod 상태/재시작 증거 수집 실패",
                    }
                    pod_snapshot_event = {
                        "type": "tool_result",
                        "detail": pod_evidence,
                        "id": f"{request_id}-pod-snapshot-evidence",
                        "name": "pod_snapshot_evidence",
                        "evidenceType": "snapshot",
                        "missingReason": safe_exception_text(exc),
                        "status": "error",
                        "summary": "Pod snapshot 증거 수집 실패",
                    }
                    yield sse(pod_event)
                    for evidence_event in build_evidence_reference_events(
                        event=pod_event,
                        incident_id=incident_id,
                        run_id=run_id,
                        source_type="gateway-preflight-evidence",
                        subject=subject,
                    ):
                        yield sse(evidence_event)
                    yield sse(pod_snapshot_event)
                    for evidence_event in build_evidence_reference_events(
                        event=pod_snapshot_event,
                        incident_id=incident_id,
                        run_id=run_id,
                        source_type="gateway-preflight-evidence",
                        subject=subject,
                    ):
                        yield sse(evidence_event)

            crashloop_demo_target = crashloop_demo_target_from_request(req)
            official_restart_namespace = official_namespace_restart_namespace(runtime_tool_plan)
            if official_restart_namespace and not crashloop_demo_target:
                yield sse(
                    {
                        "type": "tool_call",
                        "id": f"{request_id}-official-namespace-restart-evidence",
                        "name": "official_namespace_restart_evidence",
                        "summary": f"공식 Evidence RCA namespace 재시작 증거 수집: `{official_restart_namespace}`",
                    }
                )
                try:
                    official_restart_events = await collect_official_namespace_restart_evidence_events(
                        authorization,
                        official_restart_namespace,
                        request_id,
                    )
                except Exception as exc:
                    safe_detail = safe_exception_text(exc)
                    official_restart_events = official_namespace_restart_skipped_evidence_events(
                        namespace=official_restart_namespace,
                        request_id=request_id,
                        reason=safe_detail,
                        detail=safe_detail,
                    )

                for official_restart_event in official_restart_events:
                    gateway_evidence = append_gateway_evidence(
                        gateway_evidence,
                        str(
                            official_restart_event.get("detail")
                            or official_restart_event.get("summary")
                            or ""
                        ),
                    )
                    yield sse(official_restart_event)
                    for evidence_event in build_evidence_reference_events(
                        event=official_restart_event,
                        incident_id=incident_id,
                        run_id=run_id,
                        source_type="gateway-preflight-evidence",
                        subject=subject,
                    ):
                        yield sse(evidence_event)

            if crashloop_demo_target:
                yield sse(
                    {
                        "type": "tool_call",
                        "id": f"{request_id}-crashloop-demo-evidence",
                        "name": "crashloop_demo_evidence",
                        "summary": "CrashLoopBackOff 시연 증거 수집",
                    }
                )
                try:
                    crashloop_events = await collect_crashloop_demo_evidence_events(
                        authorization,
                        crashloop_demo_target,
                        request_id,
                    )
                except Exception as exc:
                    safe_detail = safe_exception_text(exc)
                    crashloop_events = [
                        {
                            "type": "tool_result",
                            "detail": f"CrashLoop event evidence unavailable: {safe_detail}",
                            "evidenceType": "event",
                            "id": f"{request_id}-crashloop-event-evidence",
                            "missingReason": safe_detail,
                            "name": "crashloop_event_evidence",
                            "status": "error",
                            "summary": "CrashLoop Event 증거 수집 실패",
                        },
                        {
                            "type": "tool_result",
                            "detail": f"CrashLoop previous log availability unavailable: {safe_detail}",
                            "evidenceType": "pod_log",
                            "id": f"{request_id}-crashloop-log-availability",
                            "missingReason": safe_detail,
                            "name": "crashloop_log_availability",
                            "status": "error",
                            "summary": "CrashLoop 이전 로그 가용성 확인 실패",
                        },
                        {
                            "type": "tool_result",
                            "detail": f"CrashLoop Pod snapshot unavailable: {safe_detail}",
                            "evidenceType": "snapshot",
                            "id": f"{request_id}-crashloop-pod-snapshot",
                            "missingReason": safe_detail,
                            "name": "crashloop_pod_snapshot",
                            "status": "error",
                            "summary": "CrashLoop Pod snapshot 증거 수집 실패",
                        },
                    ]

                for crashloop_event in crashloop_events:
                    gateway_evidence = append_gateway_evidence(
                        gateway_evidence,
                        str(crashloop_event.get("detail") or crashloop_event.get("summary") or ""),
                    )
                    yield sse(crashloop_event)
                    for evidence_event in build_evidence_reference_events(
                        event=crashloop_event,
                        incident_id=incident_id,
                        run_id=run_id,
                        source_type="gateway-preflight-evidence",
                        subject=subject,
                    ):
                        yield sse(evidence_event)

            if (
                str(policy.get("decision") or "") == "allow_read_only_evidence"
                and should_collect_rca_signal_evidence(req.message)
            ):
                rca_preflight_collectors = [
                    (
                        "node-status-rca-evidence",
                        "node_status_evidence",
                        "Node 상태 RCA 증거 수집",
                        collect_node_status_rca_evidence,
                    ),
                    (
                        "active-alerts-rca-evidence",
                        "active_alerts_evidence",
                        "Active Alert RCA 증거 수집",
                        collect_active_alerts_rca_evidence,
                    ),
                    (
                        "restart-metric-rca-evidence",
                        "restart_metric_evidence",
                        "Restart metric RCA 증거 수집",
                        collect_restart_metric_rca_evidence,
                    ),
                ]
                for suffix, event_name, call_summary, collector in rca_preflight_collectors:
                    event_id = f"{request_id}-{suffix}"
                    yield sse(
                        {
                            "type": "tool_call",
                            "id": event_id,
                            "name": event_name,
                            "summary": call_summary,
                        }
                    )
                    try:
                        evidence_result = await collector(authorization)
                        evidence_detail = str(evidence_result.get("detail") or "")
                        gateway_evidence = append_gateway_evidence(gateway_evidence, evidence_detail)
                        evidence_event = {
                            "type": "tool_result",
                            "detail": evidence_detail,
                            "evidenceType": evidence_result.get("evidenceType"),
                            "id": event_id,
                            "missingReason": evidence_result.get("missingReason"),
                            "name": event_name,
                            "sourcePath": evidence_result.get("sourcePath"),
                            "status": evidence_result.get("status") or "error",
                            "summary": evidence_result.get("summary") or f"{call_summary} 완료",
                        }
                    except Exception as exc:
                        safe_detail = safe_exception_text(exc)
                        evidence_type = (
                            "node"
                            if event_name == "node_status_evidence"
                            else "alert"
                            if event_name == "active_alerts_evidence"
                            else "metric"
                        )
                        evidence_detail = f"{call_summary} unavailable: {safe_detail}"
                        gateway_evidence = append_gateway_evidence(gateway_evidence, evidence_detail)
                        evidence_event = {
                            "type": "tool_result",
                            "detail": evidence_detail,
                            "evidenceType": evidence_type,
                            "id": event_id,
                            "missingReason": safe_detail,
                            "name": event_name,
                            "status": "error",
                            "summary": f"{call_summary} 실패",
                        }

                    yield sse(evidence_event)
                    for evidence_ref_event in build_evidence_reference_events(
                        event=evidence_event,
                        incident_id=incident_id,
                        run_id=run_id,
                        source_type="gateway-preflight-evidence",
                        subject=subject,
                    ):
                        yield sse(evidence_ref_event)

            yield sse(
                {
                    "type": "tool_call",
                    "id": f"{request_id}-rag-context-evidence",
                    "name": "rag_context_evidence",
                    "summary": "RAG 문서 근거 검색",
                }
            )
            try:
                rag_request = RagSearchCreate(
                    query=req.message,
                    topK=3,
                    includeContent=False,
                    runId=run_id,
                )
                rag_status, rag_reason, rag_results = search_pgvector_runbooks(
                    rag_request,
                    subject=subject,
                )
                rag_detail = build_rag_context_detail(rag_results, rag_reason)
                gateway_evidence = append_gateway_evidence(gateway_evidence, rag_detail)
                rag_answer_citation_text = build_rag_answer_citation_text(rag_results)
                rag_event = {
                    "type": "tool_result",
                    "detail": rag_detail,
                    "evidenceType": "runbook",
                    "id": f"{request_id}-rag-context-evidence",
                    "missingReason": "" if rag_results else rag_reason,
                    "name": "rag_context_evidence",
                    "result": {
                        "query": req.message,
                        "resultCount": len(rag_results),
                        "results": [
                            {
                                "documentId": result.get("documentId"),
                                "score": result.get("score"),
                                "sourceType": result.get("sourceType"),
                                "sourceUri": result.get("sourceUri"),
                                "title": result.get("title"),
                            }
                            for result in rag_results
                        ],
                        "status": rag_status,
                    },
                    "sourcePath": "/v1/rag/search",
                    "status": "success" if rag_results else "skipped",
                    "summary": (
                        f"RAG 근거 {len(rag_results)}건 검색"
                        if rag_results
                        else "RAG 근거 검색 결과 없음"
                    ),
                }
            except Exception as exc:
                rag_detail = f"RAG evidence unavailable: {safe_exception_text(exc)}"
                gateway_evidence = append_gateway_evidence(gateway_evidence, rag_detail)
                rag_event = {
                    "type": "tool_result",
                    "detail": rag_detail,
                    "evidenceType": "runbook",
                    "id": f"{request_id}-rag-context-evidence",
                    "missingReason": safe_exception_text(exc),
                    "name": "rag_context_evidence",
                    "sourcePath": "/v1/rag/search",
                    "status": "error",
                    "summary": "RAG 근거 검색 실패",
                }
            yield sse(rag_event)
            for evidence_ref_event in build_evidence_reference_events(
                event=rag_event,
                incident_id=incident_id,
                run_id=run_id,
                source_type="gateway-rag-evidence",
                subject=subject,
            ):
                yield sse(evidence_ref_event)

            rca_context_event = current_rca_context_event("pre_answer")
            LAST_RCA_CONTEXT = rca_context_event["context"]
            yield sse(rca_context_event)
            pre_ols_safety_contract = build_runtime_safety_contract(
                mutations_enabled=MUTATIONS_ENABLED,
                unrestricted_commands_enabled=UNRESTRICTED_COMMANDS_ENABLED,
                diagnostics_enabled=DIAGNOSTICS_ENABLED,
                record_store_enabled=RECORD_STORE_ENABLED,
                diagnostics_controller_configured=bool(HOST_DIAGNOSTICS_CONTROLLER_URL),
                lightspeed_status=redact_sensitive(dict(OLS_STREAM_STATUS)),
                latest_runtime_tool_plan=runtime_tool_plan,
                latest_rca_context=rca_context_event["context"],
            )
            ols_gateway_context = build_ols_gateway_context(
                tool_plan=runtime_tool_plan,
                rca_context=rca_context_event["context"],
                safety_contract=pre_ols_safety_contract,
                policy=policy,
                gateway_evidence=gateway_evidence,
            )

            yield sse(
                {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": "lightspeed",
                    "message": "실제 OpenShift Lightspeed로 스트림 요청 전달",
                    "gatewayContextDigest": ols_gateway_context["metadata"]["digest"],
                    "rcaContextDigest": rca_context_event["context"]["metadata"]["digest"],
                }
            )
            ols_query = build_ols_query(
                req,
                image_analysis,
                policy=policy,
                subject=subject,
                gateway_evidence=gateway_evidence,
            )
            emitted_answer_text = False
            ols_tool_results: list[Mapping[str, Any]] = []
            try:
                async for ols_event in stream_with_heartbeats(
                    call_ols_stream(
                        authorization,
                        ols_query,
                        req.conversationId,
                        req.attachments,
                        ols_gateway_context,
                    ),
                    run_id,
                ):
                    normalized_event = normalize_ols_event(ols_event)
                    if normalized_event.get("type") == "text":
                        filtered_content = text_reference_filter.filter(
                            str(normalized_event.get("content") or "")
                        )
                        if filtered_content:
                            if filtered_content.strip():
                                emitted_answer_text = True
                            text_event: dict[str, Any] = {"type": "text", "content": filtered_content}
                            for key in (
                                "fallbackAnswer",
                                "gatewayContextDigest",
                                "source",
                                "streamProbe",
                            ):
                                if key in normalized_event:
                                    text_event[key] = normalized_event[key]
                            yield sse(text_event)
                        continue

                    if normalized_event.get("type") == "end":
                        final_text = text_reference_filter.flush()
                        if final_text:
                            if final_text.strip():
                                emitted_answer_text = True
                            yield sse({"type": "text", "content": final_text})

                    yield sse(normalized_event)
                    if normalized_event.get("type") == "tool_result":
                        ols_tool_results.append(dict(normalized_event))
                        for evidence_event in build_evidence_reference_events(
                            event=normalized_event,
                            incident_id=incident_id,
                            run_id=run_id,
                            source_type="ols-tool-result",
                            subject=subject,
                        ):
                            yield sse(evidence_event)
            except Exception as exc:
                safe_detail = safe_exception_text(exc)
                update_ols_stream_status(
                    "failed",
                    context_digest=ols_gateway_context["metadata"]["digest"],
                    fallback_active=True,
                    reason=safe_detail,
                )
                ols_error_event = {
                    "type": "tool_result",
                    "detail": safe_detail,
                    "id": f"{request_id}-lightspeed-stream",
                    "name": "lightspeed_stream",
                    "status": "error",
                    "summary": "OpenShift Lightspeed stream failed; Gateway fallback will answer from collected evidence",
                    "gatewayContextDigest": ols_gateway_context["metadata"]["digest"],
                    "fallbackAnswer": True,
                }
                ols_tool_results.append(ols_error_event)
                yield sse(ols_error_event)

            if not emitted_answer_text:
                update_ols_stream_status(
                    "failed",
                    context_digest=ols_gateway_context["metadata"]["digest"],
                    fallback_active=True,
                    reason="OLS stream ended without answer text; Gateway fallback emitted",
                )
                yield sse(
                    {
                        "type": "text",
                        "content": build_empty_answer_fallback(
                            req,
                            policy,
                            ols_tool_results,
                            gateway_evidence,
                        ),
                        "source": "gateway_fallback",
                        "fallbackAnswer": True,
                        "gatewayContextDigest": ols_gateway_context["metadata"]["digest"],
                        "streamProbe": "failed",
                    }
                )

            if rag_answer_citation_text:
                yield sse(
                    {
                        "type": "text",
                        "content": rag_answer_citation_text,
                        "source": "gateway_rag_citation",
                        "gatewayContextDigest": ols_gateway_context["metadata"]["digest"],
                    }
                )

            crashloop_answer_contract = build_crashloop_demo_answer_contract_text(req, run_id)
            if crashloop_answer_contract:
                yield sse(
                    {
                        "type": "text",
                        "content": crashloop_answer_contract,
                        "source": "gateway_answer_contract",
                        "answerContract": "crashloop-v0.1.3",
                        "gatewayContextDigest": ols_gateway_context["metadata"]["digest"],
                    }
                )

            rca_context_event = current_rca_context_event("post_answer")
            LAST_RCA_CONTEXT = rca_context_event["context"]
            yield sse(rca_context_event)

            yield sse(
                {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": "completed",
                    "message": "Gateway 실행 루프 완료",
                }
            )
            completed_audit_record = build_trace_record(
                action="chat_request_completed",
                incident_id=incident_id,
                policy=policy,
                request_id=request_id,
                run_id=run_id,
                subject=subject,
            )
            log_audit_record(completed_audit_record)
            increment_metric("aiops_chat_completed_total")
            record_workflow(
                run_id=run_id,
                incident_id=incident_id,
                policy=policy,
                request_id=request_id,
                stage="completed",
                status="completed",
                subject=subject,
            )
            yield sse("[DONE]")
        except HTTPException as exc:
            error_message = http_exception_message(exc)
            error_tool_plan = runtime_tool_plan or build_runtime_tool_plan(
                req.message,
                page_context=normalize_console_page_context(req.pageContext),
                execution_mode=page_context_aiops_execution_mode(req),
            )
            rca_context_event = build_rca_context_stream_event(
                req=req,
                runtime_tool_plan=error_tool_plan,
                run_id=run_id,
                incident_id=incident_id,
                phase="failed",
            )
            LAST_RCA_CONTEXT = rca_context_event["context"]
            yield sse(rca_context_event)
            log_audit_record(
                build_trace_record(
                    action="chat_request_failed",
                    incident_id=incident_id,
                    policy=policy,
                    request_id=request_id,
                    run_id=run_id,
                    subject=subject,
                    target={"error": error_message, "statusCode": exc.status_code},
                )
            )
            increment_metric("aiops_chat_failed_total")
            record_workflow(
                run_id=run_id,
                incident_id=incident_id,
                policy=policy,
                request_id=request_id,
                stage="failed",
                status="failed",
                subject=subject,
                target={"error": error_message, "statusCode": exc.status_code},
            )

            if is_openshift_user_auth_failure(exc):
                yield sse(
                    {
                        "type": "tool_result",
                        "detail": error_message,
                        "id": f"{request_id}-subject-review",
                        "name": "subject_review",
                        "result": redact_sensitive(exc.detail),
                        "status": "error",
                        "summary": "OpenShift 사용자 인증 갱신 필요",
                    }
                )
                yield sse({"type": "text", "content": error_message})
                yield sse(
                    {
                        "type": "run_status",
                        "runId": run_id,
                        "stage": "failed",
                        "message": "OpenShift 사용자 인증 갱신 필요",
                    }
                )
                yield sse("[DONE]")
                return

            yield sse(
                {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": "failed",
                    "message": error_message,
                }
            )
            yield sse({"type": "error", "message": error_message})
            yield sse("[DONE]")
        except Exception as exc:
            safe_detail = safe_exception_text(exc)
            error_tool_plan = runtime_tool_plan or build_runtime_tool_plan(
                req.message,
                page_context=normalize_console_page_context(req.pageContext),
                execution_mode=page_context_aiops_execution_mode(req),
            )
            rca_context_event = build_rca_context_stream_event(
                req=req,
                runtime_tool_plan=error_tool_plan,
                run_id=run_id,
                incident_id=incident_id,
                phase="failed",
            )
            LAST_RCA_CONTEXT = rca_context_event["context"]
            yield sse(rca_context_event)
            log_audit_record(
                build_trace_record(
                    action="chat_request_failed",
                    incident_id=incident_id,
                    policy=policy,
                    request_id=request_id,
                    run_id=run_id,
                    subject=subject,
                    target={"error": safe_detail},
                )
            )
            increment_metric("aiops_chat_failed_total")
            record_workflow(
                run_id=run_id,
                incident_id=incident_id,
                policy=policy,
                request_id=request_id,
                stage="failed",
                status="failed",
                subject=subject,
                target={"error": safe_detail},
            )
            yield sse(
                {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": "failed",
                    "message": safe_detail,
                }
            )
            yield sse({"type": "error", "message": safe_detail})
            yield sse("[DONE]")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
