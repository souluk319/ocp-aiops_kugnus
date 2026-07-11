import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException


OPENSHIFT_USER_AUTH_FAILURE_MESSAGE = (
    "OpenShift 사용자 인증이 만료되었거나 Gateway로 전달된 사용자 토큰이 유효하지 않습니다. "
    "OpenShift 콘솔을 새로고침하거나 다시 로그인한 뒤 요청을 재시도하세요."
)


@dataclass(frozen=True)
class AuthRuntimeConfig:
    openshift_api_url: str
    openshift_api_ca_file: str | bool
    product_access_review_enabled: bool
    product_access_review_required: bool
    product_access_review_group: str
    product_access_review_resource: str
    product_access_review_verb: str
    product_access_review_name: str
    mutations_enabled: bool


@dataclass(frozen=True)
class AuthRuntimeCallbacks:
    http_client_factory: Callable[..., Any]
    redact_sensitive: Callable[[Any], Any]
    safe_exception_text: Callable[..., str]
    safe_subject: Callable[[Mapping[str, Any] | None], dict[str, Any]]
    enforce_rate_limit: Callable[[str], None]


def verify_user_access(
    callbacks: AuthRuntimeCallbacks,
    user_auth_header: str,
    req: Any,
) -> None:
    if not user_auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing OpenShift bearer token")

    if not req.message.strip() and not req.attachments:
        raise HTTPException(status_code=400, detail="Message or image attachment is required")

    callbacks.enforce_rate_limit(user_auth_header)


def verify_bearer_header(user_auth_header: str | None) -> str:
    if not user_auth_header or not user_auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing OpenShift bearer token")

    token = user_auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing OpenShift bearer token")

    return f"Bearer {token}"


def build_product_access_review_request(config: AuthRuntimeConfig) -> dict[str, Any]:
    resource_attributes: dict[str, Any] = {
        "resource": config.product_access_review_resource,
        "verb": config.product_access_review_verb,
    }
    if config.product_access_review_group:
        resource_attributes["group"] = config.product_access_review_group
    if config.product_access_review_name:
        resource_attributes["name"] = config.product_access_review_name

    return {
        "apiVersion": "authorization.k8s.io/v1",
        "kind": "SelfSubjectAccessReview",
        "spec": {"resourceAttributes": resource_attributes},
    }


def build_action_access_review_request(plan: Mapping[str, Any]) -> dict[str, Any]:
    action = plan.get("action") if isinstance(plan.get("action"), Mapping) else {}
    target = plan.get("target") if isinstance(plan.get("target"), Mapping) else {}
    authorization = action.get("authorization") if isinstance(action.get("authorization"), Mapping) else {}
    resource_attributes: dict[str, Any] = {
        "group": authorization.get("apiGroup") or "",
        "resource": authorization.get("resource") or "",
        "subresource": authorization.get("subresource") or "",
        "verb": authorization.get("verb") or "",
        "namespace": target.get("namespace") or "",
        "name": target.get("name") or "",
    }
    if resource_attributes["verb"] == "create":
        resource_attributes.pop("name", None)
    if not resource_attributes["group"]:
        resource_attributes.pop("group", None)
    if not resource_attributes["subresource"]:
        resource_attributes.pop("subresource", None)
    return {
        "apiVersion": "authorization.k8s.io/v1",
        "kind": "SelfSubjectAccessReview",
        "spec": {"resourceAttributes": resource_attributes},
    }


async def fetch_action_access_review(
    config: AuthRuntimeConfig,
    callbacks: AuthRuntimeCallbacks,
    user_auth_header: str,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    review_request = build_action_access_review_request(plan)
    if not config.openshift_api_url:
        return {
            "allowed": not config.mutations_enabled,
            "enabled": True,
            "resourceAttributes": review_request["spec"]["resourceAttributes"],
            "skipped": True,
            "reason": "OPENSHIFT_API_URL is not configured",
        }

    try:
        async with callbacks.http_client_factory(
            verify=config.openshift_api_ca_file,
            timeout=httpx.Timeout(10.0, connect=5.0),
        ) as client:
            response = await client.post(
                f"{config.openshift_api_url}/apis/authorization.k8s.io/v1/selfsubjectaccessreviews",
                headers={
                    "Accept": "application/json",
                    "Authorization": user_auth_header,
                    "Content-Type": "application/json",
                },
                json=review_request,
            )
    except httpx.RequestError as exc:
        return {
            "allowed": False,
            "enabled": True,
            "resourceAttributes": review_request["spec"]["resourceAttributes"],
            "reason": "OpenShift API unavailable during action access review",
            "evaluationError": json.dumps(
                {
                    "code": "openshift_api_unavailable",
                    "message": "OpenShift API 응답 지연 또는 연결 실패로 action access review를 완료하지 못했습니다.",
                    "operation": "action_access_review",
                    "remediation": "VPN/OCP API 연결을 확인한 뒤 요청을 다시 실행하세요.",
                    "upstreamReason": callbacks.safe_exception_text(exc),
                },
                ensure_ascii=False,
            ),
        }

    if response.status_code >= 400:
        return {
            "allowed": False,
            "enabled": True,
            "resourceAttributes": review_request["spec"]["resourceAttributes"],
            "reason": f"SelfSubjectAccessReview failed with HTTP {response.status_code}",
            "evaluationError": response.text[:500],
        }

    payload = response.json()
    status_payload = payload.get("status", {}) if isinstance(payload, Mapping) else {}
    status_map = status_payload if isinstance(status_payload, Mapping) else {}
    return {
        "allowed": bool(status_map.get("allowed")),
        "denied": bool(status_map.get("denied")),
        "enabled": True,
        "evaluationError": status_map.get("evaluationError") or "",
        "reason": status_map.get("reason") or "",
        "resourceAttributes": review_request["spec"]["resourceAttributes"],
        "skipped": False,
    }


def enforce_action_access_review(
    callbacks: AuthRuntimeCallbacks,
    review: Mapping[str, Any],
) -> None:
    if review.get("allowed") is True:
        return
    raise HTTPException(
        status_code=403,
        detail={
            "reason": "action_authorization_denied",
            "message": "Approver is not authorized for the exact Kubernetes action.",
            "review": callbacks.redact_sensitive(dict(review)),
        },
    )


async def fetch_product_access_review(
    config: AuthRuntimeConfig,
    callbacks: AuthRuntimeCallbacks,
    user_auth_header: str,
) -> dict[str, Any]:
    if not config.product_access_review_enabled:
        return {
            "allowed": True,
            "enabled": False,
            "required": config.product_access_review_required,
            "skipped": True,
            "reason": "product access review disabled",
        }

    review_request = build_product_access_review_request(config)
    if not config.openshift_api_url:
        return {
            "allowed": not config.product_access_review_required,
            "enabled": True,
            "required": config.product_access_review_required,
            "resourceAttributes": review_request["spec"]["resourceAttributes"],
            "skipped": True,
            "reason": "OPENSHIFT_API_URL is not configured",
        }

    try:
        async with callbacks.http_client_factory(
            verify=config.openshift_api_ca_file,
            timeout=httpx.Timeout(10.0, connect=5.0),
        ) as client:
            response = await client.post(
                f"{config.openshift_api_url}/apis/authorization.k8s.io/v1/selfsubjectaccessreviews",
                headers={
                    "Accept": "application/json",
                    "Authorization": user_auth_header,
                    "Content-Type": "application/json",
                },
                json=review_request,
            )
    except httpx.RequestError as exc:
        return {
            "allowed": False,
            "enabled": True,
            "required": config.product_access_review_required,
            "resourceAttributes": review_request["spec"]["resourceAttributes"],
            "reason": "OpenShift API unavailable during product access review",
            "evaluationError": json.dumps(
                {
                    "code": "openshift_api_unavailable",
                    "message": "OpenShift API 응답 지연 또는 연결 실패로 product access review를 완료하지 못했습니다.",
                    "operation": "product_access_review",
                    "remediation": "VPN/OCP API 연결을 확인한 뒤 요청을 다시 실행하세요.",
                    "upstreamReason": callbacks.safe_exception_text(exc),
                },
                ensure_ascii=False,
            ),
        }

    if response.status_code >= 400:
        return {
            "allowed": False,
            "enabled": True,
            "required": config.product_access_review_required,
            "resourceAttributes": review_request["spec"]["resourceAttributes"],
            "reason": f"SelfSubjectAccessReview failed with HTTP {response.status_code}",
            "evaluationError": response.text[:500],
        }

    payload = response.json()
    status_payload = payload.get("status", {}) if isinstance(payload, Mapping) else {}
    status_map = status_payload if isinstance(status_payload, Mapping) else {}
    return {
        "allowed": bool(status_map.get("allowed")),
        "denied": bool(status_map.get("denied")),
        "enabled": True,
        "evaluationError": status_map.get("evaluationError") or "",
        "reason": status_map.get("reason") or "",
        "required": config.product_access_review_required,
        "resourceAttributes": review_request["spec"]["resourceAttributes"],
        "skipped": False,
    }


def product_access_review_status(review: Mapping[str, Any]) -> str:
    if review.get("skipped"):
        return "skipped"
    if review.get("allowed") is True:
        return "success"
    if review.get("required") is True:
        return "error"
    return "warning"


def summarize_product_access_review(
    callbacks: AuthRuntimeCallbacks,
    review: Mapping[str, Any],
) -> str:
    if review.get("enabled") is False:
        return "Product access SSAR is disabled by configuration."

    attributes = review.get("resourceAttributes")
    attributes_text = json.dumps(callbacks.redact_sensitive(attributes), ensure_ascii=False)
    return "\n".join(
        [
            f"enabled: {review.get('enabled')}",
            f"required: {review.get('required')}",
            f"allowed: {review.get('allowed')}",
            f"denied: {review.get('denied', False)}",
            f"resourceAttributes: {attributes_text}",
            f"reason: {review.get('reason') or '-'}",
            f"evaluationError: {review.get('evaluationError') or '-'}",
        ]
    )


def enforce_product_access_review(review: Mapping[str, Any]) -> None:
    if review.get("required") is True and review.get("allowed") is not True:
        reason = review.get("reason") or review.get("evaluationError") or "product access denied"
        raise HTTPException(status_code=403, detail=f"KOMSCO AI product access denied: {reason}")


def build_openshift_user_auth_failure_detail(
    callbacks: AuthRuntimeCallbacks,
    status_code: int,
    body: str,
) -> dict[str, Any]:
    upstream_reason = ""
    try:
        payload = json.loads(body)
        if isinstance(payload, Mapping):
            upstream_reason = str(payload.get("reason") or payload.get("message") or "")
    except json.JSONDecodeError:
        upstream_reason = body[:120]
    return {
        "code": "openshift_user_auth_failed",
        "message": OPENSHIFT_USER_AUTH_FAILURE_MESSAGE,
        "remediation": "OpenShift 콘솔 세션을 갱신한 뒤 AIOps 요청을 다시 실행하세요.",
        "upstreamStatus": status_code,
        "upstreamReason": callbacks.redact_sensitive(upstream_reason),
    }


def build_openshift_api_unavailable_detail(
    callbacks: AuthRuntimeCallbacks,
    operation: str,
    exc: BaseException,
) -> dict[str, Any]:
    return {
        "code": "openshift_api_unavailable",
        "message": "OpenShift API 응답 지연 또는 연결 실패로 Gateway가 현재 클러스터 증거를 수집하지 못했습니다.",
        "operation": operation,
        "remediation": "VPN/OCP API 연결을 확인한 뒤 요청을 다시 실행하세요.",
        "upstreamReason": callbacks.safe_exception_text(exc),
    }


def http_exception_message(
    callbacks: AuthRuntimeCallbacks,
    exc: HTTPException,
) -> str:
    detail = exc.detail
    if isinstance(detail, Mapping):
        message = detail.get("message")
        if message:
            return str(message)
        return json.dumps(callbacks.redact_sensitive(detail), ensure_ascii=False)
    return str(detail) or exc.__class__.__name__


def is_openshift_user_auth_failure(exc: HTTPException) -> bool:
    detail = exc.detail
    return (
        exc.status_code == 401
        and isinstance(detail, Mapping)
        and detail.get("code") == "openshift_user_auth_failed"
    )


async def fetch_self_subject_review(
    config: AuthRuntimeConfig,
    callbacks: AuthRuntimeCallbacks,
    user_auth_header: str,
) -> dict[str, Any]:
    if not config.openshift_api_url:
        return callbacks.safe_subject(None)

    try:
        async with callbacks.http_client_factory(
            verify=config.openshift_api_ca_file,
            timeout=httpx.Timeout(10.0, connect=5.0),
        ) as client:
            response = await client.post(
                f"{config.openshift_api_url}/apis/authentication.k8s.io/v1/selfsubjectreviews",
                headers={
                    "Accept": "application/json",
                    "Authorization": user_auth_header,
                    "Content-Type": "application/json",
                },
                json={
                    "apiVersion": "authentication.k8s.io/v1",
                    "kind": "SelfSubjectReview",
                },
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=504,
            detail=build_openshift_api_unavailable_detail(
                callbacks, "self_subject_review", exc
            ),
        ) from exc

    if response.status_code >= 400:
        body = response.text[:500]
        if response.status_code == 401:
            raise HTTPException(
                status_code=401,
                detail=build_openshift_user_auth_failure_detail(
                    callbacks, response.status_code, body
                ),
            )
        raise HTTPException(
            status_code=response.status_code,
            detail=f"OpenShift subject review failed: {body}",
        )

    payload = response.json()
    user_info = payload.get("status", {}).get("userInfo", {}) if isinstance(payload, Mapping) else {}
    return callbacks.safe_subject(user_info if isinstance(user_info, Mapping) else None)


def summarize_subject_detail(subject: Mapping[str, Any], *, live_review: bool) -> str:
    if not live_review:
        return "OPENSHIFT_API_URL 미설정: bearer 형식만 확인했고 live SelfSubjectReview는 건너뜀"

    return "\n".join(
        [
            f"username: {subject.get('username')}",
            f"uid: {subject.get('uid')}",
            f"groupsDigest: {subject.get('groupsDigest')}",
            f"authenticatedByCluster: {subject.get('authenticatedByCluster')}",
        ]
    )


def build_status_access_review_failure(
    callbacks: AuthRuntimeCallbacks,
    exc: HTTPException,
) -> dict[str, Any]:
    detail = exc.detail
    if isinstance(detail, Mapping):
        safe_detail: Any = callbacks.redact_sensitive(dict(detail))
    else:
        safe_detail = http_exception_message(callbacks, exc)
    return {
        "status": "degraded",
        "recordsVisible": False,
        "reason": "OpenShift subject review unavailable; runtime safety status is returned without user-scoped records.",
        "subjectReview": {
            "ok": False,
            "statusCode": exc.status_code,
            "detail": safe_detail,
        },
    }


def build_skipped_product_access_review(
    config: AuthRuntimeConfig,
    reason: str,
) -> dict[str, Any]:
    return {
        "allowed": False,
        "enabled": config.product_access_review_enabled,
        "required": config.product_access_review_required,
        "resourceAttributes": build_product_access_review_request(config)["spec"]["resourceAttributes"],
        "skipped": True,
        "reason": reason,
    }
