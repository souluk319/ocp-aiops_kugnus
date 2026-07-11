import asyncio
import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import HTTPException

from komsco_ai_gateway import auth_runtime
from komsco_ai_gateway import main as gateway_main


def runtime_config(**overrides: Any) -> auth_runtime.AuthRuntimeConfig:
    values = {
        "openshift_api_url": "https://api.example:6443",
        "openshift_api_ca_file": False,
        "product_access_review_enabled": True,
        "product_access_review_required": False,
        "product_access_review_group": "console.openshift.io",
        "product_access_review_resource": "consoleplugins",
        "product_access_review_verb": "get",
        "product_access_review_name": "komsco-ai-console-plugin-kugnus",
        "mutations_enabled": False,
    }
    values.update(overrides)
    return auth_runtime.AuthRuntimeConfig(**values)


def runtime_callbacks(
    http_client_factory: Any = httpx.AsyncClient,
    *,
    enforce_rate_limit: Any = lambda _header: None,
    redact_sensitive: Any = lambda value: value,
    safe_subject: Any = lambda value: dict(value or {"username": "unknown"}),
) -> auth_runtime.AuthRuntimeCallbacks:
    return auth_runtime.AuthRuntimeCallbacks(
        http_client_factory=http_client_factory,
        redact_sensitive=redact_sensitive,
        safe_exception_text=lambda exc, **_kwargs: f"safe:{type(exc).__name__}",
        safe_subject=safe_subject,
        enforce_rate_limit=enforce_rate_limit,
    )


def test_auth_runtime_does_not_import_main() -> None:
    source_path = Path(auth_runtime.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_from = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }

    assert "komsco_ai_gateway.main" not in imported_modules
    assert not any(module == "main" or module.endswith(".main") for module in imported_from)


def test_verify_user_access_uses_injected_rate_limit_callback() -> None:
    observed: list[str] = []
    callbacks = runtime_callbacks(enforce_rate_limit=observed.append)

    auth_runtime.verify_user_access(
        callbacks,
        "Bearer current-token",
        SimpleNamespace(message="pod 상태", attachments=[]),
    )

    assert observed == ["Bearer current-token"]


def test_action_access_review_create_request_omits_resource_name() -> None:
    request = auth_runtime.build_action_access_review_request(
        {
            "action": {
                "authorization": {
                    "apiGroup": "apps",
                    "resource": "deployments",
                    "verb": "create",
                }
            },
            "target": {"namespace": "aiops-demo", "name": "web"},
        }
    )

    attributes = request["spec"]["resourceAttributes"]
    assert attributes == {
        "group": "apps",
        "resource": "deployments",
        "verb": "create",
        "namespace": "aiops-demo",
    }


def test_product_access_request_uses_explicit_config() -> None:
    request = auth_runtime.build_product_access_review_request(
        runtime_config(
            product_access_review_group="custom.example.io",
            product_access_review_resource="assistants",
            product_access_review_verb="use",
            product_access_review_name="operations",
        )
    )

    assert request["spec"]["resourceAttributes"] == {
        "group": "custom.example.io",
        "resource": "assistants",
        "verb": "use",
        "name": "operations",
    }


def test_fetch_self_subject_review_uses_injected_http_client_and_subject_callback() -> None:
    observed: dict[str, Any] = {}

    class SubjectClient:
        def __init__(self, **kwargs: Any) -> None:
            observed["client"] = kwargs

        async def __aenter__(self) -> "SubjectClient":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        async def post(self, url: str, **kwargs: Any) -> httpx.Response:
            observed["url"] = url
            observed["request"] = kwargs
            return httpx.Response(
                201,
                json={
                    "status": {
                        "userInfo": {
                            "username": "alice",
                            "uid": "uid-alice",
                            "groups": ["system:authenticated"],
                        }
                    }
                },
            )

    subject = asyncio.run(
        auth_runtime.fetch_self_subject_review(
            runtime_config(),
            runtime_callbacks(
                SubjectClient,
                safe_subject=lambda value: {"normalized": value["username"]},
            ),
            "Bearer current-token",
        )
    )

    assert subject == {"normalized": "alice"}
    assert observed["url"].endswith("/apis/authentication.k8s.io/v1/selfsubjectreviews")
    assert observed["request"]["headers"]["Authorization"] == "Bearer current-token"
    assert observed["request"]["json"]["kind"] == "SelfSubjectReview"


def test_fetch_product_access_review_disabled_does_not_create_http_client() -> None:
    def fail_client(**_kwargs: Any) -> Any:
        raise AssertionError("HTTP client must not be created")

    review = asyncio.run(
        auth_runtime.fetch_product_access_review(
            runtime_config(product_access_review_enabled=False),
            runtime_callbacks(fail_client),
            "Bearer current-token",
        )
    )

    assert review == {
        "allowed": True,
        "enabled": False,
        "required": False,
        "skipped": True,
        "reason": "product access review disabled",
    }


def test_main_auth_wrappers_follow_current_config_and_callbacks(monkeypatch) -> None:
    monkeypatch.setattr(gateway_main, "PRODUCT_ACCESS_REVIEW_RESOURCE", "patched-resources")
    monkeypatch.setattr(gateway_main, "PRODUCT_ACCESS_REVIEW_VERB", "list")
    request = gateway_main.build_product_access_review_request()

    assert request["spec"]["resourceAttributes"]["resource"] == "patched-resources"
    assert request["spec"]["resourceAttributes"]["verb"] == "list"

    observed: list[str] = []
    monkeypatch.setattr(gateway_main, "enforce_rate_limit", observed.append)
    asyncio.run(
        gateway_main.verify_user_access(
            "Bearer patched-token",
            SimpleNamespace(message="pod 상태", attachments=[]),
        )
    )

    assert observed == ["Bearer patched-token"]


def test_main_error_mapping_uses_current_redaction_callback(monkeypatch) -> None:
    monkeypatch.setattr(gateway_main, "redact_sensitive", lambda _value: "patched-redaction")

    detail = gateway_main.build_openshift_user_auth_failure_detail(
        401,
        '{"reason":"Unauthorized"}',
    )

    assert detail["upstreamReason"] == "patched-redaction"


def test_enforce_action_access_review_redacts_review() -> None:
    with pytest.raises(HTTPException) as exc:
        auth_runtime.enforce_action_access_review(
            runtime_callbacks(redact_sensitive=lambda _value: {"redacted": True}),
            {"allowed": False, "evaluationError": "secret"},
        )

    assert exc.value.status_code == 403
    assert exc.value.detail["review"] == {"redacted": True}
