#!/usr/bin/env python3
"""Sync a local directory of .md/.txt/.pdf files to the Gateway RAG backend via --apply mode.

Reuses build_plan / apply_plan from ingest-rag-documents.py; no new dependencies needed.

Usage:
  python scripts/kugnus-rag-sync.py --dir docs/runbooks --token $TOKEN
  KOMSCO_INGEST_TOKEN=xxx python scripts/kugnus-rag-sync.py --dir docs/runbooks
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path


def load_ingest_module():
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "ingest_rag_documents",
        here / "ingest-rag-documents.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync a directory of runbook files to the Gateway RAG backend.")
    parser.add_argument("--dir", default=os.getenv("KOMSCO_AI_RAG_SYNC_DIR", ""), help="Directory to sync")
    parser.add_argument("--gateway-url", default="http://localhost:18080")
    parser.add_argument("--token", default="", help="Bearer token (or set KOMSCO_INGEST_TOKEN env var)")
    parser.add_argument("--source-type", default="runbook")
    parser.add_argument("--customer", default="komsco")
    parser.add_argument("--namespace", default="komsco-ai-kugnus")
    parser.add_argument("--version", default="v0.1.7")
    parser.add_argument("--collection", default="komsco-aiops-runbooks")
    parser.add_argument("--acl-group", action="append", default=["aiops-admins"])
    parser.add_argument("--max-chunk-chars", type=int, default=1200)
    parser.add_argument("--dry-run", action="store_true", help="Print plans without POSTing to Gateway")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.dir:
        print("ERROR: --dir is required (or set KOMSCO_AI_RAG_SYNC_DIR env var).", file=sys.stderr)
        return 1

    sync_dir = Path(args.dir)
    if not sync_dir.is_dir():
        print(f"ERROR: directory not found: {sync_dir}", file=sys.stderr)
        return 1

    token = args.token or os.environ.get("KOMSCO_INGEST_TOKEN", "")
    if not token and not args.dry_run:
        print("ERROR: bearer token required via --token or KOMSCO_INGEST_TOKEN env var.", file=sys.stderr)
        return 1

    cli = load_ingest_module()

    _EXTS = {".md", ".txt", ".pdf"}
    files = sorted(p for p in sync_dir.rglob("*") if p.is_file() and p.suffix.lower() in _EXTS)
    if not files:
        print(f"No .md/.txt/.pdf files found in {sync_dir}")
        return 0

    print(f"Syncing {len(files)} file(s) from {sync_dir} → {args.gateway_url}")
    errors = 0
    for path in files:
        fake_args = type(
            "Args",
            (),
            {
                "source": str(path),
                "encoding": "utf-8",
                "customer": args.customer,
                "source_type": args.source_type,
                "version": args.version,
                "max_chunk_chars": args.max_chunk_chars,
                "collection": args.collection,
                "namespace": args.namespace,
                "acl_group": args.acl_group,
                "label": [],
            },
        )()
        plan = cli.build_plan(fake_args)
        if args.dry_run:
            print(f"  [dry-run] {path.name}: {len(plan['spec']['chunks'])} chunk(s)")
            continue
        result = cli.apply_plan(plan, args.gateway_url, token)
        status = result.get("status")
        doc_id = result.get("documentId", "?")
        chunks = result.get("expectedChunks", "?")
        if status == "applied":
            print(f"  OK  {path.name} → {doc_id} ({chunks} chunks)")
        else:
            print(f"  ERR {path.name}: HTTP {result.get('httpStatus')} — {result.get('error', '')}", file=sys.stderr)
            errors += 1

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
