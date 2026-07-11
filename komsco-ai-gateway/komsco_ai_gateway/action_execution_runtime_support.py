from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import HTTPException

from . import action_execution
from .action_execution import ActionExecutionConfig
from .test_pod_create import TestPodCreateSettings


FetchOcpJson = Callable[..., Awaitable[dict[str, Any] | None]]
SubmitOcpRequest = Callable[..., Awaitable[httpx.Response]]


@dataclass(frozen=True, slots=True)
class UnrestrictedCommandConfig:
    enabled: bool
    cwd: str
    timeout_seconds: int
    max_output_bytes: int


@dataclass(frozen=True, slots=True)
class UnrestrictedCommandDependencies:
    redact_sensitive: Callable[[Any], Any]
    now_rfc3339: Callable[[], str]
    build_trace_record: Callable[..., dict[str, Any]]
    log_audit_record: Callable[[Mapping[str, Any]], None]
    truncate_output: Callable[[bytes], tuple[str, bool]]
    resolve_timeout: Callable[[int | None], int]
    resolve_cwd: Callable[[str | None], str]


@dataclass(frozen=True, slots=True)
class ActionExecutionDependencies:
    fetch_ocp_json: FetchOcpJson
    fetch_ocp_json_for_action_execution: FetchOcpJson
    submit_ocp_request: SubmitOcpRequest


@dataclass(frozen=True, slots=True)
class PodInventoryCandidateDependencies:
    candidate_cache: MutableMapping[str, dict[str, Any]]
    build_candidates: Callable[..., list[dict[str, Any]]]
    parse_timestamp: Callable[[Any], datetime | None]


def remember_pod_inventory_action_candidates(
    req: Any,
    gateway_evidence: str | None,
    *,
    incident_id: str,
    run_id: str,
    dependencies: PodInventoryCandidateDependencies,
) -> list[dict[str, Any]]:
    candidates = dependencies.build_candidates(
        req,
        gateway_evidence,
        incident_id=incident_id,
        run_id=run_id,
    )
    now = datetime.now(UTC)
    for key, candidate in list(dependencies.candidate_cache.items()):
        expires_at = dependencies.parse_timestamp(candidate.get("expiresAt"))
        if expires_at and expires_at < now:
            dependencies.candidate_cache.pop(key, None)
    for candidate in candidates:
        dependencies.candidate_cache[str(candidate["id"])] = candidate
    return candidates


def truncate_unrestricted_output(
    value: bytes,
    *,
    config: UnrestrictedCommandConfig,
    redact_sensitive: Callable[[Any], Any],
) -> tuple[str, bool]:
    truncated = len(value) > config.max_output_bytes
    if truncated:
        value = value[: config.max_output_bytes]
    text = value.decode("utf-8", errors="replace")
    return str(redact_sensitive(text)), truncated


def unrestricted_command_timeout(
    requested_timeout: int | None,
    *,
    config: UnrestrictedCommandConfig,
) -> int:
    default_timeout = max(1, min(config.timeout_seconds, 3600))
    if requested_timeout is None:
        return default_timeout
    return max(1, min(int(requested_timeout), 3600))


def unrestricted_command_cwd(
    requested_cwd: str | None = None,
    *,
    config: UnrestrictedCommandConfig,
) -> str:
    cwd = requested_cwd or config.cwd or os.getcwd()
    return os.path.abspath(os.path.expanduser(cwd))


async def execute_unrestricted_command_request(
    req: Any,
    subject: Mapping[str, Any],
    *,
    config: UnrestrictedCommandConfig,
    dependencies: UnrestrictedCommandDependencies,
    request_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    if not config.enabled:
        raise HTTPException(
            status_code=403,
            detail="Experimental unrestricted command execution is disabled",
        )

    command = req.command.strip()
    if not command:
        raise HTTPException(status_code=400, detail="Command is empty")

    cwd = dependencies.resolve_cwd(req.cwd)
    if not os.path.isdir(cwd):
        raise HTTPException(status_code=400, detail=f"Command cwd does not exist: {cwd}")
    timeout_seconds = dependencies.resolve_timeout(req.timeoutSeconds)
    started_at = time.monotonic()
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=cwd,
        executable="/bin/bash",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    timed_out = False
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_seconds
        )
    except asyncio.TimeoutError:
        timed_out = True
        proc.kill()
        stdout_bytes, stderr_bytes = await proc.communicate()

    duration_ms = int((time.monotonic() - started_at) * 1000)
    stdout_text, stdout_truncated = dependencies.truncate_output(stdout_bytes)
    stderr_text, stderr_truncated = dependencies.truncate_output(stderr_bytes)
    exit_code = proc.returncode if proc.returncode is not None else -1
    result = {
        "apiVersion": "aiops.komsco/v1",
        "kind": "UnrestrictedCommandExecution",
        "metadata": {
            "name": f"unrestricted-command-{uuid.uuid4().hex[:16]}",
            "createdAt": dependencies.now_rfc3339(),
        },
        "spec": {
            "command": dependencies.redact_sensitive(command),
            "cwd": cwd,
            "durationMs": duration_ms,
            "exitCode": exit_code,
            "requestId": request_id or "",
            "runId": run_id or "",
            "stderr": stderr_text,
            "stderrTruncated": stderr_truncated,
            "stdout": stdout_text,
            "stdoutTruncated": stdout_truncated,
            "subject": dependencies.redact_sensitive(dict(subject)),
            "timedOut": timed_out,
            "timeoutSeconds": timeout_seconds,
            "warning": "Experimental dev-only unrestricted command execution ran with Gateway local process privileges.",
        },
    }
    dependencies.log_audit_record(
        dependencies.build_trace_record(
            action="unrestricted_command_executed",
            incident_id="dev-unrestricted",
            policy={
                "schemaVersion": "v1",
                "phase": "experimental-unrestricted-command",
                "decision": "executed",
                "mutationAllowed": True,
                "risk": "unrestricted",
                "reason": "User selected experimental unrestricted mode.",
            },
            request_id=request_id or f"req-{uuid.uuid4()}",
            run_id=run_id or f"run-{uuid.uuid4()}",
            subject=subject,
            target={
                "command": dependencies.redact_sensitive(command),
                "cwd": cwd,
                "durationMs": duration_ms,
                "exitCode": exit_code,
                "timedOut": timed_out,
            },
        )
    )
    return result


def unrestricted_command_response(result: Mapping[str, Any]) -> str:
    spec = result.get("spec") if isinstance(result.get("spec"), Mapping) else {}
    stdout_text = str(spec.get("stdout") or "")
    stderr_text = str(spec.get("stderr") or "")
    lines = [
        "실험용 무제한 명령 실행 결과입니다.",
        "",
        f"- Command: `{spec.get('command') or ''}`",
        f"- CWD: `{spec.get('cwd') or ''}`",
        f"- Exit code: `{spec.get('exitCode')}`",
        f"- Duration: `{spec.get('durationMs')}ms`",
        f"- Timed out: `{spec.get('timedOut')}`",
        "",
        "### stdout",
        "```text",
        stdout_text or "(empty)",
        "```",
    ]
    if stderr_text:
        lines.extend(["", "### stderr", "```text", stderr_text, "```"])
    return "\n".join(lines)


def append_query(path: str, query: Mapping[str, str]) -> str:
    return action_execution.append_query(path, query)


def executor_auth_header(config: ActionExecutionConfig) -> str:
    return action_execution.executor_auth_header(config)


def namespace_cleanup_review_execution_result(
    sealed_plan: Mapping[str, Any],
) -> dict[str, Any]:
    return action_execution.namespace_cleanup_review_execution_result(sealed_plan)


def test_pod_create_review_execution_result(
    sealed_plan: Mapping[str, Any],
) -> dict[str, Any]:
    return action_execution.test_pod_create_review_execution_result(sealed_plan)


def crashloop_test_pod_name(prefix: str, request_id: str, index: int) -> str:
    return action_execution.build_crashloop_test_pod_name(prefix, request_id, index)


def crashloop_test_pod_manifest(
    *,
    image: str,
    index: int,
    namespace: str,
    pod_name: str,
    request_id: str,
    settings: TestPodCreateSettings,
) -> dict[str, Any]:
    return action_execution.build_crashloop_test_pod_manifest(
        image=image,
        index=index,
        namespace=namespace,
        pod_name=pod_name,
        request_id=request_id,
        settings=settings,
    )


def pod_diagnostic_review_execution_result(
    sealed_plan: Mapping[str, Any],
) -> dict[str, Any]:
    return action_execution.pod_diagnostic_review_execution_result(sealed_plan)


def pod_fix_or_rollback_review_execution_result(
    sealed_plan: Mapping[str, Any],
) -> dict[str, Any]:
    return action_execution.pod_fix_or_rollback_review_execution_result(sealed_plan)


REVIEW_ONLY_ACTION_TOOLS = frozenset(
    {
        "namespace_cleanup_review",
        "test_pod_create_review",
        "pod_diagnostic_review",
        "pod_fix_or_rollback_review",
    }
)


def sealed_plan_is_review_only(sealed_plan: Mapping[str, Any]) -> bool:
    action = sealed_plan.get("action") if isinstance(sealed_plan.get("action"), Mapping) else {}
    tool_name = str(action.get("toolName") or "")
    normalized_parameters = (
        action.get("normalizedParameters")
        if isinstance(action.get("normalizedParameters"), Mapping)
        else {}
    )
    return tool_name in REVIEW_ONLY_ACTION_TOOLS or bool(
        normalized_parameters.get("reviewOnly")
    )


async def fetch_ocp_json_for_action_execution(
    client: httpx.AsyncClient,
    path: str,
    authorization: str,
    *,
    dependencies: ActionExecutionDependencies,
    required: bool = False,
    config: ActionExecutionConfig | None = None,
) -> dict[str, Any] | None:
    _ = config
    return await dependencies.fetch_ocp_json(
        client, path, authorization, required=required
    )


async def fetch_executor_live_state(
    client: httpx.AsyncClient,
    authorization: str,
    plan: Mapping[str, Any],
    *,
    config: ActionExecutionConfig,
    dependencies: ActionExecutionDependencies,
) -> dict[str, Any]:
    return await action_execution.fetch_executor_live_state(
        client,
        authorization,
        plan,
        config=config,
        fetch_ocp_json_func=dependencies.fetch_ocp_json_for_action_execution,
    )


async def submit_ocp_request(
    client: httpx.AsyncClient,
    authorization: str,
    *,
    method: str,
    path: str,
    content_type: str,
    body: Mapping[str, Any],
    config: ActionExecutionConfig,
) -> httpx.Response:
    return await action_execution.submit_ocp_request(
        client,
        authorization,
        method=method,
        path=path,
        content_type=content_type,
        body=body,
        config=config,
    )


async def verify_typed_action_postcondition(
    client: httpx.AsyncClient,
    authorization: str,
    sealed_plan: Mapping[str, Any],
    *,
    config: ActionExecutionConfig,
    dependencies: ActionExecutionDependencies,
) -> dict[str, Any]:
    return await action_execution.verify_typed_action_postcondition(
        client,
        authorization,
        sealed_plan,
        config=config,
        fetch_ocp_json_func=dependencies.fetch_ocp_json_for_action_execution,
    )


async def create_crashloop_test_pods_execution_result(
    sealed_plan: Mapping[str, Any],
    client: httpx.AsyncClient,
    authorization: str,
    *,
    config: ActionExecutionConfig,
    dependencies: ActionExecutionDependencies,
) -> dict[str, Any]:
    return await action_execution.create_crashloop_test_pods_execution_result(
        sealed_plan,
        client,
        authorization,
        config=config,
        submit_ocp_request_func=dependencies.submit_ocp_request,
        fetch_ocp_json_func=dependencies.fetch_ocp_json_for_action_execution,
    )


async def execute_typed_action_plan(
    sealed_plan: Mapping[str, Any],
    *,
    config: ActionExecutionConfig,
    dependencies: ActionExecutionDependencies,
) -> dict[str, Any]:
    return await action_execution.execute_typed_action_plan(
        sealed_plan,
        config=config,
        fetch_ocp_json_func=dependencies.fetch_ocp_json_for_action_execution,
        submit_ocp_request_func=dependencies.submit_ocp_request,
    )


async def execute_action_with_executor(
    sealed_plan: Mapping[str, Any],
    grant_reference: Mapping[str, Any],
    *,
    config: ActionExecutionConfig,
    dependencies: ActionExecutionDependencies,
    fallback_authorization: str | None = None,
) -> dict[str, Any]:
    return await action_execution.execute_action_with_executor(
        sealed_plan,
        grant_reference,
        config=config,
        fallback_authorization=fallback_authorization,
        fetch_ocp_json_func=dependencies.fetch_ocp_json_for_action_execution,
        submit_ocp_request_func=dependencies.submit_ocp_request,
    )
