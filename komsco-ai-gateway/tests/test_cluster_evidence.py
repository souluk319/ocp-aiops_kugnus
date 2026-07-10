import pytest

import komsco_ai_gateway.cluster_evidence as cluster_evidence
import komsco_ai_gateway.main as gateway_main
from komsco_ai_gateway.cluster_evidence import (
    build_cluster_operator_status_evidence,
    build_cronjob_activity_evidence,
    build_deployment_rollout_evidence,
    build_pod_status_evidence,
)
def test_build_cronjob_activity_evidence_includes_schedule_env_and_recent_jobs() -> None:
    evidence = build_cronjob_activity_evidence(
        {
            "items": [
                {
                    "metadata": {"namespace": "tools-dev", "name": "notebook-cleaner"},
                    "spec": {
                        "schedule": "*/15 * * * *",
                        "concurrencyPolicy": "Forbid",
                        "successfulJobsHistoryLimit": 2,
                        "failedJobsHistoryLimit": 3,
                        "jobTemplate": {
                            "spec": {
                                "template": {
                                    "spec": {
                                        "containers": [
                                            {
                                                "image": (
                                                    "ghcr.io/jungyuoo/"
                                                    "ocpops-playbookstudio-sandbox:dev"
                                                ),
                                                "env": [
                                                    {
                                                        "name": (
                                                            "NOTEBOOK_HIBERNATE_AFTER_SECONDS"
                                                        ),
                                                        "value": "1800",
                                                    },
                                                    {
                                                        "name": "NOTEBOOK_RETENTION_DELETE_AFTER_SECONDS",
                                                        "value": "1209600",
                                                    },
                                                ],
                                            }
                                        ]
                                    }
                                }
                            }
                        },
                    },
                }
            ]
        },
        {
            "items": [
                {
                    "metadata": {
                        "namespace": "tools-dev",
                        "name": "notebook-cleaner-29147292",
                        "creationTimestamp": "2026-06-21T03:00:00Z",
                        "ownerReferences": [{"kind": "CronJob", "name": "notebook-cleaner"}],
                    },
                    "status": {
                        "startTime": "2026-06-21T03:00:01Z",
                        "completionTime": "2026-06-21T03:00:05Z",
                        "succeeded": 1,
                    },
                }
            ]
        },
        context_text="notebook-cleaner가 15분마다 보여",
    )

    assert "`notebook-cleaner`" in evidence
    assert "`*/15 * * * *`" in evidence
    assert "15분마다" in evidence
    assert "Forbid" in evidence
    assert "2 | 3 |" in evidence
    assert "`NOTEBOOK_HIBERNATE_AFTER_SECONDS`" in evidence
    assert "1800초 (30분)" in evidence
    assert "1209600초 (14일)" in evidence
    assert "threshold values only" in evidence
    assert "`notebook-cleaner-29147292`" in evidence



def test_build_cronjob_activity_evidence_matches_arbitrary_requested_interval() -> None:
    evidence = build_cronjob_activity_evidence(
        {
            "items": [
                {
                    "metadata": {"namespace": "ops", "name": "fifteen-minute-cleaner"},
                    "spec": {"schedule": "*/15 * * * *"},
                },
                {
                    "metadata": {"namespace": "ops", "name": "backup-cleaner"},
                    "spec": {"schedule": "*/30 * * * *"},
                },
            ]
        },
        context_text="backup-cleaner가 30분마다 보여",
    )

    assert "`backup-cleaner`" in evidence
    assert "30분마다" in evidence
    assert "`fifteen-minute-cleaner`" not in evidence





def test_build_cluster_operator_status_evidence_summarizes_operator_health() -> None:
    evidence = build_cluster_operator_status_evidence(
        {
            "items": [
                {
                    "metadata": {"name": "example-operator"},
                    "status": {
                        "versions": [{"version": "4.20.23"}],
                        "conditions": [
                            {"type": "Available", "status": "True"},
                            {"type": "Degraded", "status": "False"},
                            {"type": "Progressing", "status": "False"},
                        ],
                    },
                }
            ]
        }
    )

    assert "ClusterOperator status evidence" in evidence
    assert "example-operator" in evidence
    assert "Available | Degraded | Progressing" in evidence
    assert "True | False | False" in evidence





def test_build_pod_status_evidence_sorts_container_restart_counts() -> None:
    evidence = build_pod_status_evidence(
        {
            "items": [
                {
                    "metadata": {
                        "name": "lightspeed-app-server-abc",
                        "namespace": "openshift-lightspeed",
                        "ownerReferences": [{"kind": "ReplicaSet", "name": "lightspeed-app-server"}],
                    },
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": "lightspeed-service-api",
                                "ready": True,
                                "restartCount": 0,
                                "state": {"running": {"startedAt": "2026-06-16T01:40:29Z"}},
                            },
                            {
                                "name": "lightspeed-to-dataverse-exporter",
                                "ready": True,
                                "restartCount": 44,
                                "state": {"running": {"startedAt": "2026-06-16T05:04:55Z"}},
                                "lastState": {
                                    "terminated": {
                                        "reason": "Error",
                                        "exitCode": 137,
                                        "finishedAt": "2026-06-16T04:59:40Z",
                                    }
                                },
                            },
                        ],
                    },
                },
                {
                    "metadata": {
                        "name": "nginx-gateway-fabric-controller-manager-abc",
                        "namespace": "openshift-operators",
                    },
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": "manager",
                                "ready": True,
                                "restartCount": 36,
                                "state": {"running": {"startedAt": "2026-06-20T04:54:32Z"}},
                                "lastState": {
                                    "terminated": {
                                        "reason": "Error",
                                        "exitCode": 1,
                                        "finishedAt": "2026-06-20T04:54:32Z",
                                    }
                                },
                            }
                        ],
                    },
                },
            ]
        }
    )

    assert "Restart counts below are cumulative container-level counts" in evidence
    assert "`lightspeed-to-dataverse-exporter`" in evidence
    assert "`manager`" in evidence
    assert evidence.index("`lightspeed-to-dataverse-exporter`") < evidence.index("`manager`")
    assert "Error/137" in evidence


def test_build_pod_status_evidence_includes_requested_namespace_pod_list() -> None:
    evidence = build_pod_status_evidence(
        {
            "items": [
                {
                    "metadata": {"name": "api-a-111", "namespace": "team-a"},
                    "status": {
                        "phase": "Running",
                        "startTime": "2026-06-22T00:00:00Z",
                        "containerStatuses": [
                            {
                                "name": "app",
                                "ready": True,
                                "restartCount": 0,
                                "state": {"running": {"startedAt": "2026-06-22T00:00:10Z"}},
                            }
                        ],
                    },
                },
                {
                    "metadata": {"name": "worker-a-222", "namespace": "team-a"},
                    "status": {
                        "phase": "Pending",
                        "startTime": "2026-06-22T00:01:00Z",
                        "containerStatuses": [
                            {
                                "name": "worker",
                                "ready": False,
                                "restartCount": 2,
                                "state": {"waiting": {"reason": "ImagePullBackOff"}},
                                "lastState": {"terminated": {"reason": "Error", "exitCode": 1}},
                            }
                        ],
                    },
                },
                {
                    "metadata": {"name": "api-b-333", "namespace": "team-b"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": "app",
                                "ready": True,
                                "restartCount": 0,
                                "state": {"running": {"startedAt": "2026-06-22T00:02:00Z"}},
                            }
                        ],
                    },
                },
            ]
        },
        include_pod_list=True,
        list_namespace="team-a",
    )

    assert "Current Pod list evidence:" in evidence
    assert "Namespace filter: `team-a`" in evidence
    assert "Rows shown: 2 / 2" in evidence
    assert "`api-a-111`" in evidence
    assert "`worker-a-222`" in evidence
    assert "`api-b-333`" not in evidence.split("Current Pod list evidence:", 1)[1]


def test_build_pod_status_evidence_marks_failed_pod_start_time() -> None:
    evidence = build_pod_status_evidence(
        {
            "items": [
                {
                    "metadata": {"name": "installer-1-node-a", "namespace": "openshift-example"},
                    "status": {
                        "phase": "Failed",
                        "startTime": "2026-06-09T08:55:51Z",
                        "containerStatuses": [
                            {
                                "name": "installer",
                                "ready": False,
                                "restartCount": 0,
                                "state": {
                                    "terminated": {
                                        "reason": "Error",
                                        "exitCode": 1,
                                    }
                                },
                            }
                        ],
                    },
                }
            ]
        }
    )

    assert "old Failed pods can be historical artifacts" in evidence
    assert "2026-06-09T08:55:51Z" in evidence
    assert "Failed / terminated:Error/1" in evidence


def test_build_pod_status_evidence_includes_unhealthy_spec_and_owner_chain() -> None:
    evidence = build_pod_status_evidence(
        {
            "items": [
                {
                    "metadata": {
                        "name": "sample-crashy-6fd7d7cfd7-r4nd0",
                        "namespace": "team-a",
                        "labels": {
                            "app": "sample-crashy",
                            "aiops.komsco/scenario": "sample",
                            "pod-template-hash": "6fd7d7cfd7",
                        },
                        "ownerReferences": [{"kind": "ReplicaSet", "name": "sample-crashy-6fd7d7cfd7"}],
                    },
                    "spec": {
                        "containers": [
                            {
                                "name": "app",
                                "image": "registry.example.com/team-a/sample-crashy:v2",
                                "command": ["python", "-c", "raise SystemExit('boom')"],
                                "args": ["--token=my-secret-token-value"],
                            }
                        ],
                    },
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": "app",
                                "ready": False,
                                "restartCount": 3,
                                "state": {"waiting": {"reason": "CrashLoopBackOff"}},
                                "lastState": {
                                    "terminated": {
                                        "reason": "Error",
                                        "exitCode": 1,
                                        "finishedAt": "2026-06-22T01:00:18Z",
                                    }
                                },
                            }
                        ],
                    },
                }
            ]
        },
        {
            "items": [
                {
                    "metadata": {
                        "name": "sample-crashy-6fd7d7cfd7",
                        "namespace": "team-a",
                        "ownerReferences": [{"kind": "Deployment", "name": "sample-crashy"}],
                    }
                }
            ]
        },
    )

    assert "Spec evidence for currently non-healthy or waiting containers" in evidence
    assert "registry.example.com/team-a/sample-crashy:v2" in evidence
    assert "[\"python\", \"-c\", \"raise SystemExit('boom')\"]" in evidence
    assert "--token=[REDACTED]" in evidence
    assert "my-secret-token-value" not in evidence
    assert "app=sample-crashy" in evidence
    assert "aiops.komsco/scenario=sample" in evidence
    assert "ReplicaSet/sample-crashy-6fd7d7cfd7 -> Deployment/sample-crashy" in evidence


def test_build_deployment_rollout_evidence_does_not_treat_ready_as_replaced() -> None:
    evidence = build_deployment_rollout_evidence(
        {
            "items": [
                {
                    "metadata": {
                        "annotations": {"deployment.kubernetes.io/revision": "1"},
                        "name": "two-pod-demo",
                        "namespace": "team-a",
                        "uid": "deployment-uid-a",
                    },
                    "spec": {
                        "replicas": 2,
                        "template": {"metadata": {"labels": {"app": "two-pod-demo"}}},
                    },
                    "status": {
                        "observedGeneration": 1,
                        "readyReplicas": 2,
                        "updatedReplicas": 2,
                    },
                }
            ]
        },
        {
            "items": [
                {
                    "metadata": {
                        "annotations": {"deployment.kubernetes.io/revision": "1"},
                        "name": "two-pod-demo-69c85d74cc",
                        "namespace": "team-a",
                        "ownerReferences": [
                            {"kind": "Deployment", "name": "two-pod-demo", "uid": "deployment-uid-a"}
                        ],
                    },
                    "spec": {"replicas": 2},
                    "status": {"readyReplicas": 2},
                }
            ]
        },
        {
            "items": [
                {
                    "metadata": {
                        "labels": {"app": "two-pod-demo", "pod-template-hash": "69c85d74cc"},
                        "name": "two-pod-demo-69c85d74cc-a",
                        "namespace": "team-a",
                    },
                    "status": {"startTime": "2026-06-22T04:30:47Z"},
                },
                {
                    "metadata": {
                        "labels": {"app": "two-pod-demo", "pod-template-hash": "69c85d74cc"},
                        "name": "two-pod-demo-69c85d74cc-b",
                        "namespace": "team-a",
                    },
                    "status": {"startTime": "2026-06-22T04:30:47Z"},
                },
            ]
        },
    )

    assert "Ready replicas only prove current availability" in evidence
    assert "`two-pod-demo`" in evidence
    assert "| team-a | `two-pod-demo` | 1 | - | 1 | 2/2 | 2 |" in evidence
    assert "two-pod-demo-69c85d74cc(rev=1,desired=2,ready=2)" in evidence
    assert "two-pod-demo-69c85d74cc-a hash=69c85d74cc" in evidence


def test_evidence_builders_preserve_malformed_items_contracts() -> None:
    assert build_pod_status_evidence({"items": "invalid"}) == (
        "Pod status evidence unavailable: API response did not include an items list."
    )
    assert build_deployment_rollout_evidence(None, None, {}) == (
        "Deployment rollout evidence unavailable: deployments API response did not include an items list."
    )
    assert build_cluster_operator_status_evidence({"items": "invalid"}) == (
        "ClusterOperator evidence unavailable: API response did not include an items list."
    )
    assert build_cronjob_activity_evidence({"items": "invalid"}) == (
        "CronJob activity evidence unavailable: API response did not include an items list."
    )


def test_pod_helpers_preserve_malformed_nested_payload_errors() -> None:
    with pytest.raises(AttributeError):
        cluster_evidence.pod_ready_summary({"status": []})
    with pytest.raises(AttributeError):
        cluster_evidence.pod_owner_summary({"metadata": []})
    with pytest.raises(AttributeError):
        build_pod_status_evidence(
            {"items": []},
            {"items": [{"metadata": []}]},
        )


def test_build_pod_status_evidence_sorts_malformed_timestamp_as_oldest() -> None:
    evidence = build_pod_status_evidence(
        {
            "items": [
                {
                    "metadata": {"name": "bad-time", "namespace": "team-a"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": "app",
                                "ready": True,
                                "restartCount": 1,
                                "lastState": {
                                    "terminated": {
                                        "reason": "Error",
                                        "exitCode": 1,
                                        "finishedAt": "not-a-timestamp",
                                    }
                                },
                            }
                        ],
                    },
                },
                {
                    "metadata": {"name": "valid-time", "namespace": "team-a"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": "app",
                                "ready": True,
                                "restartCount": 1,
                                "lastState": {
                                    "terminated": {
                                        "reason": "Error",
                                        "exitCode": 1,
                                        "finishedAt": "2026-06-22T01:00:18Z",
                                    }
                                },
                            }
                        ],
                    },
                },
            ]
        }
    )

    assert "not-a-timestamp" in evidence
    assert evidence.index("`valid-time`") < evidence.index("`bad-time`")


def test_main_reexports_cluster_evidence_public_symbols() -> None:
    public_symbols = (
        "CRONJOB_POLICY_ENV_RE",
        "SECRET_ENV_RE",
        "cluster_operator_condition",
        "build_cluster_operator_status_evidence",
        "cron_minute_interval",
        "requested_minute_interval",
        "schedule_interval_summary",
        "format_seconds_duration",
        "safe_env_value",
        "cronjob_container_summary",
        "cronjob_matches_context",
        "build_cronjob_activity_evidence",
        "state_summary",
        "last_termination_summary",
        "pod_ready_summary",
        "pod_owner_summary",
        "markdown_table_cell",
        "json_list_summary",
        "pod_label_summary",
        "container_spec_index",
        "replicaset_owner_index",
        "pod_owner_chain_summary",
        "build_pod_status_evidence",
        "build_deployment_rollout_evidence",
    )

    for symbol in public_symbols:
        assert getattr(gateway_main, symbol) is getattr(cluster_evidence, symbol)
