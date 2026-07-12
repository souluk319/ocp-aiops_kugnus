#!/usr/bin/env bash

set -euo pipefail

BACKUP_DIR=${KOMSCO_AIOPS_BACKUP_DIR:-/tmp/aiops-installation-backup}
COMPANY_SERVER=${KOMSCO_AIOPS_COMPANY_SERVER:-https://api.ocp.cywell.server:6443}
APPROVAL=${KOMSCO_AIOPS_APPROVE_ROLLBACK:-}
DRY_RUN=${KOMSCO_AIOPS_ROLLBACK_DRY_RUN:-false}

require_restore_file() {
  local name=$1
  if [[ ! -s "${BACKUP_DIR}/${name}" ]]; then
    echo "Refusing rollback: missing backup ${BACKUP_DIR}/${name}." >&2
    exit 1
  fi
}

apply_sanitized_backup() {
  local name=$1
  local apply_args=()
  if [[ "${DRY_RUN}" == "true" ]]; then
    apply_args+=(--dry-run=server)
  fi
  python3 - "${BACKUP_DIR}/${name}" <<'PY' | oc apply "${apply_args[@]}" -f -
import sys
import yaml

path = sys.argv[1]
removed_metadata = {
    "creationTimestamp",
    "deletionGracePeriodSeconds",
    "deletionTimestamp",
    "generation",
    "managedFields",
    "resourceVersion",
    "selfLink",
    "uid",
}


def clean(resource):
    if not isinstance(resource, dict):
        return resource
    resource.pop("status", None)
    metadata = resource.get("metadata")
    if isinstance(metadata, dict):
        for key in removed_metadata:
            metadata.pop(key, None)
        metadata.pop("ownerReferences", None)
        annotations = metadata.get("annotations")
        if isinstance(annotations, dict):
            annotations.pop("kubectl.kubernetes.io/last-applied-configuration", None)
    if resource.get("kind") == "List":
        resource["items"] = [clean(item) for item in resource.get("items", [])]
    return resource


documents = [clean(item) for item in yaml.safe_load_all(open(path, encoding="utf-8")) if item]
yaml.safe_dump_all(documents, sys.stdout, sort_keys=False)
PY
}

if [[ "${APPROVAL}" != "cywell-aiops" ]]; then
  echo "Refusing rollback. Set KOMSCO_AIOPS_APPROVE_ROLLBACK=cywell-aiops after declaring rollout failure." >&2
  exit 1
fi

server=$(oc whoami --show-server 2>/dev/null || true)
user=$(oc whoami 2>/dev/null || true)
if [[ "${server}" != "${COMPANY_SERVER}" || -z "${user}" ]]; then
  echo "Refusing rollback: authenticated company cluster context is required." >&2
  exit 1
fi

for name in \
  SHA256SUMS \
  catalog-configmap.yaml \
  catalogsource.yaml \
  canonical-crd.yaml \
  canonical-csv.yaml \
  canonical-subscription.yaml \
  canonical-operatorgroups.yaml \
  canonical-operator-deployment.yaml \
  canonical-cr.yaml \
  gateway-ledger-configmap.yaml \
  standalone-serviceaccount.yaml \
  standalone-nginx.yaml \
  standalone-service.yaml \
  standalone-service-cert-secret.yaml \
  standalone-cookie-secret.yaml \
  standalone-deployment.yaml \
  standalone-route-with-private-key.yaml \
  application-menu-consolelink.yaml; do
  require_restore_file "${name}"
done

(cd "${BACKUP_DIR}" && sha256sum -c SHA256SUMS >/dev/null)
if [[ "${DRY_RUN}" == "true" ]]; then
  echo "Backup checksum verification passed. Validating rollback manifests with server dry-run."
  for name in \
    catalog-configmap.yaml \
    catalogsource.yaml \
    canonical-crd.yaml \
    canonical-operatorgroups.yaml \
    canonical-csv.yaml \
    canonical-subscription.yaml \
    canonical-cr.yaml \
    canonical-operator-deployment.yaml \
    gateway-ledger-configmap.yaml \
    standalone-serviceaccount.yaml \
    standalone-nginx.yaml \
    standalone-service.yaml \
    standalone-service-cert-secret.yaml \
    standalone-cookie-secret.yaml \
    standalone-deployment.yaml \
    standalone-route-with-private-key.yaml \
    application-menu-consolelink.yaml; do
    apply_sanitized_backup "${name}"
  done
  echo "Rollback server dry-run passed. No cluster resources were changed."
  exit 0
fi
echo "Backup checksum verification passed. Restoring the pre-0.1.17 deployment."

oc scale deployment cywell-aiops-operator -n cywell-aiops --replicas=0 2>/dev/null || true
oc delete subscription cywell-aiops -n cywell-aiops --ignore-not-found
oc delete csv cywell-aiops-operator.v0.1.17 -n cywell-aiops --ignore-not-found

apply_sanitized_backup catalog-configmap.yaml
apply_sanitized_backup catalogsource.yaml
oc delete pod -n openshift-marketplace -l olm.catalogSource=cywell-aiops-catalog --ignore-not-found
apply_sanitized_backup canonical-crd.yaml
apply_sanitized_backup canonical-operatorgroups.yaml
apply_sanitized_backup canonical-csv.yaml
apply_sanitized_backup canonical-subscription.yaml
apply_sanitized_backup canonical-cr.yaml
apply_sanitized_backup canonical-operator-deployment.yaml

for name in \
  gateway-ledger-configmap.yaml \
  standalone-serviceaccount.yaml \
  standalone-nginx.yaml \
  standalone-service.yaml \
  standalone-service-cert-secret.yaml \
  standalone-cookie-secret.yaml \
  standalone-deployment.yaml \
  standalone-route-with-private-key.yaml \
  application-menu-consolelink.yaml; do
  apply_sanitized_backup "${name}"
done

oc rollout status deployment/cywell-aiops-operator -n cywell-aiops --timeout=180s
oc rollout status deployment/komsco-ai-gateway -n cywell-aiops --timeout=300s
oc rollout status deployment/komsco-ai-console-plugin -n cywell-aiops --timeout=300s
oc rollout status deployment/komsco-ai-core-standalone -n cywell-aiops --timeout=300s
echo "Rollback completed to the backed-up 0.1.14/0.1.16 deployment state."
