#!/usr/bin/env python3
import base64
import json
import os
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIR = ROOT / "olm" / "generated"
BUNDLE_DIR = GENERATED_DIR / "bundle"
CATALOG_DIR = GENERATED_DIR / "catalog"
INSTALL_DIR = GENERATED_DIR / "install"

PACKAGE_NAME = os.getenv("KOMSCO_AIOPS_PACKAGE_NAME", "komsco-aiops")
OPERATOR_NAME = os.getenv("KOMSCO_AIOPS_OPERATOR_NAME", "komsco-aiops-operator")
CATALOG_NAME = os.getenv("KOMSCO_AIOPS_OLM_CATALOG_NAME", "komsco-aiops-catalog")
CATALOG_NAMESPACE = os.getenv("KOMSCO_AIOPS_OLM_CATALOG_NAMESPACE", "openshift-marketplace")
CHANNEL = os.getenv("KOMSCO_AIOPS_CHANNEL", "stable")
VERSION = os.getenv("KOMSCO_AIOPS_OPERATOR_VERSION", "0.1.1")
CSV_NAME = f"{OPERATOR_NAME}.v{VERSION}"
SKIPS_CSV = os.getenv("KOMSCO_AIOPS_SKIPS_CSV", "")
INSTALL_NAMESPACE = os.getenv("KOMSCO_AIOPS_OPERATOR_NAMESPACE", "komsco-ai")
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
DISPLAY_NAME = os.getenv("KOMSCO_AIOPS_DISPLAY_NAME", "KOMSCO AIOps")
PROVIDER_NAME = os.getenv("KOMSCO_AIOPS_PROVIDER_NAME", "Cywell")
CATALOG_DISPLAY_NAME = os.getenv("KOMSCO_AIOPS_CATALOG_DISPLAY_NAME", f"{DISPLAY_NAME} Catalog")
CATALOG_PUBLISHER = os.getenv("KOMSCO_AIOPS_CATALOG_PUBLISHER", PROVIDER_NAME)
MAINTAINER_NAME = os.getenv("KOMSCO_AIOPS_MAINTAINER_NAME", f"{PROVIDER_NAME} Platform Team")
REPOSITORY_URL = os.getenv("KOMSCO_AIOPS_REPOSITORY_URL", "https://github.com/komsco/ocp-aiops")
DESCRIPTION = os.getenv(
    "KOMSCO_AIOPS_DESCRIPTION",
    f"{DISPLAY_NAME} provides an OpenShift console assistant, audit trail, policy views, action execution, and host diagnostics integration.",
)
SHORT_DESCRIPTION = os.getenv(
    "KOMSCO_AIOPS_SHORT_DESCRIPTION",
    f"{DISPLAY_NAME} (komsco-aiops) installs the OpenShift console assistant, gateway, action executor, and host diagnostics runtime.",
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


ICON_BASE64 = os.getenv("KOMSCO_AIOPS_ICON_BASE64", default_icon_base64())
ICON_MEDIA_TYPE = os.getenv("KOMSCO_AIOPS_ICON_MEDIA_TYPE", "image/svg+xml")


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
                                        "name": {"type": "string", "default": "komsco-aiops"},
                                        "targetNamespace": {"type": "string"},
                                        "createNamespace": {"type": "boolean", "default": True},
                                        "mode": {
                                            "type": "string",
                                            "enum": ["read-only", "execute", "unrestricted"],
                                            "default": "execute",
                                        },
                                        "pluginReplicas": {"type": "integer", "minimum": 1, "default": 2},
                                        "gatewayReplicas": {"type": "integer", "minimum": 1, "default": 1},
                                        "enableConsolePlugin": {"type": "boolean", "default": True},
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
                                    },
                                },
                                "status": {
                                    "type": "object",
                                    "properties": {
                                        "observedGeneration": {"type": "integer"},
                                        "phase": {"type": "string"},
                                        "message": {"type": "string"},
                                        "lastTransitionTime": {"type": "string"},
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
        {"apiGroups": ["console.openshift.io"], "resources": ["consoleplugins"], "verbs": ["create", "get", "list", "patch", "update", "watch"]},
        {"apiGroups": ["operator.openshift.io"], "resources": ["consoles"], "verbs": ["get", "patch", "update"]},
    ]


def csv() -> dict[str, Any]:
    labels = {"app.kubernetes.io/name": OPERATOR_NAME, "app.kubernetes.io/part-of": PACKAGE_NAME}
    skips = default_skips_csv()
    return {
        "apiVersion": "operators.coreos.com/v1alpha1",
        "kind": "ClusterServiceVersion",
        "metadata": {
            "name": CSV_NAME,
            "annotations": {
                "alm-examples": json.dumps([aiops_installation()], ensure_ascii=False),
                "capabilities": "Full Lifecycle",
                "categories": CATEGORIES,
                "containerImage": OPERATOR_IMAGE,
                "description": SHORT_DESCRIPTION,
                "repository": REPOSITORY_URL,
            },
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
            "links": [{"name": DISPLAY_NAME, "url": REPOSITORY_URL}],
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
                                                    {
                                                        "name": "KOMSCO_AI_OPERATOR_BOOTSTRAP_INSTALLATION",
                                                        "value": os.getenv("KOMSCO_AIOPS_BOOTSTRAP_INSTALLATION", "true"),
                                                    },
                                                    {"name": "KOMSCO_AI_DEFAULT_MODE", "value": os.getenv("KOMSCO_AIOPS_MODE", "execute")},
                                                    {"name": "KOMSCO_AI_DEFAULT_ENABLE_MUTATIONS", "value": os.getenv("KOMSCO_AIOPS_ENABLE_MUTATIONS", "true")},
                                                    {
                                                        "name": "KOMSCO_AI_DEFAULT_ENABLE_UNRESTRICTED_COMMANDS",
                                                        "value": os.getenv("KOMSCO_AIOPS_ENABLE_UNRESTRICTED_COMMANDS", "true"),
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
        "metadata": {"name": "komsco-aiops", "namespace": INSTALL_NAMESPACE},
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
        "metadata": {"name": "komsco-aiops", "namespace": INSTALL_NAMESPACE},
        "spec": {
            "targetNamespace": TARGET_NAMESPACE,
            "createNamespace": True,
            "mode": os.getenv("KOMSCO_AIOPS_MODE", "execute"),
            "pluginReplicas": int(os.getenv("KOMSCO_AIOPS_PLUGIN_REPLICAS", "2")),
            "gatewayReplicas": int(os.getenv("KOMSCO_AIOPS_GATEWAY_REPLICAS", "1")),
            "enableConsolePlugin": True,
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
