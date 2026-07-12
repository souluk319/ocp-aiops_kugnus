#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

export KOMSCO_AIOPS_PACKAGE_NAME="${KOMSCO_AIOPS_PACKAGE_NAME:-cywell-aiops}"
export KOMSCO_AIOPS_OPERATOR_NAME="${KOMSCO_AIOPS_OPERATOR_NAME:-cywell-aiops-operator}"
export KOMSCO_AIOPS_INSTALLATION_NAME="${KOMSCO_AIOPS_INSTALLATION_NAME:-cywell-aiops}"
export KOMSCO_AIOPS_OLM_CATALOG_NAME="${KOMSCO_AIOPS_OLM_CATALOG_NAME:-cywell-aiops-catalog}"
export KOMSCO_AIOPS_DISPLAY_NAME="${KOMSCO_AIOPS_DISPLAY_NAME:-AIOps}"
export KOMSCO_AIOPS_CATALOG_DISPLAY_NAME="${KOMSCO_AIOPS_CATALOG_DISPLAY_NAME:-AIOps Catalog}"
export KOMSCO_AIOPS_OPERATOR_NAMESPACE="${KOMSCO_AIOPS_OPERATOR_NAMESPACE:-cywell-aiops}"
export KOMSCO_AIOPS_NAMESPACE="${KOMSCO_AIOPS_NAMESPACE:-cywell-aiops}"
export KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME="${KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME:-cywell-aiops-console-plugin}"
export KOMSCO_AIOPS_CONSOLE_PLUGIN_DISPLAY_NAME="${KOMSCO_AIOPS_CONSOLE_PLUGIN_DISPLAY_NAME:-AIOps}"
export KOMSCO_AIOPS_MODE="${KOMSCO_AIOPS_MODE:-evidence-check}"
export KOMSCO_AIOPS_ENABLE_MUTATIONS="${KOMSCO_AIOPS_ENABLE_MUTATIONS:-false}"
export KOMSCO_AIOPS_ENABLE_UNRESTRICTED_COMMANDS="${KOMSCO_AIOPS_ENABLE_UNRESTRICTED_COMMANDS:-false}"
export KOMSCO_AIOPS_INSTALL_PLAN_APPROVAL="${KOMSCO_AIOPS_INSTALL_PLAN_APPROVAL:-Manual}"
export KOMSCO_AIOPS_REPLACES_CSV="${KOMSCO_AIOPS_REPLACES_CSV:-cywell-aiops-operator.v0.1.14}"
export KOMSCO_AIOPS_STANDALONE_HOST="${KOMSCO_AIOPS_STANDALONE_HOST:-aiops.cywell.co.kr}"
export KOMSCO_AIOPS_STANDALONE_TLS_SECRET="${KOMSCO_AIOPS_STANDALONE_TLS_SECRET:-cywell-aiops-route-tls}"
export KOMSCO_AIOPS_STANDALONE_OAUTH_CLIENT="${KOMSCO_AIOPS_STANDALONE_OAUTH_CLIENT:-cywell-aiops-standalone}"
export KOMSCO_AIOPS_ICON_FILE="${KOMSCO_AIOPS_ICON_FILE:-komsco-ai-console-plugin/src/assets/aiops_icon.png}"
export KOMSCO_AIOPS_ICON_MEDIA_TYPE="${KOMSCO_AIOPS_ICON_MEDIA_TYPE:-image/png}"
export KOMSCO_AIOPS_IMAGE_BUILD_STRATEGY="${KOMSCO_AIOPS_IMAGE_BUILD_STRATEGY:-openshift}"
export KOMSCO_AIOPS_FORCE_IMAGE_BUILD="${KOMSCO_AIOPS_FORCE_IMAGE_BUILD:-false}"
export KOMSCO_AIOPS_BOOTSTRAP_INSTALLATION="${KOMSCO_AIOPS_BOOTSTRAP_INSTALLATION:-true}"
export KOMSCO_AIOPS_STATUS_MODE="${KOMSCO_AIOPS_STATUS_MODE:-local}"
export KOMSCO_AIOPS_APPROVE_IMAGES="${KOMSCO_AIOPS_APPROVE_IMAGES:-}"
export KOMSCO_AIOPS_APPROVE_PUBLISH="${KOMSCO_AIOPS_APPROVE_PUBLISH:-}"
export KOMSCO_AIOPS_APPROVE_INSTALL="${KOMSCO_AIOPS_APPROVE_INSTALL:-}"
export KOMSCO_AIOPS_APPROVE_INSTALL_PLAN="${KOMSCO_AIOPS_APPROVE_INSTALL_PLAN:-}"
export KOMSCO_AIOPS_APPROVE_UNINSTALL="${KOMSCO_AIOPS_APPROVE_UNINSTALL:-}"
export KOMSCO_AIOPS_COMPANY_SERVER="${KOMSCO_AIOPS_COMPANY_SERVER:-https://api.ocp.cywell.server:6443}"

usage() {
  cat <<EOF
Usage: $0 <command>

Commands:
  package   Generate and verify AIOps OLM package locally.
  preflight Verify company cluster identity and singleton AIOps installation state.
  images    Build and push AIOps images after explicit approval.
  publish   Build/push images, then register only the AIOps CatalogSource after explicit approval.
  install   Install AIOps Subscription and AIOpsInstallation after explicit approval.
  approve-install
            Approve the reviewed Manual InstallPlan and complete the rollout.
  uninstall Remove only AIOps catalog/install/runtime resources after explicit approval.
  status    Show local package readiness by default. Set KOMSCO_AIOPS_STATUS_MODE=cluster for cluster reads.

Image build strategies:
  openshift  Use OpenShift BuildConfig binary builds and internal registry only.
  local      Use local docker/podman build and external registry push only.
  auto       Try local docker/podman push first, then OpenShift binary build fallback.

Set KOMSCO_AIOPS_FORCE_IMAGE_BUILD=true to rebuild existing AIOps image tags.
Set KOMSCO_AIOPS_APPROVE_IMAGES=cywell-aiops before image builds.
Set KOMSCO_AIOPS_APPROVE_PUBLISH=cywell-aiops before CatalogSource registration.
EOF
}

resolve_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    echo "${PYTHON_BIN}"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return
  fi
  echo "python3 or python CLI is required." >&2
  exit 1
}

load_release_image_env() {
  local line key value
  while IFS='=' read -r key value; do
    if [[ -n "${key}" && -n "${value}" ]]; then
      export "${key}=${value}"
    fi
  done < <("${ROOT_DIR}/scripts/olm-release-images.sh" env)
}

set_default_image_env() {
  local version=${KOMSCO_AIOPS_OPERATOR_VERSION:-0.1.17}
  local pull_registry=${KOMSCO_AIOPS_PULL_REGISTRY:-image-registry.openshift-image-registry.svc:5000}

  export KOMSCO_AIOPS_OPERATOR_IMAGE="${KOMSCO_AIOPS_OPERATOR_IMAGE:-${pull_registry}/${KOMSCO_AIOPS_NAMESPACE}/komsco-ai-gateway:${version}}"
  export KOMSCO_AIOPS_GATEWAY_IMAGE="${KOMSCO_AIOPS_GATEWAY_IMAGE:-${pull_registry}/${KOMSCO_AIOPS_NAMESPACE}/komsco-ai-gateway:${version}}"
  export KOMSCO_AIOPS_PLUGIN_IMAGE="${KOMSCO_AIOPS_PLUGIN_IMAGE:-${pull_registry}/${KOMSCO_AIOPS_NAMESPACE}/komsco-ai-console-plugin:${version}}"
  export KOMSCO_AIOPS_STANDALONE_IMAGE="${KOMSCO_AIOPS_STANDALONE_IMAGE:-${pull_registry}/${KOMSCO_AIOPS_NAMESPACE}/komsco-ai-standalone:${version}}"
}

validate_aiops_safety() {
  if [[ "${KOMSCO_AIOPS_PACKAGE_NAME}" != "cywell-aiops" ]]; then
    echo "Refusing non-AIOps package name: ${KOMSCO_AIOPS_PACKAGE_NAME}" >&2
    exit 1
  fi

  if [[ "${KOMSCO_AIOPS_OLM_CATALOG_NAME}" != "cywell-aiops-catalog" ]]; then
    echo "Refusing non-AIOps catalog name: ${KOMSCO_AIOPS_OLM_CATALOG_NAME}" >&2
    exit 1
  fi

  if [[ "${KOMSCO_AIOPS_OPERATOR_NAME}" != "cywell-aiops-operator" ]]; then
    echo "Refusing non-AIOps operator name: ${KOMSCO_AIOPS_OPERATOR_NAME}" >&2
    exit 1
  fi

  if [[ "${KOMSCO_AIOPS_INSTALLATION_NAME}" != "cywell-aiops" ]]; then
    echo "Refusing non-AIOps AIOpsInstallation name: ${KOMSCO_AIOPS_INSTALLATION_NAME}" >&2
    exit 1
  fi

  if [[ "${KOMSCO_AIOPS_BOOTSTRAP_INSTALLATION}" != "true" ]]; then
    echo "Refusing AIOps package without bootstrap install. Catalog install must create AIOpsInstallation." >&2
    exit 1
  fi

  case "${KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME}" in
    komsco-ai-console-plugin|lightspeed-console-plugin)
      echo "Refusing protected ConsolePlugin name for AIOps: ${KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME}" >&2
      exit 1
      ;;
  esac

  if [[ "${KOMSCO_AIOPS_NAMESPACE}" != "cywell-aiops" || "${KOMSCO_AIOPS_OPERATOR_NAMESPACE}" != "cywell-aiops" ]]; then
    echo "Refusing non-AIOps namespace. Set both namespace values to cywell-aiops." >&2
    exit 1
  fi
}

verify_package() {
  local python_bin
  python_bin=$(resolve_python)
  ROOT_DIR="${ROOT_DIR}" "${python_bin}" - <<'PY'
import base64
import hashlib
import json
import os
from pathlib import Path

root = Path(os.environ["ROOT_DIR"])
csv_name = f"{os.environ['KOMSCO_AIOPS_OPERATOR_NAME']}.v{os.environ.get('KOMSCO_AIOPS_OPERATOR_VERSION', '0.1.17')}"
csv_path = root / "olm" / "generated" / "bundle" / "manifests" / f"{csv_name}.clusterserviceversion.yaml"
crd_path = root / "olm" / "generated" / "bundle" / "manifests" / "aiopsinstallations.aiops.komsco.io.crd.yaml"
catalog_path = root / "olm" / "generated" / "catalog" / "01-catalogsource.yaml"
configmap_path = root / "olm" / "generated" / "catalog" / "00-catalog-configmap.yaml"
install_path = root / "olm" / "generated" / "install" / "03-aiopsinstallation.yaml"
subscription_path = root / "olm" / "generated" / "install" / "02-subscription.yaml"
deploy_script_path = root / "scripts" / "olm-deploy.sh"
icon_path = root / os.environ["KOMSCO_AIOPS_ICON_FILE"]
console_extensions_path = root / "komsco-ai-console-plugin" / "console-extensions.json"
console_plugin_package_path = root / "komsco-ai-console-plugin" / "package.json"
use_open_aiops_path = root / "komsco-ai-console-plugin" / "src" / "hooks" / "useOpenAIOps.tsx"
expected_conditions = {
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
    "StandalonePortalReady",
    "StandaloneRouteReady",
    "StandaloneOAuthReady",
    "ApplicationLauncherReady",
}
version = os.environ.get("KOMSCO_AIOPS_OPERATOR_VERSION", "0.1.17")
expected_version_scope = os.environ.get("KOMSCO_AIOPS_VERSION_SCOPE", f"Ver.{version}")

csv_payload = json.loads(csv_path.read_text(encoding="utf-8"))
crd_payload = json.loads(crd_path.read_text(encoding="utf-8"))
catalog_payload = json.loads(catalog_path.read_text(encoding="utf-8"))
configmap_payload = json.loads(configmap_path.read_text(encoding="utf-8"))
install_payload = json.loads(install_path.read_text(encoding="utf-8"))
subscription_payload = json.loads(subscription_path.read_text(encoding="utf-8"))
console_extensions = json.loads(console_extensions_path.read_text(encoding="utf-8"))
console_plugin_package = json.loads(console_plugin_package_path.read_text(encoding="utf-8"))
use_open_aiops_source = use_open_aiops_path.read_text(encoding="utf-8")
package_payload = json.loads(configmap_payload["data"]["packages"])[0]
example_payload = json.loads(csv_payload["metadata"]["annotations"]["alm-examples"])[0]
deploy_script = deploy_script_path.read_text(encoding="utf-8")
icon = csv_payload["spec"]["icon"][0]
decoded_icon = base64.b64decode(icon["base64data"])
status_schema = crd_payload["spec"]["versions"][0]["schema"]["openAPIV3Schema"]["properties"]["status"]["properties"]
container_env = {
    env["name"]: env["value"]
    for deployment in csv_payload["spec"]["install"]["spec"]["deployments"]
    for container in deployment["spec"]["template"]["spec"]["containers"]
    for env in container["env"]
}
cluster_rules = [
    rule
    for permission in csv_payload["spec"]["install"]["spec"].get("clusterPermissions", [])
    for rule in permission.get("rules", [])
]
related_images = {
    item.get("name"): item.get("image")
    for item in csv_payload["spec"].get("relatedImages", [])
}


def has_cluster_rule(api_group, resource, required_verbs):
    return any(
        api_group in rule.get("apiGroups", [])
        and resource in rule.get("resources", [])
        and set(required_verbs).issubset(set(rule.get("verbs", [])))
        for rule in cluster_rules
    )


def has_named_delete_rule(api_group, resource, resource_name):
    return any(
        api_group in rule.get("apiGroups", [])
        and resource in rule.get("resources", [])
        and resource_name in rule.get("resourceNames", [])
        and "delete" in rule.get("verbs", [])
        for rule in cluster_rules
    )


readiness_annotation = {
    item.strip()
    for item in csv_payload["metadata"]["annotations"].get("aiops.komsco.io/readiness-conditions", "").split(",")
    if item.strip()
}
readiness_env = {
    item.strip()
    for item in container_env.get("KOMSCO_AI_OPERATOR_READINESS_CONDITIONS", "").split(",")
    if item.strip()
}
console_section = next(
    (
        extension
        for extension in console_extensions
        if extension.get("type") == "console.navigation/section"
        and extension.get("properties", {}).get("id") == "cywell-aiops"
    ),
    {},
)
console_dashboard_href = next(
    (
        extension
        for extension in console_extensions
        if extension.get("type") == "console.navigation/href"
        and extension.get("properties", {}).get("id") == "cywell-aiops-dashboard"
    ),
    {},
)
console_context_provider = next(
    (
        extension
        for extension in console_extensions
        if extension.get("type") == "console.context-provider"
        and extension.get("properties", {}).get("useValueHook", {}).get("$codeRef") == "useAssistantOverlay"
    ),
    {},
)
console_lightspeed_flag = next(
    (
        extension
        for extension in console_extensions
        if extension.get("type") == "console.flag"
        and extension.get("properties", {}).get("handler", {}).get("$codeRef") == "AIOpsFlags.enableLightspeedPluginFlag"
    ),
    {},
)
console_action_provider = next(
    (
        extension
        for extension in console_extensions
        if extension.get("type") == "console.action/provider"
        and extension.get("properties", {}).get("contextId") == "ols-open-handler"
    ),
    {},
)
exposed_modules = console_plugin_package.get("consolePlugin", {}).get("exposedModules", {})
visible_catalog_copy = "\n".join(
    [
        str(catalog_payload["spec"].get("displayName", "")),
        str(catalog_payload["spec"].get("publisher", "")),
        str(csv_payload["spec"].get("displayName", "")),
        str(csv_payload["spec"].get("description", "")),
        str(csv_payload["spec"].get("provider", {}).get("name", "")),
        str(csv_payload["metadata"]["annotations"].get("description", "")),
        " ".join(str(link.get("name", "")) for link in csv_payload["spec"].get("links", [])),
    ]
).lower()

checks = {
    "displayName": csv_payload["spec"]["displayName"] == os.environ["KOMSCO_AIOPS_DISPLAY_NAME"],
    "catalogDisplayName": catalog_payload["spec"]["displayName"] == os.environ["KOMSCO_AIOPS_CATALOG_DISPLAY_NAME"],
    "providerName": csv_payload["spec"]["provider"]["name"] == os.environ.get("KOMSCO_AIOPS_PROVIDER_NAME", "Cywell"),
    "visibleCatalogCopyHasNoPersonalName": "kugnus" not in visible_catalog_copy,
    "catalogName": catalog_payload["metadata"]["name"] == os.environ["KOMSCO_AIOPS_OLM_CATALOG_NAME"],
    "packageName": package_payload["packageName"] == os.environ["KOMSCO_AIOPS_PACKAGE_NAME"],
    "csvName": csv_payload["metadata"]["name"].startswith(os.environ["KOMSCO_AIOPS_OPERATOR_NAME"] + ".v"),
    "bootstrapEnabled": container_env["KOMSCO_AI_OPERATOR_BOOTSTRAP_INSTALLATION"] == "true",
    "installationName": example_payload["metadata"]["name"] == os.environ["KOMSCO_AIOPS_INSTALLATION_NAME"],
    "installManifestName": install_payload["metadata"]["name"] == os.environ["KOMSCO_AIOPS_INSTALLATION_NAME"],
    "installManifestNamespace": install_payload["metadata"]["namespace"] == os.environ["KOMSCO_AIOPS_OPERATOR_NAMESPACE"],
    "installManifestTargetNamespace": install_payload["spec"]["targetNamespace"] == os.environ["KOMSCO_AIOPS_NAMESPACE"],
    "consolePluginName": example_payload["spec"]["consolePluginName"] == os.environ["KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME"],
    "installConsolePluginName": install_payload["spec"]["consolePluginName"] == os.environ["KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME"],
    "consolePluginDisplayName": example_payload["spec"]["consolePluginDisplayName"] == os.environ["KOMSCO_AIOPS_CONSOLE_PLUGIN_DISPLAY_NAME"],
    "disabledConsolePluginNames": example_payload["spec"]["disabledConsolePluginNames"] == ["komsco-ai-console-plugin", "lightspeed-console-plugin"],
    "installDisabledConsolePluginNames": install_payload["spec"]["disabledConsolePluginNames"] == ["komsco-ai-console-plugin", "lightspeed-console-plugin"],
    "disabledConsolePluginEnv": container_env["KOMSCO_AI_DEFAULT_DISABLED_CONSOLE_PLUGIN_NAMES"] == "komsco-ai-console-plugin,lightspeed-console-plugin",
    "mode": example_payload["spec"]["mode"] == "evidence-check",
    "installMode": install_payload["spec"]["mode"] == "evidence-check",
    "mutations": example_payload["spec"]["capabilities"]["mutations"] is False,
    "installMutations": install_payload["spec"]["capabilities"]["mutations"] is False,
    "unrestricted": example_payload["spec"]["capabilities"]["unrestrictedCommands"] is False,
    "installUnrestricted": install_payload["spec"]["capabilities"]["unrestrictedCommands"] is False,
    "installDiagnosticsDefault": install_payload["spec"]["capabilities"]["diagnostics"] is True,
    "manualInstallPlan": subscription_payload["spec"]["installPlanApproval"] == "Manual",
    "replacesInstalledCsv": csv_payload["spec"].get("replaces") == "cywell-aiops-operator.v0.1.14",
    "standaloneEnabled": install_payload["spec"]["standalonePortal"]["enabled"] is True,
    "standaloneHost": install_payload["spec"]["standalonePortal"]["host"] == "aiops.cywell.co.kr",
    "standaloneTlsSecret": install_payload["spec"]["standalonePortal"]["tlsSecretName"] == "cywell-aiops-route-tls",
    "standaloneImage": install_payload["spec"]["images"]["standalonePortal"].endswith(":0.1.17"),
    "oauthProxyImage": bool(install_payload["spec"]["images"]["oauthProxy"]),
    "routeRbac": has_cluster_rule(
        "route.openshift.io", "routes", {"create", "get", "patch", "update", "watch"}
    ),
    "oauthClientRbac": has_cluster_rule(
        "oauth.openshift.io", "oauthclients", {"create", "get", "patch", "update", "watch"}
    ),
    "actionExecutorDeploymentCleanupRbac": has_named_delete_rule(
        "apps", "deployments", "komsco-ai-action-executor"
    ),
    "actionExecutorSecretCleanupRbac": has_named_delete_rule(
        "", "secrets", "komsco-ai-action-executor-auth"
    ),
    "actionExecutorClusterRoleCleanupRbac": has_named_delete_rule(
        "rbac.authorization.k8s.io",
        "clusterroles",
        "cywell-aiops-console-plugin-action-executor",
    ),
    "relatedStandaloneImage": related_images.get("standalone-portal")
    == install_payload["spec"]["images"]["standalonePortal"],
    "relatedOauthProxyImage": related_images.get("oauth-proxy")
    == install_payload["spec"]["images"]["oauthProxy"],
    "statusConditionsSchema": "conditions" in status_schema,
    "statusComponentsSchema": "components" in status_schema,
    "statusVersionScopeSchema": "versionScope" in status_schema,
    "readinessAnnotation": readiness_annotation == expected_conditions,
    "readinessEnv": readiness_env == expected_conditions,
    "versionScopeAnnotation": csv_payload["metadata"]["annotations"].get("aiops.komsco.io/version-scope") == expected_version_scope,
    "versionScopeEnv": container_env.get("KOMSCO_AI_OPERATOR_VERSION_SCOPE") == expected_version_scope,
    "waitMutationsGuarded": 'bool_enabled "${ENABLE_MUTATIONS}"' in deploy_script
    and "komsco-ai-action-executor" in deploy_script,
    "waitDiagnosticsGuarded": 'bool_enabled "${ENABLE_DIAGNOSTICS}"' in deploy_script
    and "komsco-ai-host-diagnostics-controller" in deploy_script,
    "clusterWriteGuard": "KOMSCO_AIOPS_APPROVE_CLUSTER_WRITE=cywell-aiops" in deploy_script,
    "iconMediaType": icon["mediatype"] == "image/png",
    "iconSha256": hashlib.sha256(decoded_icon).hexdigest() == hashlib.sha256(icon_path.read_bytes()).hexdigest(),
    "consolePluginPackageName": console_plugin_package.get("consolePlugin", {}).get("name") == os.environ["KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME"],
    "consolePluginPackageDisplayName": console_plugin_package.get("consolePlugin", {}).get("displayName") == os.environ["KOMSCO_AIOPS_CONSOLE_PLUGIN_DISPLAY_NAME"],
    "consoleNavSection": console_section.get("properties", {}).get("name") == "AIOps",
    "consoleNavAfterAdministration": console_section.get("properties", {}).get("insertAfter") == "administration",
    "consoleDashboardRoute": console_dashboard_href.get("properties", {}).get("href") == "/dashboards/aiops",
    "consoleContextProvider": bool(console_context_provider),
    "consoleLightspeedFlag": bool(console_lightspeed_flag),
    "consoleOlsOpenHandlerActionProvider": console_action_provider.get("properties", {}).get("provider", {}).get("$codeRef") == "useOpenAIOps",
    "consoleExposesAIOpsFlags": exposed_modules.get("AIOpsFlags") == "./hooks/aiopsFlags",
    "consoleExposesAssistantOverlay": exposed_modules.get("useAssistantOverlay") == "./hooks/useAssistantOverlay",
    "consoleExposesOpenAIOps": exposed_modules.get("useOpenAIOps") == "./hooks/useOpenAIOps",
    "openAIOpsReturnsCallback": "OpenAIOpsHandler" in use_open_aiops_source
    and "return React.useCallback" in use_open_aiops_source,
    "openAIOpsDoesNotReturnActionArray": "Action[]" not in use_open_aiops_source
    and "lib/extensions/actions" not in use_open_aiops_source,
    "openAIOpsLaunchesOverlay": "launchOverlay(AssistantOverlay" in use_open_aiops_source
    and "defaultOpen: true" in use_open_aiops_source,
}

failed = [name for name, passed in checks.items() if not passed]
if failed:
    raise SystemExit("AIOps package verification failed: " + ", ".join(failed))

print("AIOps package verification passed")
print(f"CSV: {csv_name}")
print(f"CatalogSource: {catalog_payload['metadata']['namespace']}/{catalog_payload['metadata']['name']}")
print(f"PackageManifest: {package_payload['packageName']}")
print(f"ConsolePlugin: {example_payload['spec']['consolePluginName']}")
print("Readiness conditions: " + ", ".join(sorted(expected_conditions)))
PY
}

package() {
  set_default_image_env
  "${ROOT_DIR}/scripts/olm-deploy.sh" package
  verify_package
}

require_oc() {
  if ! command -v oc >/dev/null 2>&1; then
    echo "oc CLI is required." >&2
    exit 1
  fi
}

require_company_server() {
  require_oc
  local server user
  server=$(oc whoami --show-server 2>/dev/null || true)
  if [[ "${server}" != "${KOMSCO_AIOPS_COMPANY_SERVER}" ]]; then
    echo "Refusing cluster write: oc server is ${server:-unavailable}, expected ${KOMSCO_AIOPS_COMPANY_SERVER}." >&2
    exit 1
  fi
  user=$(oc whoami 2>/dev/null || true)
  if [[ -z "${user}" ]]; then
    echo "Refusing cluster write: OpenShift authentication is expired or unavailable." >&2
    exit 1
  fi
}

verify_cluster_singleton() {
  require_company_server
  local unexpected_cr unexpected_subscription unexpected_csv unexpected_operator
  if oc get crd aiopsinstallations.aiops.komsco.io >/dev/null 2>&1; then
    unexpected_cr=$(oc get aiopsinstallation -A --no-headers \
      -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name 2>/dev/null \
      | awk '$1 != "cywell-aiops" || $2 != "cywell-aiops" { print }')
  else
    unexpected_cr=""
  fi
  unexpected_subscription=$(oc get subscription -A --no-headers \
    -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,PACKAGE:.spec.name 2>/dev/null \
    | awk '$3 == "cywell-aiops" && ($1 != "cywell-aiops" || $2 != "cywell-aiops") { print }')
  unexpected_csv=$(oc get csv -A --no-headers \
    -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name 2>/dev/null \
    | awk '$2 ~ /^cywell-aiops-operator\.v/ && $1 != "cywell-aiops" { print }')
  unexpected_operator=$(oc get deployment -A --no-headers \
    -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name 2>/dev/null \
    | awk '$2 == "cywell-aiops-operator" && $1 != "cywell-aiops" { print }')
  if [[ -n "${unexpected_cr}${unexpected_subscription}${unexpected_csv}${unexpected_operator}" ]]; then
    echo "Refusing deployment: duplicate AIOps installation detected outside cywell-aiops." >&2
    [[ -n "${unexpected_cr}" ]] && echo "Unexpected CR: ${unexpected_cr}" >&2
    [[ -n "${unexpected_subscription}" ]] && echo "Unexpected Subscription: ${unexpected_subscription}" >&2
    [[ -n "${unexpected_csv}" ]] && echo "Unexpected CSV: ${unexpected_csv}" >&2
    [[ -n "${unexpected_operator}" ]] && echo "Unexpected Operator: ${unexpected_operator}" >&2
    exit 1
  fi
  echo "AIOps singleton preflight passed: cywell-aiops is the only installation namespace."
}

ensure_manual_subscription_approval() {
  require_company_server
  if ! oc get subscription "${KOMSCO_AIOPS_PACKAGE_NAME}" \
    -n "${KOMSCO_AIOPS_OPERATOR_NAMESPACE}" >/dev/null 2>&1; then
    echo "No existing AIOps Subscription; Manual approval will be used at install time."
    return
  fi
  local approval
  approval=$(oc get subscription "${KOMSCO_AIOPS_PACKAGE_NAME}" \
    -n "${KOMSCO_AIOPS_OPERATOR_NAMESPACE}" \
    -o jsonpath='{.spec.installPlanApproval}')
  if [[ "${approval}" != "Manual" ]]; then
    echo "Locking existing Subscription to Manual before catalog publication."
    oc patch subscription "${KOMSCO_AIOPS_PACKAGE_NAME}" \
      -n "${KOMSCO_AIOPS_OPERATOR_NAMESPACE}" \
      --type merge -p '{"spec":{"installPlanApproval":"Manual"}}'
  fi
  approval=$(oc get subscription "${KOMSCO_AIOPS_PACKAGE_NAME}" \
    -n "${KOMSCO_AIOPS_OPERATOR_NAMESPACE}" \
    -o jsonpath='{.spec.installPlanApproval}')
  if [[ "${approval}" != "Manual" ]]; then
    echo "Refusing publish: existing Subscription is not locked to Manual approval." >&2
    exit 1
  fi
}

grant_image_pull_access() {
  require_oc
  oc policy add-role-to-group system:image-puller "system:serviceaccounts:${KOMSCO_AIOPS_NAMESPACE}" -n "${KOMSCO_AIOPS_NAMESPACE}"
}

patch_binary_build_output() {
  local name=$1
  oc patch buildconfig "${name}" -n "${KOMSCO_AIOPS_NAMESPACE}" --type=merge \
    -p "{\"spec\":{\"output\":{\"to\":{\"kind\":\"ImageStreamTag\",\"name\":\"${name}:${KOMSCO_AIOPS_OPERATOR_VERSION:-0.1.17}\"}}}}"
}

ensure_binary_build() {
  local name=$1
  local context_dir=$2
  local stage_dir
  local version=${KOMSCO_AIOPS_OPERATOR_VERSION:-0.1.17}

  require_oc
  oc get namespace "${KOMSCO_AIOPS_NAMESPACE}" >/dev/null 2>&1 || oc create namespace "${KOMSCO_AIOPS_NAMESPACE}"
  oc get imagestream "${name}" -n "${KOMSCO_AIOPS_NAMESPACE}" >/dev/null 2>&1 || oc create imagestream "${name}" -n "${KOMSCO_AIOPS_NAMESPACE}"

  if [[ "${KOMSCO_AIOPS_FORCE_IMAGE_BUILD}" != "true" ]] && oc get imagestreamtag "${name}:${version}" -n "${KOMSCO_AIOPS_NAMESPACE}" >/dev/null 2>&1; then
    echo "Using existing image stream tag ${KOMSCO_AIOPS_NAMESPACE}/${name}:${version}."
    return
  fi

  if oc get buildconfig "${name}" -n "${KOMSCO_AIOPS_NAMESPACE}" >/dev/null 2>&1; then
    patch_binary_build_output "${name}"
  else
    oc new-build --binary --strategy=docker --name="${name}" \
      --to="${name}:${version}" \
      -n "${KOMSCO_AIOPS_NAMESPACE}"
  fi

  stage_dir=$(prepare_build_context "${name}" "${context_dir}")
  oc start-build "${name}" -n "${KOMSCO_AIOPS_NAMESPACE}" --from-dir="${stage_dir}" --follow --wait
}

prepare_build_context() {
  local name=$1
  local context_dir=$2
  local build_root="${TMPDIR:-/tmp}/cywell-aiops-build"
  local stage_dir="${build_root}/${name}"

  case "${stage_dir}" in
    /tmp/cywell-aiops-build/*|/var/tmp/cywell-aiops-build/*)
      ;;
    *)
      echo "Refusing to clean unexpected build staging directory: ${stage_dir}" >&2
      exit 1
      ;;
  esac

  rm -rf "${stage_dir}"
  mkdir -p "${stage_dir}"
  tar -C "${context_dir}" \
    --exclude='./.git' \
    --exclude='./.cache' \
    --exclude='./.mypy_cache' \
    --exclude='./.nyc_output' \
    --exclude='./.parcel-cache' \
    --exclude='./node_modules' \
    --exclude='./dist' \
    --exclude='./integration-tests/screenshots' \
    --exclude='./integration-tests/videos' \
    --exclude='./integration-tests/downloads' \
    --exclude='./integration-tests/results' \
    --exclude='./integration-tests/reports' \
    --exclude='./.yarn/install-state.gz' \
    --exclude='./.venv' \
    --exclude='./__pycache__' \
    --exclude='./.pytest_cache' \
    --exclude='./.ruff_cache' \
    --exclude='./coverage' \
    --exclude='./htmlcov' \
    --exclude='./playwright-report' \
    --exclude='./test-results' \
    --exclude='./cypress/screenshots' \
    --exclude='./cypress/videos' \
    --exclude='./cypress/downloads' \
    --exclude='./.env' \
    --exclude='./.env.*' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='*.pyd' \
    --exclude='*.log' \
    --exclude='*.pid' \
    --exclude='*.tmp' \
    -cf - . | tar -C "${stage_dir}" -xf -
  echo "${stage_dir}"
}

openshift_images() {
  require_company_server
  echo "Building AIOps images with OpenShift binary builds in namespace ${KOMSCO_AIOPS_NAMESPACE}."
  ensure_binary_build "komsco-ai-gateway" "${ROOT_DIR}/komsco-ai-gateway"
  ensure_binary_build "komsco-ai-console-plugin" "${ROOT_DIR}/komsco-ai-console-plugin"
  ensure_binary_build "komsco-ai-standalone" "${ROOT_DIR}/komsco-ai-portal"
  grant_image_pull_access
  set_default_image_env
  echo "OpenShift binary image build completed."
  echo "KOMSCO_AIOPS_OPERATOR_IMAGE=${KOMSCO_AIOPS_OPERATOR_IMAGE}"
  echo "KOMSCO_AIOPS_GATEWAY_IMAGE=${KOMSCO_AIOPS_GATEWAY_IMAGE}"
  echo "KOMSCO_AIOPS_PLUGIN_IMAGE=${KOMSCO_AIOPS_PLUGIN_IMAGE}"
  echo "KOMSCO_AIOPS_STANDALONE_IMAGE=${KOMSCO_AIOPS_STANDALONE_IMAGE}"
}

local_images() {
  "${ROOT_DIR}/scripts/olm-release-images.sh" build-push
}

images() {
  if [[ "${KOMSCO_AIOPS_APPROVE_IMAGES}" != "cywell-aiops" ]]; then
    echo "Refusing image build/push. Re-run with KOMSCO_AIOPS_APPROVE_IMAGES=cywell-aiops after explicit approval." >&2
    exit 1
  fi
  case "${KOMSCO_AIOPS_IMAGE_BUILD_STRATEGY}" in
    local)
      local_images
      ;;
    openshift)
      openshift_images
      ;;
    auto)
      if local_images; then
        return
      fi
      echo "Local image build/push failed; falling back to OpenShift binary builds." >&2
      openshift_images
      ;;
    *)
      echo "Unknown KOMSCO_AIOPS_IMAGE_BUILD_STRATEGY: ${KOMSCO_AIOPS_IMAGE_BUILD_STRATEGY}" >&2
      exit 1
      ;;
  esac
}

publish() {
  if [[ "${KOMSCO_AIOPS_APPROVE_PUBLISH}" != "cywell-aiops" ]]; then
    echo "Refusing publish. Re-run with KOMSCO_AIOPS_APPROVE_PUBLISH=cywell-aiops after explicit approval." >&2
    exit 1
  fi
  require_company_server
  verify_cluster_singleton
  ensure_manual_subscription_approval
  export KOMSCO_AIOPS_APPROVE_IMAGES="cywell-aiops"
  export KOMSCO_AIOPS_APPROVE_CLUSTER_WRITE="cywell-aiops"
  images
  set_default_image_env
  "${ROOT_DIR}/scripts/olm-deploy.sh" catalog
}

install() {
  if [[ "${KOMSCO_AIOPS_APPROVE_INSTALL}" != "cywell-aiops" ]]; then
    echo "Refusing install. Re-run with KOMSCO_AIOPS_APPROVE_INSTALL=cywell-aiops after explicit approval." >&2
    exit 1
  fi
  require_company_server
  verify_cluster_singleton
  export KOMSCO_AIOPS_APPROVE_CLUSTER_WRITE="cywell-aiops"
  set_default_image_env
  "${ROOT_DIR}/scripts/olm-deploy.sh" install
}

approve_install() {
  if [[ "${KOMSCO_AIOPS_APPROVE_INSTALL_PLAN}" != "cywell-aiops" ]]; then
    echo "Refusing InstallPlan approval. Re-run with KOMSCO_AIOPS_APPROVE_INSTALL_PLAN=cywell-aiops after review." >&2
    exit 1
  fi
  require_company_server
  verify_cluster_singleton
  export KOMSCO_AIOPS_APPROVE_CLUSTER_WRITE="cywell-aiops"
  set_default_image_env
  "${ROOT_DIR}/scripts/olm-deploy.sh" approve-install
}

uninstall() {
  if [[ "${KOMSCO_AIOPS_APPROVE_UNINSTALL}" != "cywell-aiops" ]]; then
    echo "Refusing uninstall. Re-run with KOMSCO_AIOPS_APPROVE_UNINSTALL=cywell-aiops after explicit approval." >&2
    exit 1
  fi
  require_company_server
  set_default_image_env
  export KOMSCO_AIOPS_APPROVE_UNINSTALL="cywell-aiops"
  "${ROOT_DIR}/scripts/olm-deploy.sh" uninstall
}

local_status() {
  package
  local python_bin
  python_bin=$(resolve_python)
  ROOT_DIR="${ROOT_DIR}" "${python_bin}" - <<'PY'
import json
import os
from pathlib import Path

root = Path(os.environ["ROOT_DIR"])
catalog_path = root / "olm" / "generated" / "catalog" / "01-catalogsource.yaml"
install_path = root / "olm" / "generated" / "install" / "03-aiopsinstallation.yaml"
csv_files = sorted((root / "olm" / "generated" / "bundle" / "manifests").glob("*.clusterserviceversion.yaml"))

catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
install = json.loads(install_path.read_text(encoding="utf-8"))
csv_payload = json.loads(csv_files[0].read_text(encoding="utf-8"))

print("# AIOps local OLM readiness")
print(f"CatalogSource manifest: {catalog['metadata']['namespace']}/{catalog['metadata']['name']}")
print(f"Package: {os.environ['KOMSCO_AIOPS_PACKAGE_NAME']}")
print(f"CSV: {csv_payload['metadata']['name']}")
print(f"Install namespace: {install['metadata']['namespace']}")
print(f"Target namespace: {install['spec']['targetNamespace']}")
print(f"ConsolePlugin: {install['spec']['consolePluginName']}")
print(f"Mode: {install['spec']['mode']}")
print("Cluster writes: not executed in local status mode")
PY
}

status() {
  case "${KOMSCO_AIOPS_STATUS_MODE}" in
    local)
      local_status
      return
      ;;
    cluster)
      ;;
    *)
      echo "Unknown KOMSCO_AIOPS_STATUS_MODE: ${KOMSCO_AIOPS_STATUS_MODE}. Use local or cluster." >&2
      exit 1
      ;;
  esac
  require_oc
  load_release_image_env
  "${ROOT_DIR}/scripts/olm-deploy.sh" status
  echo
  echo "# Existing protected ConsolePlugins"
  oc get consoleplugin komsco-ai-console-plugin lightspeed-console-plugin "${KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME}" -o wide 2>/dev/null || true
  echo
  echo "# Active console plugins"
  oc get console.operator.openshift.io cluster -o jsonpath='{.spec.plugins}{"\n"}' 2>/dev/null || true
}

command=${1:-}
validate_aiops_safety

case "${command}" in
  package)
    package
    ;;
  preflight)
    verify_cluster_singleton
    ;;
  images)
    images
    ;;
  publish)
    publish
    ;;
  install)
    install
    ;;
  approve-install)
    approve_install
    ;;
  uninstall)
    uninstall
    ;;
  status)
    status
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    echo "Unknown command: ${command}" >&2
    usage >&2
    exit 1
    ;;
esac
