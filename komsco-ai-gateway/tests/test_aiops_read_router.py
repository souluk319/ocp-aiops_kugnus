import asyncio
import sys

import httpx

from komsco_ai_gateway import aiops_read_router, aiops_read_service, gateway_state
from komsco_ai_gateway import main as gateway_main


def test_aiops_router_uses_fresh_main_dependency_for_each_request(monkeypatch) -> None:
    async def first_overview(_authorization: str | None) -> dict:
        return {
            "spec": {
                "anomalies": {
                    "kind": "AnomalySummary",
                    "spec": {"findings": [{"id": "first", "namespace": "demo"}]},
                }
            }
        }

    async def second_overview(_authorization: str | None) -> dict:
        return {
            "spec": {
                "anomalies": {
                    "kind": "AnomalySummary",
                    "spec": {"findings": [{"id": "second", "namespace": "demo"}]},
                }
            }
        }

    async def run() -> None:
        transport = httpx.ASGITransport(app=gateway_main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            monkeypatch.setattr(gateway_main, "aiops_overview", first_overview)
            first = await client.get(
                "/v1/aiops/anomalies?namespace=demo",
                headers={"Authorization": "Bearer test-token"},
            )
            monkeypatch.setattr(gateway_main, "aiops_overview", second_overview)
            second = await client.get(
                "/v1/aiops/anomalies?namespace=demo",
                headers={"Authorization": "Bearer test-token"},
            )

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["spec"]["findings"][0]["id"] == "first"
        assert second.json()["spec"]["findings"][0]["id"] == "second"

    asyncio.run(run())


def test_main_aiops_helpers_keep_monkeypatch_freshness(monkeypatch) -> None:
    async def overview(_authorization: str | None) -> dict:
        return {"spec": {"actionCandidates": {"items": [{"id": "candidate"}]}}}

    monkeypatch.setattr(gateway_main, "aiops_overview", overview)
    monkeypatch.setattr(
        gateway_main,
        "merge_recent_namespace_cleanup_candidates",
        lambda candidates: {**candidates, "fresh": True},
    )

    result = asyncio.run(gateway_main.aiops_action_candidates("Bearer test-token"))

    assert result["items"] == [{"id": "candidate"}]
    assert result["fresh"] is True


def test_aiops_read_dependencies_reference_gateway_state() -> None:
    deps = gateway_main.aiops_read_dependencies()

    assert deps.stores.chat_transcripts is gateway_state.CHAT_TRANSCRIPTS
    assert deps.stores.chat_feedback is gateway_state.CHAT_FEEDBACK
    assert deps.stores.diagnostic_requests is gateway_state.DIAGNOSTIC_REQUESTS
    assert deps.stores.action_proposals is gateway_state.ACTION_PROPOSALS
    assert deps.stores.sealed_action_plans is gateway_state.SEALED_ACTION_PLANS
    assert deps.stores.approval_decisions is gateway_state.APPROVAL_DECISIONS
    assert deps.stores.execution_records is gateway_state.EXECUTION_RECORDS


def test_aiops_read_modules_do_not_import_main() -> None:
    assert "main" not in aiops_read_router.__dict__
    assert "main" not in aiops_read_service.__dict__
    assert all(
        value is not sys.modules.get("komsco_ai_gateway.main")
        for value in (*aiops_read_router.__dict__.values(), *aiops_read_service.__dict__.values())
    )
