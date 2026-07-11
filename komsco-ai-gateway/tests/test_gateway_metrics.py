import asyncio

import httpx

from komsco_ai_gateway.main import METRICS, WORKFLOW_RECORDS, app
from komsco_ai_gateway.security import safe_subject


def test_workflow_and_metrics_endpoints_expose_non_secret_runtime_state() -> None:
    WORKFLOW_RECORDS.clear()
    METRICS["aiops_chat_requests_total"] = 3
    subject = safe_subject(None)
    WORKFLOW_RECORDS["run-test"] = {
        "runId": "run-test",
        "status": "completed",
        "subject": subject,
        "target": {"messageLength": 10},
    }

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            workflow_response = await client.get(
                "/v1/workflows/run-test",
                headers={"Authorization": "Bearer test-token"},
            )
            metrics_response = await client.get("/metrics")

        assert workflow_response.status_code == 200
        assert workflow_response.json()["spec"]["status"] == "completed"
        assert metrics_response.status_code == 200
        assert "aiops_chat_requests_total 3" in metrics_response.text
        assert "Bearer" not in metrics_response.text

    asyncio.run(run())
