#!/usr/bin/env python3
"""Convert official PDF deliverables into searchable Markdown contract copies."""

from __future__ import annotations

import hashlib
import pathlib
import re
from datetime import datetime, timezone

import pdfplumber


ROOT = pathlib.Path(__file__).resolve().parents[1]

CONTRACT_PDFS = [
    (
        "docs/Komsco_ai_agent_final.pdf",
        "docs/contracts/Komsco_ai_agent_final.contract.md",
        "KOMSCO AIOps 공식 계약 문서 변환본",
    ),
    (
        "docs/AIOps-For-OCP.pdf",
        "docs/contracts/AIOps-For-OCP.contract.md",
        "AIOps for OCP 최종 산출물 변환본",
    ),
]


def clean_text(text: str) -> str:
    text = text.replace(chr(0), "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def convert_pdf(source: str, target: str, title: str) -> None:
    source_path = ROOT / source
    target_path = ROOT / target
    target_path.parent.mkdir(parents=True, exist_ok=True)

    source_bytes = source_path.read_bytes()
    source_sha = hashlib.sha256(source_bytes).hexdigest()

    lines: list[str] = [
        f"# {title}",
        "",
        f"> 이 파일은 검색과 구현 확인을 위해 {source}를 Markdown으로 변환한 사본입니다.",
        "> 원본 PDF가 공식 기준이며, 충돌 시 원본 PDF를 우선합니다.",
        "",
        f"- Source PDF: {source}",
        f"- Source SHA256: {source_sha}",
        f"- Converted At UTC: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "- Converter: pdfplumber text extraction",
        "",
        "---",
        "",
    ]

    with pdfplumber.open(str(source_path)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = clean_text(page.extract_text(x_tolerance=1, y_tolerance=3) or "")
            lines.extend([f"## Page {page_number}", ""])
            if text:
                lines.extend(line.strip() for line in text.split("\n"))
            else:
                lines.append("_No extractable text on this page._")
            lines.append("")

    target_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    line_count = sum(1 for _ in target_path.open(encoding="utf-8"))
    print(f"{target}: {line_count} lines, source sha256 {source_sha}")


def main() -> None:
    for source, target, title in CONTRACT_PDFS:
        convert_pdf(source, target, title)


if __name__ == "__main__":
    main()
