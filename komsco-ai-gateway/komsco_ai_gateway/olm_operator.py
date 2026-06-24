import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any


FIELD_MANAGER = os.getenv("KOMSCO_AI_FIELD_MANAGER", "komsco-aiops-operator")
GROUP = "aiops.komsco.io"
VERSION = "v1alpha1"
PLURAL = "aiopsinstallations"
DEFAULT_NAME = os.getenv("KOMSCO_AI_DEFAULT_INSTALLATION_NAME", "komsco-aiops")
DEFAULT_TARGET_NAMESPACE = os.getenv("KOMSCO_AI_DEFAULT_TARGET_NAMESPACE", "komsco-ai-kugnus")
DEFAULT_PLUGIN_IMAGE = os.getenv(
    "KOMSCO_AI_DEFAULT_PLUGIN_IMAGE",
    "image-registry.openshift-image-registry.svc:5000/komsco-ai-kugnus/komsco-ai-console-plugin:0.1.3",
)
DEFAULT_GATEWAY_IMAGE = os.getenv(
    "KOMSCO_AI_DEFAULT_GATEWAY_IMAGE",
    "image-registry.openshift-image-registry.svc:5000/komsco-ai-kugnus/komsco-ai-gateway:0.1.3",
)
DEFAULT_CONSOLE_PLUGIN_NAME = os.getenv(
    "KOMSCO_AI_DEFAULT_CONSOLE_PLUGIN_NAME",
    "komsco-ai-console-plugin-kugnus",
)
DEFAULT_CONSOLE_PLUGIN_DISPLAY_NAME = os.getenv(
    "KOMSCO_AI_DEFAULT_CONSOLE_PLUGIN_DISPLAY_NAME",
    "Cywell AI",
)
BOOTSTRAP_INSTALLATION = os.getenv("KOMSCO_AI_OPERATOR_BOOTSTRAP_INSTALLATION", "false").lower() == "true"
PROTECTED_CONSOLE_PLUGIN_NAMES = {
    name.strip()
    for name in os.getenv(
        "KOMSCO_AI_PROTECTED_CONSOLE_PLUGIN_NAMES",
        "komsco-ai-console-plugin,lightspeed-console-plugin",
    ).split(",")
    if name.strip()
}
SERVICEACCOUNT_NAMESPACE_FILE = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
SERVICEACCOUNT_TOKEN_FILE = "/var/run/secrets/kubernetes.io/serviceaccount/token"
SERVICEACCOUNT_CA_FILE = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"


def namespace() -> str:
    try:
        return open(SERVICEACCOUNT_NAMESPACE_FILE, encoding="utf-8").read().strip()
    except OSError:
        return DEFAULT_TARGET_NAMESPACE


def api_server() -> str:
    host = os.getenv("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc")
    port = os.getenv("KUBERNETES_SERVICE_PORT_HTTPS") or os.getenv("KUBERNETES_SERVICE_PORT", "443")
    return f"https://{host}:{port}"


def token() -> str:
    return open(SERVICEACCOUNT_TOKEN_FILE, encoding="utf-8").read().strip()


def ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=SERVICEACCOUNT_CA_FILE)
    return context


def request(
    method: str,
    path: str,
    *,
    body: Mapping[str, Any] | None = None,
    content_type: str = "application/json",
) -> dict[str, Any]:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token()}",
    }
    if payload is not None:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(
        f"{api_server()}{path}",
        data=payload,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, context=ssl_context(), timeout=30) as response:
            data = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {detail}") from exc

    if not data:
        return {}
    return json.loads(data)


def get_resource(api_version: str, kind: str, name: str, resource_namespace: str | None = None) -> dict[str, Any] | None:
    path = resource_path(api_version, kind, name, resource_namespace)
    try:
        return request("GET", path)
    except RuntimeError as exc:
        if " failed: 404 " in str(exc):
            return None
        raise


def validate_console_plugin_name(name: str) -> None:
    if name in PROTECTED_CONSOLE_PLUGIN_NAMES and name != DEFAULT_CONSOLE_PLUGIN_NAME:
        raise RuntimeError(f"refusing protected ConsolePlugin name: {name}")


def validate_console_plugin_apply(resource: Mapping[str, Any]) -> None:
    metadata = resource.get("metadata") if isinstance(resource.get("metadata"), Mapping) else {}
    name = str(metadata["name"])
    validate_console_plugin_name(name)
    existing = get_resource("console.openshift.io/v1", "ConsolePlugin", name)
    if not existing:
        return

    existing_metadata = existing.get("metadata") if isinstance(existing.get("metadata"), Mapping) else {}
    existing_labels = (
        existing_metadata.get("labels") if isinstance(existing_metadata.get("labels"), Mapping) else {}
    )
    if existing_labels.get("app.kubernetes.io/managed-by") != FIELD_MANAGER:
        raise RuntimeError(f"refusing to overwrite existing unmanaged ConsolePlugin: {name}")


def apply_resource(resource: Mapping[str, Any]) -> None:
    api_version = str(resource["apiVersion"])
    kind = str(resource["kind"])
    metadata = resource.get("metadata") if isinstance(resource.get("metadata"), Mapping) else {}
    name = str(metadata["name"])
    resource_namespace = metadata.get("namespace")
    if kind == "ConsolePlugin":
        validate_console_plugin_apply(resource)
    path = resource_path(api_version, kind, name, str(resource_namespace) if resource_namespace else None)
    params = urllib.parse.urlencode({"fieldManager": FIELD_MANAGER, "force": "true"})
    request(
        "PATCH",
        f"{path}?{params}",
        body=resource,
        content_type="application/apply-patch+yaml",
    )


def resource_path(api_version: str, kind: str, name: str, resource_namespace: str | None) -> str:
    core_plural = {
        "ConfigMap": "configmaps",
        "Namespace": "namespaces",
        "Secret": "secrets",
        "Service": "services",
        "ServiceAccount": "serviceaccounts",
    }
    namespaced_api_plural = {
        ("apps/v1", "Deployment"): "deployments",
        ("networking.k8s.io/v1", "NetworkPolicy"): "networkpolicies",
        ("rbac.authorization.k8s.io/v1", "Role"): "roles",
        ("rbac.authorization.k8s.io/v1", "RoleBinding"): "rolebindings",
    }
    cluster_api_plural = {
        ("console.openshift.io/v1", "ConsolePlugin"): "consoleplugins",
        ("rbac.authorization.k8s.io/v1", "ClusterRole"): "clusterroles",
        ("rbac.authorization.k8s.io/v1", "ClusterRoleBinding"): "clusterrolebindings",
    }

    if api_version == "v1":
        plural = core_plural[kind]
        if kind == "Namespace":
            return f"/api/v1/{plural}/{name}"
        return f"/api/v1/namespaces/{resource_namespace}/{plural}/{name}"

    group, version = api_version.split("/", 1)
    plural = namespaced_api_plural.get((api_version, kind))
    if plural:
        return f"/apis/{group}/{version}/namespaces/{resource_namespace}/{plural}/{name}"

    plural = cluster_api_plural[(api_version, kind)]
    return f"/apis/{group}/{version}/{plural}/{name}"


def patch_console_plugin_enabled(plugin_name: str) -> None:
    path = "/apis/operator.openshift.io/v1/consoles/cluster"
    console = request("GET", path)
    spec = console.get("spec") if isinstance(console.get("spec"), Mapping) else {}
    plugins = spec.get("plugins") if isinstance(spec.get("plugins"), list) else []
    if plugin_name in plugins:
        return
    request(
        "PATCH",
        path,
        body={"spec": {"plugins": sorted([*plugins, plugin_name])}},
        content_type="application/merge-patch+json",
    )


def list_installations() -> list[dict[str, Any]]:
    operator_namespace = namespace()
    payload = request(
        "GET",
        f"/apis/{GROUP}/{VERSION}/namespaces/{operator_namespace}/{PLURAL}",
    )
    items = payload.get("items")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def default_installation(operator_namespace: str) -> dict[str, Any]:
    return {
        "apiVersion": f"{GROUP}/{VERSION}",
        "kind": "AIOpsInstallation",
        "metadata": {
            "name": DEFAULT_NAME,
            "namespace": operator_namespace,
            "labels": common_labels(DEFAULT_NAME),
        },
        "spec": {
            "targetNamespace": DEFAULT_TARGET_NAMESPACE,
            "createNamespace": True,
            "mode": os.getenv("KOMSCO_AI_DEFAULT_MODE", "read-only"),
            "pluginReplicas": int(os.getenv("KOMSCO_AI_DEFAULT_PLUGIN_REPLICAS", "2")),
            "gatewayReplicas": int(os.getenv("KOMSCO_AI_DEFAULT_GATEWAY_REPLICAS", "1")),
            "enableConsolePlugin": True,
            "consolePluginName": DEFAULT_CONSOLE_PLUGIN_NAME,
            "consolePluginDisplayName": DEFAULT_CONSOLE_PLUGIN_DISPLAY_NAME,
            "images": {
                "plugin": DEFAULT_PLUGIN_IMAGE,
                "gateway": DEFAULT_GATEWAY_IMAGE,
                "hostDiagnosticsRunner": os.getenv("KOMSCO_AI_DEFAULT_HOST_DIAGNOSTICS_RUNNER_IMAGE", DEFAULT_GATEWAY_IMAGE),
            },
            "capabilities": {
                "diagnostics": os.getenv("KOMSCO_AI_DEFAULT_ENABLE_DIAGNOSTICS", "true").lower() == "true",
                "mutations": os.getenv("KOMSCO_AI_DEFAULT_ENABLE_MUTATIONS", "false").lower() == "true",
                "unrestrictedCommands": os.getenv("KOMSCO_AI_DEFAULT_ENABLE_UNRESTRICTED_COMMANDS", "false").lower() == "true",
            },
        },
    }


def bootstrap_installation_if_needed() -> list[dict[str, Any]]:
    installations = list_installations()
    if installations or not BOOTSTRAP_INSTALLATION:
        return installations

    operator_namespace = namespace()
    print(f"bootstrapping default AIOpsInstallation {operator_namespace}/{DEFAULT_NAME}", flush=True)
    request(
        "POST",
        f"/apis/{GROUP}/{VERSION}/namespaces/{operator_namespace}/{PLURAL}",
        body=default_installation(operator_namespace),
    )
    return list_installations()


def update_status(custom_resource: Mapping[str, Any], phase: str, message: str) -> None:
    metadata = custom_resource.get("metadata") if isinstance(custom_resource.get("metadata"), Mapping) else {}
    name = str(metadata.get("name") or DEFAULT_NAME)
    cr_namespace = str(metadata.get("namespace") or namespace())
    status = {
        "status": {
            "observedGeneration": metadata.get("generation", 0),
            "phase": phase,
            "message": message,
            "lastTransitionTime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    }
    try:
        request(
            "PATCH",
            f"/apis/{GROUP}/{VERSION}/namespaces/{cr_namespace}/{PLURAL}/{name}/status",
            body=status,
            content_type="application/merge-patch+json",
        )
    except Exception as exc:
        print(f"status update failed for {cr_namespace}/{name}: {exc}", flush=True)


def spec_value(spec: Mapping[str, Any], key: str, default: Any) -> Any:
    value = spec.get(key)
    return default if value is None else value


def installation_config(custom_resource: Mapping[str, Any]) -> dict[str, Any]:
    spec = custom_resource.get("spec") if isinstance(custom_resource.get("spec"), Mapping) else {}
    cr_metadata = custom_resource.get("metadata") if isinstance(custom_resource.get("metadata"), Mapping) else {}
    images = spec.get("images") if isinstance(spec.get("images"), Mapping) else {}
    capabilities = spec.get("capabilities") if isinstance(spec.get("capabilities"), Mapping) else {}
    config = {
        "name": str(spec_value(spec, "name", DEFAULT_NAME)),
        "namespace": str(spec_value(spec, "targetNamespace", cr_metadata.get("namespace") or DEFAULT_TARGET_NAMESPACE)),
        "createNamespace": bool(spec_value(spec, "createNamespace", True)),
        "pluginImage": str(images.get("plugin") or DEFAULT_PLUGIN_IMAGE),
        "gatewayImage": str(images.get("gateway") or DEFAULT_GATEWAY_IMAGE),
        "runnerImage": str(images.get("hostDiagnosticsRunner") or images.get("gateway") or DEFAULT_GATEWAY_IMAGE),
        "pluginReplicas": int(spec_value(spec, "pluginReplicas", 2)),
        "gatewayReplicas": int(spec_value(spec, "gatewayReplicas", 1)),
        "mode": str(spec_value(spec, "mode", "read-only")),
        "diagnosticsEnabled": bool(capabilities.get("diagnostics", True)),
        "mutationsEnabled": bool(capabilities.get("mutations", False)),
        "unrestrictedEnabled": bool(capabilities.get("unrestrictedCommands", False)),
        "enableConsolePlugin": bool(spec_value(spec, "enableConsolePlugin", True)),
        "consolePluginName": str(spec_value(spec, "consolePluginName", DEFAULT_CONSOLE_PLUGIN_NAME)),
        "consolePluginDisplayName": str(
            spec_value(spec, "consolePluginDisplayName", DEFAULT_CONSOLE_PLUGIN_DISPLAY_NAME)
        ),
    }
    validate_console_plugin_name(str(config["consolePluginName"]))
    return config


def common_labels(name: str) -> dict[str, str]:
    return {
        "app.kubernetes.io/name": name,
        "app.kubernetes.io/part-of": "komsco-aiops",
        "app.kubernetes.io/managed-by": "komsco-aiops-operator",
    }


def cluster_resource_names(console_plugin_name: str) -> dict[str, str]:
    return {
        "actionExecutorClusterRole": f"{console_plugin_name}-action-executor",
        "actionExecutorClusterRoleBinding": f"{console_plugin_name}-action-executor",
        "gatewayAuthDelegatorClusterRoleBinding": f"{console_plugin_name}-gateway-auth-delegator",
    }


def service_account(name: str, target_namespace: str, labels: Mapping[str, str]) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "ServiceAccount",
        "metadata": {"name": name, "namespace": target_namespace, "labels": dict(labels)},
    }


def service(
    name: str,
    target_namespace: str,
    labels: Mapping[str, str],
    port: int,
    target_port: int | str,
    *,
    tls_secret: str | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"name": name, "namespace": target_namespace, "labels": dict(labels)}
    if tls_secret:
        metadata["annotations"] = {"service.beta.openshift.io/serving-cert-secret-name": tls_secret}
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": metadata,
        "spec": {
            "type": "ClusterIP",
            "selector": {"app": name},
            "ports": [{"name": "http" if port == 8080 else "https", "port": port, "targetPort": target_port}],
        },
    }


def deployment(
    name: str,
    target_namespace: str,
    labels: Mapping[str, str],
    image: str,
    service_account_name: str,
    container: Mapping[str, Any],
    *,
    replicas: int = 1,
    volumes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    pod_labels = {**dict(labels), "app": name}
    container_spec = {"name": name, "image": image, "imagePullPolicy": "Always", **dict(container)}
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name, "namespace": target_namespace, "labels": dict(labels)},
        "spec": {
            "replicas": replicas,
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": {"labels": pod_labels},
                "spec": {
                    "serviceAccountName": service_account_name,
                    "containers": [container_spec],
                    "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
                    **({"volumes": volumes} if volumes else {}),
                },
            },
        },
    }


def role(name: str, target_namespace: str, labels: Mapping[str, str], rules: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "Role",
        "metadata": {"name": name, "namespace": target_namespace, "labels": dict(labels)},
        "rules": rules,
    }


def role_binding(
    name: str,
    target_namespace: str,
    labels: Mapping[str, str],
    role_kind: str,
    role_name: str,
    service_account_name: str,
) -> dict[str, Any]:
    return {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "RoleBinding",
        "metadata": {"name": name, "namespace": target_namespace, "labels": dict(labels)},
        "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": role_kind, "name": role_name},
        "subjects": [{"kind": "ServiceAccount", "name": service_account_name, "namespace": target_namespace}],
    }


def cluster_role_binding(
    name: str,
    labels: Mapping[str, str],
    role_name: str,
    service_account_name: str,
    target_namespace: str,
) -> dict[str, Any]:
    return {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRoleBinding",
        "metadata": {"name": name, "labels": dict(labels)},
        "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": role_name},
        "subjects": [{"kind": "ServiceAccount", "name": service_account_name, "namespace": target_namespace}],
    }


def resources_for(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    target_namespace = str(config["namespace"])
    name = str(config["name"])
    labels = common_labels(name)
    console_plugin_name = str(config["consolePluginName"])
    mutations_enabled = bool(config["mutationsEnabled"])
    diagnostics_enabled = bool(config["diagnosticsEnabled"])
    resources: list[dict[str, Any]] = []

    if config["createNamespace"]:
        resources.append({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": target_namespace, "labels": labels}})

    resources.extend(
        [
            service_account("komsco-ai-console-plugin", target_namespace, labels),
            service_account("komsco-ai-gateway", target_namespace, labels),
            {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {"name": "komsco-ai-console-plugin", "namespace": target_namespace, "labels": labels},
                "data": {
                    "nginx.conf": (
                        "error_log /dev/stdout info;\n"
                        "events {}\n"
                        "http {\n"
                        "  access_log /dev/stdout;\n"
                        "  include /etc/nginx/mime.types;\n"
                        "  default_type application/octet-stream;\n"
                        "  server {\n"
                        "    listen 9443 ssl;\n"
                        "    ssl_certificate /var/cert/tls.crt;\n"
                        "    ssl_certificate_key /var/cert/tls.key;\n"
                        "    root /usr/share/nginx/html;\n"
                        "  }\n"
                        "}\n"
                    )
                },
            },
            {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {
                    "name": "komsco-ai-service-ca",
                    "namespace": target_namespace,
                    "labels": labels,
                    "annotations": {"service.beta.openshift.io/inject-cabundle": "true"},
                },
                "data": {},
            },
            service("komsco-ai-console-plugin", target_namespace, labels, 9443, 9443, tls_secret="komsco-ai-console-plugin-cert"),
            service("komsco-ai-gateway", target_namespace, labels, 8443, "https", tls_secret="komsco-ai-gateway-tls"),
        ]
    )

    if mutations_enabled:
        resources.extend(
            [
                service_account("komsco-ai-action-executor", target_namespace, labels),
                service("komsco-ai-action-executor", target_namespace, labels, 8080, "http"),
            ]
        )

    if diagnostics_enabled:
        resources.extend(
            [
                service_account("komsco-ai-host-diagnostics-controller", target_namespace, labels),
                service_account("komsco-ai-host-diagnostics-runner", target_namespace, labels),
                service("komsco-ai-host-diagnostics-controller", target_namespace, labels, 8080, "http"),
            ]
        )

    resources.extend(
        rbac_resources(
            target_namespace,
            labels,
            console_plugin_name,
            mutations_enabled,
            diagnostics_enabled,
        )
    )
    resources.extend(workload_resources(config, labels))
    resources.append(
        console_plugin_resource(
            target_namespace,
            labels,
            console_plugin_name,
            str(config["consolePluginDisplayName"]),
        )
    )
    resources.extend(network_policies(target_namespace, labels, mutations_enabled, diagnostics_enabled))
    return resources


def rbac_resources(
    target_namespace: str,
    labels: Mapping[str, str],
    console_plugin_name: str,
    mutations_enabled: bool,
    diagnostics_enabled: bool,
) -> list[dict[str, Any]]:
    cluster_names = cluster_resource_names(console_plugin_name)
    resources: list[dict[str, Any]] = [
        role(
            "komsco-ai-gateway-ledger",
            target_namespace,
            labels,
            [{"apiGroups": [""], "resources": ["configmaps"], "verbs": ["create", "get", "list", "patch", "update"]}],
        ),
        role_binding("komsco-ai-gateway-ledger", target_namespace, labels, "Role", "komsco-ai-gateway-ledger", "komsco-ai-gateway"),
        cluster_role_binding(
            cluster_names["gatewayAuthDelegatorClusterRoleBinding"],
            labels,
            "system:auth-delegator",
            "komsco-ai-gateway",
            target_namespace,
        ),
    ]

    if mutations_enabled:
        resources.extend(
            [
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "ClusterRole",
            "metadata": {"name": cluster_names["actionExecutorClusterRole"], "labels": dict(labels)},
            "rules": [
                {"apiGroups": ["apps"], "resources": ["deployments", "deployments/scale", "replicasets"], "verbs": ["get", "list", "patch", "update", "watch"]},
                {"apiGroups": ["autoscaling"], "resources": ["horizontalpodautoscalers"], "verbs": ["get", "list", "patch", "update", "watch"]},
                {"apiGroups": [""], "resources": ["pods"], "verbs": ["get", "list", "watch"]},
                {"apiGroups": [""], "resources": ["pods/eviction"], "verbs": ["create"]},
                {"apiGroups": ["policy"], "resources": ["poddisruptionbudgets"], "verbs": ["get", "list", "watch"]},
            ],
        },
        cluster_role_binding(
            cluster_names["actionExecutorClusterRoleBinding"],
            labels,
            cluster_names["actionExecutorClusterRole"],
            "komsco-ai-action-executor",
            target_namespace,
        ),
            ]
        )

    if diagnostics_enabled:
        resources.extend(
            [
        role(
            "komsco-ai-host-diagnostics-controller",
            target_namespace,
            labels,
            [
                {"apiGroups": ["batch"], "resources": ["jobs"], "verbs": ["create", "delete", "get", "list", "watch"]},
                {"apiGroups": [""], "resources": ["pods"], "verbs": ["get", "list", "watch"]},
                {"apiGroups": [""], "resources": ["pods/log"], "verbs": ["get"]},
                {"apiGroups": [""], "resources": ["events"], "verbs": ["get", "list", "watch"]},
            ],
        ),
        role_binding(
            "komsco-ai-host-diagnostics-controller",
            target_namespace,
            labels,
            "Role",
            "komsco-ai-host-diagnostics-controller",
            "komsco-ai-host-diagnostics-controller",
        ),
        role_binding(
            "komsco-ai-host-diagnostics-runner-scc",
            target_namespace,
            labels,
            "ClusterRole",
            "system:openshift:scc:hostmount-anyuid-v2",
            "komsco-ai-host-diagnostics-runner",
        ),
            ]
        )

    return resources


def workload_resources(config: Mapping[str, Any], labels: Mapping[str, str]) -> list[dict[str, Any]]:
    target_namespace = str(config["namespace"])
    gateway_image = str(config["gatewayImage"])
    console_plugin_name = str(config["consolePluginName"])
    mutations_enabled_bool = bool(config["mutationsEnabled"])
    diagnostics_enabled_bool = bool(config["diagnosticsEnabled"])
    mutations_enabled = str(mutations_enabled_bool).lower()
    diagnostics_enabled = str(diagnostics_enabled_bool).lower()
    unrestricted_enabled = str(bool(config["unrestrictedEnabled"])).lower()
    resources = [
        deployment(
            "komsco-ai-console-plugin",
            target_namespace,
            labels,
            str(config["pluginImage"]),
            "komsco-ai-console-plugin",
            {
                "ports": [{"containerPort": 9443, "protocol": "TCP"}],
                "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}, "runAsNonRoot": True},
                "volumeMounts": [
                    {"name": "komsco-ai-console-plugin-cert", "mountPath": "/var/cert", "readOnly": True},
                    {"name": "nginx-conf", "mountPath": "/etc/nginx/nginx.conf", "subPath": "nginx.conf", "readOnly": True},
                ],
            },
            replicas=int(config["pluginReplicas"]),
            volumes=[
                {"name": "komsco-ai-console-plugin-cert", "secret": {"secretName": "komsco-ai-console-plugin-cert"}},
                {"name": "nginx-conf", "configMap": {"name": "komsco-ai-console-plugin"}},
            ],
        ),
        deployment(
            "komsco-ai-gateway",
            target_namespace,
            labels,
            gateway_image,
            "komsco-ai-gateway",
            {
                "ports": [{"name": "https", "containerPort": 8443}],
                "env": [
                    {"name": "OLS_BASE_URL", "value": "https://lightspeed-app-server.openshift-lightspeed.svc:8443"},
                    {"name": "OLS_CA_FILE", "value": "/var/run/configmaps/service-ca/service-ca.crt"},
                    {"name": "KOMSCO_AI_SECURITY_PHASE", "value": "phase5-action-execution"},
                    {"name": "KOMSCO_AI_ENABLE_MUTATIONS", "value": mutations_enabled},
                    {"name": "KOMSCO_AI_ENABLE_UNRESTRICTED_COMMANDS", "value": unrestricted_enabled},
                    {"name": "KOMSCO_AI_ACTION_EXECUTOR_URL", "value": "http://komsco-ai-action-executor:8080" if mutations_enabled_bool else ""},
                    {"name": "KOMSCO_AI_DIAGNOSTICS_ENABLED", "value": diagnostics_enabled},
                    {"name": "KOMSCO_AI_HOST_DIAGNOSTICS_CONTROLLER_URL", "value": "http://komsco-ai-host-diagnostics-controller:8080" if diagnostics_enabled_bool else ""},
                    {"name": "KOMSCO_AI_RECORD_STORE_ENABLED", "value": "true"},
                    {"name": "KOMSCO_AI_RECORD_STORE_CONFIGMAP", "value": "komsco-ai-gateway-ledger"},
                    {"name": "KOMSCO_AI_PRODUCT_ACCESS_REVIEW_ENABLED", "value": "true"},
                    {"name": "KOMSCO_AI_PRODUCT_ACCESS_REVIEW_REQUIRED", "value": "true"},
                    {"name": "KOMSCO_AI_PRODUCT_ACCESS_REVIEW_GROUP", "value": "console.openshift.io"},
                    {"name": "KOMSCO_AI_PRODUCT_ACCESS_REVIEW_RESOURCE", "value": "consoleplugins"},
                    {"name": "KOMSCO_AI_PRODUCT_ACCESS_REVIEW_VERB", "value": "get"},
                    {"name": "KOMSCO_AI_PRODUCT_ACCESS_REVIEW_NAME", "value": console_plugin_name},
                ],
                "readinessProbe": {"httpGet": {"path": "/healthz", "port": "https", "scheme": "HTTPS"}, "initialDelaySeconds": 5, "periodSeconds": 10},
                "livenessProbe": {"httpGet": {"path": "/healthz", "port": "https", "scheme": "HTTPS"}, "initialDelaySeconds": 15, "periodSeconds": 20},
                "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}, "runAsNonRoot": True},
                "volumeMounts": [
                    {"name": "tls", "mountPath": "/var/run/secrets/tls", "readOnly": True},
                    {"name": "service-ca", "mountPath": "/var/run/configmaps/service-ca", "readOnly": True},
                ],
            },
            replicas=int(config["gatewayReplicas"]),
            volumes=[
                {"name": "tls", "secret": {"secretName": "komsco-ai-gateway-tls"}},
                {"name": "service-ca", "configMap": {"name": "komsco-ai-service-ca"}},
            ],
        ),
    ]

    if mutations_enabled_bool:
        resources.append(
            deployment(
            "komsco-ai-action-executor",
            target_namespace,
            labels,
            gateway_image,
            "komsco-ai-action-executor",
            {
                "command": ["uvicorn"],
                "args": ["komsco_ai_gateway.action_executor:app", "--host", "0.0.0.0", "--port", "8080"],
                "ports": [{"name": "http", "containerPort": 8080}],
                "env": [
                    {"name": "KOMSCO_AI_ACTION_EXECUTOR_ENABLED", "value": "true"},
                    {"name": "KOMSCO_AI_ENABLE_MUTATIONS", "value": mutations_enabled},
                    {"name": "KOMSCO_AI_ACTION_EXECUTOR_TOKEN_FILE", "value": "/var/run/secrets/kubernetes.io/serviceaccount/token"},
                    {"name": "OPENSHIFT_API_CA_FILE", "value": "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"},
                ],
                "readinessProbe": {"httpGet": {"path": "/healthz", "port": "http"}, "initialDelaySeconds": 5, "periodSeconds": 10},
                "livenessProbe": {"httpGet": {"path": "/healthz", "port": "http"}, "initialDelaySeconds": 15, "periodSeconds": 20},
                "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}, "runAsNonRoot": True},
            },
            )
        )

    if diagnostics_enabled_bool:
        resources.append(
            deployment(
            "komsco-ai-host-diagnostics-controller",
            target_namespace,
            labels,
            gateway_image,
            "komsco-ai-host-diagnostics-controller",
            {
                "command": ["uvicorn"],
                "args": ["komsco_ai_gateway.host_diagnostics_controller:app", "--host", "0.0.0.0", "--port", "8080"],
                "ports": [{"name": "http", "containerPort": 8080}],
                "env": [
                    {"name": "KOMSCO_AI_HOST_DIAGNOSTICS_CONTROLLER_ENABLED", "value": diagnostics_enabled},
                    {"name": "KOMSCO_AI_HOST_DIAGNOSTICS_RUNNER_IMAGE", "value": str(config["runnerImage"])},
                    {"name": "KOMSCO_AI_HOST_DIAGNOSTICS_RUNNER_SERVICE_ACCOUNT", "value": "komsco-ai-host-diagnostics-runner"},
                    {"name": "OPENSHIFT_API_CA_FILE", "value": "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"},
                ],
                "readinessProbe": {"httpGet": {"path": "/healthz", "port": "http"}, "initialDelaySeconds": 5, "periodSeconds": 10},
                "livenessProbe": {"httpGet": {"path": "/healthz", "port": "http"}, "initialDelaySeconds": 15, "periodSeconds": 20},
                "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}, "runAsNonRoot": True},
            },
            )
        )

    return resources


def console_plugin_resource(
    target_namespace: str,
    labels: Mapping[str, str],
    console_plugin_name: str,
    console_plugin_display_name: str,
) -> dict[str, Any]:
    return {
        "apiVersion": "console.openshift.io/v1",
        "kind": "ConsolePlugin",
        "metadata": {"name": console_plugin_name, "labels": dict(labels)},
        "spec": {
            "displayName": console_plugin_display_name,
            "i18n": {"loadType": "Preload"},
            "backend": {
                "type": "Service",
                "service": {
                    "name": "komsco-ai-console-plugin",
                    "namespace": target_namespace,
                    "port": 9443,
                    "basePath": "/",
                },
            },
            "proxy": [
                {
                    "alias": "ai-gateway",
                    "authorization": "UserToken",
                    "endpoint": {
                        "type": "Service",
                        "service": {
                            "name": "komsco-ai-gateway",
                            "namespace": target_namespace,
                            "port": 8443,
                        },
                    },
                }
            ],
        },
    }


def network_policies(
    target_namespace: str,
    labels: Mapping[str, str],
    mutations_enabled: bool,
    diagnostics_enabled: bool,
) -> list[dict[str, Any]]:
    def policy(name: str, app: str, from_items: list[dict[str, Any]], port: int) -> dict[str, Any]:
        return {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {"name": name, "namespace": target_namespace, "labels": dict(labels)},
            "spec": {
                "podSelector": {"matchLabels": {"app": app}},
                "policyTypes": ["Ingress"],
                "ingress": [{"from": from_items, "ports": [{"port": port, "protocol": "TCP"}]}],
            },
        }

    resources = [
        policy(
            "komsco-ai-gateway-ingress",
            "komsco-ai-gateway",
            [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "openshift-console"}}}],
            8443,
        ),
    ]

    if mutations_enabled:
        resources.append(
            policy(
                "komsco-ai-action-executor-ingress",
                "komsco-ai-action-executor",
                [{"podSelector": {"matchLabels": {"app": "komsco-ai-gateway"}}}],
                8080,
            )
        )

    if diagnostics_enabled:
        resources.append(
            policy(
                "komsco-ai-host-diagnostics-controller-ingress",
                "komsco-ai-host-diagnostics-controller",
                [{"podSelector": {"matchLabels": {"app": "komsco-ai-gateway"}}}],
                8080,
            )
        )

    return resources

def reconcile(custom_resource: Mapping[str, Any]) -> None:
    metadata = custom_resource.get("metadata") if isinstance(custom_resource.get("metadata"), Mapping) else {}
    name = str(metadata.get("name") or DEFAULT_NAME)
    try:
        config = installation_config(custom_resource)
        print(f"reconciling {name} into namespace {config['namespace']}", flush=True)
        for resource in resources_for(config):
            apply_resource(resource)
        if config["enableConsolePlugin"]:
            patch_console_plugin_enabled(str(config["consolePluginName"]))
        update_status(custom_resource, "Ready", "KOMSCO AIOps runtime reconciled")
    except Exception as exc:
        print(f"reconcile failed for {name}: {exc}", flush=True)
        update_status(custom_resource, "Failed", str(exc))


def main() -> None:
    print("KOMSCO AIOps operator started", flush=True)
    while True:
        try:
            installations = bootstrap_installation_if_needed()
            if not installations:
                print("waiting for AIOpsInstallation resources", flush=True)
            for item in installations:
                reconcile(item)
        except Exception as exc:
            print(f"operator loop failed: {exc}", flush=True)
        time.sleep(int(os.getenv("KOMSCO_AI_OPERATOR_RECONCILE_SECONDS", "30")))


if __name__ == "__main__":
    main()
