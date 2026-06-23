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
  uninstall   Remove the AIOpsInstallation, Subscription, OperatorGroup, CSV, and CatalogSource resources.

Key environment variables:
  KOMSCO_AIOPS_OPERATOR_VERSION     Operator/CSV version. Default: 0.1.0
  KOMSCO_AIOPS_OPERATOR_IMAGE       Operator image. Default: gateway image
  KOMSCO_AIOPS_PLUGIN_IMAGE         Console plugin operand image
  KOMSCO_AIOPS_GATEWAY_IMAGE        Gateway/operator operand image
  KOMSCO_AIOPS_OPERATOR_NAMESPACE   Operator install namespace. Default: komsco-ai
  KOMSCO_AIOPS_NAMESPACE            Operand target namespace. Default: operator namespace
  KOMSCO_AIOPS_MODE                 read-only, execute, or unrestricted. Default: execute

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
}

wait_catalog() {
  require_cmd oc
  echo "Waiting for PackageManifest ${PACKAGE_NAME} from ${CATALOG_NAME}..."
  for _ in $(seq 1 60); do
    if oc get packagemanifest "${PACKAGE_NAME}" -n "${CATALOG_NAMESPACE}" >/dev/null 2>&1; then
      return
    fi
    sleep 5
  done
  echo "PackageManifest ${PACKAGE_NAME} did not appear in ${CATALOG_NAMESPACE}." >&2
  oc get catalogsource "${CATALOG_NAME}" -n "${CATALOG_NAMESPACE}" -o yaml || true
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
    if [[ -n "${csv_name}" ]]; then
      phase=$(oc get csv "${csv_name}" -n "${OPERATOR_NAMESPACE}" -o jsonpath='{.status.phase}' 2>/dev/null || true)
      if [[ "${phase}" == "Succeeded" ]]; then
        echo "CSV ${csv_name} is Succeeded."
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
  oc rollout status deployment/"${OPERATOR_NAME}" -n "${OPERATOR_NAMESPACE}" --timeout=180s
  oc rollout status deployment/komsco-ai-console-plugin -n "${TARGET_NAMESPACE}" --timeout=300s
  oc rollout status deployment/komsco-ai-gateway -n "${TARGET_NAMESPACE}" --timeout=300s
  oc rollout status deployment/komsco-ai-action-executor -n "${TARGET_NAMESPACE}" --timeout=300s
  oc rollout status deployment/komsco-ai-host-diagnostics-controller -n "${TARGET_NAMESPACE}" --timeout=300s
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
  oc delete aiopsinstallation komsco-aiops -n "${OPERATOR_NAMESPACE}" --ignore-not-found
  oc delete subscription "${PACKAGE_NAME}" -n "${OPERATOR_NAMESPACE}" --ignore-not-found
  oc delete csv -n "${OPERATOR_NAMESPACE}" -l "operators.coreos.com/${PACKAGE_NAME}.${OPERATOR_NAMESPACE}" --ignore-not-found
  oc delete operatorgroup komsco-aiops -n "${OPERATOR_NAMESPACE}" --ignore-not-found
  oc delete -f "${CATALOG_DIR}" --ignore-not-found=true || true
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
