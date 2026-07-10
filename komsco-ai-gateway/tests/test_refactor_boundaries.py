import asyncio
from types import SimpleNamespace

import pytest

from komsco_ai_gateway import main as gateway_main
from komsco_ai_gateway import pod_answering
from komsco_ai_gateway.cluster_evidence_runtime import (
    ClusterEvidenceRuntimeConfig,
    collect_crashloop_demo_evidence_events,
    collect_official_namespace_restart_evidence_events,
)


def test_missing_openshift_api_url_preserves_public_evidence_strings() -> None:
    config = ClusterEvidenceRuntimeConfig(
        openshift_api_url="",
        openshift_api_ca_file=False,
        demo_namespace_allowlist=frozenset(),
    )

    crashloop_events = asyncio.run(
        collect_crashloop_demo_evidence_events(
            config,
            SimpleNamespace(),
            "Bearer test-token",
            {"namespace": "demo", "name": "crashing-pod"},
            "req-test",
        )
    )
    restart_events = asyncio.run(
        collect_official_namespace_restart_evidence_events(
            config,
            SimpleNamespace(),
            "Bearer test-token",
            "demo",
            "req-test",
        )
    )

    assert [event["detail"] for event in crashloop_events] == [
        "CrashLoop event evidence unavailable: OPENSHIFT_API_URL is not configured.",
        "CrashLoop previous log availability unavailable: OPENSHIFT_API_URL is not configured.",
        "CrashLoop Pod snapshot unavailable: OPENSHIFT_API_URL is not configured.",
    ]
    assert {event["missingReason"] for event in crashloop_events} == {
        "OPENSHIFT_API_URL is not configured"
    }
    assert {event["missingReason"] for event in restart_events} == {
        "OPENSHIFT_API_URL is not configured"
    }


def test_pod_answering_unconfigured_dependency_has_clear_runtime_error(monkeypatch) -> None:
    monkeypatch.setattr(pod_answering, "_dependencies", None)
    request = SimpleNamespace(message="pod 목록", page_context={})

    with pytest.raises(RuntimeError, match="call configure_pod_answering"):
        pod_answering.build_grounded_aiops_answer(
            request,
            {"task_type": "pod_inventory"},
            None,
        )


def test_main_composite_helpers_follow_current_main_monkeypatches(monkeypatch) -> None:
    request = SimpleNamespace(message="pod 목록", page_context={}, attachments=[])

    monkeypatch.setattr(
        gateway_main,
        "build_pod_namespace_pattern_lookup_answer",
        lambda *_args, **_kwargs: "patched grounded answer",
    )
    assert (
        gateway_main.build_grounded_aiops_answer(request, {"task_type": "pod_inventory"}, None)
        == "patched grounded answer"
    )

    monkeypatch.setattr(gateway_main, "crashloop_demo_target_from_request", lambda _req: {})
    monkeypatch.setattr(
        gateway_main,
        "build_action_proposal_fallback",
        lambda _req, _policy: "patched empty fallback",
    )
    assert (
        gateway_main.build_empty_answer_fallback(
            request,
            {"decision": "action_proposal_only"},
            [],
        )
        == "patched empty fallback"
    )
