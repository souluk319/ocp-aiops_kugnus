#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_PATH="${REPORT_PATH:-${ROOT_DIR}/docs/Ver.0.1.2/aiops-scenario-evaluation-report.json}"
RUN_UI_VERIFY="${RUN_UI_VERIFY:-true}"

cd "$ROOT_DIR"

load_node() {
  if command -v node >/dev/null 2>&1; then
    return
  fi

  local nvm_dir="${NVM_DIR:-${HOME}/.nvm}"
  if [ -s "${nvm_dir}/nvm.sh" ]; then
    # shellcheck source=/dev/null
    . "${nvm_dir}/nvm.sh"
  fi
}

select_python() {
  local candidates=(
    "${ROOT_DIR}/komsco-ai-gateway/.venv/bin/python"
    "/tmp/ocp-aiops-stage2-venv/bin/python"
    "/tmp/ocp-aiops-pytest-venv/bin/python"
    "python3"
    "python"
  )

  for candidate in "${candidates[@]}"; do
    if command -v "$candidate" >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return
    fi
  done

  echo "Python runtime not found" >&2
  exit 1
}

load_node
PYTHON_BIN="$(select_python)"
STAGE6_DIFF_PATHS=(
  "Taskfile.yml"
  "scripts/verify-kugnus-ui.mjs"
  "scripts/kugnus-stage6-verify.sh"
  "evals/aiops-scenarios/01-pod-restart-rca.json"
  "evals/aiops-scenarios/02-crashloopbackoff.json"
  "evals/aiops-scenarios/03-imagepullbackoff.json"
  "docs/Ver.0.1.2/aiops-scenario-evaluation-report.json"
  "docs/Ver.0.1.2/functional-connection-report.md"
  "docs/Ver.0.1.2/operation-scenarios.md"
  "docs/Ver.0.1.2/stage-6-review.md"
)

echo "== Ref stamp =="
git status --short --branch
git log -1 --oneline --decorate

echo "== Static checks =="
git diff --check -- "${STAGE6_DIFF_PATHS[@]}"
node --check ./scripts/verify-kugnus-ui.mjs

echo "== Gateway tests =="
"$PYTHON_BIN" -m pytest komsco-ai-gateway -q

echo "== Frontend build =="
(
  cd komsco-ai-console-plugin
  corepack yarn build
)

echo "== Offline AIOps scenarios =="
"$PYTHON_BIN" scripts/evaluate-aiops-scenarios.py \
  --scenarios evals/aiops-scenarios \
  --report "$REPORT_PATH"

echo "== Local API smoke =="
curl -sS http://127.0.0.1:18080/healthz
printf '\n'
curl -sS -i http://127.0.0.1:18080/v1/aiops/overview | sed -n '1,12p'

echo "== OCP evidence-check snapshot =="
oc whoami
oc whoami --show-server
oc get consoleplugin komsco-ai-console-plugin lightspeed-console-plugin --no-headers

if [ "$RUN_UI_VERIFY" = "true" ]; then
  echo "== UI verifier =="
  task kugnus:ui:verify
else
  echo "== UI verifier skipped =="
  echo "RUN_UI_VERIFY=false"
fi
