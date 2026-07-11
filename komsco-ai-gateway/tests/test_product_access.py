import asyncio

import httpx

import komsco_ai_gateway.main as gateway_main
from komsco_ai_gateway.main import (
    build_product_access_review_request,
    product_access_review_status,
    summarize_product_access_review,
)


def test_product_access_review_request_is_config_driven_ssar() -> None:
    request = build_product_access_review_request()

    assert request["apiVersion"] == "authorization.k8s.io/v1"
    assert request["kind"] == "SelfSubjectAccessReview"
    attributes = request["spec"]["resourceAttributes"]
    assert attributes["verb"]
    assert attributes["resource"]
    assert "token" not in str(request).lower()


def test_product_access_review_statuses_are_nonblocking_by_default() -> None:
    review = {
        "allowed": False,
        "enabled": True,
        "reason": "not allowed in this namespace",
        "required": False,
        "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
    }

    assert product_access_review_status(review) == "warning"
    assert "required: False" in summarize_product_access_review(review)


def test_product_access_review_timeout_is_reported_without_500(monkeypatch) -> None:
    class TimeoutClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, *args, **kwargs):
            raise httpx.ConnectTimeout("connect timed out")

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.example:6443")
    monkeypatch.setattr(gateway_main.httpx, "AsyncClient", TimeoutClient)

    review = asyncio.run(gateway_main.fetch_product_access_review("Bearer test-token"))

    assert review["allowed"] is False
    assert review["enabled"] is True
    assert review["reason"] == "OpenShift API unavailable during product access review"
    assert "openshift_api_unavailable" in review["evaluationError"]
