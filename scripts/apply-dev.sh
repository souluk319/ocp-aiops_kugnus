#!/usr/bin/env bash

set -euo pipefail

if ! command -v oc >/dev/null 2>&1; then
  echo "oc CLI is required. Install it or add it to PATH, then run oc login." >&2
  exit 1
fi

oc apply -k openshift/overlays/dev
