from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STANDARD_LLM_VARIABLES = (
    "KOMSCO_AI_LLM_PROVIDER",
    "KOMSCO_AI_LLM_API_STYLE",
    "KOMSCO_AI_LLM_BASE_URL",
    "KOMSCO_AI_LLM_MODEL",
)


def test_retired_home_server_variables_do_not_configure_llm() -> None:
    # Given: only the retired personal-server LLM variables are present.
    environment = os.environ.copy()
    for name in STANDARD_LLM_VARIABLES:
        environment.pop(name, None)
    environment.update(
        {
            "KUGNUS_HOME_LLM_URL": "http://home.invalid:11434",
            "KUGNUS_HOME_LLM_MODEL": "retired-personal-model",
        }
    )

    # When: Gateway LLM configuration is loaded in an isolated process.
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from komsco_ai_gateway import main; "
                "print(repr((main.LLM_BASE_URL, main.LLM_MODEL, main.LLM_API_STYLE)))"
            ),
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    # Then: the retired variables do not activate an LLM connection.
    assert completed.stdout.strip() == "('', '', 'lightspeed')"
