from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .security import canonical_digest, now_rfc3339, redact_sensitive


class ChatFeedbackInputError(ValueError):
    pass


def _field(req: Any, name: str, default: Any = "") -> Any:
    if isinstance(req, Mapping):
        return req.get(name, default)
    return getattr(req, name, default)


def build_chat_feedback_record(req: Any, subject: Mapping[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    rating = str(_field(req, "rating") or "").strip().lower()
    if rating not in {"up", "down"}:
        raise ChatFeedbackInputError("rating must be up or down")

    user_message = str(_field(req, "userMessage") or "").strip()
    assistant_answer = str(_field(req, "assistantAnswer") or "").strip()
    if not user_message or not assistant_answer:
        raise ChatFeedbackInputError(
            "userMessage and assistantAnswer are required for runbook-reviewable chat feedback"
        )

    created_at = now_rfc3339()
    submitted_at = str(_field(req, "timestamp") or created_at)
    projection = {
        "conversationId": _field(req, "conversationId") or "",
        "messageId": _field(req, "messageId"),
        "mode": _field(req, "mode"),
        "rating": rating,
        "timestamp": submitted_at,
    }
    feedback_id = _field(req, "feedbackId") or (
        f"chat-feedback-{canonical_digest(redact_sensitive(projection)).removeprefix('sha256:')[:16]}"
    )
    record = {
        "apiVersion": "aiops.komsco/v1",
        "kind": "ChatFeedbackRecord",
        "metadata": {
            "createdAt": created_at,
            "name": feedback_id,
        },
        "spec": {
            "answerContract": _field(req, "answerContract") or "",
            "assistantAnswer": redact_sensitive(assistant_answer),
            "answerSource": _field(req, "answerSource") or "",
            "conversationId": _field(req, "conversationId") or "",
            "intent": _field(req, "intent") or "",
            "messageId": _field(req, "messageId"),
            "mode": _field(req, "mode"),
            "optionalComment": redact_sensitive(_field(req, "optionalComment") or ""),
            "rating": rating,
            "route": _field(req, "route") or "",
            "source": _field(req, "source") or _field(req, "answerSource") or "",
            "submittedAt": submitted_at,
            "userMessage": redact_sensitive(user_message),
        },
        "subject": redact_sensitive(dict(subject)),
    }
    response = {
        "apiVersion": "aiops.komsco/v1",
        "kind": "ChatFeedback",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }
    return str(feedback_id), record, response
