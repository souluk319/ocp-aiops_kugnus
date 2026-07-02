#!/usr/bin/env python3
import base64
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIR = ROOT / "olm" / "generated"
BUNDLE_DIR = GENERATED_DIR / "bundle"
CATALOG_DIR = GENERATED_DIR / "catalog"
INSTALL_DIR = GENERATED_DIR / "install"

PACKAGE_NAME = os.getenv("KOMSCO_AIOPS_PACKAGE_NAME", "cywell-aiops")
OPERATOR_NAME = os.getenv("KOMSCO_AIOPS_OPERATOR_NAME", "cywell-aiops-operator")
INSTALLATION_NAME = os.getenv("KOMSCO_AIOPS_INSTALLATION_NAME", "cywell-aiops")
CATALOG_NAME = os.getenv("KOMSCO_AIOPS_OLM_CATALOG_NAME", "cywell-aiops-catalog")
CATALOG_NAMESPACE = os.getenv("KOMSCO_AIOPS_OLM_CATALOG_NAMESPACE", "openshift-marketplace")
CHANNEL = os.getenv("KOMSCO_AIOPS_CHANNEL", "stable")
VERSION = os.getenv("KOMSCO_AIOPS_OPERATOR_VERSION", "0.1.9")
CSV_NAME = f"{OPERATOR_NAME}.v{VERSION}"
SKIPS_CSV = os.getenv("KOMSCO_AIOPS_SKIPS_CSV", "")
VERSION_SCOPE = os.getenv("KOMSCO_AIOPS_VERSION_SCOPE", f"Ver.{VERSION}")
INSTALL_NAMESPACE = os.getenv("KOMSCO_AIOPS_OPERATOR_NAMESPACE", "cywell-aiops")
TARGET_NAMESPACE = os.getenv("KOMSCO_AIOPS_NAMESPACE", INSTALL_NAMESPACE)
PLUGIN_IMAGE = os.getenv(
    "KOMSCO_AIOPS_PLUGIN_IMAGE",
    f"image-registry.openshift-image-registry.svc:5000/{TARGET_NAMESPACE}/komsco-ai-console-plugin:{VERSION}",
)
GATEWAY_IMAGE = os.getenv(
    "KOMSCO_AIOPS_GATEWAY_IMAGE",
    f"image-registry.openshift-image-registry.svc:5000/{TARGET_NAMESPACE}/komsco-ai-gateway:{VERSION}",
)
OPERATOR_IMAGE = os.getenv("KOMSCO_AIOPS_OPERATOR_IMAGE", GATEWAY_IMAGE)
DISPLAY_NAME = os.getenv("KOMSCO_AIOPS_DISPLAY_NAME", "AIOps")
CONSOLE_PLUGIN_NAME = os.getenv("KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME", "cywell-aiops-console-plugin")
CONSOLE_PLUGIN_DISPLAY_NAME = os.getenv("KOMSCO_AIOPS_CONSOLE_PLUGIN_DISPLAY_NAME", DISPLAY_NAME)
DISABLED_CONSOLE_PLUGIN_NAMES = [
    item.strip()
    for item in os.getenv(
        "KOMSCO_AIOPS_DISABLED_CONSOLE_PLUGIN_NAMES",
        "komsco-ai-console-plugin,lightspeed-console-plugin",
    ).split(",")
    if item.strip()
]
PROVIDER_NAME = os.getenv("KOMSCO_AIOPS_PROVIDER_NAME", "Cywell")
CATALOG_DISPLAY_NAME = os.getenv("KOMSCO_AIOPS_CATALOG_DISPLAY_NAME", f"{DISPLAY_NAME} Catalog")
CATALOG_PUBLISHER = os.getenv("KOMSCO_AIOPS_CATALOG_PUBLISHER", PROVIDER_NAME)
MAINTAINER_NAME = os.getenv("KOMSCO_AIOPS_MAINTAINER_NAME", f"{PROVIDER_NAME} Platform Team")
REPOSITORY_URL = os.getenv("KOMSCO_AIOPS_REPOSITORY_URL", "").strip()
DESCRIPTION = os.getenv(
    "KOMSCO_AIOPS_DESCRIPTION",
    f"{DISPLAY_NAME} provides an OpenShift console assistant, audit trail, policy views, action execution, and host diagnostics integration.",
)
SHORT_DESCRIPTION = os.getenv(
    "KOMSCO_AIOPS_SHORT_DESCRIPTION",
    f"{DISPLAY_NAME} installs the OpenShift console assistant, gateway, action executor, and host diagnostics runtime.",
)
CATEGORIES = os.getenv("KOMSCO_AIOPS_CATEGORIES", "OpenShift Optional, Monitoring")
KEYWORDS = [
    item.strip()
    for item in os.getenv(
        "KOMSCO_AIOPS_KEYWORDS",
        "komsco-aiops,komsco,cywell,aiops,openshift,assistant,operations",
    ).split(",")
    if item.strip()
]
DEFAULT_ICON_FILE = ROOT / "komsco-ai-console-plugin" / "src" / "assets" / "aiops_icon.png"
READINESS_CONDITION_TYPES = [
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

OLM_SAFE_SEMVER_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z][0-9A-Za-z.-]*)?$"
)


def validate_operator_version(version: str) -> None:
    if OLM_SAFE_SEMVER_RE.fullmatch(version):
        return
    raise SystemExit(
        "KOMSCO_AIOPS_OPERATOR_VERSION must be an OLM-safe SemVer value such as "
        "0.1.8 or 0.1.8-1. Do not use four-part document versions like 0.1.8.1 "
        "as a ClusterServiceVersion version."
    )


validate_operator_version(VERSION)


def default_skips_csv() -> list[str]:
    if SKIPS_CSV:
        return [item.strip() for item in SKIPS_CSV.split(",") if item.strip()]

    parts = VERSION.split(".")
    if len(parts) != 3:
        return []
    try:
        major, minor, patch = (int(part) for part in parts)
    except ValueError:
        return []
    if patch <= 0:
        return []
    return [f"{OPERATOR_NAME}.v{major}.{minor}.{patch - 1}"]


def default_icon_base64() -> str:
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="12" fill="#0f766e"/>
<path d="M18 45 30 17h8l12 28h-8l-2-6H28l-2 6h-8Zm12-13h8l-4-11-4 11Z" fill="#ffffff"/>
</svg>"""
    return base64.b64encode(svg.encode("utf-8")).decode("ascii")


def infer_icon_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".svg":
        return "image/svg+xml"
    return "application/octet-stream"


def load_icon_file(path: Path) -> tuple[str, str]:
    resolved_path = path if path.is_absolute() else ROOT / path
    if not resolved_path.exists():
        raise FileNotFoundError(f"OLM icon file does not exist: {resolved_path}")
    return (
        base64.b64encode(resolved_path.read_bytes()).decode("ascii"),
        os.getenv("KOMSCO_AIOPS_ICON_MEDIA_TYPE", infer_icon_media_type(resolved_path)),
    )


def resolve_icon() -> tuple[str, str]:
    configured_base64 = os.getenv("KOMSCO_AIOPS_ICON_BASE64")
    if configured_base64:
        return configured_base64, os.getenv("KOMSCO_AIOPS_ICON_MEDIA_TYPE", "image/svg+xml")

    configured_file = os.getenv("KOMSCO_AIOPS_ICON_FILE")
    if configured_file:
        return load_icon_file(Path(configured_file))

    if DEFAULT_ICON_FILE.exists():
        return load_icon_file(DEFAULT_ICON_FILE)

    return default_icon_base64(), os.getenv("KOMSCO_AIOPS_ICON_MEDIA_TYPE", "image/svg+xml")


ICON_BASE64, ICON_MEDIA_TYPE = resolve_icon()


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


RAG_EMBEDDING_PROVIDER = first_env_value(
    "KOMSCO_AI_DEFAULT_EMBEDDING_PROVIDER",
    "KOMSCO_AI_EMBEDDING_PROVIDER",
)
RAG_EMBEDDING_API_STYLE = first_env_value(
    "KOMSCO_AI_DEFAULT_EMBEDDING_API_STYLE",
    "KOMSCO_AI_EMBEDDING_API_STYLE",
)
RAG_EMBEDDING_BASE_URL = first_env_value(
    "KOMSCO_AI_DEFAULT_EMBEDDING_BASE_URL",
    "KOMSCO_AI_EMBEDDING_BASE_URL",
)
RAG_EMBEDDING_MODEL = first_env_value(
    "KOMSCO_AI_DEFAULT_EMBEDDING_MODEL",
    "KOMSCO_AI_EMBEDDING_MODEL",
    "KOMSCO_AI_DEFAULT_RAG_EMBEDDING_MODEL",
    default="hashing-local-dev",
)
RAG_EMBEDDING_TIMEOUT_SECONDS = first_int_env(
    "KOMSCO_AI_DEFAULT_EMBEDDING_TIMEOUT_SECONDS",
    "KOMSCO_AI_EMBEDDING_TIMEOUT_SECONDS",
    "KOMSCO_AI_DEFAULT_RAG_EMBEDDING_TIMEOUT_SECONDS",
    default=10,
)
RAG_VECTOR_DIMENSIONS = first_int_env(
    "KOMSCO_AI_DEFAULT_EMBEDDING_DIMENSIONS",
    "KOMSCO_AI_EMBEDDING_DIMENSIONS",
    "KOMSCO_AI_DEFAULT_RAG_VECTOR_DIMENSIONS",
    default=64,
)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def crd() -> dict[str, Any]:
    return {
        "apiVersion": "apiextensions.k8s.io/v1",
        "kind": "CustomResourceDefinition",
        "metadata": {
            "name": "aiopsinstallations.aiops.komsco.io",
            "labels": {"app.kubernetes.io/name": PACKAGE_NAME},
        },
        "spec": {
            "group": "aiops.komsco.io",
            "scope": "Namespaced",
            "names": {
                "plural": "aiopsinstallations",
                "singular": "aiopsinstallation",
                "kind": "AIOpsInstallation",
                "shortNames": ["aiopsinst"],
            },
            "versions": [
                {
                    "name": "v1alpha1",
                    "served": True,
                    "storage": True,
                    "subresources": {"status": {}},
                    "schema": {
                        "openAPIV3Schema": {
                            "type": "object",
                            "description": f"AIOpsInstallation configures a {DISPLAY_NAME} runtime managed by OLM.",
                            "properties": {
                                "spec": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string", "default": INSTALLATION_NAME},
                                        "targetNamespace": {"type": "string"},
                                        "createNamespace": {"type": "boolean", "default": True},
                                        "mode": {
                                            "type": "string",
                                            "enum": ["execute", "unrestricted"],
                                            "default": "execute",
                                        },
                                        "pluginReplicas": {"type": "integer", "minimum": 1, "default": 2},
                                        "gatewayReplicas": {"type": "integer", "minimum": 1, "default": 1},
                                        "enableConsolePlugin": {"type": "boolean", "default": True},
                                        "consolePluginName": {
                                            "type": "string",
                                            "default": CONSOLE_PLUGIN_NAME,
                                        },
                                        "consolePluginDisplayName": {
                                            "type": "string",
                                            "default": CONSOLE_PLUGIN_DISPLAY_NAME,
                                        },
                                        "consoleApplicationMenuEnabled": {
                                            "type": "boolean",
                                            "default": True,
                                        },
                                        "consoleApplicationMenuName": {
                                            "type": "string",
                                            "default": "komsco-aiops-application-menu",
                                        },
                                        "consoleApplicationMenuSection": {
                                            "type": "string",
                                            "default": "Cywell",
                                        },
                                        "consoleApplicationMenuText": {
                                            "type": "string",
                                            "default": "AIOps",
                                        },
                                        "consoleApplicationMenuHref": {
                                            "type": "string",
                                            "default": "https://console-openshift-console.apps.ocp.cywell.server/dashboards/aiops",
                                        },
                                        "consoleApplicationMenuImageURL": {
                                            "type": "string",
                                            "default": "data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2064%2064%22%3E%3Crect%20width%3D%2264%22%20height%3D%2264%22%20rx%3D%2214%22%20fill%3D%22%2306131f%22%2F%3E%3Crect%20x%3D%2212%22%20y%3D%2212%22%20width%3D%2240%22%20height%3D%2240%22%20rx%3D%2212%22%20fill%3D%22%23081827%22%20stroke%3D%22%23334155%22%20stroke-width%3D%222%22%2F%3E%3Cpath%20d%3D%22M32%2015%2049%2032%2032%2049%2015%2032%2032%2015Z%22%20fill%3D%22none%22%20stroke%3D%22%2338d6c1%22%20stroke-width%3D%224%22%20stroke-linejoin%3D%22round%22%2F%3E%3Cpath%20d%3D%22M23%2039%2031%2022h3l8%2017h-5l-1.3-3h-6.5l-1.2%203h-5Zm7.7-7h3.7L32.5%2027%2030.7%2032Z%22%20fill%3D%22%23e5faff%22%2F%3E%3Ccircle%20cx%3D%2232%22%20cy%3D%2232%22%20r%3D%2212%22%20fill%3D%22none%22%20stroke%3D%22%2338d6c1%22%20stroke-opacity%3D%22.18%22%20stroke-width%3D%224%22%2F%3E%3C%2Fsvg%3E",
                                        },
                                        "disabledConsolePluginNames": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "default": DISABLED_CONSOLE_PLUGIN_NAMES,
                                        },
                                        "images": {
                                            "type": "object",
                                            "properties": {
                                                "plugin": {"type": "string"},
                                                "gateway": {"type": "string"},
                                                "hostDiagnosticsRunner": {"type": "string"},
                                            },
                                        },
                                        "capabilities": {
                                            "type": "object",
                                            "properties": {
                                                "diagnostics": {"type": "boolean", "default": True},
                                                "mutations": {"type": "boolean", "default": True},
                                                "unrestrictedCommands": {"type": "boolean", "default": True},
                                            },
                                        },
                                        "rag": {
                                            "type": "object",
                                            "properties": {
                                                "backendUrlSecret": {"type": "string"},
                                                "backendUrlKey": {"type": "string", "default": "url"},
                                                "embeddingProvider": {"type": "string"},
                                                "embeddingApiStyle": {"type": "string"},
                                                "embeddingBaseUrl": {"type": "string"},
                                                "embeddingModel": {"type": "string"},
                                                "embeddingTimeoutSeconds": {"type": "integer", "minimum": 1},
                                                "vectorDimensions": {"type": "integer", "minimum": 1},
                                            },
                                        },
                                    },
                                },
                                "status": {
                                    "type": "object",
                                    "properties": {
                                        "observedGeneration": {"type": "integer"},
                                        "phase": {"type": "string"},
                                        "message": {"type": "string"},
                                        "lastTransitionTime": {"type": "string"},
                                        "versionScope": {"type": "string"},
                                        "conditions": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "required": ["type", "status"],
                                                "properties": {
                                                    "type": {"type": "string"},
                                                    "status": {
                                                        "type": "string",
                                                        "enum": ["True", "False", "Unknown"],
                                                    },
                                                    "reason": {"type": "string"},
                                                    "message": {"type": "string"},
                                                    "lastTransitionTime": {"type": "string"},
                                                    "observedGeneration": {"type": "integer"},
                                                },
                                            },
                                        },
                                        "components": {
                                            "type": "object",
                                            "additionalProperties": {
                                                "type": "object",
                                                "properties": {
                                                    "ready": {"type": "boolean"},
                                                    "reason": {"type": "string"},
                                                    "message": {"type": "string"},
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        }
                    },
                }
            ],
        },
    }


def operator_rules() -> list[dict[str, Any]]:
    return [
        {"apiGroups": ["aiops.komsco.io"], "resources": ["aiopsinstallations"], "verbs": ["create", "delete", "get", "list", "watch", "patch", "update"]},
        {"apiGroups": ["aiops.komsco.io"], "resources": ["aiopsinstallations/status"], "verbs": ["get", "patch", "update"]},
        {"apiGroups": [""], "resources": ["namespaces", "serviceaccounts", "services", "configmaps", "secrets", "events"], "verbs": ["create", "get", "list", "patch", "update", "watch"]},
        {"apiGroups": [""], "resources": ["pods"], "verbs": ["get", "list", "watch"]},
        {"apiGroups": [""], "resources": ["pods/log"], "verbs": ["get"]},
        {"apiGroups": [""], "resources": ["pods/eviction"], "verbs": ["create"]},
        {"apiGroups": ["authentication.k8s.io"], "resources": ["tokenreviews"], "verbs": ["create"]},
        {"apiGroups": ["authorization.k8s.io"], "resources": ["subjectaccessreviews"], "verbs": ["create"]},
        {"apiGroups": ["apps"], "resources": ["deployments"], "verbs": ["create", "get", "list", "patch", "update", "watch"]},
        {"apiGroups": ["apps"], "resources": ["deployments/scale", "replicasets"], "verbs": ["get", "list", "patch", "update", "watch"]},
        {"apiGroups": ["autoscaling"], "resources": ["horizontalpodautoscalers"], "verbs": ["get", "list", "patch", "update", "watch"]},
        {"apiGroups": ["batch"], "resources": ["jobs"], "verbs": ["create", "delete", "get", "list", "watch"]},
        {"apiGroups": ["networking.k8s.io"], "resources": ["networkpolicies"], "verbs": ["create", "get", "list", "patch", "update", "watch"]},
        {"apiGroups": ["policy"], "resources": ["poddisruptionbudgets"], "verbs": ["get", "list", "watch"]},
        {"apiGroups": ["rbac.authorization.k8s.io"], "resources": ["roles", "rolebindings", "clusterroles", "clusterrolebindings"], "verbs": ["create", "get", "list", "patch", "update", "watch"]},
        {"apiGroups": ["security.openshift.io"], "resources": ["securitycontextconstraints"], "resourceNames": ["hostmount-anyuid-v2"], "verbs": ["use"]},
        {"apiGroups": ["console.openshift.io"], "resources": ["consolelinks", "consoleplugins"], "verbs": ["create", "get", "list", "patch", "update", "watch"]},
        {"apiGroups": ["operator.openshift.io"], "resources": ["consoles"], "verbs": ["get", "patch", "update"]},
    ]


def csv() -> dict[str, Any]:
    labels = {"app.kubernetes.io/name": OPERATOR_NAME, "app.kubernetes.io/part-of": PACKAGE_NAME}
    skips = default_skips_csv()
    annotations = {
        "alm-examples": json.dumps([aiops_installation()], ensure_ascii=False),
        "aiops.komsco.io/version-scope": VERSION_SCOPE,
        "aiops.komsco.io/readiness-conditions": ",".join(READINESS_CONDITION_TYPES),
        "capabilities": "Full Lifecycle",
        "categories": CATEGORIES,
        "containerImage": OPERATOR_IMAGE,
        "description": SHORT_DESCRIPTION,
    }
    if REPOSITORY_URL:
        annotations["repository"] = REPOSITORY_URL

    return {
        "apiVersion": "operators.coreos.com/v1alpha1",
        "kind": "ClusterServiceVersion",
        "metadata": {
            "name": CSV_NAME,
            "annotations": annotations,
        },
        "spec": {
            "displayName": DISPLAY_NAME,
            "description": DESCRIPTION,
            "version": VERSION,
            "maturity": "alpha",
            **({"skips": skips} if skips else {}),
            "provider": {"name": PROVIDER_NAME},
            "keywords": KEYWORDS,
            "maintainers": [{"name": MAINTAINER_NAME}],
            **({"links": [{"name": DISPLAY_NAME, "url": REPOSITORY_URL}]} if REPOSITORY_URL else {}),
            "icon": [{"base64data": ICON_BASE64, "mediatype": ICON_MEDIA_TYPE}],
            "installModes": [
                {"type": "OwnNamespace", "supported": True},
                {"type": "SingleNamespace", "supported": True},
                {"type": "MultiNamespace", "supported": False},
                {"type": "AllNamespaces", "supported": False},
            ],
            "customresourcedefinitions": {
                "owned": [
                    {
                        "name": "aiopsinstallations.aiops.komsco.io",
                        "version": "v1alpha1",
                        "kind": "AIOpsInstallation",
                        "displayName": "AIOps Installation",
                        "description": f"Configures a {DISPLAY_NAME} runtime installation.",
                    }
                ]
            },
            "relatedImages": [
                {"name": "operator", "image": OPERATOR_IMAGE},
                {"name": "console-plugin", "image": PLUGIN_IMAGE},
                {"name": "gateway", "image": GATEWAY_IMAGE},
            ],
            "install": {
                "strategy": "deployment",
                "spec": {
                    "clusterPermissions": [
                        {
                            "serviceAccountName": OPERATOR_NAME,
                            "rules": operator_rules(),
                        }
                    ],
                    "deployments": [
                        {
                            "name": OPERATOR_NAME,
                            "spec": {
                                "replicas": 1,
                                "selector": {"matchLabels": {"app": OPERATOR_NAME}},
                                "template": {
                                    "metadata": {"labels": {"app": OPERATOR_NAME, **labels}},
                                    "spec": {
                                        "serviceAccountName": OPERATOR_NAME,
                                        "containers": [
                                            {
                                                "name": OPERATOR_NAME,
                                                "image": OPERATOR_IMAGE,
                                                "imagePullPolicy": "Always",
                                                "command": ["python", "-m", "komsco_ai_gateway.olm_operator"],
                                                "env": [
                                                    {"name": "KOMSCO_AI_DEFAULT_TARGET_NAMESPACE", "value": TARGET_NAMESPACE},
                                                    {"name": "KOMSCO_AI_DEFAULT_PLUGIN_IMAGE", "value": PLUGIN_IMAGE},
                                                    {"name": "KOMSCO_AI_DEFAULT_GATEWAY_IMAGE", "value": GATEWAY_IMAGE},
                                                    {"name": "KOMSCO_AI_DEFAULT_CONSOLE_PLUGIN_NAME", "value": CONSOLE_PLUGIN_NAME},
                                                    {
                                                        "name": "KOMSCO_AI_DEFAULT_CONSOLE_PLUGIN_DISPLAY_NAME",
                                                        "value": CONSOLE_PLUGIN_DISPLAY_NAME,
                                                    },
                                                    {
                                                        "name": "KOMSCO_AI_DEFAULT_DISABLED_CONSOLE_PLUGIN_NAMES",
                                                        "value": ",".join(DISABLED_CONSOLE_PLUGIN_NAMES),
                                                    },
                                                    {
                                                        "name": "KOMSCO_AI_OPERATOR_BOOTSTRAP_INSTALLATION",
                                                        "value": os.getenv("KOMSCO_AIOPS_BOOTSTRAP_INSTALLATION", "true"),
                                                    },
                                                    {
                                                        "name": "KOMSCO_AI_DEFAULT_INSTALLATION_NAME",
                                                        "value": INSTALLATION_NAME,
                                                    },
                                                    {"name": "KOMSCO_AI_DEFAULT_MODE", "value": os.getenv("KOMSCO_AIOPS_MODE", "execute")},
                                                    {"name": "KOMSCO_AI_DEFAULT_ENABLE_MUTATIONS", "value": os.getenv("KOMSCO_AIOPS_ENABLE_MUTATIONS", "true")},
                                                    {
                                                        "name": "KOMSCO_AI_DEFAULT_ENABLE_UNRESTRICTED_COMMANDS",
                                                        "value": os.getenv("KOMSCO_AIOPS_ENABLE_UNRESTRICTED_COMMANDS", "true"),
                                                    },
                                                    {"name": "KOMSCO_AI_DEFAULT_EMBEDDING_PROVIDER", "value": RAG_EMBEDDING_PROVIDER},
                                                    {"name": "KOMSCO_AI_DEFAULT_EMBEDDING_API_STYLE", "value": RAG_EMBEDDING_API_STYLE},
                                                    {"name": "KOMSCO_AI_DEFAULT_EMBEDDING_BASE_URL", "value": RAG_EMBEDDING_BASE_URL},
                                                    {"name": "KOMSCO_AI_DEFAULT_EMBEDDING_MODEL", "value": RAG_EMBEDDING_MODEL},
                                                    {
                                                        "name": "KOMSCO_AI_DEFAULT_EMBEDDING_TIMEOUT_SECONDS",
                                                        "value": str(RAG_EMBEDDING_TIMEOUT_SECONDS),
                                                    },
                                                    {
                                                        "name": "KOMSCO_AI_DEFAULT_EMBEDDING_DIMENSIONS",
                                                        "value": str(RAG_VECTOR_DIMENSIONS),
                                                    },
                                                    {"name": "KOMSCO_AI_OPERATOR_VERSION_SCOPE", "value": VERSION_SCOPE},
                                                    {
                                                        "name": "KOMSCO_AI_OPERATOR_READINESS_CONDITIONS",
                                                        "value": ",".join(READINESS_CONDITION_TYPES),
                                                    },
                                                    {"name": "KOMSCO_AI_OPERATOR_RECONCILE_SECONDS", "value": "30"},
                                                ],
                                                "securityContext": {
                                                    "allowPrivilegeEscalation": False,
                                                    "capabilities": {"drop": ["ALL"]},
                                                    "runAsNonRoot": True,
                                                },
                                            }
                                        ],
                                        "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
                                    },
                                },
                            },
                        }
                    ],
                },
            },
        },
    }


def package_manifest() -> dict[str, Any]:
    return {
        "packageName": PACKAGE_NAME,
        "channels": [{"name": CHANNEL, "currentCSV": CSV_NAME}],
        "defaultChannel": CHANNEL,
    }


def catalog_configmap() -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": CATALOG_NAME, "namespace": CATALOG_NAMESPACE},
        "data": {
            "customResourceDefinitions": json.dumps([crd()], ensure_ascii=False),
            "clusterServiceVersions": json.dumps([csv()], ensure_ascii=False),
            "packages": json.dumps([package_manifest()], ensure_ascii=False),
        },
    }


def catalog_source() -> dict[str, Any]:
    return {
        "apiVersion": "operators.coreos.com/v1alpha1",
        "kind": "CatalogSource",
        "metadata": {"name": CATALOG_NAME, "namespace": CATALOG_NAMESPACE},
        "spec": {
            "displayName": CATALOG_DISPLAY_NAME,
            "publisher": CATALOG_PUBLISHER,
            "sourceType": "internal",
            "configMap": CATALOG_NAME,
        },
    }


def namespace_resource() -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {"name": INSTALL_NAMESPACE},
    }


def operator_group() -> dict[str, Any]:
    return {
        "apiVersion": "operators.coreos.com/v1",
        "kind": "OperatorGroup",
        "metadata": {"name": PACKAGE_NAME, "namespace": INSTALL_NAMESPACE},
        "spec": {"targetNamespaces": [INSTALL_NAMESPACE]},
    }


def subscription() -> dict[str, Any]:
    return {
        "apiVersion": "operators.coreos.com/v1alpha1",
        "kind": "Subscription",
        "metadata": {"name": PACKAGE_NAME, "namespace": INSTALL_NAMESPACE},
        "spec": {
            "channel": CHANNEL,
            "installPlanApproval": os.getenv("KOMSCO_AIOPS_INSTALL_PLAN_APPROVAL", "Automatic"),
            "name": PACKAGE_NAME,
            "source": CATALOG_NAME,
            "sourceNamespace": CATALOG_NAMESPACE,
        },
    }


def aiops_installation() -> dict[str, Any]:
    return {
        "apiVersion": "aiops.komsco.io/v1alpha1",
        "kind": "AIOpsInstallation",
        "metadata": {"name": INSTALLATION_NAME, "namespace": INSTALL_NAMESPACE},
        "spec": {
            "targetNamespace": TARGET_NAMESPACE,
            "createNamespace": True,
            "mode": os.getenv("KOMSCO_AIOPS_MODE", "execute"),
            "pluginReplicas": int(os.getenv("KOMSCO_AIOPS_PLUGIN_REPLICAS", "2")),
            "gatewayReplicas": int(os.getenv("KOMSCO_AIOPS_GATEWAY_REPLICAS", "1")),
            "enableConsolePlugin": True,
            "consolePluginName": CONSOLE_PLUGIN_NAME,
            "consolePluginDisplayName": CONSOLE_PLUGIN_DISPLAY_NAME,
            "disabledConsolePluginNames": DISABLED_CONSOLE_PLUGIN_NAMES,
            "images": {
                "plugin": PLUGIN_IMAGE,
                "gateway": GATEWAY_IMAGE,
                "hostDiagnosticsRunner": os.getenv("KOMSCO_AIOPS_HOST_DIAGNOSTICS_RUNNER_IMAGE", GATEWAY_IMAGE),
            },
            "capabilities": {
                "diagnostics": os.getenv("KOMSCO_AIOPS_ENABLE_DIAGNOSTICS", "true").lower() == "true",
                "mutations": os.getenv("KOMSCO_AIOPS_ENABLE_MUTATIONS", "true").lower() == "true",
                "unrestrictedCommands": os.getenv("KOMSCO_AIOPS_ENABLE_UNRESTRICTED_COMMANDS", "true").lower() == "true",
            },
            "rag": {
                "embeddingProvider": RAG_EMBEDDING_PROVIDER,
                "embeddingApiStyle": RAG_EMBEDDING_API_STYLE,
                "embeddingBaseUrl": RAG_EMBEDDING_BASE_URL,
                "embeddingModel": RAG_EMBEDDING_MODEL,
                "embeddingTimeoutSeconds": RAG_EMBEDDING_TIMEOUT_SECONDS,
                "vectorDimensions": RAG_VECTOR_DIMENSIONS,
            },
        },
    }


def annotations() -> dict[str, Any]:
    return {
        "annotations": {
            "operators.operatorframework.io.bundle.mediatype.v1": "registry+v1",
            "operators.operatorframework.io.bundle.manifests.v1": "manifests/",
            "operators.operatorframework.io.bundle.metadata.v1": "metadata/",
            "operators.operatorframework.io.bundle.package.v1": PACKAGE_NAME,
            "operators.operatorframework.io.bundle.channels.v1": CHANNEL,
            "operators.operatorframework.io.bundle.channel.default.v1": CHANNEL,
        }
    }


def main() -> None:
    if GENERATED_DIR.exists():
        shutil.rmtree(GENERATED_DIR)

    write_json(BUNDLE_DIR / "manifests" / "aiopsinstallations.aiops.komsco.io.crd.yaml", crd())
    write_json(BUNDLE_DIR / "manifests" / f"{CSV_NAME}.clusterserviceversion.yaml", csv())
    write_json(BUNDLE_DIR / "metadata" / "annotations.yaml", annotations())
    write_json(CATALOG_DIR / "00-catalog-configmap.yaml", catalog_configmap())
    write_json(CATALOG_DIR / "01-catalogsource.yaml", catalog_source())
    write_json(INSTALL_DIR / "00-namespace.yaml", namespace_resource())
    write_json(INSTALL_DIR / "01-operatorgroup.yaml", operator_group())
    write_json(INSTALL_DIR / "02-subscription.yaml", subscription())
    write_json(INSTALL_DIR / "03-aiopsinstallation.yaml", aiops_installation())
    print(f"Generated OLM package under {GENERATED_DIR}")
    print(f"CSV: {CSV_NAME}")
    print(f"CatalogSource: {CATALOG_NAMESPACE}/{CATALOG_NAME}")
    print(f"Subscription namespace: {INSTALL_NAMESPACE}")


if __name__ == "__main__":
    main()
