import base64
import os
import subprocess
from pathlib import Path

import pytest

import komsco_ai_gateway.olm_operator as olm_operator
from komsco_ai_gateway.standalone_portal import (
    PORTAL_NAME,
    PORTAL_OAUTH_SECRET,
    PORTAL_ROUTE_NAME,
    readiness_conditions,
    resources_for_standalone,
)


ROOT_DIR = Path(__file__).resolve().parents[2]


def standalone_config() -> dict:
    return {
        "namespace": "cywell-aiops",
        "standaloneEnabled": True,
        "standaloneHost": "aiops.cywell.co.kr",
        "standaloneReplicas": 2,
        "standaloneTlsSecretName": "cywell-aiops-route-tls",
        "standaloneOAuthClientName": "cywell-aiops-standalone",
        "standaloneImage": "registry/komsco-ai-standalone:0.1.17",
        "oauthProxyImage": "registry/oauth-proxy@sha256:test",
    }


def resource(resources: list[dict], kind: str, name: str) -> dict:
    return next(
        item
        for item in resources
        if item["kind"] == kind and item["metadata"]["name"] == name
    )


def test_standalone_resources_use_explicit_oauth_and_approved_tls() -> None:
    resources = resources_for_standalone(
        standalone_config(),
        {"app.kubernetes.io/managed-by": "komsco-aiops-operator"},
        "stable-client-secret",
        "stable-cookie-secret",
        {
            "tls.crt": "route-certificate",
            "tls.key": "route-private-key",
            "ca.crt": "route-ca",
        },
        "service-ca",
    )

    oauth_client = resource(resources, "OAuthClient", "cywell-aiops-standalone")
    assert oauth_client["secret"] == "stable-client-secret"
    assert oauth_client["redirectURIs"] == [
        "https://aiops.cywell.co.kr/oauth/callback"
    ]
    assert oauth_client["grantMethod"] == "prompt"

    credentials = resource(resources, "Secret", PORTAL_OAUTH_SECRET)
    assert credentials["stringData"] == {
        "client-secret": "stable-client-secret",
        "cookie-secret": "stable-cookie-secret",
    }

    deployment = resource(resources, "Deployment", PORTAL_NAME)
    oauth_proxy = next(
        container
        for container in deployment["spec"]["template"]["spec"]["containers"]
        if container["name"] == "oauth-proxy"
    )
    assert "--client-id=cywell-aiops-standalone" in oauth_proxy["args"]
    assert not any(
        argument.startswith("--openshift-service-account")
        for argument in oauth_proxy["args"]
    )

    route = resource(resources, "Route", PORTAL_ROUTE_NAME)
    assert route["spec"]["host"] == "aiops.cywell.co.kr"
    assert route["spec"]["tls"] == {
        "termination": "reencrypt",
        "insecureEdgeTerminationPolicy": "Redirect",
        "certificate": "route-certificate",
        "key": "route-private-key",
        "destinationCACertificate": "service-ca",
        "caCertificate": "route-ca",
    }

    configmap = resource(resources, "ConfigMap", f"{PORTAL_NAME}-nginx")
    nginx = configmap["data"]["nginx.conf"]
    assert "komsco-ai-gateway.cywell-aiops.svc" in nginx
    assert "cywell-aiops-core" not in nginx
    assert "proxy_ssl_verify on" in nginx


def test_standalone_route_waits_for_tls_and_service_ca() -> None:
    resources = resources_for_standalone(
        standalone_config(),
        {},
        "client",
        "cookie",
        {},
        "",
    )

    assert resource(resources, "Deployment", PORTAL_NAME)
    assert not any(item["kind"] == "Route" for item in resources)


def test_standalone_readiness_validates_route_oauth_and_launcher() -> None:
    def make_condition(condition_type, status, reason, message, generation):
        return {
            "type": condition_type,
            "status": status,
            "reason": reason,
            "message": message,
            "observedGeneration": generation,
        }

    def ready(condition_type, *_args):
        return make_condition(condition_type, "True", "Available", "ready", 7)

    def lookup(condition_type, _api_version, kind, _name, _namespace, generation):
        payloads = {
            "Route": {
                "spec": {
                    "host": "aiops.cywell.co.kr",
                    "to": {"name": PORTAL_NAME},
                    "tls": {
                        "termination": "reencrypt",
                        "certificate": "route-certificate",
                        "key": "route-private-key",
                        "destinationCACertificate": "service-ca",
                    },
                }
            },
            "OAuthClient": {
                "redirectURIs": ["https://aiops.cywell.co.kr/oauth/callback"]
            },
            "ConsoleLink": {
                "spec": {
                    "location": "ApplicationMenu",
                    "href": "https://aiops.cywell.co.kr",
                }
            },
        }
        return (
            make_condition(condition_type, "True", "Found", "found", generation),
            payloads[kind],
        )

    def read_resource(_api_version, kind, _name, _namespace):
        if kind == "Secret":
            return {
                "stringData": {
                    "tls.crt": "route-certificate",
                    "tls.key": "route-private-key",
                }
            }
        if kind == "ConfigMap":
            return {"data": {"service-ca.crt": "service-ca"}}
        return None

    config = {
        **standalone_config(),
        "consoleApplicationMenuEnabled": True,
        "consoleApplicationMenuName": "komsco-aiops-application-menu",
    }
    conditions = readiness_conditions(
        config,
        7,
        condition=make_condition,
        deployment_condition=ready,
        service_condition=ready,
        lookup_condition=lookup,
        resource_reader=read_resource,
    )

    assert set(conditions) == {
        "StandalonePortalReady",
        "StandaloneRouteReady",
        "StandaloneOAuthReady",
        "ApplicationLauncherReady",
    }
    assert all(item["status"] == "True" for item in conditions.values())


def test_standalone_readiness_rejects_existing_route_without_approved_tls_secret() -> None:
    def make_condition(condition_type, status, reason, message, generation):
        return {
            "type": condition_type,
            "status": status,
            "reason": reason,
            "message": message,
            "observedGeneration": generation,
        }

    def ready(condition_type, *_args):
        return make_condition(condition_type, "True", "Available", "ready", 9)

    def lookup(condition_type, _api_version, kind, _name, _namespace, generation):
        payload = {
            "Route": {
                "spec": {
                    "host": "aiops.cywell.co.kr",
                    "to": {"name": PORTAL_NAME},
                    "tls": {"termination": "reencrypt"},
                }
            },
            "OAuthClient": {
                "redirectURIs": ["https://aiops.cywell.co.kr/oauth/callback"]
            },
            "ConsoleLink": {
                "spec": {
                    "location": "ApplicationMenu",
                    "href": "https://aiops.cywell.co.kr",
                }
            },
        }[kind]
        return make_condition(condition_type, "True", "Found", "found", generation), payload

    conditions = readiness_conditions(
        {
            **standalone_config(),
            "consoleApplicationMenuEnabled": True,
            "consoleApplicationMenuName": "komsco-aiops-application-menu",
        },
        9,
        condition=make_condition,
        deployment_condition=ready,
        service_condition=ready,
        lookup_condition=lookup,
        resource_reader=lambda *_args: None,
    )

    assert conditions["StandaloneRouteReady"]["status"] == "False"
    assert conditions["StandaloneRouteReady"]["reason"] == "ApprovedTLSSecretMissing"


def test_operator_reuses_persisted_oauth_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    persisted = {
        "client-secret": "persisted-client",
        "cookie-secret": "persisted-cookie",
    }

    def fake_get_resource(api_version, kind, name, resource_namespace):
        if kind == "Secret" and name == PORTAL_OAUTH_SECRET:
            return {
                "data": {
                    key: base64.b64encode(value.encode()).decode()
                    for key, value in persisted.items()
                }
            }
        return None

    monkeypatch.setattr(olm_operator, "get_resource", fake_get_resource)

    assert olm_operator.resolved_standalone_credentials(
        "cywell-aiops",
        olm_operator.existing_secret_string_value,
        "fallback-client",
        "fallback-cookie",
    ) == (
        "persisted-client",
        "persisted-cookie",
    )


def test_operator_does_not_rotate_oauth_credentials_on_secret_read_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_get_resource(*_args):
        raise RuntimeError("temporary API failure")

    monkeypatch.setattr(olm_operator, "get_resource", failing_get_resource)

    with pytest.raises(RuntimeError, match="temporary API failure"):
        olm_operator.resolved_standalone_credentials(
            "cywell-aiops",
            olm_operator.existing_secret_string_value,
            "fallback-client",
            "fallback-cookie",
        )


def test_operator_paths_support_route_and_oauth_client() -> None:
    assert olm_operator.resource_path(
        "route.openshift.io/v1",
        "Route",
        PORTAL_ROUTE_NAME,
        "cywell-aiops",
    ) == f"/apis/route.openshift.io/v1/namespaces/cywell-aiops/routes/{PORTAL_ROUTE_NAME}"
    assert olm_operator.resource_path(
        "oauth.openshift.io/v1",
        "OAuthClient",
        "cywell-aiops-standalone",
        None,
    ) == "/apis/oauth.openshift.io/v1/oauthclients/cywell-aiops-standalone"


def test_operator_refuses_wrong_install_namespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(olm_operator, "namespace", lambda: "default")
    with pytest.raises(SystemExit, match="required namespace is cywell-aiops"):
        olm_operator.main()


def test_installation_config_is_read_only_and_standalone_when_requested() -> None:
    config = olm_operator.installation_config(
        {
            "metadata": {"namespace": "cywell-aiops"},
            "spec": {
                "targetNamespace": "cywell-aiops",
                "standalonePortal": {
                    "enabled": True,
                    "host": "aiops.cywell.co.kr",
                    "tlsSecretName": "cywell-aiops-route-tls",
                    "oauthClientName": "cywell-aiops-standalone",
                },
                "capabilities": {
                    "diagnostics": True,
                    "mutations": False,
                    "unrestrictedCommands": False,
                },
            },
        }
    )

    assert config["mode"] == "evidence-check"
    assert config["mutationsEnabled"] is False
    assert config["unrestrictedEnabled"] is False
    assert config["standaloneEnabled"] is True


def test_read_only_reconcile_prunes_existing_action_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deleted: list[tuple[str, str, str, str | None]] = []
    monkeypatch.setattr(
        olm_operator,
        "delete_resource",
        lambda api_version, kind, name, namespace: deleted.append(
            (api_version, kind, name, namespace)
        ),
    )

    olm_operator.cleanup_disabled_mutation_resources(
        {
            "namespace": "cywell-aiops",
            "consolePluginName": "cywell-aiops-console-plugin",
            "mutationsEnabled": False,
        }
    )

    assert ("apps/v1", "Deployment", "komsco-ai-action-executor", "cywell-aiops") in deleted
    assert (
        "rbac.authorization.k8s.io/v1",
        "ClusterRoleBinding",
        "cywell-aiops-console-plugin-action-executor",
        None,
    ) in deleted
    assert ("v1", "Secret", "komsco-ai-action-executor-auth", "cywell-aiops") in deleted


def test_deployment_script_refuses_noncanonical_namespace() -> None:
    result = subprocess.run(
        ["bash", str(ROOT_DIR / "scripts" / "kugnus-olm.sh"), "package"],
        cwd=ROOT_DIR,
        env={
            **os.environ,
            "KOMSCO_AIOPS_OPERATOR_NAMESPACE": "default",
            "KOMSCO_AIOPS_NAMESPACE": "default",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Refusing non-AIOps namespace" in result.stderr


def test_preflight_refuses_duplicate_installation(tmp_path: Path) -> None:
    fake_oc = tmp_path / "oc"
    fake_oc.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
case "$*" in
  "whoami --show-server") echo "https://api.ocp.cywell.server:6443" ;;
  "whoami") echo "admin" ;;
  "get crd aiopsinstallations.aiops.komsco.io") echo "aiopsinstallations.aiops.komsco.io" ;;
  "get aiopsinstallation -A --no-headers -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name")
    echo "cywell-aiops cywell-aiops"
    echo "default cywell-aiops"
    ;;
  "get subscription -A --no-headers -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,PACKAGE:.spec.name") ;;
  "get csv -A --no-headers -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name") ;;
  "get deployment -A --no-headers -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name") ;;
  *) echo "unexpected fake oc arguments: $*" >&2; exit 2 ;;
esac
""",
        encoding="utf-8",
    )
    fake_oc.chmod(0o755)

    result = subprocess.run(
        ["bash", str(ROOT_DIR / "scripts" / "kugnus-olm.sh"), "preflight"],
        cwd=ROOT_DIR,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "duplicate AIOps installation detected" in result.stderr
    assert "default cywell-aiops" in result.stderr


def test_preflight_allows_fresh_cluster_without_aiops_crd(tmp_path: Path) -> None:
    fake_oc = tmp_path / "oc"
    fake_oc.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
case "$*" in
  "whoami --show-server") echo "https://api.ocp.cywell.server:6443" ;;
  "whoami") echo "admin" ;;
  "get crd aiopsinstallations.aiops.komsco.io") exit 1 ;;
  "get subscription -A --no-headers -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,PACKAGE:.spec.name") ;;
  "get csv -A --no-headers -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name") ;;
  "get deployment -A --no-headers -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name") ;;
  *) echo "unexpected fake oc arguments: $*" >&2; exit 2 ;;
esac
""",
        encoding="utf-8",
    )
    fake_oc.chmod(0o755)

    result = subprocess.run(
        ["bash", str(ROOT_DIR / "scripts" / "kugnus-olm.sh"), "preflight"],
        cwd=ROOT_DIR,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "singleton preflight passed" in result.stdout
