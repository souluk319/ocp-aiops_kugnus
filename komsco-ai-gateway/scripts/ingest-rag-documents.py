#!/usr/bin/env python3
"""Create a local RAG ingestion plan and optionally apply it via the Gateway API."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path


def now_rfc3339() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def redact_preview(value: str) -> str:
    redacted = value
    redacted = re.sub(
        r"(?im)(authorization\s*:\s*bearer\s+)[^\s]+",
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?im)\b(api[-_ ]?key|token|password|secret)\b\s*[:=]\s*[^\s,;]+",
        lambda match: f"{match.group(1)}=[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?im)(client-key-data|client-certificate-data|certificate-authority-data)\s*:\s*(\|[^\n]*\n(?:[ \t]+[A-Za-z0-9+/=]+\n?)+|[A-Za-z0-9+/=]+)",
        lambda match: f"{match.group(1)}: [REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?is)-----BEGIN ([A-Z ]*PRIVATE KEY|CERTIFICATE)-----.*?-----END \1-----",
        "[REDACTED PEM BLOCK]",
        redacted,
    )
    redacted = re.sub(r"\bAKIA[0-9A-Z]{16}\b", "[REDACTED_AWS_ACCESS_KEY]", redacted)
    return redacted


def split_chunks(content: str, *, max_chars: int) -> list[str]:
    paragraphs = [part.strip() for part in content.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs or [content.strip()]:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= max_chars:
            current = paragraph
            continue
        for start in range(0, len(paragraph), max_chars):
            chunks.append(paragraph[start : start + max_chars])
        current = ""
    if current:
        chunks.append(current)
    return chunks


def build_plan(args: argparse.Namespace) -> dict[str, object]:
    source = Path(args.source)
    content = source.read_text(encoding=args.encoding)
    preview_content = redact_preview(content)
    source_uri = source.as_posix()
    document_id = f"{args.customer}:{args.source_type}:{sha256_text(source_uri + ':' + args.version)[7:19]}"
    chunks = split_chunks(content, max_chars=args.max_chunk_chars)
    preview_chunks = split_chunks(preview_content, max_chars=args.max_chunk_chars)
    generated_at = now_rfc3339()
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "RagIngestionPlan",
        "metadata": {
            "name": f"rag-ingestion-{sha256_text(source_uri)[7:19]}",
            "generatedAt": generated_at,
        },
        "spec": {
            "status": "skeleton",
            "gatewayOnly": True,
            "directDatabaseAccessAllowed": False,
            "backendWritesPerformed": False,
            "collection": args.collection,
            "document": {
                "documentId": document_id,
                "sourceUri": source_uri,
                "sourceType": args.source_type,
                "customer": args.customer,
                "namespace": args.namespace,
                "version": args.version,
                "checksum": sha256_text(content),
                "aclGroups": args.acl_group,
                "labels": dict(label.split("=", 1) for label in args.label),
                "ingestedAt": generated_at,
            },
            "chunks": [
                {
                    "chunkId": f"{document_id}:chunk:{index}",
                    "chunkIndex": index,
                    "textHash": sha256_text(chunk),
                    "charLength": len(chunk),
                    "checksum": sha256_text(f"{document_id}:{index}:{chunk}"),
                    "contentPreviewRedacted": preview_chunks[index][:160] if index < len(preview_chunks) else "",
                }
                for index, chunk in enumerate(chunks)
            ],
        },
    }


def apply_plan(plan: dict[str, object], gateway_url: str, token: str) -> dict[str, object]:
    """POST each chunk to the Gateway /v1/rag/uploads endpoint and return a result summary."""
    try:
        import urllib.request
        import urllib.error
    except ImportError:
        raise SystemExit("urllib is required for --apply mode")

    spec = plan.get("spec", {})
    doc = spec.get("document", {})
    chunks = spec.get("chunks", [])
    source = Path(str(spec.get("document", {}).get("sourceUri", "")))

    try:
        raw_content = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"Cannot read source file for --apply: {exc}")

    payload = {
        "title": source.stem,
        "content": raw_content,
        "sourceUri": doc.get("sourceUri", ""),
        "sourceType": doc.get("sourceType", "runbook"),
        "customer": doc.get("customer", "komsco"),
        "namespace": doc.get("namespace", "komsco-ai-kugnus"),
        "version": doc.get("version", "v0.1.1"),
        "collection": spec.get("collection", "komsco-aiops-runbooks"),
        "aclGroups": doc.get("aclGroups", []),
        "labels": doc.get("labels", {}),
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    url = gateway_url.rstrip("/") + "/v1/rag/uploads"
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            response_body = json.loads(resp.read().decode("utf-8"))
            return {
                "status": "applied",
                "httpStatus": resp.status,
                "documentId": doc.get("documentId"),
                "expectedChunks": len(chunks),
                "gatewayUrl": url,
                "response": response_body,
            }
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        return {
            "status": "error",
            "httpStatus": exc.code,
            "documentId": doc.get("documentId"),
            "gatewayUrl": url,
            "error": error_body[:500],
        }
    except OSError as exc:
        return {
            "status": "error",
            "httpStatus": None,
            "documentId": doc.get("documentId"),
            "gatewayUrl": url,
            "error": str(exc),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a local RAG ingestion plan. "
            "By default (--dry-run), prints the plan JSON without writing to any backend. "
            "With --apply, POSTs the document to the Gateway API."
        ),
    )
    parser.add_argument("--source", required=True, help="Markdown, text, or extracted runbook file path")
    parser.add_argument("--source-type", default="runbook", help="runbook, sop, rca, pdf-extract, or note")
    parser.add_argument("--customer", default="komsco")
    parser.add_argument("--namespace", default="komsco-ai-kugnus")
    parser.add_argument("--version", default="v0.1.1")
    parser.add_argument("--collection", default="komsco-aiops-runbooks")
    parser.add_argument("--acl-group", action="append", required=True, help="Allowed group; repeatable")
    parser.add_argument("--label", action="append", default=[], help="key=value metadata label; repeatable")
    parser.add_argument("--max-chunk-chars", type=int, default=1200)
    parser.add_argument("--encoding", default="utf-8")
    parser.add_argument("--dry-run", action="store_true", help="Print plan JSON only; do not call Gateway API (default)")
    parser.add_argument("--apply", action="store_true", help="POST document to the Gateway API after building the plan")
    parser.add_argument("--gateway-url", default="http://localhost:18080", help="Gateway base URL for --apply")
    parser.add_argument("--token", default="", help="Bearer token for --apply (or set KOMSCO_INGEST_TOKEN env var)")
    parser.add_argument("--output", help="Optional output file path for the plan JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for label in args.label:
        if "=" not in label:
            raise SystemExit(f"Invalid --label {label!r}; expected key=value")
    plan = build_plan(args)

    if args.apply and not args.dry_run:
        token = args.token or os.environ.get("KOMSCO_INGEST_TOKEN", "")
        if not token:
            print(
                "ERROR: --apply requires a bearer token via --token or KOMSCO_INGEST_TOKEN env var.",
                file=sys.stderr,
            )
            return 1
        result = apply_plan(plan, args.gateway_url, token)
        output = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(output + "\n", encoding="utf-8")
        else:
            print(output)
        return 0 if result.get("status") == "applied" else 1

    rendered = json.dumps(plan, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
