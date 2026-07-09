from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


ANSWER_KIND_ACTION_PROPOSAL = "action_proposal"
ANSWER_KIND_RCA = "rca"
ANSWER_KIND_RUNTIME_HEALTH = "runtime_health"
ANSWER_KIND_CASUAL = "casual"
ANSWER_KIND_PLATFORM_CONCEPT = "platform_concept"


@dataclass(frozen=True, slots=True)
class IntentRule:
    id: str
    answer_kind: str
    max_chars: int
    include_any: tuple[re.Pattern[str], ...]
    exclude_any: tuple[re.Pattern[str], ...] = ()

    def matches(self, message: str) -> bool:
        if not message or len(message) > self.max_chars:
            return False
        return any(pattern.search(message) for pattern in self.include_any) and not any(
            pattern.search(message) for pattern in self.exclude_any
        )


def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


RUNTIME_HEALTH_EXCLUDE_RE = _compile(
    r"\b(pod|deployment|clusteroperator|operator|cronjob|job|node|event|alert|"
    r"crashloop|imagepull|rca)\b|"
    r"(파드|노드|이벤트|경고|로그|원인|분석|장애|몇)"
)

_CASUAL_RE = _compile(
    r"(헤이|안녕|ㅎㅇ|반가|오케이|뭐야|잘있어|테스트)"
    r"|\b(hi|hello|hey|test|ok)\b"
)
_PLATFORM_TERM_RE = _compile(r"(오픈\s*시프트|openshift|ocp|쿠버네티스|kubernetes|k8s)")
_CONCEPT_QUESTION_RE = _compile(
    r"(뭐야|무엇|뭔가|뭔지|설명|개념|뜻|정의|알려줘|what\s+is|explain|describe)"
)

INTENT_RULES: tuple[IntentRule, ...] = (
    IntentRule(
        id="casual-greeting",
        answer_kind=ANSWER_KIND_CASUAL,
        max_chars=40,
        include_any=(_CASUAL_RE,),
    ),
    IntentRule(
        id="generic-runtime-health",
        answer_kind=ANSWER_KIND_RUNTIME_HEALTH,
        max_chars=80,
        include_any=(
            _compile(r"(작동|동작|정상|살아|연결|되나|되냐|되는가|됩니까|돼\??)"),
            _compile(r"\b(health|healthy|working|works|alive|up)\b"),
        ),
        exclude_any=(RUNTIME_HEALTH_EXCLUDE_RE,),
    ),
)


def normalize_message(message: str) -> str:
    return re.sub(r"\s+", " ", message.strip().lower())


def is_platform_concept_question(message: str) -> bool:
    return bool(_PLATFORM_TERM_RE.search(message) and _CONCEPT_QUESTION_RE.search(message))


def classify_fallback_answer_kind(message: str, policy: Mapping[str, Any]) -> str:
    if policy.get("decision") == "action_proposal_only":
        return ANSWER_KIND_ACTION_PROPOSAL

    normalized = normalize_message(message)
    if is_platform_concept_question(normalized):
        return ANSWER_KIND_PLATFORM_CONCEPT

    for rule in INTENT_RULES:
        if rule.matches(normalized):
            return rule.answer_kind
    return ANSWER_KIND_RCA
