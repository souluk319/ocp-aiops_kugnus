#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

export KOMSCO_AIOPS_PACKAGE_NAME="${KOMSCO_AIOPS_PACKAGE_NAME:-komsco-aiops-kugnus}"
export KOMSCO_AIOPS_OPERATOR_NAME="${KOMSCO_AIOPS_OPERATOR_NAME:-komsco-aiops-kugnus-operator}"
export KOMSCO_AIOPS_INSTALLATION_NAME="${KOMSCO_AIOPS_INSTALLATION_NAME:-komsco-aiops-kugnus}"
export KOMSCO_AIOPS_OLM_CATALOG_NAME="${KOMSCO_AIOPS_OLM_CATALOG_NAME:-komsco-aiops-catalog-kugnus}"
export KOMSCO_AIOPS_DISPLAY_NAME="${KOMSCO_AIOPS_DISPLAY_NAME:-Cywell AI}"
export KOMSCO_AIOPS_CATALOG_DISPLAY_NAME="${KOMSCO_AIOPS_CATALOG_DISPLAY_NAME:-Cywell AI Kugnus Catalog}"
export KOMSCO_AIOPS_OPERATOR_NAMESPACE="${KOMSCO_AIOPS_OPERATOR_NAMESPACE:-komsco-ai-kugnus}"
export KOMSCO_AIOPS_NAMESPACE="${KOMSCO_AIOPS_NAMESPACE:-komsco-ai-kugnus}"
export KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME="${KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME:-komsco-ai-console-plugin-kugnus}"
export KOMSCO_AIOPS_CONSOLE_PLUGIN_DISPLAY_NAME="${KOMSCO_AIOPS_CONSOLE_PLUGIN_DISPLAY_NAME:-Cywell AI}"
export KOMSCO_AIOPS_MODE="${KOMSCO_AIOPS_MODE:-read-only}"
export KOMSCO_AIOPS_ENABLE_MUTATIONS="${KOMSCO_AIOPS_ENABLE_MUTATIONS:-false}"
export KOMSCO_AIOPS_ENABLE_UNRESTRICTED_COMMANDS="${KOMSCO_AIOPS_ENABLE_UNRESTRICTED_COMMANDS:-false}"
export KOMSCO_AIOPS_ICON_FILE="${KOMSCO_AIOPS_ICON_FILE:-docs/Ver.0.1.0/design-assets/K_icon.png}"
export KOMSCO_AIOPS_ICON_MEDIA_TYPE="${KOMSCO_AIOPS_ICON_MEDIA_TYPE:-image/png}"
export KOMSCO_AIOPS_IMAGE_BUILD_STRATEGY="${KOMSCO_AIOPS_IMAGE_BUILD_STRATEGY:-openshift}"
export KOMSCO_AIOPS_FORCE_IMAGE_BUILD="${KOMSCO_AIOPS_FORCE_IMAGE_BUILD:-false}"
export KOMSCO_AIOPS_BOOTSTRAP_INSTALLATION="${KOMSCO_AIOPS_BOOTSTRAP_INSTALLATION:-false}"
export KOMSCO_AIOPS_APPROVE_INSTALL="${KOMSCO_AIOPS_APPROVE_INSTALL:-}"
export KOMSCO_AIOPS_APPROVE_UNINSTALL="${KOMSCO_AIOPS_APPROVE_UNINSTALL:-}"

usage() {
  cat <<EOF
Usage: $0 <command>

Commands:
  package   Generate and verify Kugnus OLM package locally.
  images    Build and push Kugnus gateway/operator and console plugin images.
  publish   Build/push images, then register only the Kugnus CatalogSource.
  install   Install Kugnus Subscription and AIOpsInstallation after explicit approval.
  uninstall Remove only Kugnus catalog/install/runtime resources after explicit approval.
  status    Show Kugnus catalog, install, operand, and console plugin status.

Image build strategies:
  openshift  Use OpenShift BuildConfig binary builds and internal registry only.
  local      Use local docker/podman build and external registry push only.
  auto       Try local docker/podman push first, then OpenShift binary build fallback.

Set KOMSCO_AIOPS_FORCE_IMAGE_BUILD=true to rebuild existing Kugnus image tags.
EOF
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
  local version=${KOMSCO_AIOPS_OPERATOR_VERSION:-0.1.3}
  local pull_registry=${KOMSCO_AIOPS_PULL_REGISTRY:-image-registry.openshift-image-registry.svc:5000}

  export KOMSCO_AIOPS_OPERATOR_IMAGE="${KOMSCO_AIOPS_OPERATOR_IMAGE:-${pull_registry}/${KOMSCO_AIOPS_NAMESPACE}/komsco-ai-gateway:${version}}"
  export KOMSCO_AIOPS_GATEWAY_IMAGE="${KOMSCO_AIOPS_GATEWAY_IMAGE:-${pull_registry}/${KOMSCO_AIOPS_NAMESPACE}/komsco-ai-gateway:${version}}"
  export KOMSCO_AIOPS_PLUGIN_IMAGE="${KOMSCO_AIOPS_PLUGIN_IMAGE:-${pull_registry}/${KOMSCO_AIOPS_NAMESPACE}/komsco-ai-console-plugin:${version}}"
}

validate_kugnus_safety() {
  if [[ "${KOMSCO_AIOPS_PACKAGE_NAME}" != "komsco-aiops-kugnus" ]]; then
    echo "Refusing non-Kugnus package name: ${KOMSCO_AIOPS_PACKAGE_NAME}" >&2
    exit 1
  fi

  if [[ "${KOMSCO_AIOPS_OLM_CATALOG_NAME}" != "komsco-aiops-catalog-kugnus" ]]; then
    echo "Refusing non-Kugnus catalog name: ${KOMSCO_AIOPS_OLM_CATALOG_NAME}" >&2
    exit 1
  fi

  if [[ "${KOMSCO_AIOPS_OPERATOR_NAME}" != "komsco-aiops-kugnus-operator" ]]; then
    echo "Refusing non-Kugnus operator name: ${KOMSCO_AIOPS_OPERATOR_NAME}" >&2
    exit 1
  fi

  if [[ "${KOMSCO_AIOPS_INSTALLATION_NAME}" != "komsco-aiops-kugnus" ]]; then
    echo "Refusing non-Kugnus AIOpsInstallation name: ${KOMSCO_AIOPS_INSTALLATION_NAME}" >&2
    exit 1
  fi

  if [[ "${KOMSCO_AIOPS_BOOTSTRAP_INSTALLATION}" != "false" ]]; then
    echo "Refusing Kugnus bootstrap install. publish/catalog must not auto-create AIOpsInstallation." >&2
    exit 1
  fi

  case "${KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME}" in
    komsco-ai-console-plugin|lightspeed-console-plugin)
      echo "Refusing protected ConsolePlugin name for Kugnus: ${KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME}" >&2
      exit 1
      ;;
  esac

  if [[ "${KOMSCO_AIOPS_NAMESPACE}" != "komsco-ai-kugnus" || "${KOMSCO_AIOPS_OPERATOR_NAMESPACE}" != "komsco-ai-kugnus" ]]; then
    echo "Refusing non-Kugnus namespace. Set both namespace values to komsco-ai-kugnus." >&2
    exit 1
  fi
}

verify_package() {
  ROOT_DIR="${ROOT_DIR}" python3 - <<'PY'
import base64
import hashlib
import json
import os
from pathlib import Path

root = Path(os.environ["ROOT_DIR"])
csv_name = f"{os.environ['KOMSCO_AIOPS_OPERATOR_NAME']}.v{os.environ.get('KOMSCO_AIOPS_OPERATOR_VERSION', '0.1.3')}"
csv_path = root / "olm" / "generated" / "bundle" / "manifests" / f"{csv_name}.clusterserviceversion.yaml"
catalog_path = root / "olm" / "generated" / "catalog" / "01-catalogsource.yaml"
configmap_path = root / "olm" / "generated" / "catalog" / "00-catalog-configmap.yaml"
icon_path = root / os.environ["KOMSCO_AIOPS_ICON_FILE"]

csv_payload = json.loads(csv_path.read_text(encoding="utf-8"))
catalog_payload = json.loads(catalog_path.read_text(encoding="utf-8"))
configmap_payload = json.loads(configmap_path.read_text(encoding="utf-8"))
package_payload = json.loads(configmap_payload["data"]["packages"])[0]
example_payload = json.loads(csv_payload["metadata"]["annotations"]["alm-examples"])[0]
icon = csv_payload["spec"]["icon"][0]
decoded_icon = base64.b64decode(icon["base64data"])

checks = {
    "displayName": csv_payload["spec"]["displayName"] == os.environ["KOMSCO_AIOPS_DISPLAY_NAME"],
    "catalogName": catalog_payload["metadata"]["name"] == os.environ["KOMSCO_AIOPS_OLM_CATALOG_NAME"],
    "packageName": package_payload["packageName"] == os.environ["KOMSCO_AIOPS_PACKAGE_NAME"],
    "csvName": csv_payload["metadata"]["name"].startswith(os.environ["KOMSCO_AIOPS_OPERATOR_NAME"] + ".v"),
    "bootstrapDisabled": next(
        env["value"]
        for deployment in csv_payload["spec"]["install"]["spec"]["deployments"]
        for container in deployment["spec"]["template"]["spec"]["containers"]
        for env in container["env"]
        if env["name"] == "KOMSCO_AI_OPERATOR_BOOTSTRAP_INSTALLATION"
    ) == "false",
    "installationName": example_payload["metadata"]["name"] == os.environ["KOMSCO_AIOPS_INSTALLATION_NAME"],
    "consolePluginName": example_payload["spec"]["consolePluginName"] == os.environ["KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME"],
    "mode": example_payload["spec"]["mode"] == "read-only",
    "mutations": example_payload["spec"]["capabilities"]["mutations"] is False,
    "unrestricted": example_payload["spec"]["capabilities"]["unrestrictedCommands"] is False,
    "iconMediaType": icon["mediatype"] == "image/png",
    "iconSha256": hashlib.sha256(decoded_icon).hexdigest() == hashlib.sha256(icon_path.read_bytes()).hexdigest(),
}

failed = [name for name, passed in checks.items() if not passed]
if failed:
    raise SystemExit("Kugnus package verification failed: " + ", ".join(failed))

print("Kugnus package verification passed")
print(f"CSV: {csv_name}")
print(f"CatalogSource: {catalog_payload['metadata']['namespace']}/{catalog_payload['metadata']['name']}")
print(f"PackageManifest: {package_payload['packageName']}")
print(f"ConsolePlugin: {example_payload['spec']['consolePluginName']}")
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

grant_image_pull_access() {
  require_oc
  oc policy add-role-to-group system:image-puller "system:serviceaccounts:${KOMSCO_AIOPS_NAMESPACE}" -n "${KOMSCO_AIOPS_NAMESPACE}"
}

patch_binary_build_output() {
  local name=$1
  oc patch buildconfig "${name}" -n "${KOMSCO_AIOPS_NAMESPACE}" --type=merge \
    -p "{\"spec\":{\"output\":{\"to\":{\"kind\":\"ImageStreamTag\",\"name\":\"${name}:${KOMSCO_AIOPS_OPERATOR_VERSION:-0.1.3}\"}}}}"
}

ensure_binary_build() {
  local name=$1
  local context_dir=$2
  local stage_dir
  local version=${KOMSCO_AIOPS_OPERATOR_VERSION:-0.1.3}

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
  local build_root="${TMPDIR:-/tmp}/komsco-aiops-kugnus-build"
  local stage_dir="${build_root}/${name}"

  case "${stage_dir}" in
    /tmp/komsco-aiops-kugnus-build/*|/var/tmp/komsco-aiops-kugnus-build/*)
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
    --exclude='./node_modules' \
    --exclude='./dist' \
    --exclude='./integration-tests/screenshots' \
    --exclude='./integration-tests/videos' \
    --exclude='./.yarn/install-state.gz' \
    --exclude='./.venv' \
    --exclude='./__pycache__' \
    --exclude='./.pytest_cache' \
    --exclude='./.ruff_cache' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='*.pyd' \
    --exclude='*.log' \
    -cf - . | tar -C "${stage_dir}" -xf -
  echo "${stage_dir}"
}

openshift_images() {
  echo "Building Kugnus images with OpenShift binary builds in namespace ${KOMSCO_AIOPS_NAMESPACE}."
  ensure_binary_build "komsco-ai-gateway" "${ROOT_DIR}/komsco-ai-gateway"
  ensure_binary_build "komsco-ai-console-plugin" "${ROOT_DIR}/komsco-ai-console-plugin"
  grant_image_pull_access
  set_default_image_env
  echo "OpenShift binary image build completed."
  echo "KOMSCO_AIOPS_OPERATOR_IMAGE=${KOMSCO_AIOPS_OPERATOR_IMAGE}"
  echo "KOMSCO_AIOPS_GATEWAY_IMAGE=${KOMSCO_AIOPS_GATEWAY_IMAGE}"
  echo "KOMSCO_AIOPS_PLUGIN_IMAGE=${KOMSCO_AIOPS_PLUGIN_IMAGE}"
}

local_images() {
  "${ROOT_DIR}/scripts/olm-release-images.sh" build-push
}

images() {
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
  images
  set_default_image_env
  "${ROOT_DIR}/scripts/olm-deploy.sh" catalog
}

install() {
  if [[ "${KOMSCO_AIOPS_APPROVE_INSTALL}" != "komsco-ai-kugnus" ]]; then
    echo "Refusing install. Re-run with KOMSCO_AIOPS_APPROVE_INSTALL=komsco-ai-kugnus after explicit approval." >&2
    exit 1
  fi
  set_default_image_env
  "${ROOT_DIR}/scripts/olm-deploy.sh" install
}

uninstall() {
  if [[ "${KOMSCO_AIOPS_APPROVE_UNINSTALL}" != "komsco-ai-kugnus" ]]; then
    echo "Refusing uninstall. Re-run with KOMSCO_AIOPS_APPROVE_UNINSTALL=komsco-ai-kugnus after explicit approval." >&2
    exit 1
  fi
  require_oc
  set_default_image_env
  "${ROOT_DIR}/scripts/olm-deploy.sh" package
  oc delete aiopsinstallation "${KOMSCO_AIOPS_INSTALLATION_NAME}" -n "${KOMSCO_AIOPS_NAMESPACE}" --ignore-not-found=true
  oc delete consoleplugin "${KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME}" --ignore-not-found=true
  oc delete subscription "${KOMSCO_AIOPS_PACKAGE_NAME}" -n "${KOMSCO_AIOPS_OPERATOR_NAMESPACE}" --ignore-not-found=true
  oc delete csv "${KOMSCO_AIOPS_OPERATOR_NAME}.v${KOMSCO_AIOPS_OPERATOR_VERSION:-0.1.3}" -n "${KOMSCO_AIOPS_OPERATOR_NAMESPACE}" --ignore-not-found=true
  oc delete -f "${ROOT_DIR}/olm/generated/install/03-aiopsinstallation.yaml" --ignore-not-found=true || true
  oc delete -f "${ROOT_DIR}/olm/generated/install/02-subscription.yaml" --ignore-not-found=true || true
  oc delete -f "${ROOT_DIR}/olm/generated/install/01-operatorgroup.yaml" --ignore-not-found=true || true
  oc delete clusterrolebinding "${KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME}-gateway-auth-delegator" --ignore-not-found=true
  oc delete clusterrolebinding "${KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME}-action-executor" --ignore-not-found=true
  oc delete clusterrole "${KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME}-action-executor" --ignore-not-found=true
  oc delete catalogsource "${KOMSCO_AIOPS_OLM_CATALOG_NAME}" -n openshift-marketplace --ignore-not-found=true
  oc delete configmap "${KOMSCO_AIOPS_OLM_CATALOG_NAME}" -n openshift-marketplace --ignore-not-found=true
}

status() {
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
validate_kugnus_safety

case "${command}" in
  package)
    package
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
