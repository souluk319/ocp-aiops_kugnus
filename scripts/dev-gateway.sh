#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")/../komsco-ai-gateway"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements-dev.txt
export KOMSCO_AI_FORWARD_IMAGE_ATTACHMENTS_TO_OLS="${KOMSCO_AI_FORWARD_IMAGE_ATTACHMENTS_TO_OLS:-true}"
KOMSCO_AI_DEV_ECHO="${KOMSCO_AI_DEV_ECHO:-true}" uvicorn komsco_ai_gateway.main:app --reload --port 8080
