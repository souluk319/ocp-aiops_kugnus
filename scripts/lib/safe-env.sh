#!/usr/bin/env bash

env_value_is_placeholder() {
  local value="${1:-}"

  [[ "$value" == *'<'* || "$value" == *'>'* ]]
}

unset_placeholder_env_vars() {
  local key
  local value

  for key in "$@"; do
    value="${!key:-}"
    if env_value_is_placeholder "$value"; then
      unset "$key"
    fi
  done
}

trim_env_value() {
  local value="$1"

  printf '%s' "$value" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//'
}

load_env_file() {
  local file="$1"
  local key
  local line
  local value

  if [ ! -f "$file" ]; then
    return
  fi

  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    if [[ "$line" =~ ^[[:space:]]*$ ]] || [[ "$line" =~ ^[[:space:]]*# ]]; then
      continue
    fi
    if [[ "$line" != *=* ]]; then
      continue
    fi

    key="$(trim_env_value "${line%%=*}")"
    key="${key#export }"
    value="$(trim_env_value "${line#*=}")"

    if ! [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      continue
    fi
    if [[ "$value" == \"*\" && "$value" == *\" ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
      value="${value:1:${#value}-2}"
    fi
    if env_value_is_placeholder "$value"; then
      continue
    fi

    export "$key=$value"
  done <"$file"
}

oc_quick() {
  local seconds="${OPENSHIFT_OC_TIMEOUT_SECONDS:-12}"

  timeout "${seconds}s" oc "$@"
}

run_shell_with_timeout() {
  local seconds="${OPENSHIFT_LOGIN_TIMEOUT_SECONDS:-30}"
  local command="$1"

  timeout "${seconds}s" bash -lc "$command"
}
