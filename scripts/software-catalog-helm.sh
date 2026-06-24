#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

CATALOG_NAME=${KOMSCO_AIOPS_CATALOG_NAME:-komsco-aiops}
CATALOG_DISPLAY_NAME=${KOMSCO_AIOPS_CATALOG_DISPLAY_NAME:-KOMSCO AIOps}
CATALOG_DESCRIPTION=${KOMSCO_AIOPS_CATALOG_DESCRIPTION:-KOMSCO AIOps console plugin and gateway catalog}
CATALOG_DIR=${KOMSCO_AIOPS_CATALOG_DIR:-"${ROOT_DIR}/dist/software-catalog"}
CATALOG_URL=${KOMSCO_AIOPS_CATALOG_URL:-}
CHART_DIR=${KOMSCO_AIOPS_CHART_DIR:-"${ROOT_DIR}/komsco-ai-console-plugin/charts/openshift-console-plugin"}
CHART_NAME=${KOMSCO_AIOPS_CHART_NAME:-komsco-aiops}
CHART_VERSION=${KOMSCO_AIOPS_CHART_VERSION:-0.1.3}
APP_VERSION=${KOMSCO_AIOPS_APP_VERSION:-${CHART_VERSION}}
RELEASE_NAME=${KOMSCO_AIOPS_RELEASE:-komsco-ai-console-plugin}
NAMESPACE=${KOMSCO_AIOPS_NAMESPACE:-komsco-ai}
VALUES_FILE=${KOMSCO_AIOPS_VALUES:-"${ROOT_DIR}/openshift/helm-values/console-plugin-prod.yaml"}
PACKAGE_VALUES_FILE=${KOMSCO_AIOPS_PACKAGE_VALUES:-"${VALUES_FILE}"}
SERVER_HOST=${KOMSCO_AIOPS_CATALOG_HOST:-0.0.0.0}
SERVER_PORT=${KOMSCO_AIOPS_CATALOG_PORT:-18088}

usage() {
  cat <<EOF
Usage: $0 <command>

Commands:
  package     Package the Helm chart and generate index.yaml under dist/software-catalog.
  serve       Serve the generated chart repository locally for development checks.
  register    Register the chart repository in OpenShift Software Catalog.
  unregister  Remove the HelmChartRepository registration from OpenShift.
  deploy      CLI install/upgrade equivalent for the catalog chart.
  status      Show Software Catalog and runtime deployment status.

Key environment variables:
  KOMSCO_AIOPS_CATALOG_URL       Required for register and recommended for package.
  KOMSCO_AIOPS_CHART_VERSION     Chart version shown as the update version. Default: 0.1.3
  KOMSCO_AIOPS_APP_VERSION       App/image version metadata. Default: chart version
  KOMSCO_AIOPS_NAMESPACE         Target namespace for deploy/status. Default: komsco-ai
  KOMSCO_AIOPS_VALUES            Helm values file. Default: openshift/helm-values/console-plugin-prod.yaml
  KOMSCO_AIOPS_PACKAGE_VALUES    Values baked into the catalog chart defaults. Default: KOMSCO_AIOPS_VALUES

Examples:
  KOMSCO_AIOPS_CATALOG_URL=https://repo.example/komsco-aiops task catalog:package
  KOMSCO_AIOPS_CATALOG_URL=https://repo.example/komsco-aiops task catalog:register
  KOMSCO_AIOPS_CHART_VERSION=0.1.3 task catalog:deploy
EOF
}

require_cmd() {
  local command_name=$1
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "${command_name} CLI is required." >&2
    exit 1
  fi
}

require_catalog_url() {
  if [[ -z "${CATALOG_URL}" ]]; then
    echo "KOMSCO_AIOPS_CATALOG_URL is required for this command." >&2
    exit 1
  fi
}

package_chart() {
  require_cmd python3
  mkdir -p "${CATALOG_DIR}"

  python3 - \
    "${CHART_DIR}" \
    "${CATALOG_DIR}" \
    "${CHART_NAME}" \
    "${CHART_VERSION}" \
    "${APP_VERSION}" \
    "${CATALOG_URL}" \
    "${PACKAGE_VALUES_FILE}" <<'PY'
import fnmatch
import hashlib
import io
import json
import os
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path

chart_dir = Path(sys.argv[1])
catalog_dir = Path(sys.argv[2])
chart_name = sys.argv[3]
chart_version = sys.argv[4]
app_version = sys.argv[5]
catalog_url = sys.argv[6].rstrip("/")
package_values_file = Path(sys.argv[7])

ignore_patterns = [
    ".DS_Store",
    ".git",
    ".git/*",
    ".gitignore",
    ".helmignore",
    "*.swp",
    "*.bak",
    "*.tmp",
    "*.orig",
    "*~",
    ".project",
    ".idea",
    ".idea/*",
    "*.tmproj",
    ".vscode",
    ".vscode/*",
]


def ignored(relative_path: str) -> bool:
    return any(fnmatch.fnmatch(relative_path, pattern) for pattern in ignore_patterns)


def parse_chart_yaml(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def rewrite_chart_yaml(text: str) -> str:
    lines = []
    seen_app_version = False
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("name:"):
            lines.append(f"name: {chart_name}")
        elif stripped.startswith("version:"):
            lines.append(f"version: {chart_version}")
        elif stripped.startswith("appVersion:"):
            lines.append(f"appVersion: {app_version}")
            seen_app_version = True
        else:
            lines.append(raw_line)
    if not seen_app_version:
        lines.append(f"appVersion: {app_version}")
    return "\n".join(lines) + "\n"


def packaged_values_yaml(original_text: str) -> str:
    if package_values_file.is_file():
        return package_values_file.read_text(encoding="utf-8").rstrip() + "\n"
    return original_text


def add_bytes(tar: tarfile.TarFile, arcname: str, payload: bytes, source: Path) -> None:
    info = tarfile.TarInfo(arcname)
    info.size = len(payload)
    info.mode = source.stat().st_mode & 0o777
    info.mtime = int(source.stat().st_mtime)
    tar.addfile(info, io.BytesIO(payload))


catalog_dir.mkdir(parents=True, exist_ok=True)
package_path = catalog_dir / f"{chart_name}-{chart_version}.tgz"
with tarfile.open(package_path, "w:gz") as tar:
    for path in sorted(chart_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(chart_dir).as_posix()
        if ignored(relative):
            continue
        arcname = f"{chart_name}/{relative}"
        if relative == "Chart.yaml":
            payload = rewrite_chart_yaml(path.read_text(encoding="utf-8")).encode("utf-8")
            add_bytes(tar, arcname, payload, path)
        elif relative == "values.yaml":
            payload = packaged_values_yaml(path.read_text(encoding="utf-8")).encode("utf-8")
            add_bytes(tar, arcname, payload, path)
        else:
            tar.add(path, arcname=arcname)


def metadata_from_package(path: Path) -> dict[str, str]:
    with tarfile.open(path, "r:gz") as tar:
        chart_member = next(
            member for member in tar.getmembers() if member.name.endswith("/Chart.yaml")
        )
        extracted = tar.extractfile(chart_member)
        if extracted is None:
            raise RuntimeError(f"Chart.yaml is missing in {path}")
        return parse_chart_yaml(extracted.read().decode("utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def q(value: object) -> str:
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
entries: dict[str, list[dict[str, str]]] = {}
for package in sorted(catalog_dir.glob("*.tgz")):
    metadata = metadata_from_package(package)
    name = metadata.get("name", package.name.rsplit("-", 1)[0])
    url = f"{catalog_url}/{package.name}" if catalog_url else package.name
    entries.setdefault(name, []).append(
        {
            "apiVersion": metadata.get("apiVersion", "v2"),
            "appVersion": metadata.get("appVersion", ""),
            "created": now,
            "description": metadata.get("description", ""),
            "digest": digest(package),
            "name": name,
            "type": metadata.get("type", "application"),
            "url": url,
            "version": metadata.get("version", ""),
        }
    )

lines = ["apiVersion: v1", "entries:"]
for name in sorted(entries):
    lines.append(f"  {name}:")
    for entry in sorted(entries[name], key=lambda item: item["version"], reverse=True):
        lines.extend(
            [
                f"  - apiVersion: {q(entry['apiVersion'])}",
                f"    appVersion: {q(entry['appVersion'])}",
                f"    created: {q(entry['created'])}",
                f"    description: {q(entry['description'])}",
                f"    digest: {q(entry['digest'])}",
                f"    name: {q(entry['name'])}",
                f"    type: {q(entry['type'])}",
                "    urls:",
                f"    - {q(entry['url'])}",
                f"    version: {q(entry['version'])}",
            ]
        )
lines.append(f"generated: {q(now)}")
(catalog_dir / "index.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

  echo "Packaged ${CHART_DIR} as chart version ${CHART_VERSION}"
  if [[ -f "${PACKAGE_VALUES_FILE}" ]]; then
    echo "Packaged chart defaults from: ${PACKAGE_VALUES_FILE}"
  fi
  echo "Catalog repository directory: ${CATALOG_DIR}"
}

serve_catalog() {
  require_cmd python3
  if [[ ! -f "${CATALOG_DIR}/index.yaml" ]]; then
    echo "${CATALOG_DIR}/index.yaml does not exist. Run task catalog:package first." >&2
    exit 1
  fi

  echo "Serving ${CATALOG_DIR}"
  echo "Repository URL for local browser checks: http://${SERVER_HOST}:${SERVER_PORT}"
  echo "For OpenShift Software Catalog, use a URL reachable by the cluster/console."
  python3 -m http.server "${SERVER_PORT}" --bind "${SERVER_HOST}" --directory "${CATALOG_DIR}"
}

register_catalog() {
  require_cmd oc
  require_catalog_url

  oc apply -f - <<EOF
apiVersion: helm.openshift.io/v1beta1
kind: HelmChartRepository
metadata:
  name: ${CATALOG_NAME}
spec:
  name: ${CATALOG_DISPLAY_NAME}
  description: ${CATALOG_DESCRIPTION}
  connectionConfig:
    url: ${CATALOG_URL}
EOF
}

unregister_catalog() {
  require_cmd oc
  oc delete helmchartrepository.helm.openshift.io "${CATALOG_NAME}" --ignore-not-found
}

deploy_release() {
  require_cmd helm
  if [[ ! -f "${VALUES_FILE}" ]]; then
    echo "Values file does not exist: ${VALUES_FILE}" >&2
    exit 1
  fi

  local chart_package="${CATALOG_DIR}/${CHART_NAME}-${CHART_VERSION}.tgz"
  if [[ ! -f "${chart_package}" ]]; then
    package_chart
  fi

  helm upgrade --install "${RELEASE_NAME}" "${chart_package}" \
    --namespace "${NAMESPACE}" \
    --create-namespace \
    --values "${VALUES_FILE}"
}

show_status() {
  require_cmd oc
  echo "# HelmChartRepository"
  oc get helmchartrepository.helm.openshift.io "${CATALOG_NAME}" -o wide --ignore-not-found
  echo
  echo "# ConsolePlugin"
  oc get consoleplugin "${RELEASE_NAME}" -o wide --ignore-not-found
  echo
  echo "# Runtime resources in ${NAMESPACE}"
  oc get deploy,svc -n "${NAMESPACE}" \
    -l 'app in (komsco-ai-console-plugin,komsco-ai-gateway,komsco-ai-action-executor,komsco-ai-host-diagnostics-controller)' \
    || true
}

command=${1:-}

case "${command}" in
  package)
    package_chart
    ;;
  serve)
    serve_catalog
    ;;
  register)
    register_catalog
    ;;
  unregister)
    unregister_catalog
    ;;
  deploy)
    deploy_release
    ;;
  status)
    show_status
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
