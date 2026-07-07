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

is_wsl_runtime() {
  grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null
}

http_url_authority() {
  local url="$1"
  local rest="${url#*://}"

  if [ "$rest" = "$url" ]; then
    return 1
  fi

  printf '%s' "${rest%%/*}"
}

http_url_host() {
  local authority

  authority="$(http_url_authority "$1" 2>/dev/null || true)"
  if [ -z "$authority" ]; then
    return 1
  fi
  printf '%s' "${authority%%:*}"
}

http_url_port() {
  local authority
  local port

  authority="$(http_url_authority "$1" 2>/dev/null || true)"
  if [ -z "$authority" ] || [[ "$authority" != *:* ]]; then
    return 1
  fi
  port="${authority##*:}"
  if [[ "$port" =~ ^[0-9]+$ ]]; then
    printf '%s' "$port"
  else
    return 1
  fi
}

host_is_current_wsl_ip() {
  local host="$1"
  local ip

  for ip in $(hostname -I 2>/dev/null || true); do
    if [ "$host" = "$ip" ]; then
      return 0
    fi
  done

  return 1
}

normalize_gateway_endpoint_for_console_bridge() {
  local endpoint="${1:-}"
  local default_port="${2:-18080}"
  local host
  local port

  if [ -z "$endpoint" ]; then
    endpoint="http://localhost:${default_port}"
  fi

  if ! is_wsl_runtime || ! command -v docker >/dev/null 2>&1; then
    printf '%s\n' "$endpoint"
    return
  fi

  host="$(http_url_host "$endpoint" 2>/dev/null || true)"
  port="$(http_url_port "$endpoint" 2>/dev/null || true)"
  port="${port:-$default_port}"

  case "$host" in
    "" | localhost | 127.0.0.1 | host.docker.internal)
      printf 'http://host.docker.internal:%s\n' "$port"
      return
      ;;
  esac

  if host_is_current_wsl_ip "$host"; then
    printf 'http://host.docker.internal:%s\n' "$port"
    return
  fi

  printf '%s\n' "$endpoint"
}
