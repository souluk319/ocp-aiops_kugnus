#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
VERSION=${KOMSCO_AIOPS_OPERATOR_VERSION:-0.1.8}
NAMESPACE=${KOMSCO_AIOPS_NAMESPACE:-${KOMSCO_AIOPS_OPERATOR_NAMESPACE:-komsco-ai}}
PUSH_REGISTRY=${KOMSCO_AIOPS_PUSH_REGISTRY:-}
PULL_REGISTRY=${KOMSCO_AIOPS_PULL_REGISTRY:-}
TLS_VERIFY=${KOMSCO_AIOPS_REGISTRY_TLS_VERIFY:-false}
CONTAINER_ENGINE=${KOMSCO_AIOPS_CONTAINER_ENGINE:-}
GRANT_IMAGE_PULL=${KOMSCO_AIOPS_GRANT_IMAGE_PULL:-true}

usage() {
  cat <<EOF
Usage: $0 <command>

Commands:
  build-push  Build and push gateway/operator and console-plugin images.
  deploy      Build/push images, then run the OLM one-shot deployment.
  env         Print the image references that would be used.

Key environment variables:
  KOMSCO_AIOPS_OPERATOR_VERSION      Image/CSV version. Default: 0.1.8
  KOMSCO_AIOPS_NAMESPACE             Image namespace and operand namespace. Default: komsco-ai
  KOMSCO_AIOPS_PUSH_REGISTRY         Registry used by the local machine for push.
  KOMSCO_AIOPS_PULL_REGISTRY         Registry used by cluster workloads for pull.
  KOMSCO_AIOPS_REGISTRY_TLS_VERIFY   true or false for podman login/push. Default: false
  KOMSCO_AIOPS_CONTAINER_ENGINE      podman or docker. Auto-detected if unset.
  KOMSCO_AIOPS_GRANT_IMAGE_PULL      Grant all service accounts image pull access to the image namespace. Default: true

Example:
  KOMSCO_AIOPS_OPERATOR_VERSION=0.1.8 \\
  KOMSCO_AIOPS_NAMESPACE=komsco-ai \\
  task olm:release
EOF
}

require_cmd() {
  local command_name=$1
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "${command_name} CLI is required." >&2
    exit 1
  fi
}

detect_engine() {
  if [[ -n "${CONTAINER_ENGINE}" ]]; then
    echo "${CONTAINER_ENGINE}"
    return
  fi
  if command -v podman >/dev/null 2>&1; then
    echo podman
    return
  fi
  if command -v docker >/dev/null 2>&1; then
    echo docker
    return
  fi
  echo "podman or docker is required." >&2
  exit 1
}

registry_info() {
  local mode=$1
  if [[ "${mode}" == "push" && -n "${PUSH_REGISTRY}" ]]; then
    echo "${PUSH_REGISTRY}"
    return
  fi
  if [[ "${mode}" == "pull" && -n "${PULL_REGISTRY}" ]]; then
    echo "${PULL_REGISTRY}"
    return
  fi
  require_cmd oc
  if [[ "${mode}" == "pull" ]]; then
    oc registry info --internal 2>/dev/null
  else
    oc registry info 2>/dev/null
  fi
}

push_registry() {
  registry_info push
}

pull_registry() {
  registry_info pull
}

gateway_push_image() {
  echo "$(push_registry)/${NAMESPACE}/komsco-ai-gateway:${VERSION}"
}

plugin_push_image() {
  echo "$(push_registry)/${NAMESPACE}/komsco-ai-console-plugin:${VERSION}"
}

gateway_pull_image() {
  echo "$(pull_registry)/${NAMESPACE}/komsco-ai-gateway:${VERSION}"
}

plugin_pull_image() {
  echo "$(pull_registry)/${NAMESPACE}/komsco-ai-console-plugin:${VERSION}"
}

login_registry() {
  local engine=$1
  local registry=$2
  local username=${KOMSCO_AIOPS_REGISTRY_USERNAME:-}
  local password=${KOMSCO_AIOPS_REGISTRY_PASSWORD:-}

  if [[ -z "${username}" || -z "${password}" ]]; then
    require_cmd oc
    username=$(oc whoami)
    password=$(oc whoami -t)
  fi

  if [[ "${engine}" == "podman" ]]; then
    podman login --tls-verify="${TLS_VERIFY}" -u "${username}" -p "${password}" "${registry}"
  elif [[ "${engine}" == "docker" ]]; then
    if [[ "${TLS_VERIFY}" != "true" ]]; then
      echo "docker does not support per-command tls-verify=false; configure an insecure registry if needed." >&2
    fi
    printf '%s' "${password}" | docker login -u "${username}" --password-stdin "${registry}"
  else
    echo "Unsupported container engine: ${engine}" >&2
    exit 1
  fi
}

build_image() {
  local engine=$1
  local image=$2
  local context_dir=$3
  "${engine}" build -t "${image}" "${context_dir}"
}

push_image() {
  local engine=$1
  local image=$2
  if [[ "${engine}" == "podman" ]]; then
    podman push --tls-verify="${TLS_VERIFY}" "${image}"
  else
    docker push "${image}"
  fi
}

tag_image() {
  local engine=$1
  local source=$2
  local target=$3
  if [[ "${source}" != "${target}" ]]; then
    "${engine}" tag "${source}" "${target}"
  fi
}

ensure_namespace() {
  require_cmd oc
  oc get namespace "${NAMESPACE}" >/dev/null 2>&1 || oc create namespace "${NAMESPACE}"
}

grant_image_pull_access() {
  require_cmd oc
  if [[ "${GRANT_IMAGE_PULL}" != "true" ]]; then
    return
  fi
  oc policy add-role-to-group system:image-puller system:serviceaccounts -n "${NAMESPACE}"
}

build_push() {
  local engine
  local push_registry_value
  local gateway_push
  local gateway_pull
  local plugin_push
  local plugin_pull

  engine=$(detect_engine)
  push_registry_value=$(push_registry)
  gateway_push=$(gateway_push_image)
  gateway_pull=$(gateway_pull_image)
  plugin_push=$(plugin_push_image)
  plugin_pull=$(plugin_pull_image)

  ensure_namespace
  login_registry "${engine}" "${push_registry_value}"

  build_image "${engine}" "${gateway_push}" "${ROOT_DIR}/komsco-ai-gateway"
  tag_image "${engine}" "${gateway_push}" "${gateway_pull}"
  push_image "${engine}" "${gateway_push}"

  build_image "${engine}" "${plugin_push}" "${ROOT_DIR}/komsco-ai-console-plugin"
  tag_image "${engine}" "${plugin_push}" "${plugin_pull}"
  push_image "${engine}" "${plugin_push}"
  grant_image_pull_access

  print_env
}

print_env() {
  cat <<EOF
KOMSCO_AIOPS_OPERATOR_IMAGE=$(gateway_pull_image)
KOMSCO_AIOPS_GATEWAY_IMAGE=$(gateway_pull_image)
KOMSCO_AIOPS_PLUGIN_IMAGE=$(plugin_pull_image)
EOF
}

deploy_release() {
  build_push
  KOMSCO_AIOPS_OPERATOR_IMAGE="$(gateway_pull_image)" \
  KOMSCO_AIOPS_GATEWAY_IMAGE="$(gateway_pull_image)" \
  KOMSCO_AIOPS_PLUGIN_IMAGE="$(plugin_pull_image)" \
    "${ROOT_DIR}/scripts/olm-deploy.sh" deploy
}

command=${1:-}

case "${command}" in
  build-push)
    build_push
    ;;
  deploy)
    deploy_release
    ;;
  env)
    print_env
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
