from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from .security import canonical_digest, redact_sensitive


CANDIDATE_ACTION_DIGEST_FIELDS = (
    "schemaVersion",
    "clusterId",
    "requester",
    "target",
    "action",
    "policy",
)
SEALED_ACTION_PLAN_DIGEST_FIELDS = (
    "schemaVersion",
    "clusterId",
    "metadata",
    "target",
    "action",
    "safety",
    "approvalPresentation",
)


def default_policy_binding(policy: Mapping[str, Any]) -> dict[str, Any]:
    policy_projection = redact_sensitive(dict(policy))
    policy_digest = canonical_digest(policy_projection)
    return {
        "policyDecisionId": policy_projection.get("policyDecisionId") or "pd-local-foundation",
        "policyBundleHash": policy_projection.get("policyBundleHash") or "sha256:local-foundation",
        "policyInputDigest": policy_projection.get("policyInputDigest") or policy_digest,
        "policyDecisionDigest": policy_projection.get("policyDecisionDigest") or policy_digest,
    }


def subject_digest(subject: Mapping[str, Any]) -> str:
    return canonical_digest(
        {
            "groupsDigest": subject.get("groupsDigest"),
            "uid": subject.get("uid"),
            "username": subject.get("username"),
        }
    )


def normalized_parameters_digest(candidate: Mapping[str, Any]) -> str:
    action = candidate.get("action") if isinstance(candidate.get("action"), Mapping) else {}
    return canonical_digest(action.get("normalizedParameters") or {})


def policy_binding_digest(policy: Mapping[str, Any]) -> str:
    return canonical_digest(default_policy_binding(policy))


def candidate_action_request_digest(candidate: Mapping[str, Any]) -> str:
    projection = {field: candidate.get(field) for field in CANDIDATE_ACTION_DIGEST_FIELDS}
    return canonical_digest(redact_sensitive(projection))


def sealed_action_plan_digest(plan: Mapping[str, Any]) -> str:
    projection = {field: plan.get(field) for field in SEALED_ACTION_PLAN_DIGEST_FIELDS}
    return canonical_digest(redact_sensitive(projection))


def same_observed_subject(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return (
        left.get("username") == right.get("username")
        and left.get("uid") == right.get("uid")
        and left.get("groupsDigest") == right.get("groupsDigest")
    )


def parse_rfc3339(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def expires_at_rfc3339(delta: timedelta) -> str:
    return (datetime.now(UTC) + delta).isoformat()
