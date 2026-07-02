#!/usr/bin/env python3
"""Build the Ver.0.1.6 local demo preflight report.

The script is intentionally read-oriented. It diagnoses the Ubuntu/WSL demo
workspace, local dev endpoints, RAG readiness, and OpenShift read access
without installing or mutating company OCP/OKD resources.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import platform
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON_REPORT = REPO_ROOT / "docs/Ver.0.1.6/preflight-report.json"
DEFAULT_HTML_REPORT = REPO_ROOT / "docs/Ver.0.1.6/preflight-report.html"
DEFAULT_GATEWAY_URL = "http://127.0.0.1:18080"
DEFAULT_CONSOLE_URL = "http://127.0.0.1:9000/dashboards"
DEFAULT_AIOPS_ROUTE_URL = "http://127.0.0.1:9000/dashboards/aiops"
DEFAULT_DOCS_ROUTE_URL = "http://127.0.0.1:9000/dashboards/aiops/docs"
DEFAULT_PLUGIN_MANIFEST_URL = "http://127.0.0.1:9001/plugin-manifest.json"
EXPECTED_OCP_SERVER = "https://api.ocp.cywell.server:6443"


@dataclass
class CmdResult:
    ok: bool
    return_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    timeout: bool = False


@dataclass
class Check:
    id: str
    group: str
    title: str
    status: str
    required: bool
    next_action: str
    details: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0

    @property
    def ok(self) -> bool:
        return self.status == "pass"


def now_rfc3339() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def safe_preview(value: str, limit: int = 500) -> str:
    return value.replace("\r", "").strip()[:limit]


def run_cmd(args: list[str], *, timeout: int = 10, max_chars: int = 800) -> CmdResult:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            args,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return CmdResult(
            ok=proc.returncode == 0,
            return_code=proc.returncode,
            stdout=safe_preview(proc.stdout, max_chars),
            stderr=safe_preview(proc.stderr, max_chars),
            duration_ms=elapsed_ms(started),
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return CmdResult(
            ok=False,
            return_code=None,
            stdout=safe_preview(stdout, max_chars),
            stderr=safe_preview(stderr, max_chars),
            duration_ms=elapsed_ms(started),
            timeout=True,
        )


def run_secret_stdout(args: list[str], *, timeout: int = 10) -> tuple[bool, str, int]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            args,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode == 0, proc.stdout.strip(), elapsed_ms(started)
    except subprocess.TimeoutExpired:
        return False, "", elapsed_ms(started)


def tcp_open(host: str, port: int, timeout: float = 1.5) -> tuple[bool, str, int]:
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "", elapsed_ms(started)
    except OSError as exc:
        return False, str(exc)[:240], elapsed_ms(started)


def http_request(
    method: str,
    url: str,
    *,
    timeout: int,
    token: str = "",
    body: dict[str, Any] | None = None,
) -> tuple[bool, int, dict[str, Any], str, int]:
    started = time.monotonic()
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310 local preflight
            raw = response.read().decode("utf-8", errors="replace")
            payload: dict[str, Any] = {}
            try:
                parsed = json.loads(raw)
                payload = parsed if isinstance(parsed, dict) else {"value": parsed}
            except json.JSONDecodeError:
                payload = {"textPreview": raw[:300]}
            return 200 <= response.status < 400, response.status, payload, "", elapsed_ms(started)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")[:500]
        payload = {}
        try:
            parsed = json.loads(raw)
            payload = parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            payload = {"textPreview": raw}
        return False, exc.code, payload, "", elapsed_ms(started)
    except Exception as exc:  # noqa: BLE001 diagnostic script
        return False, 0, {}, str(exc)[:500], elapsed_ms(started)


def https_endpoint_answering(url: str, *, timeout: int) -> tuple[bool, int, str, int]:
    started = time.monotonic()
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"Accept": "*/*"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as response:  # noqa: S310 local preflight
            response.read(1)
            return True, response.status, "", elapsed_ms(started)
    except urllib.error.HTTPError as exc:
        exc.read(1)
        return True, exc.code, "", elapsed_ms(started)
    except Exception as exc:  # noqa: BLE001 diagnostic script
        return False, 0, str(exc)[:500], elapsed_ms(started)


def summarize_gateway_payload(check_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    spec = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
    if check_id == "gateway.aiops-status":
        capabilities = spec.get("capabilities") if isinstance(spec.get("capabilities"), dict) else {}
        safety = spec.get("safetyContract") if isinstance(spec.get("safetyContract"), dict) else {}
        rag = capabilities.get("rag") if isinstance(capabilities.get("rag"), dict) else {}
        return {
            "kind": payload.get("kind"),
            "mode": capabilities.get("mode") or safety.get("mode"),
            "mutationsEnabled": capabilities.get("mutationsEnabled"),
            "actionExecutorConfigured": capabilities.get("actionExecutorConfigured"),
            "ragStatus": rag.get("status"),
            "lightspeedStatus": safety.get("lightspeedStatus", {}).get("status")
            if isinstance(safety.get("lightspeedStatus"), dict)
            else None,
        }
    if check_id == "gateway.cluster-summary":
        nodes = payload.get("nodes") if isinstance(payload.get("nodes"), dict) else {}
        operators = payload.get("operators") if isinstance(payload.get("operators"), dict) else {}
        return {
            "kind": payload.get("kind"),
            "healthScore": payload.get("healthScore"),
            "apiUrl": payload.get("apiUrl"),
            "readyNodes": nodes.get("ready"),
            "totalNodes": nodes.get("total"),
            "availableOperators": operators.get("available"),
            "totalOperators": operators.get("total"),
            "degradedOperators": operators.get("degraded"),
        }
    if check_id == "rag.uploads":
        safety = spec.get("safety") if isinstance(spec.get("safety"), dict) else {}
        backend = spec.get("backend") if isinstance(spec.get("backend"), dict) else {}
        documents = spec.get("documents") if isinstance(spec.get("documents"), list) else []
        return {
            "kind": payload.get("kind"),
            "status": spec.get("status"),
            "reason": spec.get("reason"),
            "documentCount": len(documents),
            "backendStatus": backend.get("status"),
            "rawContentReturned": safety.get("rawContentReturned"),
        }
    if check_id == "rag.search":
        backend = spec.get("backend") if isinstance(spec.get("backend"), dict) else {}
        results = spec.get("results") if isinstance(spec.get("results"), list) else []
        safety = spec.get("safety") if isinstance(spec.get("safety"), dict) else {}
        return {
            "kind": payload.get("kind"),
            "status": spec.get("status"),
            "reason": spec.get("reason"),
            "resultCount": len(results),
            "backendStatus": backend.get("status"),
            "mockResultsAreProductionEvidence": safety.get("mockResultsAreProductionEvidence"),
        }
    if check_id == "gateway.auth-subject":
        return {
            "kind": payload.get("kind"),
            "username": payload.get("username"),
            "authenticatedByCluster": payload.get("authenticatedByCluster"),
            "groupsDigest": payload.get("groupsDigest"),
        }
    return {"kind": payload.get("kind") or payload.get("apiVersion") or "unknown"}


class Preflight:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.timeout = int(args.timeout)
        self.checks: list[Check] = []
        self.oc_token = ""

    def add(
        self,
        check_id: str,
        group: str,
        title: str,
        status: str,
        *,
        required: bool = True,
        next_action: str = "",
        details: dict[str, Any] | None = None,
        duration_ms: int = 0,
    ) -> None:
        self.checks.append(
            Check(
                id=check_id,
                group=group,
                title=title,
                status=status,
                required=required,
                next_action=next_action,
                details=details or {},
                duration_ms=duration_ms,
            )
        )

    def command_check(self, name: str, *, required: bool = True) -> None:
        started = time.monotonic()
        path = shutil.which(name)
        status = "pass" if path else "fail"
        self.add(
            f"tool.{name}",
            "toolchain",
            f"{name} command is available",
            status,
            required=required,
            next_action=f"Install {name} in Ubuntu/WSL or fix PATH.",
            details={"path": path or ""},
            duration_ms=elapsed_ms(started),
        )

    def check_workspace(self) -> None:
        release = platform.release().lower()
        is_wsl = "microsoft" in release or "wsl" in release
        path_text = str(REPO_ROOT)
        native = path_text.startswith("/home/") and not path_text.startswith("/mnt/")
        self.add(
            "workspace.location",
            "workspace",
            "Repository is in native Ubuntu filesystem",
            "pass" if native else "fail",
            next_action="Open the workspace under /home/kugnus/... instead of /mnt/c/...",
            details={"repo": path_text, "isWsl": is_wsl, "kernelRelease": platform.release()},
        )

        branch = run_cmd(["git", "branch", "--show-current"], timeout=5)
        head = run_cmd(["git", "rev-parse", "--short=12", "HEAD"], timeout=5)
        status = run_cmd(["git", "status", "--short", "--branch"], timeout=5, max_chars=2000)
        dirty_lines = [
            line
            for line in status.stdout.splitlines()
            if line and not line.startswith("##") and "preflight-report" not in line
        ]
        self.add(
            "workspace.git",
            "workspace",
            "Git branch and worktree are visible",
            "warn" if dirty_lines else "pass",
            required=False,
            next_action="Commit or review intentional local changes before publishing the demo baseline.",
            details={
                "branch": branch.stdout,
                "head": head.stdout,
                "statusShort": status.stdout,
                "dirtyNonReportLines": dirty_lines,
            },
            duration_ms=branch.duration_ms + head.duration_ms + status.duration_ms,
        )

    def check_env_file(self) -> None:
        started = time.monotonic()
        env_path = REPO_ROOT / ".env"
        if not env_path.exists():
            self.add(
                "workspace.env",
                "workspace",
                ".env exists and is private",
                "fail",
                next_action="Move the Windows .env into this Ubuntu repo and run chmod 600 .env.",
                details={"exists": False},
                duration_ms=elapsed_ms(started),
            )
            return

        mode = env_path.stat().st_mode & 0o777
        raw = env_path.read_bytes()
        crlf_count = raw.count(b"\r\n")
        ignored = run_cmd(["git", "check-ignore", "-q", ".env"], timeout=5)
        ok = mode & 0o077 == 0 and crlf_count == 0 and ignored.ok
        self.add(
            "workspace.env",
            "workspace",
            ".env exists, is LF-only, private, and ignored",
            "pass" if ok else "fail",
            next_action="Run chmod 600 .env, remove CRLF, and ensure .env stays git-ignored.",
            details={
                "exists": True,
                "mode": oct(mode)[2:],
                "crlfCount": crlf_count,
                "gitIgnored": ignored.ok,
                "activeKeyCount": sum(
                    1
                    for line in raw.decode("utf-8", errors="replace").splitlines()
                    if line.strip() and not line.lstrip().startswith("#") and "=" in line
                ),
            },
            duration_ms=elapsed_ms(started),
        )

    def check_toolchain(self) -> None:
        for name in ("bash", "curl", "task", "python3", "node", "yarn", "docker", "oc", "google-chrome"):
            self.command_check(name)

        node = run_cmd(["node", "--version"], timeout=5)
        yarn = run_cmd(["bash", "-ic", "yarn --version"], timeout=10)
        task = run_cmd(["task", "--version"], timeout=5)
        self.add(
            "tool.versions",
            "toolchain",
            "Core tool versions are callable from Ubuntu",
            "pass" if node.ok and yarn.ok and task.ok else "fail",
            next_action="Fix nvm/corepack/task availability in the Ubuntu shell.",
            details={"node": node.stdout, "yarn": yarn.stdout, "task": task.stdout},
            duration_ms=node.duration_ms + yarn.duration_ms + task.duration_ms,
        )

    def check_browser(self) -> None:
        version = run_cmd(["google-chrome", "--version"], timeout=10)
        dump = run_cmd(
            [
                "google-chrome",
                "--headless=new",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--dump-dom",
                "data:text/html,<title>kugnus-preflight</title><main>ok</main>",
            ],
            timeout=25,
            max_chars=1000,
        )
        ok = version.ok and dump.ok and "<main>ok</main>" in dump.stdout
        chrome_path = shutil.which("google-chrome") or ""
        self.add(
            "browser.chrome",
            "browser",
            "Ubuntu Chrome can run headless UI checks",
            "pass" if ok else "fail",
            next_action="Check ~/.local/bin/google-chrome and the Chrome for Testing local library wrapper.",
            details={
                "path": chrome_path,
                "version": version.stdout,
                "headlessDomContainsOk": "<main>ok</main>" in dump.stdout,
                "stderrPreview": dump.stderr[:240],
            },
            duration_ms=version.duration_ms + dump.duration_ms,
        )

    def check_docker_and_rag_db(self) -> None:
        info = run_cmd(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=10)
        self.add(
            "docker.daemon",
            "docker",
            "Docker daemon is reachable",
            "pass" if info.ok else "fail",
            next_action="Start Docker Desktop or the Docker daemon, then rerun preflight.",
            details={"serverVersion": info.stdout, "stderrPreview": info.stderr},
            duration_ms=info.duration_ms,
        )

        container = os.getenv("KOMSCO_AI_RAG_CONTAINER_NAME", "kugnus-rag-pgvector")
        ps = run_cmd(
            ["docker", "ps", "--filter", f"name=^/{container}$", "--format", "{{.Names}}"],
            timeout=10,
        )
        running = ps.ok and ps.stdout.strip() == container
        self.add(
            "rag.container",
            "rag",
            "Local pgvector RAG container is running",
            "pass" if running else "fail",
            next_action="Run task kugnus:rag:dev:up.",
            details={"container": container, "running": running},
            duration_ms=ps.duration_ms,
        )

        if not running:
            return

        pg = run_cmd(
            ["docker", "exec", container, "pg_isready", "-U", "komsco_aiops", "-d", "komsco_aiops"],
            timeout=10,
        )
        self.add(
            "rag.pg-isready",
            "rag",
            "Local pgvector database accepts connections",
            "pass" if pg.ok else "fail",
            next_action="Run task kugnus:rag:dev:up and inspect the container logs.",
            details={"stdout": pg.stdout, "stderrPreview": pg.stderr},
            duration_ms=pg.duration_ms,
        )

    def check_openshift(self) -> None:
        whoami = run_cmd(["oc", "whoami"], timeout=self.timeout)
        server = run_cmd(["oc", "whoami", "--show-server"], timeout=self.timeout)
        project = run_cmd(["oc", "project", "-q"], timeout=self.timeout)
        token_ok, token_value, token_duration_ms = run_secret_stdout(["oc", "whoami", "-t"], timeout=self.timeout)
        self.oc_token = token_value if token_ok and token_value else ""
        identity_ok = whoami.ok and bool(whoami.stdout.strip()) and server.ok and bool(server.stdout.strip())
        server_ok = server.stdout.strip() == EXPECTED_OCP_SERVER
        self.add(
            "openshift.identity",
            "openshift",
            "OpenShift identity and company API server are available",
            "pass" if identity_ok and server_ok and self.oc_token else "fail",
            next_action="Run oc login, then task kugnus:ocp:doctor if the API still does not answer.",
            details={
                "user": whoami.stdout,
                "server": server.stdout,
                "expectedServer": EXPECTED_OCP_SERVER,
                "project": project.stdout,
                "tokenAvailable": bool(self.oc_token),
                "stderrPreview": whoami.stderr or server.stderr,
            },
            duration_ms=whoami.duration_ms + server.duration_ms + project.duration_ms + token_duration_ms,
        )

        services = [
            ("openshift.lightspeed-service", "openshift-lightspeed", "lightspeed-app-server"),
            ("openshift.action-executor-service", "komsco-ai-dev", "komsco-ai-action-executor"),
        ]
        for check_id, namespace, service in services:
            result = run_cmd(
                ["oc", "-n", namespace, "get", f"svc/{service}", "-o", "jsonpath={.metadata.name}"],
                timeout=self.timeout,
            )
            self.add(
                check_id,
                "openshift",
                f"Can read {namespace}/{service}",
                "pass" if result.ok and result.stdout == service else "fail",
                next_action="Check VPN, oc login, RBAC, namespace, and service name.",
                details={"namespace": namespace, "service": service, "stdout": result.stdout, "stderrPreview": result.stderr},
                duration_ms=result.duration_ms,
            )

        for check_id, port, label, probe_url, probe_type in (
            ("openshift.lightspeed-port-forward", 18443, "Lightspeed", "https://127.0.0.1:18443/", "https"),
            (
                "openshift.action-executor-port-forward",
                18083,
                "Action Executor",
                "http://127.0.0.1:18083/healthz",
                "http",
            ),
        ):
            if probe_type == "https":
                ok, status_code, error, duration = https_endpoint_answering(probe_url, timeout=self.timeout)
                title = f"{label} local port-forward answers HTTPS"
                details = {
                    "host": "127.0.0.1",
                    "port": port,
                    "probeUrl": probe_url,
                    "statusCode": status_code,
                    "error": error,
                }
            else:
                ok, status_code, payload, error, duration = http_request("GET", probe_url, timeout=self.timeout)
                title = f"{label} local port-forward healthz responds"
                details = {
                    "host": "127.0.0.1",
                    "port": port,
                    "probeUrl": probe_url,
                    "statusCode": status_code,
                    "payload": payload,
                    "error": error,
                }
            self.add(
                check_id,
                "openshift",
                title,
                "pass" if ok else "fail",
                next_action="Run task kugnus:demo:resume to restore local port-forwarding.",
                details=details,
                duration_ms=duration,
            )

    def check_http_endpoint(
        self,
        check_id: str,
        group: str,
        title: str,
        method: str,
        url: str,
        *,
        required: bool = True,
        token: str = "",
        body: dict[str, Any] | None = None,
        next_action: str = "",
        ok_predicate: Any | None = None,
    ) -> None:
        ok, status_code, payload, error, duration = http_request(
            method,
            url,
            timeout=self.timeout,
            token=token,
            body=body,
        )
        summary = summarize_gateway_payload(check_id, payload) if payload else {}
        if ok and ok_predicate is not None:
            ok = bool(ok_predicate(summary, payload))
        details = {
            "url": url,
            "statusCode": status_code,
            "summary": summary,
            "error": error,
        }
        self.add(
            check_id,
            group,
            title,
            "pass" if ok else "fail",
            required=required,
            next_action=next_action,
            details=details,
            duration_ms=duration,
        )

    def check_local_endpoints(self) -> None:
        gateway = self.args.gateway_url.rstrip("/")
        self.check_http_endpoint(
            "gateway.healthz",
            "gateway",
            "Gateway healthz responds",
            "GET",
            f"{gateway}/healthz",
            next_action="Run task kugnus:demo:resume or inspect .tmp-kugnus-demo/gateway.log.",
        )
        if not self.oc_token:
            self.add(
                "gateway.authenticated-apis",
                "gateway",
                "Gateway authenticated API checks",
                "fail",
                next_action="Run oc login; authenticated Gateway APIs require the current user token.",
                details={"reason": "oc token unavailable"},
            )
            return

        for check_id, title, path in (
            ("gateway.auth-subject", "Gateway auth subject responds", "/v1/auth/subject"),
            ("gateway.aiops-status", "Gateway AIOps status responds", "/v1/aiops/status"),
            ("gateway.cluster-summary", "Gateway cluster summary responds", "/v1/cluster/summary"),
            ("gateway.aiops-overview", "Gateway AIOps overview responds", "/v1/aiops/overview"),
        ):
            self.check_http_endpoint(
                check_id,
                "gateway",
                title,
                "GET",
                f"{gateway}{path}",
                token=self.oc_token,
                next_action="Run task kugnus:demo:resume; if it repeats, inspect Gateway logs and oc login.",
            )

        self.check_http_endpoint(
            "rag.uploads",
            "rag",
            "Gateway lists uploaded RAG documents without raw content",
            "GET",
            f"{gateway}/v1/rag/uploads",
            token=self.oc_token,
            next_action="Run task kugnus:rag:dev:up, then task kugnus:rag:file-upload:smoke.",
            ok_predicate=lambda summary, _payload: summary.get("rawContentReturned") is False
            and int(summary.get("documentCount") or 0) > 0,
        )
        self.check_http_endpoint(
            "rag.search",
            "rag",
            "Gateway retrieves RAG evidence for the demo query",
            "POST",
            f"{gateway}/v1/rag/search",
            token=self.oc_token,
            body={
                "query": "OpenShift alert CrashLoopBackOff ImagePullBackOff restart runbook",
                "topK": 5,
                "includeContent": False,
            },
            next_action="Run task kugnus:rag:dev:up and task kugnus:rag:file-upload:smoke.",
            ok_predicate=lambda summary, _payload: summary.get("status") == "collected"
            and int(summary.get("resultCount") or 0) > 0
            and summary.get("mockResultsAreProductionEvidence") is False,
        )

    def check_console(self) -> None:
        self.check_http_endpoint(
            "console.dashboard",
            "console",
            "Local console dashboard route responds",
            "GET",
            self.args.console_url,
            next_action="Run task kugnus:dev:fe or task kugnus:demo:resume.",
        )
        self.check_http_endpoint(
            "console.aiops-route",
            "console",
            "Cywell AI route responds",
            "GET",
            self.args.aiops_route_url,
            next_action="Run task kugnus:dev:fe and verify the local console bridge.",
        )
        self.check_http_endpoint(
            "console.docs-route",
            "console",
            "Cywell AI Docs/RAG route responds",
            "GET",
            self.args.docs_route_url,
            next_action="Run task kugnus:dev:fe and verify the Docs route registration.",
        )
        self.check_http_endpoint(
            "console.plugin-manifest",
            "console",
            "Plugin manifest responds",
            "GET",
            self.args.plugin_manifest_url,
            next_action="Run task kugnus:dev:fe or inspect the webpack dev server on 9001.",
        )

    def run(self) -> dict[str, Any]:
        self.check_workspace()
        self.check_env_file()
        self.check_toolchain()
        self.check_browser()
        self.check_docker_and_rag_db()
        self.check_openshift()
        self.check_local_endpoints()
        self.check_console()
        return self.build_report()

    def build_report(self) -> dict[str, Any]:
        serialized_checks = [
            {
                "id": item.id,
                "group": item.group,
                "title": item.title,
                "status": item.status,
                "required": item.required,
                "durationMs": item.duration_ms,
                "nextAction": item.next_action,
                "details": item.details,
            }
            for item in self.checks
        ]
        blockers = [item for item in serialized_checks if item["required"] and item["status"] == "fail"]
        warnings = [item for item in serialized_checks if item["status"] == "warn" or (not item["required"] and item["status"] == "fail")]
        result = "fail" if blockers else ("warn" if warnings else "pass")
        return {
            "apiVersion": "aiops.komsco/v1alpha1",
            "kind": "KugnusDemoPreflightReport",
            "generatedAt": now_rfc3339(),
            "summary": {
                "result": result,
                "readyForOfficialDemo": len(blockers) == 0,
                "blockerCount": len(blockers),
                "warningCount": len(warnings),
                "blockers": [
                    {"id": item["id"], "title": item["title"], "nextAction": item["nextAction"]}
                    for item in blockers
                ],
                "warnings": [
                    {"id": item["id"], "title": item["title"], "nextAction": item["nextAction"]}
                    for item in warnings
                ],
            },
            "targets": {
                "gatewayUrl": self.args.gateway_url,
                "consoleUrl": self.args.console_url,
                "aiopsRouteUrl": self.args.aiops_route_url,
                "docsRouteUrl": self.args.docs_route_url,
                "pluginManifestUrl": self.args.plugin_manifest_url,
                "expectedOpenShiftServer": EXPECTED_OCP_SERVER,
            },
            "checks": serialized_checks,
            "officialDemo": {
                "scenario": "docs/Ver.0.1.6/official-demo-scenario.md",
                "contract": "docs/Ver.0.1.6/preflight-contract.md",
                "question": "최근 OpenShift 경고와 우선 확인할 항목을 실제 근거와 추가 확인 필요 항목으로 구분해서 정리해줘.",
                "route": "http://localhost:9000/dashboards/aiops",
                "supplementalEvidenceCommands": [
                    "task kugnus:runtime:smoke",
                    "task kugnus:rag:file-upload:smoke",
                    "task kugnus:rag:chat:smoke",
                    "task kugnus:ui:verify",
                ],
                "safetyBoundary": [
                    "No OCP install/deploy/apply/delete/patch/scale/exec in preflight.",
                    "Gateway fallback must not be claimed as fallback-free Lightspeed success.",
                    "RAG raw content stays hidden; report only stores metadata and summaries.",
                ],
            },
        }


def write_html_report(report: dict[str, Any], html_path: Path) -> None:
    summary = report["summary"]
    result = str(summary["result"])
    checks = report["checks"]
    rows = []
    for item in checks:
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        summary_text = json.dumps(details.get("summary", details), ensure_ascii=False, indent=2)
        rows.append(
            "<tr>"
            f"<td><span class=\"badge {html.escape(str(item['status']))}\">{html.escape(str(item['status']).upper())}</span></td>"
            f"<td>{html.escape(str(item['group']))}</td>"
            f"<td><strong>{html.escape(str(item['title']))}</strong><br><code>{html.escape(str(item['id']))}</code></td>"
            f"<td>{html.escape(str(item['nextAction'] or '-'))}</td>"
            f"<td><pre>{html.escape(summary_text[:1200])}</pre></td>"
            "</tr>"
        )

    blocker_items = "".join(
        f"<li><code>{html.escape(str(item['id']))}</code> {html.escape(str(item['title']))}: {html.escape(str(item['nextAction']))}</li>"
        for item in summary.get("blockers", [])
    )
    if not blocker_items:
        blocker_items = "<li>blocker 없음</li>"
    warning_items = "".join(
        f"<li><code>{html.escape(str(item['id']))}</code> {html.escape(str(item['title']))}: {html.escape(str(item['nextAction']))}</li>"
        for item in summary.get("warnings", [])
    )
    if not warning_items:
        warning_items = "<li>warning 없음</li>"

    doc = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Ver.0.1.6 Demo Preflight Report</title>
  <style>
    :root {{ --bg: #f5f7fb; --paper: #fff; --ink: #111827; --muted: #5f6f86; --line: #d8e0ec; --green: #12805c; --amber: #b7791f; --red: #c9190b; --blue: #0066cc; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--ink); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.55; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 34px 20px 60px; }}
    article {{ background: var(--paper); border: 1px solid var(--line); border-radius: 12px; padding: 32px; box-shadow: 0 18px 38px rgba(15, 23, 42, 0.08); }}
    h1 {{ margin: 0 0 8px; font-size: 31px; letter-spacing: 0; }}
    h2 {{ margin: 34px 0 12px; padding-top: 14px; border-top: 1px solid var(--line); font-size: 22px; }}
    p {{ margin: 0 0 10px; }}
    code {{ padding: 2px 5px; border-radius: 5px; background: #eef2f7; }}
    table {{ width: 100%; border-collapse: collapse; border: 1px solid var(--line); }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ background: #f4f7fb; color: #324055; font-size: 13px; }}
    tr:last-child td {{ border-bottom: 0; }}
    pre {{ max-width: 360px; overflow: auto; margin: 0; padding: 8px; border-radius: 8px; background: #0f172a; color: #e5edf9; font-size: 12px; }}
    .badge {{ display: inline-block; min-width: 58px; padding: 3px 7px; border-radius: 999px; color: #fff; text-align: center; font-size: 12px; font-weight: 700; }}
    .badge.pass {{ background: var(--green); }}
    .badge.warn {{ background: var(--amber); }}
    .badge.fail {{ background: var(--red); }}
    .summary {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 20px 0; }}
    .tile {{ border: 1px solid var(--line); border-radius: 8px; padding: 13px; background: #fbfdff; }}
    .tile strong {{ display: block; font-size: 24px; }}
    .muted {{ color: var(--muted); }}
  </style>
</head>
<body>
  <main>
    <article>
      <h1>Ver.0.1.6 Demo Preflight Report</h1>
      <p class="muted">Generated at <code>{html.escape(str(report['generatedAt']))}</code></p>
      <div class="summary">
        <div class="tile"><span>Result</span><strong>{html.escape(result.upper())}</strong></div>
        <div class="tile"><span>Ready</span><strong>{'YES' if summary.get('readyForOfficialDemo') else 'NO'}</strong></div>
        <div class="tile"><span>Blockers</span><strong>{html.escape(str(summary.get('blockerCount')))}</strong></div>
        <div class="tile"><span>Warnings</span><strong>{html.escape(str(summary.get('warningCount')))}</strong></div>
      </div>
      <h2>Blockers</h2>
      <ul>{blocker_items}</ul>
      <h2>Warnings</h2>
      <ul>{warning_items}</ul>
      <h2>Official Demo</h2>
      <p>Scenario: <code>docs/Ver.0.1.6/official-demo-scenario.md</code></p>
      <p>Question: <code>{html.escape(str(report['officialDemo']['question']))}</code></p>
      <h2>Checks</h2>
      <table>
        <thead>
          <tr><th>Status</th><th>Group</th><th>Check</th><th>Next action</th><th>Details</th></tr>
        </thead>
        <tbody>
          {''.join(rows)}
        </tbody>
      </table>
    </article>
  </main>
</body>
</html>
"""
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(doc, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-report", default=os.getenv("KUGNUS_PREFLIGHT_JSON_REPORT", str(DEFAULT_JSON_REPORT)))
    parser.add_argument("--html-report", default=os.getenv("KUGNUS_PREFLIGHT_HTML_REPORT", str(DEFAULT_HTML_REPORT)))
    parser.add_argument("--timeout", default=os.getenv("KUGNUS_PREFLIGHT_TIMEOUT_SECONDS", "10"))
    parser.add_argument("--gateway-url", default=os.getenv("KUGNUS_GATEWAY_URL", DEFAULT_GATEWAY_URL))
    parser.add_argument("--console-url", default=os.getenv("KUGNUS_CONSOLE_URL", DEFAULT_CONSOLE_URL))
    parser.add_argument("--aiops-route-url", default=os.getenv("KUGNUS_AIOPS_ROUTE_URL", DEFAULT_AIOPS_ROUTE_URL))
    parser.add_argument("--docs-route-url", default=os.getenv("KUGNUS_DOCS_ROUTE_URL", DEFAULT_DOCS_ROUTE_URL))
    parser.add_argument(
        "--plugin-manifest-url",
        default=os.getenv("KUGNUS_PLUGIN_MANIFEST_URL", DEFAULT_PLUGIN_MANIFEST_URL),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = Preflight(args).run()
    json_path = Path(args.json_report).resolve()
    html_path = Path(args.html_report).resolve()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_html_report(report, html_path)

    result = str(report["summary"]["result"]).upper()
    print(f"Kugnus demo preflight: {result}")
    print(f"JSON report: {json_path}")
    print(f"HTML report: {html_path}")
    for blocker in report["summary"]["blockers"]:
        print(f"[BLOCKER] {blocker['id']}: {blocker['nextAction']}")
    for warning in report["summary"]["warnings"]:
        print(f"[WARN] {warning['id']}: {warning['nextAction']}")
    return 1 if report["summary"]["result"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
