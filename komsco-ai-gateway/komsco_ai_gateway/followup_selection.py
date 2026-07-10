import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


FOLLOWUP_HEADING_RE = re.compile(
    r"^(?:(?:다음\s*단계로?|다음으로)?\s*무엇을\s*(?:도와드릴까요|확인할까요)|"
    r"what\s+would\s+you\s+like\s+(?:to\s+check|me\s+to\s+do)\s+next)\??$",
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


@dataclass(frozen=True)
class NumberedFollowupOption:
    index: int
    prompt: str


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


def rewrite_followup_option_as_query(raw_option: str) -> str:
    query = re.sub(r"[?？]\s*$", "", clean_followup_option(raw_option)).strip()

    english_lead = re.match(
        r"^(?:would you like (?:me )?to|should i|shall i)\s+(.+)$",
        query,
        re.IGNORECASE,
    )
    if english_lead:
        return english_lead.group(1).strip()

    korean_rewrites = (
        (r"해\s*드릴까요$", "해줘"),
        (r"해드릴까요$", "해줘"),
        (r"확인하시겠습니까$", "확인해줘"),
        (r"점검하시겠습니까$", "점검해줘"),
        (r"분석하시겠습니까$", "분석해줘"),
        (r"진행하시겠습니까$", "진행해줘"),
        (r"해\s*볼까요$", "해줘"),
        (r"만들까요$", "만들어줘"),
        (r"볼까요$", "봐줘"),
        (r"할까요$", "해줘"),
        (r"보여드릴까요$", "보여줘"),
        (r"알려드릴까요$", "알려줘"),
        (r"드릴까요$", "줘"),
    )
    for pattern, replacement in korean_rewrites:
        if re.search(pattern, query, re.IGNORECASE):
            query = re.sub(pattern, replacement, query, count=1, flags=re.IGNORECASE)
            break

    return re.sub(r"\s+", " ", query).strip()


def _normalize_followup_heading(line: str) -> str:
    heading = line.strip()
    heading = re.sub(r"^#{1,6}\s*", "", heading)
    heading = re.sub(r"[:：]\s*$", "", heading)
    heading = re.sub(r"^\*\*(.+?)\*\*$", r"\1", heading)
    return heading.strip()


def extract_numbered_followup_options(
    answer_text: str,
    *,
    limit: int = 3,
) -> list[NumberedFollowupOption]:
    lines = (answer_text or "").splitlines()
    options: list[NumberedFollowupOption] = []
    in_followup_section = False
    in_code_fence = False

    for line in lines:
        stripped = line.strip()
        if re.match(r"^(?:```|~~~)", stripped):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue
        if not stripped:
            continue
        if FOLLOWUP_HEADING_RE.fullmatch(_normalize_followup_heading(stripped)):
            in_followup_section = True
            continue
        if not in_followup_section:
            continue
        if stripped.startswith("---") and options:
            break

        match = NUMBERED_OPTION_RE.match(stripped)
        if not match:
            if options:
                break
            return []

        option = clean_followup_option(match.group(2))
        if option:
            options.append(NumberedFollowupOption(index=int(match.group(1)), prompt=option))
        if len(options) >= limit:
            break

    return options


def extract_numbered_followups(answer_text: str, *, limit: int = 3) -> list[str]:
    return [option.prompt for option in extract_numbered_followup_options(answer_text, limit=limit)]


def _message_role(message: Any) -> str:
    if isinstance(message, Mapping):
        return str(message.get("role") or "")
    return str(getattr(message, "role", "") or "")


def _message_content(message: Any) -> str:
    if isinstance(message, Mapping):
        return str(message.get("content") or "")
    return str(getattr(message, "content", "") or "")


def last_assistant_content(recent_messages: Sequence[Any]) -> str:
    messages = list(recent_messages or [])
    if not messages:
        return ""
    latest = messages[-1]
    if _message_role(latest).strip().lower() != "assistant":
        return ""
    return _message_content(latest).strip()


def resolve_numeric_followup_message(
    user_message: str,
    recent_messages: Sequence[Any],
) -> FollowupSelection | None:
    index = selected_followup_index(user_message)
    if index is None:
        return None

    options = extract_numbered_followup_options(last_assistant_content(recent_messages))
    selected = next((option for option in options if option.index == index), None)
    if selected is None:
        return None

    option = selected.prompt
    effective_message = rewrite_followup_option_as_query(option)
    return FollowupSelection(index=index, option=option, effective_message=effective_message[:4000])
