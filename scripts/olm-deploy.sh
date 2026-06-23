#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
GENERATED_DIR="${ROOT_DIR}/olm/generated"
CATALOG_DIR="${GENERATED_DIR}/catalog"
INSTALL_DIR="${GENERATED_DIR}/install"
CATALOG_NAMESPACE=${KOMSCO_AIOPS_OLM_CATALOG_NAMESPACE:-openshift-marketplace}
CATALOG_NAME=${KOMSCO_AIOPS_OLM_CATALOG_NAME:-komsco-aiops-catalog}
OPERATOR_NAMESPACE=${KOMSCO_AIOPS_OPERATOR_NAMESPACE:-komsco-ai}
PACKAGE_NAME=${KOMSCO_AIOPS_PACKAGE_NAME:-komsco-aiops}
OPERATOR_NAME=${KOMSCO_AIOPS_OPERATOR_NAME:-komsco-aiops-operator}
OPERATOR_VERSION=${KOMSCO_AIOPS_OPERATOR_VERSION:-0.1.1}
EXPECTED_CSV="${OPERATOR_NAME}.v${OPERATOR_VERSION}"
TARGET_NAMESPACE=${KOMSCO_AIOPS_NAMESPACE:-${OPERATOR_NAMESPACE}}

usage() {
  cat <<EOF
Usage: $0 <command>

Commands:
  package     Generate OLM bundle, ConfigMap catalog, Subscription, and AIOpsInstallation manifests.
  deploy      One-shot OLM deployment: package, catalog, subscription, CR, and rollout wait.
  catalog     Apply only the generated OLM CatalogSource resources.
  install     Apply only namespace, OperatorGroup, Subscription, and AIOpsInstallation.
  status      Show PackageManifest, Subscription, CSV, AIOpsInstallation, and operand rollout status.
  reset-install
              Remove installed operator/runtime/UI, but keep the OLM catalog for UI install tests.
  uninstall   Remove installed operator/runtime/UI and the OLM catalog resources.

Key environment variables:
  KOMSCO_AIOPS_OPERATOR_VERSION     Operator/CSV version. Default: 0.1.1
  KOMSCO_AIOPS_OPERATOR_IMAGE       Operator image. Default: gateway image
  KOMSCO_AIOPS_PLUGIN_IMAGE         Console plugin operand image
  KOMSCO_AIOPS_GATEWAY_IMAGE        Gateway/operator operand image
  KOMSCO_AIOPS_OPERATOR_NAMESPACE   Operator install namespace. Default: komsco-ai
  KOMSCO_AIOPS_NAMESPACE            Operand target namespace. Default: operator namespace
  KOMSCO_AIOPS_MODE                 read-only, execute, or unrestricted. Default: execute
  KOMSCO_AIOPS_BOOTSTRAP_INSTALLATION
                                      true creates AIOpsInstallation automatically after UI install.

Example:
  KOMSCO_AIOPS_OPERATOR_VERSION=0.1.1 \\
  KOMSCO_AIOPS_OPERATOR_IMAGE=registry.example/komsco-ai-gateway:0.1.1 \\
  KOMSCO_AIOPS_PLUGIN_IMAGE=registry.example/komsco-ai-console-plugin:0.1.1 \\
  KOMSCO_AIOPS_GATEWAY_IMAGE=registry.example/komsco-ai-gateway:0.1.1 \\
  task olm:deploy
EOF
}

require_cmd() {
  local command_name=$1
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "${command_name} CLI is required." >&2
    exit 1
  fi
}

package_olm() {
  require_cmd python3
  python3 "${ROOT_DIR}/scripts/olm-package.py"
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
  oc apply -f "${INSTALL_DIR}/00-namespace.yaml"
  oc apply -f "${INSTALL_DIR}/01-operatorgroup.yaml"
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
  wait_deployment_rollout "${TARGET_NAMESPACE}" komsco-ai-action-executor 300s
  wait_deployment_rollout "${TARGET_NAMESPACE}" komsco-ai-host-diagnostics-controller 300s
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

show_status() {
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
  echo "# Operands"
  oc get deploy,svc,consoleplugin -n "${TARGET_NAMESPACE}" \
    -l 'app.kubernetes.io/part-of=komsco-aiops' 2>/dev/null || true
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
    oc get csv -A -o jsonpath='{range .items[?(@.spec.displayName=="KOMSCO AIOps")]}{.metadata.namespace}{"\n"}{end}' 2>/dev/null || true
    oc get deploy -A -l app=komsco-aiops-operator -o jsonpath='{range .items[*]}{.metadata.namespace}{"\n"}{end}' 2>/dev/null || true
  } | awk 'NF && !seen[$0]++'
}

remove_aiops_runtime() {
  disable_console_plugin
  for namespace in $(discover_aiopsinstallation_namespaces); do
    oc delete aiopsinstallation komsco-aiops -n "${namespace}" --ignore-not-found
  done
  oc delete consoleplugin komsco-ai-console-plugin --ignore-not-found
  for namespace in $(discover_runtime_namespaces); do
    oc delete deploy,svc,sa,cm,role,rolebinding,networkpolicy -n "${namespace}" \
      -l 'app.kubernetes.io/part-of=komsco-aiops' --ignore-not-found
  done
  oc delete clusterrole komsco-ai-action-executor --ignore-not-found
  oc delete clusterrolebinding komsco-ai-action-executor komsco-ai-gateway-auth-delegator --ignore-not-found
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
    oc get aiopsinstallation -A -o jsonpath='{range .items[?(@.metadata.name=="komsco-aiops")]}{.metadata.namespace}{"\n"}{end}' 2>/dev/null || true
  } | awk 'NF && !seen[$0]++'
}

disable_console_plugin() {
  local current_plugins patched_plugins
  current_plugins=$(oc get consoles.operator.openshift.io cluster -o jsonpath='{.spec.plugins}' 2>/dev/null || echo "[]")
  patched_plugins=$(PLUGIN_NAME=komsco-ai-console-plugin CURRENT_PLUGINS="${current_plugins}" python3 - <<'PY'
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

case "${command}" in
  package)
    package_olm
    ;;
  catalog)
    package_olm
    apply_catalog
    wait_catalog
    ;;
  install)
    package_olm
    apply_install
    ;;
  deploy)
    package_olm
    apply_catalog
    wait_catalog
    apply_install
    ;;
  status)
    show_status
    ;;
  reset-install)
    reset_install
    ;;
  uninstall)
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
