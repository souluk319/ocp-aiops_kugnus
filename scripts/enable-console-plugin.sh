#!/usr/bin/env bash

set -euo pipefail

PLUGIN_NAME="${PLUGIN_NAME:-komsco-ai-console-plugin-kugnus}"

if [[ "${KOMSCO_AIOPS_ALLOW_ENABLE_CONSOLE_PLUGIN:-}" != "komsco-ai-console-plugin-kugnus" ]]; then
  echo "Refusing to patch console active plugins without explicit Kugnus approval." >&2
  echo "Set KOMSCO_AIOPS_ALLOW_ENABLE_CONSOLE_PLUGIN=komsco-ai-console-plugin-kugnus only after install verification." >&2
  exit 1
fi

if [[ "${PLUGIN_NAME}" != "komsco-ai-console-plugin-kugnus" ]]; then
  echo "Refusing to enable protected or non-Kugnus ConsolePlugin: ${PLUGIN_NAME}" >&2
  exit 1
fi

if ! command -v oc >/dev/null 2>&1; then
  echo "oc CLI is required. Install it or add it to PATH, then run oc login." >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required to preserve the existing console plugin list safely." >&2
  exit 1
fi

plugins="$(
  oc get console.operator.openshift.io cluster -o json \
    | jq \
      --arg plugin "$PLUGIN_NAME" \
      '.spec.plugins // []
       | . + [$plugin]
       | unique'
)"

oc patch console.operator.openshift.io cluster \
  --type=merge \
  -p "{\"spec\":{\"plugins\":$plugins}}"
