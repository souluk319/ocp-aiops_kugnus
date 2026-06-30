#!/usr/bin/env python3
"""Build mock customer Markdown docs into Hangul-safe PDFs with reportlab."""

from __future__ import annotations

import html
import os
import re
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT_DIR / "docs" / "Ver.0.1.6" / "mock-customer-ops-pack"
SRC_DIR = PACK_DIR / "src"
PDF_DIR = PACK_DIR / "pdf"
PDF_TOOL_PYTHON = Path(os.getenv("KUGNUS_PDF_PYTHON", "/home/kugnus/.local/share/kugnus-pdf-tools/.venv/bin/python"))
KOREAN_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/unfonts-core/UnDotum.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/mnt/c/Windows/Fonts/malgun.ttf",
    "/mnt/c/Windows/Fonts/gulim.ttc",
    "/mnt/c/Windows/Fonts/batang.ttc",
]


try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
except ModuleNotFoundError:
    if os.getenv("KUGNUS_PDF_REEXEC") != "1" and PDF_TOOL_PYTHON.is_file():
        os.environ["KUGNUS_PDF_REEXEC"] = "1"
        os.execv(str(PDF_TOOL_PYTHON), [str(PDF_TOOL_PYTHON), *sys.argv])
    raise RuntimeError(
        "reportlab is not available. Install it outside the repo: "
        f"{PDF_TOOL_PYTHON} -m pip install reportlab"
    )


FONT_NAME = "KugnusHangul"


def korean_font() -> Path:
    candidates = [os.getenv("KOREAN_FONT", ""), *KOREAN_FONT_CANDIDATES]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise RuntimeError("Korean font not found. Set KOREAN_FONT to a TTF/TTC with Hangul glyphs.")


def clean_inline(value: str) -> str:
    escaped = html.escape(value)
    return re.sub(r"`([^`]+)`", r"\1", escaped)


def styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle(
        "body",
        fontName=FONT_NAME,
        fontSize=9.5,
        leading=14,
        wordWrap="CJK",
        textColor=colors.HexColor("#151515"),
        spaceAfter=4,
    )
    return {
        "body": base,
        "h1": ParagraphStyle("h1", parent=base, fontSize=18, leading=24, spaceAfter=12),
        "h2": ParagraphStyle("h2", parent=base, fontSize=13, leading=18, spaceBefore=12, spaceAfter=6),
        "h3": ParagraphStyle("h3", parent=base, fontSize=11, leading=16, spaceBefore=8, spaceAfter=4),
        "bullet": ParagraphStyle("bullet", parent=base, leftIndent=10, firstLineIndent=-7),
        "cell": ParagraphStyle("cell", parent=base, fontSize=8.5, leading=12, spaceAfter=0),
    }


def parse_table(lines: list[str], style: ParagraphStyle) -> Table:
    rows = []
    for line in lines:
        cells = [Paragraph(clean_inline(cell.strip()), style) for cell in line.strip().strip("|").split("|")]
        rows.append(cells)
    rows = [rows[0], *rows[2:]]
    table = Table(rows, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf2f7")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c9d2dc")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def markdown_flowables(markdown: str) -> list[object]:
    st = styles()
    lines = markdown.splitlines()
    flowables: list[object] = []
    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        if not line:
            index += 1
            continue
        if line.startswith("|") and index + 1 < len(lines) and re.match(r"^\|\s*:?-{3,}", lines[index + 1]):
            block = [line, lines[index + 1].rstrip()]
            index += 2
            while index < len(lines) and lines[index].startswith("|"):
                block.append(lines[index].rstrip())
                index += 1
            flowables.append(parse_table(block, st["cell"]))
            flowables.append(Spacer(1, 5))
            continue
        if line.startswith("# "):
            flowables.append(Paragraph(clean_inline(line[2:].strip()), st["h1"]))
        elif line.startswith("## "):
            flowables.append(Paragraph(clean_inline(line[3:].strip()), st["h2"]))
        elif line.startswith("### "):
            flowables.append(Paragraph(clean_inline(line[4:].strip()), st["h3"]))
        elif line.startswith("- "):
            flowables.append(Paragraph(f"• {clean_inline(line[2:].strip())}", st["bullet"]))
        elif re.match(r"^\d+\.\s+", line):
            flowables.append(Paragraph(clean_inline(line.strip()), st["body"]))
        else:
            flowables.append(Paragraph(clean_inline(line), st["body"]))
        index += 1
    return flowables


def build_pdf(source: Path, target: Path) -> None:
    doc = SimpleDocTemplate(
        str(target),
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=source.stem,
    )
    doc.build(markdown_flowables(source.read_text(encoding="utf-8")))


def build() -> list[Path]:
    font = korean_font()
    pdfmetrics.registerFont(TTFont(FONT_NAME, str(font)))
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = []
    for source in sorted(SRC_DIR.glob("*.md")):
        pdf_path = PDF_DIR / f"{source.stem}.pdf"
        build_pdf(source, pdf_path)
        pdfs.append(pdf_path)
    return pdfs


def main() -> int:
    pdfs = build()
    print(f"Built {len(pdfs)} mock customer PDF(s)")
    for pdf in pdfs:
        print(pdf)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"Mock customer PDF build: FAIL\n[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(1)
