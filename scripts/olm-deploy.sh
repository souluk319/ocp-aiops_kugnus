#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
GENERATED_DIR="${ROOT_DIR}/olm/generated"
CATALOG_DIR="${GENERATED_DIR}/catalog"
INSTALL_DIR="${GENERATED_DIR}/install"
CATALOG_NAMESPACE=${KOMSCO_AIOPS_OLM_CATALOG_NAMESPACE:-openshift-marketplace}
CATALOG_NAME=${KOMSCO_AIOPS_OLM_CATALOG_NAME:-komsco-aiops-catalog-kugnus}
OPERATOR_NAMESPACE=${KOMSCO_AIOPS_OPERATOR_NAMESPACE:-komsco-ai-kugnus}
PACKAGE_NAME=${KOMSCO_AIOPS_PACKAGE_NAME:-komsco-aiops-kugnus}
OPERATOR_NAME=${KOMSCO_AIOPS_OPERATOR_NAME:-komsco-aiops-kugnus-operator}
INSTALLATION_NAME=${KOMSCO_AIOPS_INSTALLATION_NAME:-komsco-aiops-kugnus}
OPERATOR_VERSION=${KOMSCO_AIOPS_OPERATOR_VERSION:-0.1.8}
EXPECTED_CSV="${OPERATOR_NAME}.v${OPERATOR_VERSION}"
TARGET_NAMESPACE=${KOMSCO_AIOPS_NAMESPACE:-${OPERATOR_NAMESPACE}}
CONSOLE_PLUGIN_NAME=${KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME:-komsco-ai-console-plugin-kugnus}
DISPLAY_NAME=${KOMSCO_AIOPS_DISPLAY_NAME:-Cywell AIOps}
STATUS_MODE=${KOMSCO_AIOPS_STATUS_MODE:-local}
ENABLE_MUTATIONS=${KOMSCO_AIOPS_ENABLE_MUTATIONS:-false}
ENABLE_DIAGNOSTICS=${KOMSCO_AIOPS_ENABLE_DIAGNOSTICS:-true}
BOOTSTRAP_INSTALLATION=${KOMSCO_AIOPS_BOOTSTRAP_INSTALLATION:-true}
APPROVE_CLUSTER_WRITE=${KOMSCO_AIOPS_APPROVE_CLUSTER_WRITE:-}
APPROVE_UNINSTALL=${KOMSCO_AIOPS_APPROVE_UNINSTALL:-}
ACTION_EXECUTOR_CLUSTER_ROLE=${KOMSCO_AIOPS_ACTION_EXECUTOR_CLUSTER_ROLE:-${CONSOLE_PLUGIN_NAME}-action-executor}
ACTION_EXECUTOR_CLUSTER_ROLE_BINDING=${KOMSCO_AIOPS_ACTION_EXECUTOR_CLUSTER_ROLE_BINDING:-${CONSOLE_PLUGIN_NAME}-action-executor}
GATEWAY_AUTH_DELEGATOR_CLUSTER_ROLE_BINDING=${KOMSCO_AIOPS_GATEWAY_AUTH_DELEGATOR_CLUSTER_ROLE_BINDING:-${CONSOLE_PLUGIN_NAME}-gateway-auth-delegator}

usage() {
  cat <<EOF
Usage: $0 <command>

Commands:
  package     Generate OLM bundle, ConfigMap catalog, Subscription, and AIOpsInstallation manifests.
  deploy      One-shot OLM deployment after explicit cluster-write approval.
  catalog     Apply only the generated OLM CatalogSource resources after explicit approval.
  install     Apply only namespace, OperatorGroup, Subscription, and AIOpsInstallation after explicit approval.
  status      Show local generated package status by default. Set KOMSCO_AIOPS_STATUS_MODE=cluster for cluster reads.
  reset-install
              Remove installed operator/runtime/UI, but keep the OLM catalog for UI install tests.
  uninstall   Remove installed operator/runtime/UI and the OLM catalog resources.

Key environment variables:
  KOMSCO_AIOPS_OPERATOR_VERSION     Operator/CSV version. Default: 0.1.8
  KOMSCO_AIOPS_OPERATOR_IMAGE       Operator image. Default: gateway image
  KOMSCO_AIOPS_PLUGIN_IMAGE         Console plugin operand image
  KOMSCO_AIOPS_GATEWAY_IMAGE        Gateway/operator operand image
  KOMSCO_AIOPS_OPERATOR_NAMESPACE   Operator install namespace. Default: komsco-ai-kugnus
  KOMSCO_AIOPS_NAMESPACE            Operand target namespace. Default: operator namespace
  KOMSCO_AIOPS_MODE                 read-only, execute, or unrestricted. Default: read-only
  KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME  Cluster-scoped ConsolePlugin name.
  KOMSCO_AIOPS_BOOTSTRAP_INSTALLATION
                                      true creates AIOpsInstallation automatically after UI install.
  KOMSCO_AIOPS_APPROVE_CLUSTER_WRITE  Must equal komsco-ai-kugnus before catalog/install/deploy cluster writes.
  KOMSCO_AIOPS_STATUS_MODE            local or cluster. Default: local.
  KOMSCO_AIOPS_APPROVE_UNINSTALL      Must equal komsco-ai-kugnus before reset-install/uninstall.

Example:
  KOMSCO_AIOPS_OPERATOR_VERSION=0.1.8 \\
  KOMSCO_AIOPS_OPERATOR_IMAGE=registry.example/komsco-ai-gateway:0.1.8 \\
  KOMSCO_AIOPS_PLUGIN_IMAGE=registry.example/komsco-ai-console-plugin:0.1.8 \\
  KOMSCO_AIOPS_GATEWAY_IMAGE=registry.example/komsco-ai-gateway:0.1.8 \\
  task olm:deploy
EOF
}

bool_enabled() {
  [[ "${1,,}" == "true" ]]
}

validate_kugnus_safety() {
  if [[ "${PACKAGE_NAME}" != "komsco-aiops-kugnus" ]]; then
    echo "Refusing non-Kugnus package name: ${PACKAGE_NAME}" >&2
    exit 1
  fi
  if [[ "${CATALOG_NAME}" != "komsco-aiops-catalog-kugnus" ]]; then
    echo "Refusing non-Kugnus catalog name: ${CATALOG_NAME}" >&2
    exit 1
  fi
  if [[ "${OPERATOR_NAME}" != "komsco-aiops-kugnus-operator" ]]; then
    echo "Refusing non-Kugnus operator name: ${OPERATOR_NAME}" >&2
    exit 1
  fi
  if [[ "${INSTALLATION_NAME}" != "komsco-aiops-kugnus" ]]; then
    echo "Refusing non-Kugnus installation name: ${INSTALLATION_NAME}" >&2
    exit 1
  fi
  if [[ "${OPERATOR_NAMESPACE}" != "komsco-ai-kugnus" || "${TARGET_NAMESPACE}" != "komsco-ai-kugnus" ]]; then
    echo "Refusing non-Kugnus namespace. Set operator and target namespace to komsco-ai-kugnus." >&2
    exit 1
  fi
  case "${CONSOLE_PLUGIN_NAME}" in
    komsco-ai-console-plugin|lightspeed-console-plugin)
      echo "Refusing protected ConsolePlugin name: ${CONSOLE_PLUGIN_NAME}" >&2
      exit 1
      ;;
  esac
  if [[ "${BOOTSTRAP_INSTALLATION}" != "true" ]]; then
    echo "Refusing package without bootstrap install. Catalog install must create AIOpsInstallation." >&2
    exit 1
  fi
}

require_cluster_write_approval() {
  validate_kugnus_safety
  if [[ "${APPROVE_CLUSTER_WRITE}" != "komsco-ai-kugnus" ]]; then
    echo "Refusing cluster write. Re-run with KOMSCO_AIOPS_APPROVE_CLUSTER_WRITE=komsco-ai-kugnus after explicit approval." >&2
    exit 1
  fi
}

require_uninstall_approval() {
  validate_kugnus_safety
  if [[ "${APPROVE_UNINSTALL}" != "komsco-ai-kugnus" ]]; then
    echo "Refusing uninstall/reset. Re-run with KOMSCO_AIOPS_APPROVE_UNINSTALL=komsco-ai-kugnus after explicit approval." >&2
    exit 1
  fi
}

require_cmd() {
  local command_name=$1
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "${command_name} CLI is required." >&2
    exit 1
  fi
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

package_olm() {
  local python_bin
  python_bin=$(resolve_python)
  "${python_bin}" "${ROOT_DIR}/scripts/olm-package.py"
}

apply_catalog() {
  require_cmd oc
  oc apply -f "${CATALOG_DIR}"
  oc delete pod -n "${CATALOG_NAMESPACE}" -l "olm.catalogSource=${CATALOG_NAME}" --ignore-not-found
}

wait_catalog() {
  require_cmd oc
  echo "Waiting for PackageManifest ${PACKAGE_NAME} from ${CATALOG_NAME} to publish ${EXPECTED_CSV}..."
  for _ in $(seq 1 60); do
    catalog_state=$(oc get catalogsource "${CATALOG_NAME}" -n "${CATALOG_NAMESPACE}" -o jsonpath='{.status.connectionState.lastObservedState}' 2>/dev/null || true)
    current_csv=$(oc get packagemanifest "${PACKAGE_NAME}" -n "${CATALOG_NAMESPACE}" -o jsonpath='{.status.channels[?(@.name=="'"${KOMSCO_AIOPS_CHANNEL:-stable}"'")].currentCSV}' 2>/dev/null || true)
    if [[ "${catalog_state}" == "READY" && "${current_csv}" == "${EXPECTED_CSV}" ]]; then
      return
    fi
    sleep 5
  done
  echo "PackageManifest ${PACKAGE_NAME} did not publish ${EXPECTED_CSV} in ${CATALOG_NAMESPACE}." >&2
  oc get catalogsource "${CATALOG_NAME}" -n "${CATALOG_NAMESPACE}" -o yaml || true
  oc get pod -n "${CATALOG_NAMESPACE}" -l "olm.catalogSource=${CATALOG_NAME}" -o wide || true
  oc logs -n "${CATALOG_NAMESPACE}" -l "olm.catalogSource=${CATALOG_NAME}" --tail=120 || true
  oc get packagemanifest "${PACKAGE_NAME}" -n "${CATALOG_NAMESPACE}" -o yaml 2>/dev/null || true
  exit 1
}

apply_install() {
  require_cmd oc
  local operatorgroups operatorgroup_count
  oc apply -f "${INSTALL_DIR}/00-namespace.yaml"
  operatorgroups=$(oc get operatorgroup -n "${OPERATOR_NAMESPACE}" -o name 2>/dev/null | sed '/^$/d' || true)
  operatorgroup_count=$(printf '%s\n' "${operatorgroups}" | sed '/^$/d' | wc -l)
  if [[ "${operatorgroup_count}" == "0" ]]; then
    oc apply -f "${INSTALL_DIR}/01-operatorgroup.yaml"
  elif [[ "${operatorgroup_count}" == "1" ]]; then
    echo "Reusing existing OperatorGroup in ${OPERATOR_NAMESPACE}: ${operatorgroups}"
  else
    echo "Refusing install: multiple OperatorGroups already exist in ${OPERATOR_NAMESPACE}." >&2
    printf '%s\n' "${operatorgroups}" >&2
    exit 1
  fi
  oc apply -f "${INSTALL_DIR}/02-subscription.yaml"
  wait_subscription_csv
  oc apply -f "${INSTALL_DIR}/03-aiopsinstallation.yaml"
  wait_operands
}

wait_subscription_csv() {
  require_cmd oc
  echo "Waiting for Subscription ${OPERATOR_NAMESPACE}/${PACKAGE_NAME}..."
  for _ in $(seq 1 90); do
    csv_name=$(oc get subscription "${PACKAGE_NAME}" -n "${OPERATOR_NAMESPACE}" -o jsonpath='{.status.installedCSV}' 2>/dev/null || true)
    if [[ "${csv_name}" == "${EXPECTED_CSV}" ]]; then
      phase=$(oc get csv "${EXPECTED_CSV}" -n "${OPERATOR_NAMESPACE}" -o jsonpath='{.status.phase}' 2>/dev/null || true)
      if [[ "${phase}" == "Succeeded" ]]; then
        echo "CSV ${EXPECTED_CSV} is Succeeded."
        return
      fi
    fi
    sleep 5
  done
  echo "Subscription did not reach a Succeeded CSV." >&2
  oc get subscription "${PACKAGE_NAME}" -n "${OPERATOR_NAMESPACE}" -o yaml || true
  oc get csv -n "${OPERATOR_NAMESPACE}" || true
  exit 1
}

wait_operands() {
  require_cmd oc
  echo "Waiting for KOMSCO AIOps operands in ${TARGET_NAMESPACE}..."
  wait_deployment_rollout "${OPERATOR_NAMESPACE}" "${OPERATOR_NAME}" 180s
  wait_deployment_rollout "${TARGET_NAMESPACE}" komsco-ai-console-plugin 300s
  wait_deployment_rollout "${TARGET_NAMESPACE}" komsco-ai-gateway 300s
  if bool_enabled "${ENABLE_MUTATIONS}"; then
    wait_deployment_rollout "${TARGET_NAMESPACE}" komsco-ai-action-executor 300s
  else
    echo "Skipping action executor rollout wait because KOMSCO_AIOPS_ENABLE_MUTATIONS=${ENABLE_MUTATIONS}."
  fi
  if bool_enabled "${ENABLE_DIAGNOSTICS}"; then
    wait_deployment_rollout "${TARGET_NAMESPACE}" komsco-ai-host-diagnostics-controller 300s
  else
    echo "Skipping host diagnostics rollout wait because KOMSCO_AIOPS_ENABLE_DIAGNOSTICS=${ENABLE_DIAGNOSTICS}."
  fi
  oc get consoleplugin "${CONSOLE_PLUGIN_NAME}" >/dev/null
}

wait_deployment_rollout() {
  local namespace=$1
  local deployment=$2
  local timeout=$3
  echo "Waiting for Deployment ${namespace}/${deployment}..."
  for _ in $(seq 1 60); do
    if oc get deployment "${deployment}" -n "${namespace}" >/dev/null 2>&1; then
      oc rollout status deployment/"${deployment}" -n "${namespace}" --timeout="${timeout}"
      return
    fi
    sleep 5
  done
  echo "Deployment ${namespace}/${deployment} did not appear." >&2
  oc get aiopsinstallation -n "${OPERATOR_NAMESPACE}" -o yaml 2>/dev/null || true
  oc logs deployment/"${OPERATOR_NAME}" -n "${OPERATOR_NAMESPACE}" --tail=120 2>/dev/null || true
  exit 1
}

show_local_status() {
  package_olm
  local python_bin
  python_bin=$(resolve_python)
  ROOT_DIR="${ROOT_DIR}" \
  CATALOG_NAME="${CATALOG_NAME}" \
  CATALOG_NAMESPACE="${CATALOG_NAMESPACE}" \
  PACKAGE_NAME="${PACKAGE_NAME}" \
  OPERATOR_NAME="${OPERATOR_NAME}" \
  OPERATOR_VERSION="${OPERATOR_VERSION}" \
  INSTALLATION_NAME="${INSTALLATION_NAME}" \
  OPERATOR_NAMESPACE="${OPERATOR_NAMESPACE}" \
  TARGET_NAMESPACE="${TARGET_NAMESPACE}" \
  CONSOLE_PLUGIN_NAME="${CONSOLE_PLUGIN_NAME}" \
  "${python_bin}" - <<'PY'
import json
import os
from pathlib import Path

root = Path(os.environ["ROOT_DIR"])
csv_path = root / "olm" / "generated" / "bundle" / "manifests" / f"{os.environ['OPERATOR_NAME']}.v{os.environ['OPERATOR_VERSION']}.clusterserviceversion.yaml"
catalog_path = root / "olm" / "generated" / "catalog" / "01-catalogsource.yaml"
install_path = root / "olm" / "generated" / "install" / "03-aiopsinstallation.yaml"
csv_payload = json.loads(csv_path.read_text(encoding="utf-8"))
catalog_payload = json.loads(catalog_path.read_text(encoding="utf-8"))
install_payload = json.loads(install_path.read_text(encoding="utf-8"))
print("# Local OLM package status")
print(f"CatalogSource manifest: {catalog_payload['metadata']['namespace']}/{catalog_payload['metadata']['name']}")
print(f"Package: {os.environ['PACKAGE_NAME']}")
print(f"CSV: {csv_payload['metadata']['name']}")
print(f"Installation: {install_payload['metadata']['namespace']}/{install_payload['metadata']['name']}")
print(f"Target namespace: {install_payload['spec']['targetNamespace']}")
print(f"ConsolePlugin: {install_payload['spec']['consolePluginName']}")
print(f"Mode: {install_payload['spec']['mode']}")
print("Cluster reads/writes: not executed in local status mode")
PY
}

show_cluster_status() {
  require_cmd oc
  echo "# CatalogSource"
  oc get catalogsource "${CATALOG_NAME}" -n "${CATALOG_NAMESPACE}" -o wide --ignore-not-found
  echo
  echo "# PackageManifest"
  oc get packagemanifest "${PACKAGE_NAME}" -n "${CATALOG_NAMESPACE}" -o wide 2>/dev/null || true
  echo
  echo "# Subscription"
  oc get subscription "${PACKAGE_NAME}" -n "${OPERATOR_NAMESPACE}" -o wide --ignore-not-found
  echo
  echo "# CSV"
  oc get csv -n "${OPERATOR_NAMESPACE}" | grep "${OPERATOR_NAME}" || true
  echo
  echo "# AIOpsInstallation"
  oc get aiopsinstallation -n "${OPERATOR_NAMESPACE}" -o wide 2>/dev/null || true
  echo
  echo "# ConsolePlugin"
  oc get consoleplugin "${CONSOLE_PLUGIN_NAME}" -o wide --ignore-not-found
  echo
  echo "# Operands"
  oc get deploy,svc -n "${TARGET_NAMESPACE}" \
    -l 'app.kubernetes.io/part-of=komsco-aiops' 2>/dev/null || true
}

show_status() {
  case "${STATUS_MODE}" in
    local)
      show_local_status
      ;;
    cluster)
      validate_kugnus_safety
      show_cluster_status
      ;;
    *)
      echo "Unknown KOMSCO_AIOPS_STATUS_MODE: ${STATUS_MODE}. Use local or cluster." >&2
      exit 1
      ;;
  esac
}

uninstall_olm() {
  require_cmd oc
  reset_install
  oc delete -f "${CATALOG_DIR}" --ignore-not-found=true || true
}

reset_install() {
  require_cmd oc
  local install_namespaces
  install_namespaces=$(discover_operator_namespaces)
  for namespace in ${install_namespaces}; do
    remove_operator_install "${namespace}"
  done
  remove_aiops_runtime
}

remove_operator_install() {
  local namespace=${1:-${OPERATOR_NAMESPACE}}
  local csv_name
  csv_name=$(oc get subscription "${PACKAGE_NAME}" -n "${namespace}" -o jsonpath='{.status.installedCSV}' 2>/dev/null || true)
  oc delete subscription "${PACKAGE_NAME}" -n "${namespace}" --ignore-not-found
  if [[ -n "${csv_name}" ]]; then
    oc delete csv "${csv_name}" -n "${namespace}" --ignore-not-found
  fi
  csv_names=$(oc get csv -n "${namespace}" -o name 2>/dev/null | grep "/${OPERATOR_NAME}\\.v" || true)
  if [[ -n "${csv_names}" ]]; then
    printf '%s\n' "${csv_names}" | xargs -r oc delete -n "${namespace}" --ignore-not-found
  fi
  operator_groups=$(oc get operatorgroup -n "${namespace}" -o name 2>/dev/null | grep -E '/(komsco-aiops|default-)' || true)
  if [[ -n "${operator_groups}" ]]; then
    printf '%s\n' "${operator_groups}" | xargs -r oc delete -n "${namespace}" --ignore-not-found
  fi
  oc delete deployment "${OPERATOR_NAME}" -n "${namespace}" --ignore-not-found
}

discover_operator_namespaces() {
  {
    echo "${OPERATOR_NAMESPACE}"
    oc get subscription -A -o jsonpath='{range .items[?(@.metadata.name=="'"${PACKAGE_NAME}"'")]}{.metadata.namespace}{"\n"}{end}' 2>/dev/null || true
    oc get csv -A -o jsonpath='{range .items[?(@.spec.displayName=="'"${DISPLAY_NAME}"'")]}{.metadata.namespace}{"\n"}{end}' 2>/dev/null || true
    oc get deploy -A -l app=komsco-aiops-operator -o jsonpath='{range .items[*]}{.metadata.namespace}{"\n"}{end}' 2>/dev/null || true
  } | awk 'NF && !seen[$0]++'
}

remove_aiops_runtime() {
  disable_console_plugin
  for namespace in $(discover_aiopsinstallation_namespaces); do
  oc delete aiopsinstallation "${INSTALLATION_NAME}" -n "${namespace}" --ignore-not-found
  done
  oc delete consoleplugin "${CONSOLE_PLUGIN_NAME}" --ignore-not-found
  for namespace in $(discover_runtime_namespaces); do
    oc delete deploy,svc,sa,cm,role,rolebinding,networkpolicy -n "${namespace}" \
      -l 'app.kubernetes.io/part-of=komsco-aiops' --ignore-not-found
  done
  oc delete clusterrole "${ACTION_EXECUTOR_CLUSTER_ROLE}" --ignore-not-found
  oc delete clusterrolebinding \
    "${ACTION_EXECUTOR_CLUSTER_ROLE_BINDING}" \
    "${GATEWAY_AUTH_DELEGATOR_CLUSTER_ROLE_BINDING}" \
    --ignore-not-found
}

discover_runtime_namespaces() {
  {
    echo "${TARGET_NAMESPACE}"
    echo "${OPERATOR_NAMESPACE}"
    oc get deploy -A -l app.kubernetes.io/part-of=komsco-aiops -o jsonpath='{range .items[*]}{.metadata.namespace}{"\n"}{end}' 2>/dev/null || true
    oc get svc -A -l app.kubernetes.io/part-of=komsco-aiops -o jsonpath='{range .items[*]}{.metadata.namespace}{"\n"}{end}' 2>/dev/null || true
  } | awk 'NF && !seen[$0]++'
}

discover_aiopsinstallation_namespaces() {
  {
    echo "${OPERATOR_NAMESPACE}"
    oc get aiopsinstallation -A -o jsonpath='{range .items[?(@.metadata.name=="'"${INSTALLATION_NAME}"'")]}{.metadata.namespace}{"\n"}{end}' 2>/dev/null || true
  } | awk 'NF && !seen[$0]++'
}

disable_console_plugin() {
  local current_plugins patched_plugins python_bin
  python_bin=$(resolve_python)
  current_plugins=$(oc get consoles.operator.openshift.io cluster -o jsonpath='{.spec.plugins}' 2>/dev/null || echo "[]")
  patched_plugins=$(PLUGIN_NAME="${CONSOLE_PLUGIN_NAME}" CURRENT_PLUGINS="${current_plugins}" "${python_bin}" - <<'PY'
import json
import os

plugin_name = os.environ["PLUGIN_NAME"]
try:
    plugins = json.loads(os.environ.get("CURRENT_PLUGINS") or "[]")
except json.JSONDecodeError:
    plugins = []
if not isinstance(plugins, list):
    plugins = []
filtered = [plugin for plugin in plugins if plugin != plugin_name]
print(json.dumps({"spec": {"plugins": filtered}}))
PY
)
  oc patch consoles.operator.openshift.io cluster --type=merge -p "${patched_plugins}" >/dev/null
}

command=${1:-}
validate_kugnus_safety

case "${command}" in
  package)
    package_olm
    ;;
  catalog)
    package_olm
    require_cluster_write_approval
    apply_catalog
    wait_catalog
    ;;
  install)
    package_olm
    require_cluster_write_approval
    apply_install
    ;;
  deploy)
    package_olm
    require_cluster_write_approval
    apply_catalog
    wait_catalog
    apply_install
    ;;
  status)
    show_status
    ;;
  reset-install)
    require_uninstall_approval
    reset_install
    ;;
  uninstall)
    require_uninstall_approval
    uninstall_olm
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
