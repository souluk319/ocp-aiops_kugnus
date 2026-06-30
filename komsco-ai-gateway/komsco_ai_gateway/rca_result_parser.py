"""Post-answer RCA result extraction from Lightspeed streaming response text.

Parses the final answer text to extract structured cause/action candidates
and computes a confidence score from tool result statuses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass
class RcaResult:
    cause_candidates: list[str] = field(default_factory=list)
    action_candidates: list[str] = field(default_factory=list)
    confidence: float = 0.0
    evidence_types: list[str] = field(default_factory=list)


_CAUSE_RE = re.compile(
    r"(OOMKilled|CrashLoopBackOff|ImagePullBackOff|Evicted|Pending|DiskPressure|NodeNotReady"
    r"|(?:^|\n)\s*(?:원인|근본\s*원인|주요\s*원인)[^\n:：]{0,30}[:：]\s*[^\n]+)",
    re.IGNORECASE,
)

_ACTION_RE = re.compile(
    r"(?:^|\n)\s*(?:조치|권장|해결|대응|수행)[^\n:：]{0,30}[:：]\s*([^\n]+)",
    re.IGNORECASE,
)

_OK_STATUSES = {"success", "ok"}
_FALLBACK_CAUSE = "수집된 증거 기준 원인 후보 미확정"


def parse_rca_result(
    answer_text: str,
    tool_results: list[Mapping[str, Any]],
) -> RcaResult:
    """Extract structured RCA findings from the final Lightspeed answer text.

    Args:
        answer_text: Concatenated streaming text from the Lightspeed response.
        tool_results: List of tool_result events collected during the chat run.
    """
    causes = [m.group(0).strip()[:200] for m in _CAUSE_RE.finditer(answer_text)][:3]
    actions = [m.group(1).strip()[:200] for m in _ACTION_RE.finditer(answer_text)][:3]

    ok_count = sum(1 for t in tool_results if t.get("status") in _OK_STATUSES)
    confidence = round(ok_count / max(len(tool_results), 1), 2)

    ev_types = list(
        {t["name"] for t in tool_results if t.get("status") in _OK_STATUSES and t.get("name")}
    )

    return RcaResult(
        cause_candidates=causes if causes else [_FALLBACK_CAUSE],
        action_candidates=actions,
        confidence=confidence,
        evidence_types=ev_types,
    )
