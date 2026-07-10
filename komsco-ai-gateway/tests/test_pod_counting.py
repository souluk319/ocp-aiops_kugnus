import subprocess
import sys

import pytest

import komsco_ai_gateway.pod_counting as pod_counting
from komsco_ai_gateway.pod_counting import build_pod_count_investigation


MOVED_PUBLIC_SYMBOLS = (
    "selector_matches_labels",
    "pod_matches_deployment_selector",
    "pod_ready_numbers",
    "pod_is_fully_ready",
    "pod_restart_total",
    "pod_is_terminating",
    "pod_matches_target_fallback",
    "deployment_matches_identity",
    "summarize_counted_pods",
    "build_top_pod_namespace_count_result",
    "top_pod_namespace_count_response",
    "build_pod_count_investigation",
    "pod_count_investigation_response",
    "pod_display_state",
)


def test_pod_counting_import_does_not_import_main() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import komsco_ai_gateway.pod_counting; "
            "assert 'komsco_ai_gateway.main' not in sys.modules",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize(
    ("selector", "labels", "expected"),
    [
        ({"matchLabels": {"app": "web"}}, {"app": "web"}, True),
        ({"matchExpressions": [{"key": "tier", "operator": "In", "values": ["api"]}]}, {"tier": "api"}, True),
        ({"matchExpressions": [{"key": "tier", "operator": "In", "values": ["api"]}]}, {"tier": "db"}, False),
        ({"matchExpressions": [{"key": "tier", "operator": "NotIn", "values": ["db"]}]}, {}, True),
        ({"matchExpressions": [{"key": "tier", "operator": "NotIn", "values": ["db"]}]}, {"tier": "db"}, False),
        ({"matchExpressions": [{"key": "tier", "operator": "Exists"}]}, {"tier": "api"}, True),
        ({"matchExpressions": [{"key": "tier", "operator": "Exists"}]}, {}, False),
        ({"matchExpressions": [{"key": "debug", "operator": "DoesNotExist"}]}, {}, True),
        ({"matchExpressions": [{"key": "debug", "operator": "DoesNotExist"}]}, {"debug": "true"}, False),
        ({"matchExpressions": [{"key": "tier", "operator": "Other"}]}, {"tier": "api"}, False),
        ({}, {}, False),
    ],
)
def test_selector_matches_labels_operators(selector: dict, labels: dict, expected: bool) -> None:
    assert pod_counting.selector_matches_labels(selector, labels) is expected


def test_pod_readiness_restarts_terminating_and_display_state() -> None:
    pod = {
        "metadata": {"deletionTimestamp": "2026-07-11T00:00:00Z"},
        "status": {
            "containerStatuses": [
                {"ready": True, "restartCount": 2},
                {
                    "ready": False,
                    "restartCount": 3,
                    "state": {"waiting": {"reason": "CrashLoopBackOff"}},
                },
            ],
            "phase": "Running",
        },
    }

    assert pod_counting.pod_ready_numbers(pod) == (1, 2)
    assert pod_counting.pod_is_fully_ready(pod) is False
    assert pod_counting.pod_restart_total(pod) == 5
    assert pod_counting.pod_is_terminating(pod) is True
    assert pod_counting.pod_display_state(pod) == "Running (CrashLoopBackOff)"
    ready_pod = {"status": {"containerStatuses": [{"ready": True, "restartCount": 0}]}}
    assert pod_counting.pod_is_fully_ready(ready_pod) is True
    assert pod_counting.pod_is_terminating(ready_pod) is False


def test_fallback_and_deployment_identity_matching() -> None:
    pod = {"metadata": {"name": "web-api-abc", "namespace": "team-a", "labels": {"app": "web-api"}}}
    deployment = {
        "metadata": {"name": "generated", "labels": {}},
        "spec": {"template": {"metadata": {"labels": {"app.kubernetes.io/name": "web-api"}}}},
    }

    assert pod_counting.pod_matches_target_fallback(pod, "web-api", namespace="team-a") is True
    assert pod_counting.pod_matches_target_fallback(pod, "web-api", namespace="team-b") is False
    assert pod_counting.pod_matches_target_fallback(
        {"metadata": {"name": "generated", "labels": {"app.kubernetes.io/instance": "web-api"}}},
        "web-api",
    ) is True
    assert pod_counting.deployment_matches_identity(deployment, "web-api") is True
    assert pod_counting.deployment_matches_identity(
        {"metadata": {"name": "generated", "labels": {"deployment": "web-api"}}},
        "web-api",
    ) is True
    assert pod_counting.deployment_matches_identity(deployment, "other") is False


def test_top_namespace_sorting_skips_missing_namespace() -> None:
    result = pod_counting.build_top_pod_namespace_count_result(
        {
            "items": [
                {"metadata": {"namespace": "team-b"}},
                {"metadata": {}},
                {"metadata": {"namespace": "team-a"}},
                {"metadata": {"namespace": "team-b"}},
                {"metadata": {"namespace": "team-a"}},
            ]
        }
    )

    assert result["rows"] == [
        {"namespace": "team-a", "podCount": 2},
        {"namespace": "team-b", "podCount": 2},
    ]
    assert result["totalPods"] == 4
    assert "default" not in str(result)


def test_pod_count_investigation_preserves_missing_namespace_as_empty_string() -> None:
    result = build_pod_count_investigation(
        {"namespace": "", "targetName": "web-api"},
        {
            "items": [
                {
                    "metadata": {"name": "web-api"},
                    "spec": {"selector": {"matchLabels": {"app": "web-api"}}},
                }
            ]
        },
        {
            "items": [
                {
                    "metadata": {"name": "web-api-a", "labels": {"app": "web-api"}},
                    "status": {"containerStatuses": [{"ready": True}], "phase": "Running"},
                }
            ]
        },
    )

    assert result["namespace"] == ""
    assert result["rows"][0]["namespace"] == ""


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ({"status": "unavailable", "reason": "denied"}, "namespace별 Pod 수를 직접 조회하지 못했습니다."),
        ({"status": "not_found"}, "Pod namespace 정보를 확인하지 못했습니다."),
        (
            {
                "status": "found",
                "rows": [{"namespace": "team-a", "podCount": 2}],
                "topNamespace": "team-a",
                "topPodCount": 2,
            },
            "`team-a`입니다. 현재 조회 범위에서 Pod 2개로 가장 많습니다.",
        ),
    ],
)
def test_top_namespace_response_statuses(result: dict, expected: str) -> None:
    assert expected in pod_counting.top_pod_namespace_count_response(result)


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ({"status": "unavailable", "reason": "denied", "namespace": ""}, "Pod 개수 직접 조회를 수행하지 못했습니다."),
        ({"status": "missing_target", "namespace": ""}, "대상 Deployment 또는 Pod 이름이 필요합니다."),
        (
            {"status": "not_found", "targetName": "web", "namespace": "", "matchStrategy": "fallback"},
            "매칭되는 Deployment 또는 Pod를 찾지 못했습니다.",
        ),
        (
            {
                "status": "found",
                "targetName": "web",
                "namespace": "",
                "rows": [
                    {
                        "namespace": "",
                        "kind": "PodSelector",
                        "targetName": "web",
                        "desiredReplicas": "-",
                        "totalPods": 1,
                        "runningPods": 1,
                        "readyPods": 1,
                        "terminatingPods": 0,
                        "podDetails": [],
                    }
                ],
            },
            "`/web` 기준 현재 Pod는 총 1개",
        ),
    ],
)
def test_pod_count_response_statuses(result: dict, expected: str) -> None:
    assert expected in pod_counting.pod_count_investigation_response(result)


def test_main_reexports_moved_public_symbols_by_identity() -> None:
    import komsco_ai_gateway.main as gateway_main

    for symbol in MOVED_PUBLIC_SYMBOLS:
        assert getattr(gateway_main, symbol) is getattr(pod_counting, symbol)


def test_build_pod_count_investigation_uses_deployment_selector() -> None:
    result = build_pod_count_investigation(
        {"namespace": "team-a", "targetName": "web-api"},
        {
            "items": [
                {
                    "metadata": {"name": "web-api", "namespace": "team-a"},
                    "spec": {
                        "replicas": 3,
                        "selector": {"matchLabels": {"app": "web-api"}},
                    },
                    "status": {"readyReplicas": 3, "availableReplicas": 3},
                }
            ]
        },
        {
            "items": [
                {
                    "metadata": {
                        "labels": {"app": "web-api"},
                        "name": "web-api-7d9c4f4d5f-a",
                        "namespace": "team-a",
                    },
                    "status": {
                        "containerStatuses": [{"ready": True, "restartCount": 0}],
                        "phase": "Running",
                    },
                },
                {
                    "metadata": {
                        "labels": {"app": "web-api"},
                        "name": "web-api-7d9c4f4d5f-b",
                        "namespace": "team-a",
                    },
                    "status": {
                        "containerStatuses": [{"ready": True, "restartCount": 0}],
                        "phase": "Running",
                    },
                },
                {
                    "metadata": {
                        "labels": {"app": "web-api"},
                        "name": "web-api-7d9c4f4d5f-c",
                        "namespace": "team-a",
                    },
                    "status": {
                        "containerStatuses": [{"ready": True, "restartCount": 1}],
                        "phase": "Running",
                    },
                },
                {
                    "metadata": {
                        "labels": {"app": "other"},
                        "name": "other-7d9c4f4d5f-a",
                        "namespace": "team-a",
                    },
                    "status": {
                        "containerStatuses": [{"ready": True, "restartCount": 0}],
                        "phase": "Running",
                    },
                },
            ]
        },
    )

    assert result["status"] == "found"
    assert result["matchStrategy"] == "deployment_selector"
    assert result["rows"][0]["desiredReplicas"] == 3
    assert result["rows"][0]["totalPods"] == 3
    assert result["rows"][0]["runningPods"] == 3
    assert result["rows"][0]["readyPods"] == 3
