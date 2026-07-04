#!/usr/bin/env python3
"""Verify the v0.2.7 fixed PDF source used by chatbot/action/UI tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

import pdfplumber


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXED_PDF = REPO_ROOT / "docs" / "AIOps-For-OCP.pdf"
FIXED_PDF_COPY = REPO_ROOT / "docs" / "Ver.0.2.5" / "AIOps-For-OCP.pdf"
OFFICIAL_SOURCE_PDF = REPO_ROOT / "docs" / "Komsco_ai_agent_final.pdf"

EXPECTED_FIXED_SHA256 = "193cf62eea36bea9cf7d370203ac413fab6a9ef044a89d8e121f93e1df6a7cb5"
EXPECTED_FIXED_PAGES = 16
EXPECTED_OFFICIAL_PAGES = 14

FIXED_REQUIRED_PHRASES = [
    "AIOps for OCP",
    "OpenShift Lightspeed",
    "AI Gateway",
    "UserToken",
    "RBAC",
    "Action Executor",
    "Tool Plan JSON",
    "RCA JSON",
    "승인",
    "감사",
]

OFFICIAL_REQUIRED_PHRASES = [
    "KOMSCO AIOps Agentic Model",
    "Tool Plan JSON",
    "Evidence 기반 RCA Reasoning",
    "Lightspeed API 최종 답변 스트리밍",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_pdf_text(path: Path) -> tuple[int, str]:
    with pdfplumber.open(path) as pdf:
        page_count = len(pdf.pages)
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    return page_count, text


def missing_phrases(text: str, phrases: Iterable[str]) -> list[str]:
    normalized = " ".join(text.split())
    return [phrase for phrase in phrases if phrase not in normalized]


def main() -> None:
    for path in (FIXED_PDF, FIXED_PDF_COPY, OFFICIAL_SOURCE_PDF):
        if not path.exists():
            raise SystemExit(f"missing PDF: {path.relative_to(REPO_ROOT)}")
        if path.stat().st_size <= 0:
            raise SystemExit(f"empty PDF: {path.relative_to(REPO_ROOT)}")

    fixed_hash = sha256(FIXED_PDF)
    fixed_copy_hash = sha256(FIXED_PDF_COPY)
    official_hash = sha256(OFFICIAL_SOURCE_PDF)
    if fixed_hash != EXPECTED_FIXED_SHA256:
        raise SystemExit(f"fixed PDF sha mismatch: {fixed_hash}")
    if fixed_copy_hash != EXPECTED_FIXED_SHA256:
        raise SystemExit(f"fixed PDF copy sha mismatch: {fixed_copy_hash}")
    if fixed_hash != fixed_copy_hash:
        raise SystemExit("fixed PDF and versioned copy differ")

    fixed_pages, fixed_text = extract_pdf_text(FIXED_PDF)
    official_pages, official_text = extract_pdf_text(OFFICIAL_SOURCE_PDF)
    if fixed_pages != EXPECTED_FIXED_PAGES:
        raise SystemExit(f"fixed PDF page count mismatch: {fixed_pages}")
    if official_pages != EXPECTED_OFFICIAL_PAGES:
        raise SystemExit(f"official source PDF page count mismatch: {official_pages}")

    fixed_missing = missing_phrases(fixed_text, FIXED_REQUIRED_PHRASES)
    official_missing = missing_phrases(official_text, OFFICIAL_REQUIRED_PHRASES)
    if fixed_missing:
        raise SystemExit(f"fixed PDF missing required phrases: {fixed_missing}")
    if official_missing:
        raise SystemExit(f"official PDF missing required phrases: {official_missing}")

    print(
        json.dumps(
            {
                "fixedPdf": str(FIXED_PDF.relative_to(REPO_ROOT)),
                "fixedPdfCopy": str(FIXED_PDF_COPY.relative_to(REPO_ROOT)),
                "fixedPages": fixed_pages,
                "fixedSha256": fixed_hash,
                "officialPdf": str(OFFICIAL_SOURCE_PDF.relative_to(REPO_ROOT)),
                "officialPages": official_pages,
                "officialSha256": official_hash,
                "ok": True,
                "verifier": "verify-v027-fixed-pdf",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
