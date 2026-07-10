import pytest

from komsco_ai_gateway.aiops_core import (
    AiopsCoreError,
    build_mutation_request,
    build_rollback_request,
    build_set_deployment_container_command_request,
    matching_hpas_for_deployment,
)


def test_core_action_hpa_guard_requires_review_for_deployment_scale() -> None:
    plan = {
        "target": {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "namespace": "team-a",
            "name": "web-a",
            "uid": "deployment-uid-a",
        },
        "action": {
            "toolName": "set_replicas_within_bounds",
            "normalizedParameters": {
                "replicas": 4,
                "minReplicas": 1,
                "maxReplicas": 5,
                "hpaReviewed": False,
            },
        },
    }
    deployment = {
        "metadata": {"namespace": "team-a", "name": "web-a", "uid": "deployment-uid-a"},
        "spec": {"replicas": 2},
    }
    hpa = {
        "metadata": {"namespace": "team-a", "name": "web-hpa", "uid": "hpa-uid-a"},
        "spec": {
            "scaleTargetRef": {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "name": "web-a",
            }
        },
    }

    assert matching_hpas_for_deployment([hpa], plan["target"])[0]["metadata"]["name"] == "web-hpa"
    with pytest.raises(AiopsCoreError):
        build_mutation_request(plan, live_target=deployment, hpas=[hpa])

    reviewed_plan = {
        **plan,
        "action": {
            **plan["action"],
            "normalizedParameters": {
                **plan["action"]["normalizedParameters"],
                "hpaReviewed": True,
            },
        },
    }
    request = build_mutation_request(reviewed_plan, live_target=deployment, hpas=[hpa])

    assert request.path.endswith("/deployments/web-a/scale")
    assert request.body == {"spec": {"replicas": 4}}


def test_core_action_rollback_uses_owned_replicaset_revision() -> None:
    plan = {
        "target": {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "namespace": "team-a",
            "name": "web-a",
            "uid": "deployment-uid-a",
        },
        "action": {
            "toolName": "rollback_deployment_to_revision",
            "normalizedParameters": {"revision": 2},
        },
    }
    deployment = {
        "metadata": {
            "namespace": "team-a",
            "name": "web-a",
            "uid": "deployment-uid-a",
            "annotations": {"deployment.kubernetes.io/revision": "3"},
        },
        "spec": {"template": {"metadata": {"labels": {"app": "web"}}}},
    }
    replica_set = {
        "metadata": {
            "namespace": "team-a",
            "name": "web-a-abc",
            "uid": "rs-uid-a",
            "annotations": {"deployment.kubernetes.io/revision": "2"},
            "ownerReferences": [{"uid": "deployment-uid-a", "controller": True}],
        },
        "spec": {
            "template": {
                "metadata": {
                    "labels": {"app": "web", "pod-template-hash": "abc"},
                    "annotations": {"deployment.kubernetes.io/revision": "2"},
                },
                "spec": {"containers": [{"name": "web", "image": "example/web:v1"}]},
            }
        },
    }

    request = build_rollback_request(plan, deployment, [replica_set])
    template = request.body["spec"]["template"]

    assert request.path.endswith("/deployments/web-a")
    assert template["metadata"]["labels"] == {"app": "web"}
    assert template["metadata"]["annotations"]["aiops.komsco/rollback-revision"] == "2"
    assert "pod-template-hash" not in str(template)


def test_core_action_updates_deployment_container_command() -> None:
    plan = {
        "target": {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "namespace": "team-a",
            "name": "sample-crashy",
            "uid": "deployment-uid-a",
        },
        "action": {
            "toolName": "set_deployment_container_command",
            "normalizedParameters": {
                "command": ["python", "-c", "import time; time.sleep(86400)"],
                "containerName": "app",
                "expectedPreviousCommandDigest": "",
                "reason": "CrashLoopBackOff command fix",
            },
        },
    }
    deployment = {
        "metadata": {
            "namespace": "team-a",
            "name": "sample-crashy",
            "uid": "deployment-uid-a",
        },
        "spec": {
            "template": {
                "metadata": {"labels": {"app": "sample-crashy"}},
                "spec": {
                    "containers": [
                        {
                            "name": "app",
                            "image": "example/sample:v1",
                            "command": ["python", "-c", "raise SystemExit('boom')"],
                        }
                    ]
                },
            }
        },
    }

    request = build_set_deployment_container_command_request(plan, deployment)
    container_patch = request.body["spec"]["template"]["spec"]["containers"][0]
    annotations = request.body["spec"]["template"]["metadata"]["annotations"]

    assert request.method == "PATCH"
    assert request.path.endswith("/deployments/sample-crashy")
    assert request.content_type == "application/strategic-merge-patch+json"
    assert container_patch == {
        "name": "app",
        "command": ["python", "-c", "import time; time.sleep(86400)"],
    }
    assert annotations["aiops.komsco/command-container"] == "app"
    assert annotations["aiops.komsco/command-action-digest"].startswith("sha256:")
