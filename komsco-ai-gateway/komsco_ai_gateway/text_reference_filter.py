from __future__ import annotations

import re


DISALLOWED_GATEWAY_API_REFERENCE_RE = re.compile(
    r"^\s*(Gateway|GatewayClass)\s+\[gateway\.networking\.k8s\.io/v1\]:\s+https?://",
    re.IGNORECASE,
)
EXPLICIT_KUBERNETES_GATEWAY_API_RE = re.compile(
    r"(?i)(gatewayclass|gateway\.networking\.k8s\.io|kubernetes gateway api|openshift gateway api|gateway api)"
)
LOW_SIGNAL_REFERENCE_RE = re.compile(
    r"^\s*("
    r"Extension APIs|"
    r"Admission plugins|"
    r"TokenReview\s+\[authentication\.k8s\.io/v1\]|"
    r"ClusterRole\s+\[authorization\.openshift\.io/v1\]"
    r"):\s+https?://",
    re.IGNORECASE,
)
EXPLICIT_OPENSHIFT_DOC_REFERENCE_RE = re.compile(
    r"(?i)(문서|docs?|reference|참고 링크|api\s*문서|extension api|admission plugin|tokenreview|clusterrole)"
)
POD_RESTART_LANGUAGE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("재시작 빈도", "누적 재시작 횟수"),
    ("높은 빈도", "높은 누적 재시작 횟수"),
    ("빈번한 재시작", "누적 재시작 이력"),
    ("재시작이 빈번하게 발생", "재시작 이력이 누적"),
    ("재시작이 빈번", "누적 재시작 횟수가 높음"),
)
PRIVATE_REASONING_START_RE = re.compile(
    r"(<\|channel\|>\s*(?:thought|analysis)\s*<channel>|"
    r"<\|start_header_id\|>\s*(?:thought|analysis)\s*<\|end_header_id\|>|"
    r"<think>|"
    r"<(?:thought|analysis)>)",
    re.IGNORECASE,
)
PRIVATE_REASONING_END_RE = re.compile(
    r"(<\|channel\|>\s*(?:final|assistant)\s*<channel>|"
    r"<\|start_header_id\|>\s*(?:final|assistant)\s*<\|end_header_id\|>|"
    r"</think>|"
    r"</(?:thought|analysis)>|"
    r"<(?:final|assistant)>)",
    re.IGNORECASE,
)
PRIVATE_REASONING_TOKEN_RE = re.compile(
    r"<\|[^>\n]*\|>|</?channel>|</?(?:thought|analysis|final|assistant)>",
    re.IGNORECASE,
)
PRIVATE_REASONING_LEAK_LINE_RE = re.compile(
    r"^\s*(?:(?:thought|analysis)\b.*\b(?:user|I\s+(?:need|should|have|will)|tool|called|already)\b|"
    r"(?:I\s+(?:need|should|have|will)|I\s+have\s+already|Let's\s+search|Looking\s+at\s+the\s+.*output|Patterns\s+to\s+search)\b)",
    re.IGNORECASE,
)


def should_filter_gateway_api_references(message: str) -> bool:
    return not bool(EXPLICIT_KUBERNETES_GATEWAY_API_RE.search(message))


def should_filter_low_signal_references(message: str) -> bool:
    return not bool(EXPLICIT_OPENSHIFT_DOC_REFERENCE_RE.search(message))


def is_disallowed_gateway_api_reference(line: str) -> bool:
    return bool(DISALLOWED_GATEWAY_API_REFERENCE_RE.search(line))


def is_low_signal_reference(line: str) -> bool:
    return bool(LOW_SIGNAL_REFERENCE_RE.search(line))


def normalize_pod_restart_language(text: str) -> str:
    normalized = text
    for source, replacement in POD_RESTART_LANGUAGE_REPLACEMENTS:
        normalized = normalized.replace(source, replacement)
    return normalized


def strip_private_reasoning_tokens(text: str) -> str:
    return PRIVATE_REASONING_TOKEN_RE.sub("", text)


def strip_private_reasoning_sections(text: str) -> str:
    private_reasoning_active = False
    filtered_lines: list[str] = []

    for line in text.replace("\r\n", "\n").splitlines(keepends=True):
        remaining = line
        while remaining:
            if private_reasoning_active:
                end_match = PRIVATE_REASONING_END_RE.search(remaining)
                if not end_match:
                    remaining = ""
                    break
                private_reasoning_active = False
                remaining = remaining[end_match.end() :]
                continue

            start_match = PRIVATE_REASONING_START_RE.search(remaining)
            if not start_match:
                cleaned = strip_private_reasoning_tokens(remaining)
                if not PRIVATE_REASONING_LEAK_LINE_RE.search(cleaned):
                    filtered_lines.append(cleaned)
                remaining = ""
                break

            before = strip_private_reasoning_tokens(remaining[: start_match.start()])
            if before:
                filtered_lines.append(before)
            private_reasoning_active = True
            remaining = remaining[start_match.end() :]

    return "".join(filtered_lines)


class TextReferenceFilter:
    def __init__(
        self,
        *,
        filter_gateway_api_references: bool,
        filter_low_signal_references: bool = False,
        normalize_restart_language: bool = False,
    ) -> None:
        self.filter_gateway_api_references = filter_gateway_api_references
        self.filter_low_signal_references = filter_low_signal_references
        self.normalize_restart_language = normalize_restart_language
        self.pending = ""
        self.held_lines: list[str] = []
        self.private_reasoning_active = False

    def filter(self, content: str, *, final: bool = False) -> str:
        content = self.filter_private_reasoning(content, final=final)
        if not content and not final:
            return ""
        if (
            not self.filter_gateway_api_references
            and not self.filter_low_signal_references
            and not self.normalize_restart_language
        ):
            return content

        text = f"{self.pending}{content}"
        if final:
            complete = text
            self.pending = ""
        else:
            last_newline = text.rfind("\n")
            if last_newline == -1:
                self.pending = text
                return ""

            complete = text[: last_newline + 1]
            self.pending = text[last_newline + 1 :]

        if self.normalize_restart_language:
            complete = normalize_pod_restart_language(complete)

        lines = complete.splitlines(keepends=True)
        filtered_lines: list[str] = []
        for line in lines:
            if self.is_disallowed_reference(line):
                self.held_lines = []
                continue

            if self.held_lines:
                if not line.strip():
                    self.held_lines.append(line)
                    continue

                filtered_lines.extend(self.held_lines)
                self.held_lines = []

            if line.strip() == "---":
                self.held_lines = [line]
                continue

            filtered_lines.append(line)

        return "".join(filtered_lines)

    def filter_private_reasoning(self, content: str, *, final: bool = False) -> str:
        lines = content.replace("\r\n", "\n").splitlines(keepends=True)
        filtered_lines: list[str] = []

        for line in lines:
            remaining = line
            while remaining:
                if self.private_reasoning_active:
                    end_match = PRIVATE_REASONING_END_RE.search(remaining)
                    if not end_match:
                        remaining = ""
                        break
                    self.private_reasoning_active = False
                    remaining = remaining[end_match.end() :]
                    continue

                start_match = PRIVATE_REASONING_START_RE.search(remaining)
                if not start_match:
                    cleaned = strip_private_reasoning_tokens(remaining)
                    if not PRIVATE_REASONING_LEAK_LINE_RE.search(cleaned):
                        filtered_lines.append(cleaned)
                    remaining = ""
                    break

                before = strip_private_reasoning_tokens(remaining[: start_match.start()])
                if before:
                    filtered_lines.append(before)
                self.private_reasoning_active = True
                remaining = remaining[start_match.end() :]

        if final:
            self.private_reasoning_active = False

        return "".join(filtered_lines)

    def is_disallowed_reference(self, line: str) -> bool:
        return (
            self.filter_gateway_api_references
            and is_disallowed_gateway_api_reference(line)
        ) or (
            self.filter_low_signal_references
            and is_low_signal_reference(line)
        )

    def flush(self) -> str:
        filtered = self.filter("", final=True)
        if self.held_lines:
            filtered = f"{filtered}{''.join(self.held_lines)}"
            self.held_lines = []
        return filtered
