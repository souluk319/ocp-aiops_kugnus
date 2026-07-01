#!/usr/bin/env python3
"""Verify the Ver.0.2.1 answer/action boundary contract."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATEWAY_MAIN = ROOT / "komsco-ai-gateway" / "komsco_ai_gateway" / "main.py"
ASSISTANT = ROOT / "komsco-ai-console-plugin" / "src" / "components" / "AssistantLauncher.tsx"
SERVICE = ROOT / "komsco-ai-console-plugin" / "src" / "services" / "aiGateway.ts"
PAGES = ROOT / "komsco-ai-console-plugin" / "src" / "pages" / "AiopsPages.tsx"
CONTRACT = ROOT / "docs" / "Ver.0.2.1" / "answer-quality-contract.md"


def require(path: Path, needle: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if needle not in text:
        raise SystemExit(f"FAIL {label}: missing {needle!r} in {path.relative_to(ROOT)}")
    print(f"PASS {label}")


def main() -> None:
    require(CONTRACT, "AC-04 Action Boundary", "contract locks action boundary")
    require(
        GATEWAY_MAIN,
        'if decision != "action_proposal_only":\n        return ""',
        "gateway omits action text unless policy selects action proposal",
    )
    require(
        GATEWAY_MAIN,
        'natural_action_text_event["answerContract"] = "natural-action-plan-v0.2.1"',
        "gateway marks planned natural actions only",
    )
    require(SERVICE, "answerContract?: string;", "stream text event exposes answerContract")
    require(
        ASSISTANT,
        "markLastAssistantAnswerContract(prev, event.answerContract)",
        "frontend stores answerContract on streamed answers",
    )
    require(
        ASSISTANT,
        "isActionAnswerContract(message.answerContract)",
        "frontend gates inline action cards by current answer contract",
    )
    require(CONTRACT, "AC-06 Chat Transcript Storage", "contract locks chat transcript storage")
    require(GATEWAY_MAIN, '"chatTranscripts.json"', "gateway persists chat transcripts in ledger")
    require(GATEWAY_MAIN, '"var/aiops/chat-transcripts.jsonl"', "gateway writes local JSONL transcripts")
    require(GATEWAY_MAIN, "append_chat_transcript_jsonl(record)", "gateway appends transcript JSONL")
    require(GATEWAY_MAIN, '"kind": "ChatTranscriptRecord"', "gateway builds transcript records")
    require(GATEWAY_MAIN, '"chatTranscripts": latest_readable_records', "status exposes chat transcripts")
    require(PAGES, "최근 챗봇 대화기록", "frontend exposes chat transcript records")
    require(
        ROOT / "komsco-ai-gateway" / "tests" / "test_health.py",
        "transcript_jsonl_path.read_text",
        "gateway test covers transcript JSONL persistence",
    )


if __name__ == "__main__":
    main()
