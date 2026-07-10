from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import math
import mimetypes
import os
import re
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import httpx
from fastapi import HTTPException
from pydantic import Field

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

from .schemas import RagSearchCreate, RagSearchFilters, StrictBaseModel
from .security import canonical_digest, now_rfc3339, redact_sensitive, safe_subject
from .settings import (
    first_env_value,
    infer_embedding_api_style,
    parse_bool,
    parse_float_env,
)


RAG_BACKEND_URL = os.getenv("KOMSCO_AI_RAG_BACKEND_URL", "").rstrip("/")
RAG_BACKEND_TYPE = os.getenv("KOMSCO_AI_RAG_BACKEND_TYPE", "pgvector")
RAG_COLLECTION = os.getenv("KOMSCO_AI_RAG_COLLECTION", "komsco-aiops-runbooks")
RAG_EMBEDDING_PROVIDER = first_env_value("KOMSCO_AI_EMBEDDING_PROVIDER")
RAG_EMBEDDING_SERVICE_URL = first_env_value(
    "KOMSCO_AI_EMBEDDING_BASE_URL",
    "KOMSCO_AI_RAG_EMBEDDING_SERVICE_URL",
).rstrip("/")
RAG_EMBEDDING_API_STYLE = (
    first_env_value("KOMSCO_AI_EMBEDDING_API_STYLE")
    or infer_embedding_api_style(
        RAG_EMBEDDING_PROVIDER,
        RAG_EMBEDDING_SERVICE_URL,
    )
).strip().lower()
RAG_EMBEDDING_MODEL = first_env_value(
    "KOMSCO_AI_EMBEDDING_MODEL",
    "KOMSCO_AI_RAG_EMBEDDING_MODEL",
)
RAG_VECTOR_DIMENSIONS = int(
    first_env_value(
        "KOMSCO_AI_EMBEDDING_DIMENSIONS",
        "KOMSCO_AI_RAG_VECTOR_DIMENSIONS",
    )
    or "0"
)
RAG_EFFECTIVE_VECTOR_DIMENSIONS = RAG_VECTOR_DIMENSIONS or 64
RAG_DEMO_SEED_ENABLED = parse_bool(os.getenv("KOMSCO_AI_RAG_DEMO_SEED_ENABLED"), default=True)
RAG_UPLOAD_MAX_BYTES = int(os.getenv("KOMSCO_AI_RAG_UPLOAD_MAX_BYTES", str(5 * 1024 * 1024)))
RAG_UPLOAD_MAX_CHARS = int(os.getenv("KOMSCO_AI_RAG_UPLOAD_MAX_CHARS", "120000"))
RAG_UPLOAD_MAX_CHUNKS = int(os.getenv("KOMSCO_AI_RAG_UPLOAD_MAX_CHUNKS", "80"))
RAG_UPLOAD_MAX_CHUNK_CHARS = int(os.getenv("KOMSCO_AI_RAG_UPLOAD_MAX_CHUNK_CHARS", "1200"))
RAG_UPLOAD_CHUNK_OVERLAP_CHARS = int(os.getenv("KOMSCO_AI_RAG_UPLOAD_CHUNK_OVERLAP_CHARS", "0"))
RAG_EMBEDDING_TIMEOUT_SECONDS = parse_float_env(
    "KOMSCO_AI_EMBEDDING_TIMEOUT_SECONDS",
    "KOMSCO_AI_RAG_EMBEDDING_TIMEOUT_SECONDS",
    default=10.0,
)
RAG_SYNC_DIR = os.getenv("KOMSCO_AI_RAG_SYNC_DIR", "")
RAG_SYNC_SOURCE_TYPE = os.getenv("KOMSCO_AI_RAG_SYNC_SOURCE_TYPE", "runbook")
RAG_SYNC_ACL_GROUPS = [
    g.strip()
    for g in os.getenv("KOMSCO_AI_RAG_SYNC_ACL_GROUPS", "aiops-admins").split(",")
    if g.strip()
]
RAG_SYNC_CUSTOMER = os.getenv("KOMSCO_AI_RAG_SYNC_CUSTOMER", "komsco")
RAG_SYNC_NAMESPACE = os.getenv("KOMSCO_AI_RAG_SYNC_NAMESPACE", "komsco-ai-kugnus")
RAG_SYNC_VERSION = os.getenv("KOMSCO_AI_RAG_SYNC_VERSION", "v0.1.7")
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
            "Pod 재시작 RCA는 Event, previous container log, restart metric, Pod snapshot 순서로 확인 자료를 수집한다. "
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


def split_rag_upload_chunks(
    content: str,
    *,
    max_chars: int | None = None,
    overlap_chars: int | None = None,
) -> list[str]:
    limit = max_chars or RAG_UPLOAD_MAX_CHUNK_CHARS
    effective_overlap = overlap_chars if overlap_chars is not None else RAG_UPLOAD_CHUNK_OVERLAP_CHARS
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
    result = chunks[:RAG_UPLOAD_MAX_CHUNKS]
    if effective_overlap <= 0 or len(result) <= 1:
        return result
    overlapped: list[str] = [result[0]]
    for i in range(1, len(result)):
        body = result[i]
        available = limit - len(body) - 2  # reserve 2 for "\n\n" separator
        raw_tail = result[i - 1][-effective_overlap:].strip()
        tail = raw_tail[:available] if available > 0 and raw_tail else ""
        overlapped.append(f"{tail}\n\n{body}" if tail else body)
    return overlapped


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
    if requested in {"approved-exec", "dangerous", "evidence-check"}:
        return requested
    return "approved-exec"


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


_rag_embedding_model_warned = False
_rag_embedding_fallback_warned = False


def _warn_embedding_fallback(raw_vec: list[float] | None) -> None:
    """Emit a one-time warning when the embedding service result cannot be used."""
    global _rag_embedding_fallback_warned
    if not RAG_EMBEDDING_SERVICE_URL or _rag_embedding_fallback_warned:
        return
    import warnings
    reason = (
        f"expected {RAG_EFFECTIVE_VECTOR_DIMENSIONS}-dim but got {len(raw_vec)}-dim; "
        "set KOMSCO_AI_EMBEDDING_DIMENSIONS to match the service output dimensions"
        if raw_vec
        else "embedding service returned None (connection error or bad response)"
    )
    warnings.warn(
        f"RAG embedding service fallback active — {reason}. "
        "Chunks will be stored with hashing-bow-v1 until this is resolved.",
        RuntimeWarning,
        stacklevel=3,
    )
    _rag_embedding_fallback_warned = True


def build_rag_embedding(value: str, dimensions: int | None = None) -> list[float]:
    global _rag_embedding_model_warned
    if RAG_EMBEDDING_MODEL and not _rag_embedding_model_warned:
        import warnings
        warnings.warn(
            f"KOMSCO_AI_EMBEDDING_MODEL={RAG_EMBEDDING_MODEL!r} is configured "
            "but hashing-bow-v1 fallback is being used for this embedding call. "
            "Check the embedding service URL, response dimensions, or timeout if semantic-service was expected.",
            stacklevel=2,
        )
        _rag_embedding_model_warned = True
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


async def call_embedding_service_async(text: str) -> list[float] | None:
    """Call external embedding service; returns None on failure (caller falls back to hashing).

    Supports embedding API formats used by company and local model providers:
    - Ollama native       : POST /api/embed       {"model": ..., "input": text}
    - OpenAI-compat TEI  : POST /v1/embeddings  {"input": text, "model": ...}
    - TEI native         : POST /embed           {"inputs": text}
    - Ollama legacy      : POST /api/embeddings  {"model": ..., "prompt": text}
    """
    if not RAG_EMBEDDING_SERVICE_URL:
        return None

    # Resolve endpoint URL and request payload.
    # _has_version_path: URL contains a versioned path segment (/v1, /v2, …) — indicates OpenAI-compat.
    # Bare-hostname + model name also implies OpenAI-compat; in that case append the standard path.
    url = RAG_EMBEDDING_SERVICE_URL.rstrip("/")
    _has_version_path = bool(re.search(r"/v\d+(?:/|$)", url))
    style = RAG_EMBEDDING_API_STYLE
    if style == "ollama":
        if url.endswith("/api/embed"):
            pass
        elif url.endswith("/api"):
            url = url + "/embed"
        else:
            url = url + "/api/embed"
        payload = {"input": text}
        if RAG_EMBEDDING_MODEL:
            payload["model"] = RAG_EMBEDDING_MODEL
    elif style in {"openai", "openai-compatible", "tei-openai"} or (
        not style and (bool(RAG_EMBEDDING_MODEL) or _has_version_path)
    ):
        if re.search(r"/v\d+$", url):
            url = url + "/embeddings"
        elif not _has_version_path:
            url = url + "/v1/embeddings"
        payload: dict[str, Any] = {"input": text}
        if RAG_EMBEDDING_MODEL:
            payload["model"] = RAG_EMBEDDING_MODEL
    else:
        if style == "tei" and not url.endswith("/embed"):
            url = url + "/embed"
        payload = {"inputs": text}

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(RAG_EMBEDDING_TIMEOUT_SECONDS, connect=5.0)
        ) as client:
            resp = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
            resp.raise_for_status()
            data = resp.json()
            # OpenAI-compat: {"data": [{"embedding": [...]}]}
            if isinstance(data, dict) and "data" in data:
                items = data["data"]
                if items and isinstance(items[0], dict) and "embedding" in items[0]:
                    return [float(v) for v in items[0]["embedding"]]
            # TEI native: [[...]] or [...]
            if isinstance(data, list) and data:
                vec = data[0] if isinstance(data[0], list) else data
                return [float(v) for v in vec]
            # Ollama: {"embedding": [...]}
            if isinstance(data, dict) and "embedding" in data:
                return [float(v) for v in data["embedding"]]
            # Ollama /api/embed: {"embeddings": [[...]]}
            if isinstance(data, dict) and "embeddings" in data:
                embeddings = data["embeddings"]
                if isinstance(embeddings, list) and embeddings:
                    vec = embeddings[0] if isinstance(embeddings[0], list) else embeddings
                    return [float(v) for v in vec]
            return None
    except Exception:
        return None


def pgvector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{item:.6f}" for item in vector) + "]"


RAG_MIGRATIONS: list[tuple[int, str, str]] = [
    (1, "initial schema", ""),
    (
        2,
        "add content_chars to chunks",
        "ALTER TABLE aiops_rag_chunks ADD COLUMN IF NOT EXISTS content_chars integer",
    ),
    (
        3,
        "add embedding_model to chunks",
        "ALTER TABLE aiops_rag_chunks ADD COLUMN IF NOT EXISTS embedding_model text NOT NULL DEFAULT 'hashing-bow-v1'",
    ),
]


def apply_rag_migrations(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS aiops_rag_schema_version (
          version integer PRIMARY KEY,
          description text NOT NULL,
          applied_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    applied = {
        row["version"]
        for row in conn.execute("SELECT version FROM aiops_rag_schema_version").fetchall()
    }
    for version, description, sql in RAG_MIGRATIONS:
        if version in applied:
            continue
        if sql:
            conn.execute(sql)
        conn.execute(
            "INSERT INTO aiops_rag_schema_version (version, description) VALUES (%s, %s)",
            (version, description),
        )


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
    apply_rag_migrations(conn)


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


async def persist_rag_upload_document(record: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
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
                chunk_text = f"{chunk['title']} {chunk['content']}"
                raw_vec = await call_embedding_service_async(chunk_text)
                if raw_vec and len(raw_vec) == RAG_EFFECTIVE_VECTOR_DIMENSIONS:
                    embedding = pgvector_literal(raw_vec)
                else:
                    _warn_embedding_fallback(raw_vec)
                    embedding = pgvector_literal(build_rag_embedding(chunk_text))
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


async def sync_rag_directory_on_startup() -> None:
    """Ingest all .md/.txt/.pdf files in RAG_SYNC_DIR into pgvector on startup."""
    sync_dir = Path(RAG_SYNC_DIR)
    if not sync_dir.is_dir():
        return

    _RAG_SYNC_EXTS = {".md", ".txt", ".pdf"}
    synced, skipped = 0, 0
    for path in sorted(sync_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _RAG_SYNC_EXTS:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        checksum = canonical_digest(content)
        document_id = f"sync:{checksum.removeprefix('sha256:')[:16]}"
        chunks = split_rag_upload_chunks(content)
        if not chunks:
            continue

        generated_at = now_rfc3339()
        source_uri = path.as_posix()
        name = path.name
        record: dict[str, Any] = {
            "document": {
                "documentId": document_id,
                "name": name,
                "title": name,
                "mimeType": "text/plain",
                "sourceUri": source_uri,
                "sourceType": RAG_SYNC_SOURCE_TYPE,
                "customer": RAG_SYNC_CUSTOMER,
                "namespace": RAG_SYNC_NAMESPACE,
                "version": RAG_SYNC_VERSION,
                "aclGroups": RAG_SYNC_ACL_GROUPS,
                "labels": {"source": "rag-sync-dir"},
                "checksum": checksum,
                "contentBytes": len(content.encode("utf-8")),
                "chunkCount": len(chunks),
                "ingestedAt": generated_at,
                "uploadedBy": "rag-sync",
                "runId": "",
            },
            "chunks": [
                {
                    "chunkId": f"{document_id}:chunk:{i}",
                    "documentId": document_id,
                    "chunkIndex": i,
                    "title": name,
                    "sourceUri": f"{source_uri}#chunk-{i}",
                    "sourceType": RAG_SYNC_SOURCE_TYPE,
                    "customer": RAG_SYNC_CUSTOMER,
                    "namespace": RAG_SYNC_NAMESPACE,
                    "version": RAG_SYNC_VERSION,
                    "aclGroups": RAG_SYNC_ACL_GROUPS,
                    "labels": {"source": "rag-sync-dir"},
                    "content": chunk,
                    "textHash": canonical_digest(chunk),
                    "checksum": canonical_digest(f"{document_id}:{i}:{chunk}"),
                }
                for i, chunk in enumerate(chunks)
            ],
        }
        status, _, _ = await persist_rag_upload_document(record)
        if status == "persisted":
            synced += 1
        else:
            skipped += 1


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


async def search_pgvector_runbooks(
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

    raw_query_vec = await call_embedding_service_async(req.query)
    if raw_query_vec and len(raw_query_vec) == RAG_EFFECTIVE_VECTOR_DIMENSIONS:
        query_vector = pgvector_literal(raw_query_vec)
    else:
        _warn_embedding_fallback(raw_query_vec)
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
        "Gateway-collected local document evidence from `/v1/rag/search`.",
        "Use only the retrieved titles and previews below. Do not expose source URIs, public web URLs, or similarity scores in the user-facing answer.",
        "",
        "| Document | Type | Preview |",
        "| - | - | - |",
    ]
    for result in results[:5]:
        title = str(result.get("title") or result.get("documentId") or "untitled")
        source_type = str(result.get("sourceType") or "runbook")
        preview = str(result.get("contentPreview") or result.get("content") or "").replace("\n", " ")
        lines.append(f"| {title} | {source_type} | {preview[:180]} |")
    return "\n".join(lines)


def build_rag_answer_citation_text(results: Sequence[Mapping[str, Any]]) -> str:
    if not results:
        return ""

    lines = ["\n\n[ 참고 자료 ]"]
    for index, result in enumerate(results[:3], start=1):
        title = str(result.get("title") or result.get("documentId") or "untitled")
        source_type = str(result.get("sourceType") or "runbook")
        lines.append(f"{index}. {title} ({source_type})")
    lines.append("문서 위치와 원문은 상세 보기에서 확인하세요.")
    return "\n".join(lines)


def build_rag_backend_status() -> dict[str, Any]:
    backend_configured = bool(RAG_BACKEND_URL)
    embedding_service_configured = bool(RAG_EMBEDDING_SERVICE_URL and backend_configured)
    return {
        "status": "configured" if backend_configured else "not_configured",
        "backendType": RAG_BACKEND_TYPE,
        "collection": RAG_COLLECTION,
        "endpointConfigured": backend_configured,
        "embeddingModel": RAG_EMBEDDING_MODEL if backend_configured else "not_configured",
        "embeddingProvider": RAG_EMBEDDING_PROVIDER or ("ollama" if RAG_EMBEDDING_API_STYLE == "ollama" else ""),
        "embeddingApiStyle": RAG_EMBEDDING_API_STYLE or "auto",
        "embeddingModelConfiguredButIgnored": bool(
            RAG_EMBEDDING_MODEL and backend_configured and not embedding_service_configured
        ),
        "embeddingModelSentToService": bool(RAG_EMBEDDING_MODEL and embedding_service_configured),
        "embeddingServiceConfigured": embedding_service_configured,
        "activeEmbeddingAlgorithm": "semantic-service" if embedding_service_configured else "hashing-bow-v1",
        "vectorDimensions": RAG_EFFECTIVE_VECTOR_DIMENSIONS if backend_configured else RAG_VECTOR_DIMENSIONS,
        "chunkOverlapChars": RAG_UPLOAD_CHUNK_OVERLAP_CHARS,
        "olsStaticGuidelinesChars": 21203,
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
