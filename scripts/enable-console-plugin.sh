#!/usr/bin/env bash

set -euo pipefail

PLUGIN_NAME="${PLUGIN_NAME:-komsco-ai-console-plugin}"
DISABLED_LIGHTSPEED_PLUGIN="${DISABLED_LIGHTSPEED_PLUGIN:-lightspeed-console-plugin}"

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
      --arg disabled "$DISABLED_LIGHTSPEED_PLUGIN" \
      '.spec.plugins // []
       | map(select(. != $disabled))
       | . + [$plugin]
       | unique'
)"

oc patch console.operator.openshift.io cluster \
  --type=merge \
  -p "{\"spec\":{\"plugins\":$plugins}}"
