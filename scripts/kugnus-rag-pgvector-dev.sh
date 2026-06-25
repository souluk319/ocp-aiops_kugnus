#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_NAME="${KOMSCO_AI_RAG_CONTAINER_NAME:-kugnus-rag-pgvector}"
IMAGE="${KOMSCO_AI_RAG_IMAGE:-pgvector/pgvector:pg16}"
HOST_PORT="${KOMSCO_AI_RAG_HOST_PORT:-15432}"
DB_NAME="${KOMSCO_AI_RAG_DB:-komsco_aiops}"
DB_USER="${KOMSCO_AI_RAG_USER:-komsco_aiops}"
DSN="postgresql://${DB_USER}@127.0.0.1:${HOST_PORT}/${DB_NAME}"

if ! docker ps --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
  if docker ps -a --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
    docker start "${CONTAINER_NAME}" >/dev/null
  else
    docker run -d \
      --name "${CONTAINER_NAME}" \
      -e POSTGRES_DB="${DB_NAME}" \
      -e POSTGRES_USER="${DB_USER}" \
      -e POSTGRES_HOST_AUTH_METHOD=trust \
      -p "127.0.0.1:${HOST_PORT}:5432" \
      "${IMAGE}" >/dev/null
  fi
fi

"${ROOT_DIR}/komsco-ai-gateway/.venv/bin/python" -m pip install -q 'psycopg[binary]>=3.2,<4'

for _ in $(seq 1 60); do
  if KOMSCO_AI_RAG_BACKEND_URL="${DSN}" "${ROOT_DIR}/komsco-ai-gateway/.venv/bin/python" - <<'PY' >/dev/null 2>&1
import os
import psycopg
with psycopg.connect(os.environ['KOMSCO_AI_RAG_BACKEND_URL']) as conn:
    conn.execute('CREATE EXTENSION IF NOT EXISTS vector')
PY
  then
    break
  fi
  sleep 1
done

cat <<EOF
RAG pgvector dev backend is ready.
Container: ${CONTAINER_NAME}
DSN env: KOMSCO_AI_RAG_BACKEND_URL=${DSN}
Use with Gateway:
  KOMSCO_AI_RAG_BACKEND_URL='${DSN}' KOMSCO_AI_RAG_EMBEDDING_MODEL=hashing-bow-v1 KOMSCO_AI_RAG_VECTOR_DIMENSIONS=64 task kugnus:dev:be:execute
EOF
