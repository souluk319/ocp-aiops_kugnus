#!/usr/bin/env python3
"""Create a local RAG ingestion plan without writing to any backend."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a local RAG ingestion plan. This does not connect to pgvector or write secrets.",
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
    parser.add_argument("--dry-run", action="store_true", help="Kept for clarity; this script is always dry-run")
    parser.add_argument("--output", help="Optional output file path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for label in args.label:
        if "=" not in label:
            raise SystemExit(f"Invalid --label {label!r}; expected key=value")
    plan = build_plan(args)
    rendered = json.dumps(plan, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
