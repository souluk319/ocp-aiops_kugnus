#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OC_BIN="${OC_BIN:-oc}"
OC_TIMEOUT="${OC_TIMEOUT:-60s}"
OC_USER_TIMEOUT="${OC_USER_TIMEOUT:-5s}"
EXPECTED_SERVER="${KOMSCO_AIOPS_COMPANY_SERVER:-https://api.ocp.cywell.server:6443}"
SESSION="$(date -u +%Y%m%d%H%M%S)"
NAMESPACE="aiops-copilot-e2e-${SESSION}"
JSON_OUTPUT=false
DRY_RUN=false

usage() {
  cat <<EOF
Usage: $0 [--namespace NAME] [--session SESSION] [--dry-run] [--json]

Creates a safe, disposable OKD namespace for connected AIOps Copilot tests.
The namespace must use the aiops-copilot-e2e-* prefix and receives safety labels
that cleanup verifies before deletion.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --namespace)
      NAMESPACE="${2:-}"
      shift 2
      ;;
    --session)
      SESSION="${2:-}"
      NAMESPACE="aiops-copilot-e2e-${SESSION}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --json)
      JSON_OUTPUT=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

log() {
  if [ "$JSON_OUTPUT" != "true" ]; then
    printf '%s\n' "$*"
  fi
}

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

oc_run() {
  timeout "$OC_TIMEOUT" "$OC_BIN" "$@"
}

oc_user_optional() {
  timeout "$OC_USER_TIMEOUT" "$OC_BIN" whoami 2>/dev/null || true
}

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().rstrip("\n")))' <<<"$1"
}

emit_json() {
  local status="$1"
  local reason="${2:-}"
  local server user
  server="$(oc_run whoami --show-server 2>/dev/null || true)"
  user="$(oc_user_optional)"
  cat <<EOF
{"status":$(json_escape "$status"),"reason":$(json_escape "$reason"),"namespace":$(json_escape "$NAMESPACE"),"session":$(json_escape "$SESSION"),"server":$(json_escape "$server"),"user":$(json_escape "$user"),"labels":{"app.kubernetes.io/managed-by":"komsco-aiops-test","aiops.komsco/safe-delete":"true","aiops.komsco/test-suite":"v0281-connected","aiops.komsco/session":$(json_escape "$SESSION")}}
EOF
}

require_safe_namespace_name() {
  if [[ ! "$NAMESPACE" =~ ^aiops-copilot-e2e-[a-zA-Z0-9][a-zA-Z0-9-]{4,40}$ ]]; then
    fail "unsafe namespace name: ${NAMESPACE}. Required prefix: aiops-copilot-e2e-"
  fi
}

label_value() {
  local key="$1"
  oc_run get namespace "$NAMESPACE" -o "go-template={{ index .metadata.labels \"${key}\" }}" 2>/dev/null || true
}

verify_existing_namespace_is_safe() {
  local managed safe suite session_label
  managed="$(label_value 'app.kubernetes.io/managed-by')"
  safe="$(label_value 'aiops.komsco/safe-delete')"
  suite="$(label_value 'aiops.komsco/test-suite')"
  session_label="$(label_value 'aiops.komsco/session')"
  [ "$managed" = "komsco-aiops-test" ] || fail "existing namespace is not managed by komsco-aiops-test"
  [ "$safe" = "true" ] || fail "existing namespace is missing safe-delete=true"
  [ "$suite" = "v0281-connected" ] || fail "existing namespace belongs to another suite: ${suite:-missing}"
  [ "$session_label" = "$SESSION" ] || fail "existing namespace session mismatch: ${session_label:-missing} != ${SESSION}"
}

check_cluster() {
  command -v "$OC_BIN" >/dev/null 2>&1 || fail "oc CLI not found"
  local server user
  server="$(oc_run whoami --show-server 2>/dev/null || true)"
  [ "$server" = "$EXPECTED_SERVER" ] || fail "refusing cluster write: current server=${server:-unavailable}, expected=${EXPECTED_SERVER}"
  user="$(oc_user_optional)"
  if [ -z "$user" ]; then
    log "[WARN] oc whoami did not return a user within ${OC_USER_TIMEOUT}; continuing with server and RBAC checks."
  fi
}

check_permissions() {
  local can_ns can_project
  can_ns="$(oc_run auth can-i create namespaces 2>/dev/null || true)"
  can_project="$(oc_run auth can-i create projectrequests.project.openshift.io 2>/dev/null || true)"
  if [ "$can_ns" != "yes" ] && [ "$can_project" != "yes" ]; then
    fail "current user cannot create a test namespace/project"
  fi
}

create_namespace() {
  if oc_run get namespace "$NAMESPACE" >/dev/null 2>&1; then
    log "[INFO] namespace already exists: $NAMESPACE"
    verify_existing_namespace_is_safe
    return
  fi

  if [ "$DRY_RUN" = "true" ]; then
    log "[DRY-RUN] would create namespace $NAMESPACE"
    return
  fi

  if ! oc_run create namespace "$NAMESPACE" >/dev/null 2>&1; then
    oc_run new-project "$NAMESPACE" >/dev/null
  fi
}

apply_safety_labels() {
  [ "$DRY_RUN" = "true" ] && return
  oc_run label namespace "$NAMESPACE" \
    app.kubernetes.io/managed-by=komsco-aiops-test \
    aiops.komsco/safe-delete=true \
    aiops.komsco/test-suite=v0281-connected \
    "aiops.komsco/session=${SESSION}" \
    --overwrite >/dev/null
  oc_run annotate namespace "$NAMESPACE" \
    aiops.komsco/purpose="Connected OKD AIOps Copilot safe scenario test" \
    --overwrite >/dev/null
}

apply_workloads() {
  if [ "$DRY_RUN" = "true" ]; then
    log "[DRY-RUN] would apply quota, limitrange, configmap, and four deployments"
    return
  fi

  cat <<YAML | oc_run apply -n "$NAMESPACE" -f - >/dev/null
apiVersion: v1
kind: ResourceQuota
metadata:
  name: aiops-connected-quota
  labels:
    app.kubernetes.io/managed-by: komsco-aiops-test
    aiops.komsco/test-suite: v0281-connected
    aiops.komsco/session: "${SESSION}"
spec:
  hard:
    pods: "8"
    requests.cpu: "500m"
    requests.memory: "512Mi"
    limits.cpu: "1"
    limits.memory: "1Gi"
---
apiVersion: v1
kind: LimitRange
metadata:
  name: aiops-connected-limits
  labels:
    app.kubernetes.io/managed-by: komsco-aiops-test
    aiops.komsco/test-suite: v0281-connected
    aiops.komsco/session: "${SESSION}"
spec:
  limits:
    - type: Container
      default:
        cpu: 50m
        memory: 64Mi
      defaultRequest:
        cpu: 10m
        memory: 32Mi
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: aiops-connected-scenario
  labels:
    app.kubernetes.io/managed-by: komsco-aiops-test
    aiops.komsco/test-suite: v0281-connected
    aiops.komsco/session: "${SESSION}"
data:
  scenario: "Connected OKD AIOps Copilot safe e2e"
  allowed_mutation: "scale deployment/aiops-connected-scale-target from 1 to 2 or rollout restart test deployment only"
  forbidden_mutation: "no production namespace mutation; no deletion outside this namespace"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aiops-connected-ok
  labels:
    app.kubernetes.io/managed-by: komsco-aiops-test
    app.kubernetes.io/part-of: komsco-aiops-connected-test
    aiops.komsco/test-suite: v0281-connected
    aiops.komsco/session: "${SESSION}"
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: aiops-connected-ok
      app.kubernetes.io/part-of: komsco-aiops-connected-test
  template:
    metadata:
      labels:
        app.kubernetes.io/managed-by: komsco-aiops-test
        app.kubernetes.io/part-of: komsco-aiops-connected-test
        aiops.komsco/test-suite: v0281-connected
        aiops.komsco/session: "${SESSION}"
        app.kubernetes.io/name: aiops-connected-ok
    spec:
      containers:
        - name: ok
          image: registry.access.redhat.com/ubi9/ubi-minimal:9.5
          command: ["/bin/sh", "-c", "sleep 3600"]
          resources:
            requests:
              cpu: 10m
              memory: 32Mi
            limits:
              cpu: 50m
              memory: 64Mi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aiops-connected-scale-target
  labels:
    app.kubernetes.io/managed-by: komsco-aiops-test
    app.kubernetes.io/part-of: komsco-aiops-connected-test
    aiops.komsco/test-suite: v0281-connected
    aiops.komsco/session: "${SESSION}"
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: aiops-connected-scale-target
      app.kubernetes.io/part-of: komsco-aiops-connected-test
  template:
    metadata:
      labels:
        app.kubernetes.io/managed-by: komsco-aiops-test
        app.kubernetes.io/part-of: komsco-aiops-connected-test
        aiops.komsco/test-suite: v0281-connected
        aiops.komsco/session: "${SESSION}"
        app.kubernetes.io/name: aiops-connected-scale-target
    spec:
      containers:
        - name: worker
          image: registry.access.redhat.com/ubi9/ubi-minimal:9.5
          command: ["/bin/sh", "-c", "sleep 3600"]
          resources:
            requests:
              cpu: 10m
              memory: 32Mi
            limits:
              cpu: 50m
              memory: 64Mi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aiops-connected-crashloop
  labels:
    app.kubernetes.io/managed-by: komsco-aiops-test
    app.kubernetes.io/part-of: komsco-aiops-connected-test
    aiops.komsco/test-suite: v0281-connected
    aiops.komsco/session: "${SESSION}"
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: aiops-connected-crashloop
      app.kubernetes.io/part-of: komsco-aiops-connected-test
  template:
    metadata:
      labels:
        app.kubernetes.io/managed-by: komsco-aiops-test
        app.kubernetes.io/part-of: komsco-aiops-connected-test
        aiops.komsco/test-suite: v0281-connected
        aiops.komsco/session: "${SESSION}"
        app.kubernetes.io/name: aiops-connected-crashloop
    spec:
      containers:
        - name: crashloop
          image: registry.access.redhat.com/ubi9/ubi-minimal:9.5
          command: ["/bin/sh", "-c", "echo aiops connected crashloop fixture; exit 1"]
          resources:
            requests:
              cpu: 10m
              memory: 32Mi
            limits:
              cpu: 50m
              memory: 64Mi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aiops-connected-imagepull
  labels:
    app.kubernetes.io/managed-by: komsco-aiops-test
    app.kubernetes.io/part-of: komsco-aiops-connected-test
    aiops.komsco/test-suite: v0281-connected
    aiops.komsco/session: "${SESSION}"
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: aiops-connected-imagepull
      app.kubernetes.io/part-of: komsco-aiops-connected-test
  template:
    metadata:
      labels:
        app.kubernetes.io/managed-by: komsco-aiops-test
        app.kubernetes.io/part-of: komsco-aiops-connected-test
        aiops.komsco/test-suite: v0281-connected
        aiops.komsco/session: "${SESSION}"
        app.kubernetes.io/name: aiops-connected-imagepull
    spec:
      containers:
        - name: imagepull
          image: image-registry.openshift-image-registry.svc:5000/nonexistent/aiops-connected-missing:never
          imagePullPolicy: Always
          resources:
            requests:
              cpu: 10m
              memory: 32Mi
            limits:
              cpu: 50m
              memory: 64Mi
YAML
}

wait_for_ready_workloads() {
  [ "$DRY_RUN" = "true" ] && return
  oc_run rollout status deployment/aiops-connected-ok -n "$NAMESPACE" --timeout=120s >/dev/null
  oc_run rollout status deployment/aiops-connected-scale-target -n "$NAMESPACE" --timeout=120s >/dev/null
}

main() {
  cd "$ROOT_DIR"
  require_safe_namespace_name
  check_cluster
  check_permissions
  log "[INFO] creating connected AIOps sandbox: $NAMESPACE"
  create_namespace
  apply_safety_labels
  apply_workloads
  wait_for_ready_workloads
  log "[PASS] connected sandbox ready: $NAMESPACE"
  emit_json "ready"
}

main "$@"
