import base64
import hashlib
import json
import os
import secrets
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any


def first_env_value(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip() != "":
            return value.strip()
    return default


def first_int_env(*names: str, default: int) -> int:
    value = first_env_value(*names)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


FIELD_MANAGER = os.getenv("KOMSCO_AI_FIELD_MANAGER", "komsco-aiops-operator")
GROUP = "aiops.komsco.io"
VERSION = "v1alpha1"
PLURAL = "aiopsinstallations"
DEFAULT_NAME = os.getenv("KOMSCO_AI_DEFAULT_INSTALLATION_NAME", "komsco-aiops-kugnus")
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
DEFAULT_DISABLED_CONSOLE_PLUGIN_NAMES = [
    name.strip()
    for name in os.getenv("KOMSCO_AI_DEFAULT_DISABLED_CONSOLE_PLUGIN_NAMES", "komsco-ai-console-plugin").split(",")
    if name.strip()
]
DEFAULT_ACTION_EXECUTOR_AUTH_SECRET = os.getenv(
    "KOMSCO_AI_DEFAULT_ACTION_EXECUTOR_AUTH_SECRET",
    "komsco-ai-action-executor-auth",
)
DEFAULT_ACTION_EXECUTOR_AUTH_KEY = os.getenv(
    "KOMSCO_AI_DEFAULT_ACTION_EXECUTOR_AUTH_KEY",
    "shared-token",
)
DEFAULT_ACTION_EXECUTOR_SHARED_TOKEN = os.getenv(
    "KOMSCO_AI_DEFAULT_ACTION_EXECUTOR_SHARED_TOKEN",
    secrets.token_urlsafe(32),
)
ALLOW_PROTECTED_CONSOLE_PLUGIN = os.getenv("KOMSCO_AI_ALLOW_PROTECTED_CONSOLE_PLUGIN", "false").lower() == "true"
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
VERSION_SCOPE = os.getenv("KOMSCO_AI_OPERATOR_VERSION_SCOPE", "Ver.0.1.1")
DEFAULT_READINESS_CONDITION_TYPES = [
    "TargetNamespaceReady",
    "GatewayServiceReady",
    "GatewayReady",
    "ConsolePluginDeploymentReady",
    "ConsolePluginConfigured",
    "ServiceCABundleReady",
    "RBACReady",
    "ActionExecutorReady",
    "HostDiagnosticsReady",
    "SafetyModeReady",
]
READINESS_CONDITION_TYPES = [
    item.strip()
    for item in os.getenv(
        "KOMSCO_AI_OPERATOR_READINESS_CONDITIONS",
        ",".join(DEFAULT_READINESS_CONDITION_TYPES),
    ).split(",")
    if item.strip()
]


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
    if name in PROTECTED_CONSOLE_PLUGIN_NAMES and not ALLOW_PROTECTED_CONSOLE_PLUGIN:
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


def string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


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


def patch_console_plugin_enabled(plugin_name: str, disabled_plugins: list[str] | None = None) -> None:
    path = "/apis/operator.openshift.io/v1/consoles/cluster"
    console = request("GET", path)
    spec = console.get("spec") if isinstance(console.get("spec"), Mapping) else {}
    plugins = spec.get("plugins") if isinstance(spec.get("plugins"), list) else []
    disabled = {name for name in (disabled_plugins or []) if name and name != plugin_name}
    next_plugins: list[str] = []
    for plugin in plugins:
        if plugin in disabled or plugin in next_plugins:
            continue
        next_plugins.append(plugin)
    if plugin_name not in next_plugins:
        next_plugins.append(plugin_name)
    if next_plugins == plugins:
        return
    request(
        "PATCH",
        path,
        body={"spec": {"plugins": next_plugins}},
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
            "mode": os.getenv("KOMSCO_AI_DEFAULT_MODE", "execute"),
            "pluginReplicas": int(os.getenv("KOMSCO_AI_DEFAULT_PLUGIN_REPLICAS", "2")),
            "gatewayReplicas": int(os.getenv("KOMSCO_AI_DEFAULT_GATEWAY_REPLICAS", "1")),
            "enableConsolePlugin": True,
            "consolePluginName": DEFAULT_CONSOLE_PLUGIN_NAME,
            "consolePluginDisplayName": DEFAULT_CONSOLE_PLUGIN_DISPLAY_NAME,
            "disabledConsolePluginNames": DEFAULT_DISABLED_CONSOLE_PLUGIN_NAMES,
            "images": {
                "plugin": DEFAULT_PLUGIN_IMAGE,
                "gateway": DEFAULT_GATEWAY_IMAGE,
                "hostDiagnosticsRunner": os.getenv("KOMSCO_AI_DEFAULT_HOST_DIAGNOSTICS_RUNNER_IMAGE", DEFAULT_GATEWAY_IMAGE),
            },
            "capabilities": {
                "diagnostics": os.getenv("KOMSCO_AI_DEFAULT_ENABLE_DIAGNOSTICS", "true").lower() == "true",
                "mutations": os.getenv("KOMSCO_AI_DEFAULT_ENABLE_MUTATIONS", "true").lower() == "true",
                "unrestrictedCommands": os.getenv("KOMSCO_AI_DEFAULT_ENABLE_UNRESTRICTED_COMMANDS", "true").lower() == "true",
            },
            "rag": {
                "backendUrlSecret": os.getenv("KOMSCO_AI_DEFAULT_RAG_BACKEND_URL_SECRET", ""),
                "backendUrlKey": os.getenv("KOMSCO_AI_DEFAULT_RAG_BACKEND_URL_KEY", "url"),
                "embeddingProvider": first_env_value(
                    "KOMSCO_AI_DEFAULT_EMBEDDING_PROVIDER",
                    "KOMSCO_AI_EMBEDDING_PROVIDER",
                ),
                "embeddingApiStyle": first_env_value(
                    "KOMSCO_AI_DEFAULT_EMBEDDING_API_STYLE",
                    "KOMSCO_AI_EMBEDDING_API_STYLE",
                ),
                "embeddingBaseUrl": first_env_value(
                    "KOMSCO_AI_DEFAULT_EMBEDDING_BASE_URL",
                    "KOMSCO_AI_EMBEDDING_BASE_URL",
                ),
                "embeddingModel": first_env_value(
                    "KOMSCO_AI_DEFAULT_EMBEDDING_MODEL",
                    "KOMSCO_AI_EMBEDDING_MODEL",
                    "KOMSCO_AI_DEFAULT_RAG_EMBEDDING_MODEL",
                    default="hashing-local-dev",
                ),
                "embeddingTimeoutSeconds": first_int_env(
                    "KOMSCO_AI_DEFAULT_EMBEDDING_TIMEOUT_SECONDS",
                    "KOMSCO_AI_EMBEDDING_TIMEOUT_SECONDS",
                    "KOMSCO_AI_DEFAULT_RAG_EMBEDDING_TIMEOUT_SECONDS",
                    default=10,
                ),
                "vectorDimensions": first_int_env(
                    "KOMSCO_AI_DEFAULT_EMBEDDING_DIMENSIONS",
                    "KOMSCO_AI_EMBEDDING_DIMENSIONS",
                    "KOMSCO_AI_DEFAULT_RAG_VECTOR_DIMENSIONS",
                    default=64,
                ),
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


def now_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def condition(
    condition_type: str,
    status: str,
    reason: str,
    message: str,
    generation: int,
) -> dict[str, Any]:
    return {
        "type": condition_type,
        "status": status,
        "reason": reason,
        "message": message,
        "lastTransitionTime": now_timestamp(),
        "observedGeneration": generation,
    }


def lookup_condition(
    condition_type: str,
    api_version: str,
    kind: str,
    name: str,
    resource_namespace: str | None,
    generation: int,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    try:
        resource = get_resource(api_version, kind, name, resource_namespace)
    except Exception as exc:
        return condition(condition_type, "Unknown", "LookupFailed", str(exc), generation), None
    if resource is None:
        scope = f"{resource_namespace}/{name}" if resource_namespace else name
        return condition(condition_type, "False", "Missing", f"{kind} {scope} was not found.", generation), None
    return condition(condition_type, "True", "Found", f"{kind} {name} exists.", generation), resource


def service_condition(condition_type: str, name: str, target_namespace: str, generation: int) -> dict[str, Any]:
    result, _ = lookup_condition(condition_type, "v1", "Service", name, target_namespace, generation)
    if result["status"] == "True":
        result["reason"] = "ServiceFound"
        result["message"] = f"Service {target_namespace}/{name} is present."
    return result


def deployment_condition(condition_type: str, name: str, target_namespace: str, generation: int) -> dict[str, Any]:
    result, deployment_resource = lookup_condition(
        condition_type,
        "apps/v1",
        "Deployment",
        name,
        target_namespace,
        generation,
    )
    if result["status"] != "True" or deployment_resource is None:
        return result

    spec = deployment_resource.get("spec") if isinstance(deployment_resource.get("spec"), Mapping) else {}
    status = deployment_resource.get("status") if isinstance(deployment_resource.get("status"), Mapping) else {}
    desired = int(spec.get("replicas") or 1)
    available = int(status.get("availableReplicas") or 0)
    ready = int(status.get("readyReplicas") or 0)
    updated = int(status.get("updatedReplicas") or 0)
    if available >= desired and ready >= desired and updated >= desired:
        return condition(
            condition_type,
            "True",
            "DeploymentAvailable",
            f"Deployment {target_namespace}/{name} has {available}/{desired} available replicas.",
            generation,
        )
    return condition(
        condition_type,
        "False",
        "WaitingForRollout",
        f"Deployment {target_namespace}/{name} has available={available}, ready={ready}, updated={updated}, desired={desired}.",
        generation,
    )


def service_ca_condition(target_namespace: str, generation: int) -> dict[str, Any]:
    result, configmap_resource = lookup_condition(
        "ServiceCABundleReady",
        "v1",
        "ConfigMap",
        "komsco-ai-service-ca",
        target_namespace,
        generation,
    )
    if result["status"] != "True" or configmap_resource is None:
        return result

    data = configmap_resource.get("data") if isinstance(configmap_resource.get("data"), Mapping) else {}
    if data.get("service-ca.crt"):
        return condition(
            "ServiceCABundleReady",
            "True",
            "CABundleInjected",
            "OpenShift service-ca bundle is present.",
            generation,
        )
    return condition(
        "ServiceCABundleReady",
        "False",
        "CABundlePending",
        "OpenShift service-ca ConfigMap exists but service-ca.crt has not been injected yet.",
        generation,
    )


def console_plugin_condition(config: Mapping[str, Any], generation: int) -> dict[str, Any]:
    target_namespace = str(config["namespace"])
    console_plugin_name = str(config["consolePluginName"])
    result, plugin_resource = lookup_condition(
        "ConsolePluginConfigured",
        "console.openshift.io/v1",
        "ConsolePlugin",
        console_plugin_name,
        None,
        generation,
    )
    if result["status"] != "True" or plugin_resource is None:
        return result

    spec = plugin_resource.get("spec") if isinstance(plugin_resource.get("spec"), Mapping) else {}
    backend = spec.get("backend") if isinstance(spec.get("backend"), Mapping) else {}
    backend_service = backend.get("service") if isinstance(backend.get("service"), Mapping) else {}
    proxies = spec.get("proxy") if isinstance(spec.get("proxy"), list) else []
    gateway_proxy = next(
        (
            proxy
            for proxy in proxies
            if isinstance(proxy, Mapping)
            and proxy.get("alias") == "ai-gateway"
            and isinstance(proxy.get("endpoint"), Mapping)
        ),
        None,
    )
    gateway_service = (
        gateway_proxy.get("endpoint", {}).get("service")
        if isinstance(gateway_proxy, Mapping) and isinstance(gateway_proxy.get("endpoint"), Mapping)
        else {}
    )
    backend_matches = (
        backend_service.get("name") == "komsco-ai-console-plugin"
        and backend_service.get("namespace") == target_namespace
    )
    proxy_matches = (
        isinstance(gateway_service, Mapping)
        and gateway_service.get("name") == "komsco-ai-gateway"
        and gateway_service.get("namespace") == target_namespace
    )
    if backend_matches and proxy_matches:
        return condition(
            "ConsolePluginConfigured",
            "True",
            "PluginTargetsKugnusServices",
            f"ConsolePlugin {console_plugin_name} points to Kugnus services in {target_namespace}.",
            generation,
        )
    return condition(
        "ConsolePluginConfigured",
        "False",
        "BackendMismatch",
        f"ConsolePlugin {console_plugin_name} does not point to the expected Kugnus plugin/gateway services.",
        generation,
    )


def rbac_condition(config: Mapping[str, Any], generation: int) -> dict[str, Any]:
    target_namespace = str(config["namespace"])
    console_plugin_name = str(config["consolePluginName"])
    cluster_names = cluster_resource_names(console_plugin_name)
    required_resources: list[tuple[str, str, str, str | None]] = [
        ("rbac.authorization.k8s.io/v1", "Role", "komsco-ai-gateway-ledger", target_namespace),
        ("rbac.authorization.k8s.io/v1", "RoleBinding", "komsco-ai-gateway-ledger", target_namespace),
        (
            "rbac.authorization.k8s.io/v1",
            "ClusterRoleBinding",
            cluster_names["gatewayAuthDelegatorClusterRoleBinding"],
            None,
        ),
    ]
    if bool(config["mutationsEnabled"]):
        required_resources.extend(
            [
                (
                    "rbac.authorization.k8s.io/v1",
                    "ClusterRole",
                    cluster_names["actionExecutorClusterRole"],
                    None,
                ),
                (
                    "rbac.authorization.k8s.io/v1",
                    "ClusterRoleBinding",
                    cluster_names["actionExecutorClusterRoleBinding"],
                    None,
                ),
            ]
        )
    if bool(config["diagnosticsEnabled"]):
        required_resources.extend(
            [
                (
                    "rbac.authorization.k8s.io/v1",
                    "Role",
                    "komsco-ai-host-diagnostics-controller",
                    target_namespace,
                ),
                (
                    "rbac.authorization.k8s.io/v1",
                    "RoleBinding",
                    "komsco-ai-host-diagnostics-controller",
                    target_namespace,
                ),
                (
                    "rbac.authorization.k8s.io/v1",
                    "RoleBinding",
                    "komsco-ai-host-diagnostics-runner-scc",
                    target_namespace,
                ),
            ]
        )

    missing: list[str] = []
    unknown: list[str] = []
    for api_version, kind, name, resource_namespace in required_resources:
        item_condition, _ = lookup_condition("RBACReady", api_version, kind, name, resource_namespace, generation)
        if item_condition["status"] == "False":
            missing.append(f"{kind}/{name}")
        elif item_condition["status"] == "Unknown":
            unknown.append(f"{kind}/{name}: {item_condition['message']}")

    if unknown:
        return condition(
            "RBACReady",
            "Unknown",
            "LookupFailed",
            "; ".join(unknown),
            generation,
        )
    if missing:
        return condition(
            "RBACReady",
            "False",
            "MissingRBAC",
            "Missing RBAC resources: " + ", ".join(missing),
            generation,
        )
    return condition(
        "RBACReady",
        "True",
        "RBACPresent",
        "Required Kugnus RBAC resources are present.",
        generation,
    )


def action_executor_condition(config: Mapping[str, Any], generation: int) -> dict[str, Any]:
    mode = str(config["mode"])
    if not bool(config["mutationsEnabled"]):
        return condition(
            "ActionExecutorReady",
            "False",
            "MutationCapabilityMismatch",
            f"Action executor cannot be ready because mode={mode} but capabilities.mutations=false.",
            generation,
        )
    target_namespace = str(config["namespace"])
    deployment = deployment_condition("ActionExecutorReady", "komsco-ai-action-executor", target_namespace, generation)
    if deployment["status"] != "True":
        return deployment
    service_ready = service_condition("ActionExecutorReady", "komsco-ai-action-executor", target_namespace, generation)
    if service_ready["status"] != "True":
        return service_ready
    return condition(
        "ActionExecutorReady",
        "True",
        "ExecutorAvailable",
        f"Action executor deployment and service are ready in {target_namespace}.",
        generation,
    )


def host_diagnostics_condition(config: Mapping[str, Any], generation: int) -> dict[str, Any]:
    if not bool(config["diagnosticsEnabled"]):
        return condition(
            "HostDiagnosticsReady",
            "True",
            "DisabledByPolicy",
            "Host diagnostics is intentionally disabled by capabilities.diagnostics=false.",
            generation,
        )
    target_namespace = str(config["namespace"])
    deployment = deployment_condition(
        "HostDiagnosticsReady",
        "komsco-ai-host-diagnostics-controller",
        target_namespace,
        generation,
    )
    if deployment["status"] != "True":
        return deployment
    service_ready = service_condition(
        "HostDiagnosticsReady",
        "komsco-ai-host-diagnostics-controller",
        target_namespace,
        generation,
    )
    if service_ready["status"] != "True":
        return service_ready
    return condition(
        "HostDiagnosticsReady",
        "True",
        "DiagnosticsAvailable",
        f"Host diagnostics controller deployment and service are ready in {target_namespace}.",
        generation,
    )


def safety_mode_condition(config: Mapping[str, Any], generation: int) -> dict[str, Any]:
    mode = str(config["mode"])
    mutations_enabled = bool(config["mutationsEnabled"])
    unrestricted_enabled = bool(config["unrestrictedEnabled"])
    if mode == "execute" and not mutations_enabled:
        return condition(
            "SafetyModeReady",
            "False",
            "ExecuteCapabilityMismatch",
            "mode=execute requires capabilities.mutations=true.",
            generation,
        )
    if mode == "unrestricted" and (not mutations_enabled or not unrestricted_enabled):
        return condition(
            "SafetyModeReady",
            "False",
            "UnrestrictedCapabilityMismatch",
            "mode=unrestricted requires mutations=true and unrestrictedCommands=true.",
            generation,
        )
    if unrestricted_enabled or mode == "unrestricted":
        return condition(
            "SafetyModeReady",
            "False",
            "UnrestrictedCommandsEnabled",
            "Unrestricted command mode is not part of the 0.1.1 default install readiness contract.",
            generation,
        )
    return condition(
        "SafetyModeReady",
        "True",
        "ActionExecutionEnabled",
        "Action execution mode is enabled by explicit AIOpsInstallation spec.",
        generation,
    )


def runtime_conditions(config: Mapping[str, Any], generation: int) -> list[dict[str, Any]]:
    target_namespace = str(config["namespace"])
    conditions_by_type = {
        "TargetNamespaceReady": lookup_condition(
            "TargetNamespaceReady",
            "v1",
            "Namespace",
            target_namespace,
            None,
            generation,
        )[0],
        "GatewayServiceReady": service_condition(
            "GatewayServiceReady",
            "komsco-ai-gateway",
            target_namespace,
            generation,
        ),
        "GatewayReady": deployment_condition(
            "GatewayReady",
            "komsco-ai-gateway",
            target_namespace,
            generation,
        ),
        "ConsolePluginDeploymentReady": deployment_condition(
            "ConsolePluginDeploymentReady",
            "komsco-ai-console-plugin",
            target_namespace,
            generation,
        ),
        "ConsolePluginConfigured": console_plugin_condition(config, generation),
        "ServiceCABundleReady": service_ca_condition(target_namespace, generation),
        "RBACReady": rbac_condition(config, generation),
        "ActionExecutorReady": action_executor_condition(config, generation),
        "HostDiagnosticsReady": host_diagnostics_condition(config, generation),
        "SafetyModeReady": safety_mode_condition(config, generation),
    }
    return [conditions_by_type[item] for item in READINESS_CONDITION_TYPES if item in conditions_by_type]


def components_from_conditions(conditions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    component_names = {
        "TargetNamespaceReady": "targetNamespace",
        "GatewayServiceReady": "gatewayService",
        "GatewayReady": "gateway",
        "ConsolePluginDeploymentReady": "consolePluginDeployment",
        "ConsolePluginConfigured": "consolePlugin",
        "ServiceCABundleReady": "serviceCA",
        "RBACReady": "rbac",
        "ActionExecutorReady": "actionExecutor",
        "HostDiagnosticsReady": "hostDiagnostics",
        "SafetyModeReady": "safetyMode",
    }
    return {
        component_names[item["type"]]: {
            "ready": item["status"] == "True",
            "reason": item.get("reason", ""),
            "message": item.get("message", ""),
        }
        for item in conditions
        if item["type"] in component_names
    }


def status_phase(phase: str, conditions: list[dict[str, Any]]) -> str:
    if phase == "Failed":
        return "Failed"
    if conditions and all(item["status"] == "True" for item in conditions):
        return "Ready"
    return "Progressing"


def build_status_payload(
    custom_resource: Mapping[str, Any],
    phase: str,
    message: str,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = custom_resource.get("metadata") if isinstance(custom_resource.get("metadata"), Mapping) else {}
    generation = int(metadata.get("generation") or 0)
    conditions = runtime_conditions(config, generation) if config is not None else []
    resolved_phase = status_phase(phase, conditions)
    resolved_message = message
    if phase != "Failed" and resolved_phase == "Progressing":
        waiting = [item["type"] for item in conditions if item["status"] != "True"]
        resolved_message = "Waiting for readiness conditions: " + ", ".join(waiting)
    return {
        "observedGeneration": generation,
        "phase": resolved_phase,
        "message": resolved_message,
        "lastTransitionTime": now_timestamp(),
        "versionScope": VERSION_SCOPE,
        "conditions": conditions,
        "components": components_from_conditions(conditions),
    }


def update_status(
    custom_resource: Mapping[str, Any],
    phase: str,
    message: str,
    config: Mapping[str, Any] | None = None,
) -> None:
    metadata = custom_resource.get("metadata") if isinstance(custom_resource.get("metadata"), Mapping) else {}
    name = str(metadata.get("name") or DEFAULT_NAME)
    cr_namespace = str(metadata.get("namespace") or namespace())
    status = {"status": build_status_payload(custom_resource, phase, message, config)}
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


def inferred_mode(spec: Mapping[str, Any], capabilities: Mapping[str, Any]) -> str:
    if spec.get("mode") is not None:
        return str(spec["mode"])
    mutations_enabled = bool(capabilities.get("mutations", True))
    unrestricted_enabled = bool(capabilities.get("unrestrictedCommands", False))
    if unrestricted_enabled:
        return "unrestricted"
    return "execute"


def installation_config(custom_resource: Mapping[str, Any]) -> dict[str, Any]:
    spec = custom_resource.get("spec") if isinstance(custom_resource.get("spec"), Mapping) else {}
    cr_metadata = custom_resource.get("metadata") if isinstance(custom_resource.get("metadata"), Mapping) else {}
    images = spec.get("images") if isinstance(spec.get("images"), Mapping) else {}
    capabilities = spec.get("capabilities") if isinstance(spec.get("capabilities"), Mapping) else {}
    rag = spec.get("rag") if isinstance(spec.get("rag"), Mapping) else {}
    config = {
        "name": str(spec_value(spec, "name", DEFAULT_NAME)),
        "namespace": str(spec_value(spec, "targetNamespace", cr_metadata.get("namespace") or DEFAULT_TARGET_NAMESPACE)),
        "createNamespace": bool(spec_value(spec, "createNamespace", True)),
        "pluginImage": str(images.get("plugin") or DEFAULT_PLUGIN_IMAGE),
        "gatewayImage": str(images.get("gateway") or DEFAULT_GATEWAY_IMAGE),
        "runnerImage": str(images.get("hostDiagnosticsRunner") or images.get("gateway") or DEFAULT_GATEWAY_IMAGE),
        "pluginReplicas": int(spec_value(spec, "pluginReplicas", 2)),
        "gatewayReplicas": int(spec_value(spec, "gatewayReplicas", 1)),
        "mode": inferred_mode(spec, capabilities),
        "diagnosticsEnabled": bool(capabilities.get("diagnostics", True)),
        "mutationsEnabled": bool(capabilities.get("mutations", True)),
        "unrestrictedEnabled": bool(capabilities.get("unrestrictedCommands", False)),
        "enableConsolePlugin": bool(spec_value(spec, "enableConsolePlugin", True)),
        "consolePluginName": str(spec_value(spec, "consolePluginName", DEFAULT_CONSOLE_PLUGIN_NAME)),
        "consolePluginDisplayName": str(
            spec_value(spec, "consolePluginDisplayName", DEFAULT_CONSOLE_PLUGIN_DISPLAY_NAME)
        ),
        "disabledConsolePluginNames": string_list(
            spec_value(spec, "disabledConsolePluginNames", DEFAULT_DISABLED_CONSOLE_PLUGIN_NAMES)
        ),
        "ragBackendUrlSecret": str(rag.get("backendUrlSecret") or ""),
        "ragBackendUrlKey": str(rag.get("backendUrlKey") or "url"),
        "ragEmbeddingProvider": str(rag.get("embeddingProvider") or ""),
        "ragEmbeddingApiStyle": str(rag.get("embeddingApiStyle") or ""),
        "ragEmbeddingBaseUrl": str(rag.get("embeddingBaseUrl") or ""),
        "ragEmbeddingModel": str(rag.get("embeddingModel") or "hashing-local-dev"),
        "ragEmbeddingTimeoutSeconds": int(rag.get("embeddingTimeoutSeconds") or 10),
        "ragVectorDimensions": int(rag.get("vectorDimensions") or 64),
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


def secret(name: str, target_namespace: str, labels: Mapping[str, str], string_data: Mapping[str, str]) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": name, "namespace": target_namespace, "labels": dict(labels)},
        "type": "Opaque",
        "stringData": dict(string_data),
    }


def secret_key_env(name: str, secret_name: str, key: str) -> dict[str, Any]:
    return {
        "name": name,
        "valueFrom": {"secretKeyRef": {"name": secret_name, "key": key}},
    }


def token_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def existing_secret_string_value(target_namespace: str, name: str, key: str) -> str:
    try:
        existing = get_resource("v1", "Secret", name, target_namespace)
    except Exception:
        return ""
    if not isinstance(existing, Mapping):
        return ""

    string_data = existing.get("stringData")
    if isinstance(string_data, Mapping):
        value = string_data.get(key)
        if isinstance(value, str) and value:
            return value

    data = existing.get("data")
    if not isinstance(data, Mapping):
        return ""
    encoded = data.get(key)
    if not isinstance(encoded, str) or not encoded:
        return ""
    try:
        return base64.b64decode(encoded, validate=True).decode("utf-8")
    except Exception:
        return ""


def resolved_action_executor_shared_token(target_namespace: str) -> str:
    return (
        existing_secret_string_value(
            target_namespace,
            DEFAULT_ACTION_EXECUTOR_AUTH_SECRET,
            DEFAULT_ACTION_EXECUTOR_AUTH_KEY,
        )
        or DEFAULT_ACTION_EXECUTOR_SHARED_TOKEN
    )


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
    pod_annotations: Mapping[str, str] | None = None,
    volumes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    pod_labels = {**dict(labels), "app": name}
    container_spec = {"name": name, "image": image, "imagePullPolicy": "Always", **dict(container)}
    pod_metadata = {"labels": pod_labels}
    if pod_annotations:
        pod_metadata["annotations"] = dict(pod_annotations)
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name, "namespace": target_namespace, "labels": dict(labels)},
        "spec": {
            "replicas": replicas,
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": pod_metadata,
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
    action_executor_shared_token = (
        resolved_action_executor_shared_token(target_namespace)
        if mutations_enabled
        else DEFAULT_ACTION_EXECUTOR_SHARED_TOKEN
    )
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
                secret(
                    DEFAULT_ACTION_EXECUTOR_AUTH_SECRET,
                    target_namespace,
                    labels,
                    {DEFAULT_ACTION_EXECUTOR_AUTH_KEY: action_executor_shared_token},
                ),
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
    resources.extend(workload_resources(config, labels, action_executor_shared_token))
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


def workload_resources(
    config: Mapping[str, Any],
    labels: Mapping[str, str],
    action_executor_shared_token: str | None = None,
) -> list[dict[str, Any]]:
    target_namespace = str(config["namespace"])
    gateway_image = str(config["gatewayImage"])
    console_plugin_name = str(config["consolePluginName"])
    mutations_enabled_bool = bool(config["mutationsEnabled"])
    diagnostics_enabled_bool = bool(config["diagnosticsEnabled"])
    mutations_enabled = str(mutations_enabled_bool).lower()
    diagnostics_enabled = str(diagnostics_enabled_bool).lower()
    unrestricted_enabled = str(bool(config["unrestrictedEnabled"])).lower()
    action_executor_secret_ref = secret_key_env(
        "KOMSCO_AI_ACTION_EXECUTOR_SHARED_TOKEN",
        DEFAULT_ACTION_EXECUTOR_AUTH_SECRET,
        DEFAULT_ACTION_EXECUTOR_AUTH_KEY,
    )
    action_executor_secret_digest = token_digest(action_executor_shared_token or DEFAULT_ACTION_EXECUTOR_SHARED_TOKEN)
    gateway_env = [
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
        {"name": "KOMSCO_AI_EMBEDDING_PROVIDER", "value": str(config["ragEmbeddingProvider"])},
        {"name": "KOMSCO_AI_EMBEDDING_API_STYLE", "value": str(config["ragEmbeddingApiStyle"])},
        {"name": "KOMSCO_AI_EMBEDDING_BASE_URL", "value": str(config["ragEmbeddingBaseUrl"])},
        {"name": "KOMSCO_AI_EMBEDDING_MODEL", "value": str(config["ragEmbeddingModel"])},
        {"name": "KOMSCO_AI_EMBEDDING_DIMENSIONS", "value": str(config["ragVectorDimensions"])},
        {"name": "KOMSCO_AI_EMBEDDING_TIMEOUT_SECONDS", "value": str(config["ragEmbeddingTimeoutSeconds"])},
        {"name": "KOMSCO_AI_RAG_EMBEDDING_MODEL", "value": str(config["ragEmbeddingModel"])},
        {"name": "KOMSCO_AI_RAG_VECTOR_DIMENSIONS", "value": str(config["ragVectorDimensions"])},
    ]
    if mutations_enabled_bool:
        gateway_env.append(action_executor_secret_ref)
    if config["ragBackendUrlSecret"]:
        gateway_env.append(
            {
                "name": "KOMSCO_AI_RAG_BACKEND_URL",
                "valueFrom": {
                    "secretKeyRef": {
                        "name": str(config["ragBackendUrlSecret"]),
                        "key": str(config["ragBackendUrlKey"]),
                    }
                },
            }
        )
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
                "env": gateway_env,
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
            pod_annotations={"aiops.komsco/action-executor-token-digest": action_executor_secret_digest}
            if mutations_enabled_bool
            else None,
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
                        action_executor_secret_ref,
                        {
                            "name": "KOMSCO_AI_ACTION_EXECUTOR_TOKEN_FILE",
                            "value": "/var/run/secrets/kubernetes.io/serviceaccount/token",
                        },
                        {"name": "OPENSHIFT_API_CA_FILE", "value": "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"},
                    ],
                    "readinessProbe": {"httpGet": {"path": "/healthz", "port": "http"}, "initialDelaySeconds": 5, "periodSeconds": 10},
                    "livenessProbe": {"httpGet": {"path": "/healthz", "port": "http"}, "initialDelaySeconds": 15, "periodSeconds": 20},
                    "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}, "runAsNonRoot": True},
                },
                pod_annotations={"aiops.komsco/action-executor-token-digest": action_executor_secret_digest},
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
        {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {
                "name": f"allow-{target_namespace}-gateway-to-lightspeed-app-server",
                "namespace": "openshift-lightspeed",
                "labels": dict(labels),
            },
            "spec": {
                "podSelector": {
                    "matchLabels": {
                        "app.kubernetes.io/component": "application-server",
                        "app.kubernetes.io/name": "lightspeed-service-api",
                        "app.kubernetes.io/part-of": "openshift-lightspeed",
                    }
                },
                "policyTypes": ["Ingress"],
                "ingress": [
                    {
                        "from": [
                            {
                                "namespaceSelector": {
                                    "matchLabels": {"kubernetes.io/metadata.name": target_namespace}
                                },
                                "podSelector": {"matchLabels": {"app": "komsco-ai-gateway"}},
                            }
                        ],
                        "ports": [{"port": 8443, "protocol": "TCP"}],
                    }
                ],
            },
        },
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
    config: dict[str, Any] | None = None
    try:
        config = installation_config(custom_resource)
        print(f"reconciling {name} into namespace {config['namespace']}", flush=True)
        for resource in resources_for(config):
            apply_resource(resource)
        if config["enableConsolePlugin"]:
            patch_console_plugin_enabled(
                str(config["consolePluginName"]),
                list(config["disabledConsolePluginNames"]),
            )
        update_status(custom_resource, "Ready", "KOMSCO AIOps runtime reconciled", config=config)
    except Exception as exc:
        print(f"reconcile failed for {name}: {exc}", flush=True)
        update_status(custom_resource, "Failed", str(exc), config=config)


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
