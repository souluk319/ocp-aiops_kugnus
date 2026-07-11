import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from komsco_ai_gateway import main as gateway_main
from komsco_ai_gateway import gateway_state
from komsco_ai_gateway import namespace_cleanup_runtime_support
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


def test_namespace_cleanup_uses_current_main_parser_binding(monkeypatch) -> None:
    monkeypatch.setattr(
        gateway_main,
        "parse_gateway_current_pod_list_rows",
        lambda _evidence: (
            [
                {
                    "namespace": "gpu-test-kugnus",
                    "pod": "aiops-test-pod-latest",
                    "podStart": "2026-07-10T10:00:00Z",
                }
            ],
            "gpu-test-kugnus",
            "1 / 1",
        ),
    )

    selected = gateway_main.select_latest_cleanup_pod_rows(
        {"namespace": "gpu-test-kugnus", "podPattern": "aiops-test-pod-*"},
        "ignored by patched parser",
        1,
    )

    assert [row["pod"] for row in selected] == ["aiops-test-pod-latest"]


def test_namespace_cleanup_runtime_support_does_not_import_main() -> None:
    module_path = (
        Path(__file__).parents[1]
        / "komsco_ai_gateway"
        / "namespace_cleanup_runtime_support.py"
    )
    source = module_path.read_text(encoding="utf-8")

    assert "from .main import" not in source
    assert "import komsco_ai_gateway.main" not in source


def test_namespace_cleanup_wrappers_keep_current_dependencies(monkeypatch) -> None:
    fetch = object()
    observed = {}

    async def collect(_auth, _names, config, deps):
        observed["config"] = config
        observed["fetch"] = deps.fetch_ocp_json
        return {"ok": True}

    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fetch)
    monkeypatch.setattr(
        namespace_cleanup_runtime_support,
        "collect_namespace_cleanup_inventory",
        collect,
    )

    result = asyncio.run(
        gateway_main.collect_namespace_cleanup_inventory("Bearer test", ["team-a"])
    )

    assert result == {"ok": True}
    assert observed["fetch"] is fetch
    assert observed["config"].api_url == gateway_main.OPENSHIFT_API_URL


def test_namespace_cleanup_candidate_store_preserves_state_identity(monkeypatch) -> None:
    assert (
        gateway_main.NAMESPACE_CLEANUP_CHAT_CANDIDATES
        is gateway_state.NAMESPACE_CLEANUP_CHAT_CANDIDATES
    )
    observed = {}

    def remember(_inventory, _run_id, _incident_id, deps):
        observed["cache"] = deps.candidate_cache
        observed["builder"] = deps.build_candidate

    builder = lambda *_args: {}  # noqa: E731
    monkeypatch.setattr(gateway_main, "namespace_cleanup_candidate_from_item", builder)
    monkeypatch.setattr(
        namespace_cleanup_runtime_support,
        "remember_namespace_cleanup_candidates",
        remember,
    )

    gateway_main.remember_namespace_cleanup_candidates({}, "run", "incident")

    assert observed["cache"] is gateway_state.NAMESPACE_CLEANUP_CHAT_CANDIDATES
    assert observed["builder"] is builder
