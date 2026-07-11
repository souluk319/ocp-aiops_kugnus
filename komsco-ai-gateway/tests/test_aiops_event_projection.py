from __future__ import annotations

from datetime import UTC, datetime, timedelta

from komsco_ai_gateway.aiops_event_projection import (
    aiops_event_severity,
    build_kubernetes_event_items,
    build_problem_pod_event_items,
)


def test_kubernetes_event_projection_prioritizes_risk_and_caps_normal_events() -> None:
    payload = {
        "items": [
            {
                "metadata": {"uid": "normal-1"},
                "reason": "Pulled",
                "type": "Normal",
                "message": "image pulled",
                "lastTimestamp": "2026-07-11T01:00:00Z",
                "involvedObject": {"kind": "Pod", "name": "web-1", "namespace": "team-a"},
            },
            {
                "metadata": {"uid": "normal-2"},
                "reason": "Created",
                "type": "Normal",
                "message": "container created",
                "lastTimestamp": "2026-07-11T02:00:00Z",
                "involvedObject": {"kind": "Pod", "name": "web-2", "namespace": "team-a"},
            },
            {
                "metadata": {"uid": "normal-3"},
                "reason": "Started",
                "type": "Normal",
                "message": "container started",
                "lastTimestamp": "2026-07-11T03:00:00Z",
                "involvedObject": {"kind": "Pod", "name": "web-3", "namespace": "team-a"},
            },
            {
                "metadata": {"uid": "risk-1"},
                "reason": "FailedMount",
                "type": "Warning",
                "message": "volume mount failed",
                "lastTimestamp": "2026-07-11T04:00:00Z",
                "involvedObject": {"kind": "Pod", "name": "broken", "namespace": "team-b"},
            },
        ]
    }

    items = build_kubernetes_event_items(payload, limit=10)

    assert len(items) == 3
    assert items[0]["id"] == "k8s-event-risk-1"
    assert items[0]["severity"] == "risk"
    assert items[0]["target"] == "team-b/Pod/broken"
    assert sum(item["severity"] == "ok" for item in items) == 2


def test_event_severity_keeps_warning_and_failure_distinct() -> None:
    assert aiops_event_severity("FailedScheduling", "Warning") == "risk"
    assert aiops_event_severity("BackOff", "Warning") == "warn"
    assert aiops_event_severity("Started", "Normal") == "ok"


def test_problem_pod_projection_excludes_healthy_build_and_stale_failed_pods() -> None:
    now = datetime.now(UTC)
    payload = {
        "items": [
            {
                "metadata": {
                    "name": "healthy",
                    "namespace": "team-a",
                    "creationTimestamp": now.isoformat(),
                },
                "status": {
                    "phase": "Running",
                    "containerStatuses": [
                        {"name": "app", "ready": True, "restartCount": 0, "state": {"running": {}}}
                    ],
                },
            },
            {
                "metadata": {
                    "name": "crashing",
                    "namespace": "team-a",
                    "creationTimestamp": now.isoformat(),
                },
                "status": {
                    "phase": "Running",
                    "containerStatuses": [
                        {
                            "name": "app",
                            "ready": False,
                            "restartCount": 5,
                            "state": {"waiting": {"reason": "CrashLoopBackOff"}},
                            "lastState": {
                                "terminated": {
                                    "reason": "Error",
                                    "exitCode": 1,
                                    "finishedAt": now.isoformat(),
                                }
                            },
                        }
                    ],
                },
            },
            {
                "metadata": {
                    "name": "sample-build",
                    "namespace": "team-a",
                    "labels": {"openshift.io/build.name": "sample"},
                    "creationTimestamp": now.isoformat(),
                },
                "status": {"phase": "Pending", "containerStatuses": []},
            },
            {
                "metadata": {
                    "name": "old-failure",
                    "namespace": "team-a",
                    "creationTimestamp": (now - timedelta(days=2)).isoformat(),
                },
                "status": {"phase": "Failed", "containerStatuses": []},
            },
        ]
    }

    items = build_problem_pod_event_items(payload)

    assert [item["id"] for item in items] == ["pod-signal-team-a-crashing"]
    assert items[0]["severity"] == "risk"
    assert "CrashLoopBackOff" in items[0]["detail"]
