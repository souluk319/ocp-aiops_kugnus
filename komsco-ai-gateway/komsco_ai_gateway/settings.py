import os
import re


def parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_int(value: str | None, *, default: int, minimum: int = 0, maximum: int | None = None) -> int:
    try:
        parsed = int(value) if value is not None and value.strip() != "" else default
    except ValueError:
        parsed = default

    parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def parse_ols_verify(value: str | None) -> bool | str:
    if value is None or value.strip() == "":
        return True

    normalized = value.strip().lower()
    if normalized in {"0", "false", "no", "off"}:
        return False
    if normalized in {"1", "true", "yes", "on"}:
        return True

    return value


def first_env_value(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip() != "":
            return value.strip()
    return ""


def parse_float_env(*names: str, default: float) -> float:
    value = first_env_value(*names)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def parse_millis_env_as_seconds(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value) / 1000.0
    except ValueError:
        return default


def infer_llm_api_style(provider: str, base_url: str, legacy_home_url: str) -> str:
    normalized_provider = provider.strip().lower()
    if normalized_provider in {"ollama", "ollama-native"}:
        return "ollama"
    if normalized_provider in {"lightspeed", "ols", "openshift-lightspeed"}:
        return "lightspeed"
    if legacy_home_url:
        return "ollama"
    if ":11434" in base_url:
        return "ollama"
    return "lightspeed"


def infer_embedding_api_style(provider: str, base_url: str, legacy_home_url: str) -> str:
    normalized_provider = provider.strip().lower()
    if normalized_provider in {"ollama", "ollama-native"}:
        return "ollama"
    if normalized_provider in {"openai", "openai-compatible", "tei-openai"}:
        return "openai"
    if normalized_provider == "tei":
        return "tei"
    if legacy_home_url:
        return "ollama"
    if ":11435" in base_url or base_url.rstrip("/").endswith("/api/embed"):
        return "ollama"
    if re.search(r"/v\d+(?:/|$)", base_url):
        return "openai"
    return ""
