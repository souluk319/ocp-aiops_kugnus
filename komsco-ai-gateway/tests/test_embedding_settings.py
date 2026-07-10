from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STANDARD_EMBEDDING_VARIABLES = (
    "KOMSCO_AI_EMBEDDING_BASE_URL",
    "KOMSCO_AI_RAG_EMBEDDING_SERVICE_URL",
    "KOMSCO_AI_EMBEDDING_MODEL",
    "KOMSCO_AI_RAG_EMBEDDING_MODEL",
    "KOMSCO_AI_EMBEDDING_DIMENSIONS",
    "KOMSCO_AI_RAG_VECTOR_DIMENSIONS",
    "KOMSCO_AI_EMBEDDING_TIMEOUT_SECONDS",
    "KOMSCO_AI_RAG_EMBEDDING_TIMEOUT_SECONDS",
)


def test_sweet12_legacy_home_variables_do_not_configure_embedding() -> None:
    # Given: only the retired home-server embedding variables are present.
    environment = os.environ.copy()
    for name in STANDARD_EMBEDDING_VARIABLES:
        environment.pop(name, None)
    environment.update(
        {
            "KUGNUS_HOME_EMBED_URL": "http://home.invalid:11435",
            "KUGNUS_HOME_EMBED_MODEL": "retired-home-model",
            "KUGNUS_HOME_EMBED_DIMENSIONS": "768",
            "KUGNUS_HOME_EMBED_TIMEOUT_MS": "120000",
        }
    )

    # When: Gateway embedding configuration is loaded in an isolated process.
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from komsco_ai_gateway import rag_pgvector as r; "
                "print(repr((r.RAG_EMBEDDING_SERVICE_URL, r.RAG_EMBEDDING_MODEL, "
                "r.RAG_VECTOR_DIMENSIONS, r.RAG_EMBEDDING_TIMEOUT_SECONDS)))"
            ),
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    # Then: no embedding service is configured from the retired variables.
    assert completed.stdout.strip() == "('', '', 0, 10.0)"
