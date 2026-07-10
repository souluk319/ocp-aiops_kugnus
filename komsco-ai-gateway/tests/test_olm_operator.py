import base64

import pytest
from fastapi import HTTPException

import komsco_ai_gateway.action_executor as action_executor
import komsco_ai_gateway.olm_operator as olm_operator


def test_olm_operator_evidence_check_installation_skips_mutating_operands() -> None:
    config = olm_operator.installation_config(
        {
            "metadata": {"namespace": "komsco-ai-kugnus"},
            "spec": {
                "targetNamespace": "komsco-ai-kugnus",
                "consolePluginName": "komsco-ai-console-plugin-kugnus",
                "capabilities": {
                    "diagnostics": False,
                    "mutations": False,
                    "unrestrictedCommands": False,
                },
            },
        }
    )
    resources = olm_operator.resources_for(config)
    names = {(resource["kind"], resource["metadata"]["name"]) for resource in resources}

    assert ("Deployment", "komsco-ai-gateway") in names
    assert ("Deployment", "komsco-ai-console-plugin") in names
    assert ("ConsolePlugin", "komsco-ai-console-plugin-kugnus") in names
    assert ("NetworkPolicy", "allow-komsco-ai-kugnus-gateway-to-lightspeed-app-server") in names
    assert ("Deployment", "komsco-ai-action-executor") not in names
    assert ("Deployment", "komsco-ai-host-diagnostics-controller") not in names
    assert ("ServiceAccount", "komsco-ai-action-executor") not in names
    assert ("ServiceAccount", "komsco-ai-host-diagnostics-controller") not in names

    lightspeed_policy = next(
        resource
        for resource in resources
        if resource["kind"] == "NetworkPolicy"
        and resource["metadata"]["name"] == "allow-komsco-ai-kugnus-gateway-to-lightspeed-app-server"
    )
    assert lightspeed_policy["metadata"]["namespace"] == "openshift-lightspeed"
    assert lightspeed_policy["spec"]["ingress"][0]["from"][0]["namespaceSelector"]["matchLabels"] == {
        "kubernetes.io/metadata.name": "komsco-ai-kugnus"
    }


def test_olm_operator_default_installation_runs_action_executor() -> None:
    config = olm_operator.installation_config(
        {
            "metadata": {"namespace": "komsco-ai-kugnus"},
            "spec": {
                "targetNamespace": "komsco-ai-kugnus",
                "consolePluginName": "komsco-ai-console-plugin-kugnus",
            },
        }
    )
    resources = olm_operator.resources_for(config)
    names = {(resource["kind"], resource["metadata"]["name"]) for resource in resources}

    assert config["mode"] == "execute"
    assert config["mutationsEnabled"] is True
    assert config["unrestrictedEnabled"] is False
    assert ("ServiceAccount", "komsco-ai-action-executor") in names
    assert ("Secret", "komsco-ai-action-executor-auth") in names
    assert ("Service", "komsco-ai-action-executor") in names
    assert ("Deployment", "komsco-ai-action-executor") in names
    gateway = next(
        resource
        for resource in resources
        if resource["kind"] == "Deployment" and resource["metadata"]["name"] == "komsco-ai-gateway"
    )
    executor = next(
        resource
        for resource in resources
        if resource["kind"] == "Deployment" and resource["metadata"]["name"] == "komsco-ai-action-executor"
    )
    gateway_env = {item["name"]: item for item in gateway["spec"]["template"]["spec"]["containers"][0]["env"]}
    executor_env = {item["name"]: item for item in executor["spec"]["template"]["spec"]["containers"][0]["env"]}
    expected_ref = {
        "secretKeyRef": {"name": "komsco-ai-action-executor-auth", "key": "shared-token"}
    }

    assert gateway_env["KOMSCO_AI_ACTION_EXECUTOR_SHARED_TOKEN"]["valueFrom"] == expected_ref
    assert executor_env["KOMSCO_AI_ACTION_EXECUTOR_SHARED_TOKEN"]["valueFrom"] == expected_ref
    assert gateway["spec"]["template"]["metadata"]["annotations"][
        "aiops.komsco/action-executor-token-digest"
    ]
    assert (
        gateway["spec"]["template"]["metadata"]["annotations"][
            "aiops.komsco/action-executor-token-digest"
        ]
        == executor["spec"]["template"]["metadata"]["annotations"][
            "aiops.komsco/action-executor-token-digest"
        ]
    )


def test_olm_operator_reuses_existing_action_executor_secret(monkeypatch) -> None:
    existing_token = "existing-action-executor-token"

    def fake_get_resource(
        api_version: str,
        kind: str,
        name: str,
        resource_namespace: str | None = None,
    ) -> dict[str, object] | None:
        if (
            api_version,
            kind,
            name,
            resource_namespace,
        ) == ("v1", "Secret", "komsco-ai-action-executor-auth", "komsco-ai-kugnus"):
            return {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": name, "namespace": resource_namespace},
                "data": {"shared-token": base64.b64encode(existing_token.encode("utf-8")).decode("ascii")},
            }
        return None

    monkeypatch.setattr(olm_operator, "get_resource", fake_get_resource)

    config = olm_operator.installation_config(
        {
            "metadata": {"namespace": "komsco-ai-kugnus"},
            "spec": {
                "targetNamespace": "komsco-ai-kugnus",
                "consolePluginName": "komsco-ai-console-plugin-kugnus",
            },
        }
    )
    resources = olm_operator.resources_for(config)
    secret = next(
        resource
        for resource in resources
        if resource["kind"] == "Secret" and resource["metadata"]["name"] == "komsco-ai-action-executor-auth"
    )
    gateway = next(
        resource
        for resource in resources
        if resource["kind"] == "Deployment" and resource["metadata"]["name"] == "komsco-ai-gateway"
    )
    executor = next(
        resource
        for resource in resources
        if resource["kind"] == "Deployment" and resource["metadata"]["name"] == "komsco-ai-action-executor"
    )
    expected_digest = olm_operator.token_digest(existing_token)

    assert secret["stringData"]["shared-token"] == existing_token
    assert gateway["spec"]["template"]["metadata"]["annotations"][
        "aiops.komsco/action-executor-token-digest"
    ] == expected_digest
    assert executor["spec"]["template"]["metadata"]["annotations"][
        "aiops.komsco/action-executor-token-digest"
    ] == expected_digest


def test_action_executor_requires_shared_token(monkeypatch) -> None:
    monkeypatch.setattr(action_executor, "EXECUTOR_ENABLED", True)
    monkeypatch.setattr(action_executor, "EXECUTOR_SHARED_TOKEN", "")

    with pytest.raises(HTTPException) as missing_config:
        action_executor.verify_executor_ingress(None)
    assert missing_config.value.status_code == 503

    monkeypatch.setattr(action_executor, "EXECUTOR_SHARED_TOKEN", "shared")
    with pytest.raises(HTTPException) as bad_token:
        action_executor.verify_executor_ingress(None)
    assert bad_token.value.status_code == 401

    action_executor.verify_executor_ingress("Bearer shared")


def test_olm_operator_console_transition_disables_legacy_aiops_plugin(monkeypatch) -> None:
    calls = []

    def fake_request(method: str, path: str, **kwargs):
        if method == "GET":
            return {
                "spec": {
                    "plugins": [
                        "komsco-ai-console-plugin",
                        "komsco-ai-console-plugin-kugnus",
                        "lightspeed-console-plugin",
                        "monitoring-plugin",
                    ]
                }
            }
        calls.append((method, path, kwargs))
        return {}

    monkeypatch.setattr(olm_operator, "request", fake_request)

    olm_operator.patch_console_plugin_enabled(
        "komsco-ai-console-plugin-kugnus",
        ["komsco-ai-console-plugin"],
    )

    assert calls == [
        (
            "PATCH",
            "/apis/operator.openshift.io/v1/consoles/cluster",
            {
                "body": {
                    "spec": {
                        "plugins": [
                            "komsco-ai-console-plugin-kugnus",
                            "lightspeed-console-plugin",
                            "monitoring-plugin",
                        ]
                    }
                },
                "content_type": "application/merge-patch+json",
            },
        )
    ]


def test_olm_operator_can_wire_rag_backend_url_from_secret() -> None:
    config = olm_operator.installation_config(
        {
            "metadata": {"namespace": "komsco-ai-kugnus"},
            "spec": {
                "targetNamespace": "komsco-ai-kugnus",
                "consolePluginName": "komsco-ai-console-plugin-kugnus",
                "rag": {
                    "backendUrlSecret": "komsco-ai-rag-pgvector",
                    "backendUrlKey": "database-url",
                    "embeddingProvider": "ollama",
                    "embeddingApiStyle": "ollama",
                    "embeddingBaseUrl": "http://ollama.example:11434",
                    "embeddingModel": "nomic-embed-text:latest",
                    "embeddingTimeoutSeconds": 120,
                    "vectorDimensions": 768,
                },
            },
        }
    )
    gateway = next(
        resource
        for resource in olm_operator.resources_for(config)
        if resource["kind"] == "Deployment" and resource["metadata"]["name"] == "komsco-ai-gateway"
    )
    env = {item["name"]: item for item in gateway["spec"]["template"]["spec"]["containers"][0]["env"]}

    assert env["KOMSCO_AI_RAG_BACKEND_URL"]["valueFrom"]["secretKeyRef"] == {
        "name": "komsco-ai-rag-pgvector",
        "key": "database-url",
    }
    assert env["KOMSCO_AI_EMBEDDING_PROVIDER"]["value"] == "ollama"
    assert env["KOMSCO_AI_EMBEDDING_API_STYLE"]["value"] == "ollama"
    assert env["KOMSCO_AI_EMBEDDING_BASE_URL"]["value"] == "http://ollama.example:11434"
    assert env["KOMSCO_AI_EMBEDDING_MODEL"]["value"] == "nomic-embed-text:latest"
    assert env["KOMSCO_AI_EMBEDDING_TIMEOUT_SECONDS"]["value"] == "120"
    assert env["KOMSCO_AI_EMBEDDING_DIMENSIONS"]["value"] == "768"
    assert env["KOMSCO_AI_RAG_EMBEDDING_MODEL"]["value"] == "nomic-embed-text:latest"
    assert env["KOMSCO_AI_RAG_VECTOR_DIMENSIONS"]["value"] == "768"


def _ready_olm_resource(
    api_version: str,
    kind: str,
    name: str,
    resource_namespace: str | None = None,
) -> dict:
    if kind == "Deployment":
        return {
            "metadata": {"name": name, "namespace": resource_namespace},
            "spec": {"replicas": 1},
            "status": {"availableReplicas": 1, "readyReplicas": 1, "updatedReplicas": 1},
        }
    if kind == "ConfigMap" and name == "komsco-ai-service-ca":
        return {
            "metadata": {"name": name, "namespace": resource_namespace},
            "data": {"service-ca.crt": "test-ca"},
        }
    if kind == "ConsolePlugin":
        return {
            "metadata": {"name": name},
            "spec": {
                "backend": {
                    "service": {
                        "name": "komsco-ai-console-plugin",
                        "namespace": "komsco-ai-kugnus",
                    }
                },
                "proxy": [
                    {
                        "alias": "ai-gateway",
                        "endpoint": {
                            "service": {
                                "name": "komsco-ai-gateway",
                                "namespace": "komsco-ai-kugnus",
                            }
                        },
                    }
                ],
            },
        }
    return {"apiVersion": api_version, "kind": kind, "metadata": {"name": name, "namespace": resource_namespace}}


def test_olm_operator_status_payload_exposes_v011_readiness_conditions(monkeypatch) -> None:
    monkeypatch.setattr(olm_operator, "get_resource", _ready_olm_resource)
    config = olm_operator.installation_config(
        {
            "metadata": {"namespace": "komsco-ai-kugnus", "generation": 7},
            "spec": {
                "targetNamespace": "komsco-ai-kugnus",
                "pluginReplicas": 1,
                "gatewayReplicas": 1,
                "consolePluginName": "komsco-ai-console-plugin-kugnus",
                "capabilities": {
                    "diagnostics": False,
                    "mutations": False,
                    "unrestrictedCommands": False,
                },
            },
        }
    )

    payload = olm_operator.build_status_payload(
        {"metadata": {"name": "komsco-aiops-kugnus", "namespace": "komsco-ai-kugnus", "generation": 7}},
        "Ready",
        "KOMSCO AIOps runtime reconciled",
        config,
    )
    by_type = {item["type"]: item for item in payload["conditions"]}

    assert payload["phase"] == "Ready"
    assert payload["versionScope"] == "Ver.0.1.1"
    assert set(olm_operator.DEFAULT_READINESS_CONDITION_TYPES) <= set(by_type)
    assert by_type["ActionExecutorReady"]["reason"] == "DisabledByReadOnly"
    assert by_type["HostDiagnosticsReady"]["reason"] == "DisabledByPolicy"
    assert payload["components"]["gateway"]["ready"] is True
    assert payload["components"]["consolePlugin"]["ready"] is True
    assert payload["components"]["serviceCA"]["ready"] is True
    assert payload["components"]["rbac"]["ready"] is True
    assert payload["components"]["safetyMode"]["reason"] == "ReadOnlyLocked"


def test_olm_operator_status_payload_reports_progressing_when_gateway_unavailable(monkeypatch) -> None:
    def fake_resource(
        api_version: str,
        kind: str,
        name: str,
        resource_namespace: str | None = None,
    ) -> dict:
        resource = _ready_olm_resource(api_version, kind, name, resource_namespace)
        if kind == "Deployment" and name == "komsco-ai-gateway":
            resource["status"] = {"availableReplicas": 0, "readyReplicas": 0, "updatedReplicas": 1}
        return resource

    monkeypatch.setattr(olm_operator, "get_resource", fake_resource)
    config = olm_operator.installation_config(
        {
            "metadata": {"namespace": "komsco-ai-kugnus", "generation": 8},
            "spec": {
                "targetNamespace": "komsco-ai-kugnus",
                "pluginReplicas": 1,
                "gatewayReplicas": 1,
                "consolePluginName": "komsco-ai-console-plugin-kugnus",
                "capabilities": {
                    "diagnostics": False,
                    "mutations": False,
                    "unrestrictedCommands": False,
                },
            },
        }
    )

    payload = olm_operator.build_status_payload(
        {"metadata": {"name": "komsco-aiops-kugnus", "namespace": "komsco-ai-kugnus", "generation": 8}},
        "Ready",
        "KOMSCO AIOps runtime reconciled",
        config,
    )
    by_type = {item["type"]: item for item in payload["conditions"]}

    assert payload["phase"] == "Progressing"
    assert "GatewayReady" in payload["message"]
    assert by_type["GatewayReady"]["status"] == "False"
    assert by_type["GatewayReady"]["reason"] == "WaitingForRollout"
    assert payload["components"]["gateway"]["ready"] is False


def test_olm_operator_status_rejects_execute_mode_without_mutations(monkeypatch) -> None:
    monkeypatch.setattr(olm_operator, "get_resource", _ready_olm_resource)
    config = olm_operator.installation_config(
        {
            "metadata": {"namespace": "komsco-ai-kugnus", "generation": 9},
            "spec": {
                "targetNamespace": "komsco-ai-kugnus",
                "mode": "execute",
                "pluginReplicas": 1,
                "gatewayReplicas": 1,
                "consolePluginName": "komsco-ai-console-plugin-kugnus",
                "capabilities": {
                    "diagnostics": False,
                    "mutations": False,
                    "unrestrictedCommands": False,
                },
            },
        }
    )

    payload = olm_operator.build_status_payload(
        {"metadata": {"name": "komsco-aiops-kugnus", "namespace": "komsco-ai-kugnus", "generation": 9}},
        "Ready",
        "KOMSCO AIOps runtime reconciled",
        config,
    )
    by_type = {item["type"]: item for item in payload["conditions"]}

    assert payload["phase"] == "Progressing"
    assert by_type["ActionExecutorReady"]["status"] == "False"
    assert by_type["ActionExecutorReady"]["reason"] == "MutationCapabilityMismatch"
    assert by_type["SafetyModeReady"]["status"] == "False"
    assert by_type["SafetyModeReady"]["reason"] == "ExecuteCapabilityMismatch"


def test_olm_operator_status_rejects_evidence_check_mode_with_mutations(monkeypatch) -> None:
    monkeypatch.setattr(olm_operator, "get_resource", _ready_olm_resource)
    config = olm_operator.installation_config(
        {
            "metadata": {"namespace": "komsco-ai-kugnus", "generation": 10},
            "spec": {
                "targetNamespace": "komsco-ai-kugnus",
                "mode": "evidence-check",
                "pluginReplicas": 1,
                "gatewayReplicas": 1,
                "consolePluginName": "komsco-ai-console-plugin-kugnus",
                "capabilities": {
                    "diagnostics": False,
                    "mutations": True,
                    "unrestrictedCommands": False,
                },
            },
        }
    )

    payload = olm_operator.build_status_payload(
        {"metadata": {"name": "komsco-aiops-kugnus", "namespace": "komsco-ai-kugnus", "generation": 10}},
        "Ready",
        "KOMSCO AIOps runtime reconciled",
        config,
    )
    by_type = {item["type"]: item for item in payload["conditions"]}

    assert payload["phase"] == "Progressing"
    assert by_type["SafetyModeReady"]["status"] == "False"
    assert by_type["SafetyModeReady"]["reason"] == "ReadOnlyCapabilityMismatch"
