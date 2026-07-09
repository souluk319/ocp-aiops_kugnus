import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


FOLLOWUP_ANCHOR_RE = re.compile(
    r"(?:다음\s*단계|무엇을\s*도와|원하시면|이어(?:서)?\s*진행|선택해\s*주세요|어떤\s*것을)",
    re.IGNORECASE,
)
NUMBERED_OPTION_RE = re.compile(r"^\s*(\d{1,2})[\.)]\s+(.+?)\s*$")
INLINE_BOLD_HEADING_RE = re.compile(r"^\*\*(.+?)\*\*\s*[:：]?\s*(.*)$")
SELECTION_WORDS = {
    "첫번째": 1,
    "첫 번째": 1,
    "일번": 1,
    "두번째": 2,
    "두 번째": 2,
    "이번": 2,
    "세번째": 3,
    "세 번째": 3,
    "삼번": 3,
    "네번째": 4,
    "네 번째": 4,
    "사번": 4,
    "다섯번째": 5,
    "다섯 번째": 5,
    "오번": 5,
}


@dataclass(frozen=True)
class FollowupSelection:
    index: int
    option: str
    effective_message: str


def selected_followup_index(message: str) -> int | None:
    text = re.sub(r"\s+", " ", message or "").strip().lower()
    if not text:
        return None
    numeric_match = re.fullmatch(r"#?\s*(\d{1,2})\s*(?:번|번째|번으로|번\s*진행)?\s*", text)
    if numeric_match:
        index = int(numeric_match.group(1))
        return index if 1 <= index <= 9 else None
    return SELECTION_WORDS.get(text)


def clean_followup_option(raw_option: str) -> str:
    option = raw_option.strip()
    option = option.lstrip("-• ").strip()
    heading_match = INLINE_BOLD_HEADING_RE.match(option)
    if heading_match:
        heading = heading_match.group(1).strip()
        tail = heading_match.group(2).strip()
        option = f"{heading}: {tail}" if tail else heading
    option = re.sub(r"\*\*(.+?)\*\*", r"\1", option)
    option = re.sub(r"`([^`]+)`", r"\1", option)
    option = re.sub(r"\s+", " ", option).strip()
    return option


def extract_numbered_followups(answer_text: str, *, limit: int = 5) -> list[str]:
    lines = (answer_text or "").splitlines()
    options: list[str] = []
    in_followup_section = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if FOLLOWUP_ANCHOR_RE.search(stripped):
            in_followup_section = True
            continue
        if not in_followup_section:
            continue
        if stripped.startswith("---") and options:
            break

        match = NUMBERED_OPTION_RE.match(stripped)
        if not match:
            if options and re.match(r"^(?:#{1,6}\s+|\[[^\]]+\]|\*\*[^*]+\*\*)", stripped):
                break
            continue

        option = clean_followup_option(match.group(2))
        if option:
            options.append(option)
        if len(options) >= limit:
            break

    return options


def _message_role(message: Any) -> str:
    if isinstance(message, Mapping):
        return str(message.get("role") or "")
    return str(getattr(message, "role", "") or "")


def _message_content(message: Any) -> str:
    if isinstance(message, Mapping):
        return str(message.get("content") or "")
    return str(getattr(message, "content", "") or "")


def last_assistant_content(recent_messages: Sequence[Any]) -> str:
    for message in reversed(list(recent_messages or [])):
        if _message_role(message).strip().lower() == "assistant":
            content = _message_content(message).strip()
            if content:
                return content
    return ""


def resolve_numeric_followup_message(
    user_message: str,
    recent_messages: Sequence[Any],
) -> FollowupSelection | None:
    index = selected_followup_index(user_message)
    if index is None:
        return None

    options = extract_numbered_followups(last_assistant_content(recent_messages))
    if index < 1 or index > len(options):
        return None

    option = options[index - 1]
    effective_message = f"{option}\n\n이 항목을 바로 이어서 진행해줘."
    return FollowupSelection(index=index, option=option, effective_message=effective_message[:4000])
