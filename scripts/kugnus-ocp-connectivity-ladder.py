#!/usr/bin/env python3
"""Diagnose the WSL -> company OCP path without persisting secrets.

The Lightspeed strict gate depends on several layers that can fail
independently: DNS, TCP, HTTPS API, oc identity, bearer token, OpenShift
SelfSubjectReview, and the local Gateway status endpoint. This script records
which layer is currently broken so the RCA demo work does not keep circling
around the same vague "oc login" symptom.
"""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = REPO_ROOT / "docs/Ver.0.1.5/ocp-connectivity-ladder-report.json"
DEFAULT_API_SERVER = "https://api.ocp.cywell.server:6443"
DEFAULT_GATEWAY = "http://127.0.0.1:18080"
CHECK_ORDER = [
    ("dns", "DNS lookup failed"),
    ("tcp", "TCP 6443 connection failed"),
    ("tls", "TLS handshake failed"),
    ("versionEndpoint", "OCP /version did not respond"),
    ("ocServer", "oc cannot read current server"),
    ("ocIdentity", "oc whoami did not return a non-empty user"),
    ("ocToken", "oc token is unavailable"),
    ("selfSubjectReview", "SelfSubjectReview failed"),
    ("gatewayStatus", "local Gateway /v1/aiops/status failed"),
]


def now_rfc3339() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def git_value(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def safe_error(exc: BaseException) -> str:
    return str(exc).replace("\n", " ")[:500]


def run_cmd(args: list[str], timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            args,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": result.returncode == 0,
            "returnCode": result.returncode,
            "durationMs": elapsed_ms(started),
            "stdout": result.stdout.strip()[:1000],
            "stderr": result.stderr.strip()[:1000],
            "timeoutSeconds": timeout,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returnCode": None,
            "durationMs": elapsed_ms(started),
            "stdout": (exc.stdout or "").strip()[:1000] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "").strip()[:1000] if isinstance(exc.stderr, str) else "",
            "timeout": True,
            "timeoutSeconds": timeout,
        }


def text_file_preview(path: str, max_chars: int = 1200) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")[:max_chars]
    except OSError as exc:
        return f"unavailable: {safe_error(exc)}"


def dns_check(host: str, timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    socket.setdefaulttimeout(timeout)
    try:
        records = socket.getaddrinfo(host, None)
        addresses = sorted({item[4][0] for item in records})
        return {"ok": bool(addresses), "addresses": addresses, "durationMs": elapsed_ms(started)}
    except Exception as exc:  # noqa: BLE001 diagnostic script
        return {"ok": False, "error": safe_error(exc), "durationMs": elapsed_ms(started)}


def tcp_check(host: str, port: int, timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"ok": True, "durationMs": elapsed_ms(started)}
    except Exception as exc:  # noqa: BLE001 diagnostic script
        return {"ok": False, "error": safe_error(exc), "durationMs": elapsed_ms(started)}


def tls_check(host: str, port: int, timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        with socket.create_connection((host, port), timeout=timeout) as raw:
            with context.wrap_socket(raw, server_hostname=host) as conn:
                cert = conn.getpeercert()
                return {
                    "ok": True,
                    "durationMs": elapsed_ms(started),
                    "cipher": conn.cipher()[0] if conn.cipher() else "",
                    "subject": str(cert.get("subject", ""))[:300] if isinstance(cert, dict) else "",
                }
    except Exception as exc:  # noqa: BLE001 diagnostic script
        return {"ok": False, "error": safe_error(exc), "durationMs": elapsed_ms(started)}


def http_json_request(
    url: str,
    *,
    token: str = "",
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout: int,
) -> dict[str, Any]:
    started = time.monotonic()
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, headers=headers, data=data, method=method)
    context = ssl._create_unverified_context()  # noqa: S323 local diagnostic for private OCP CA
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:  # noqa: S310 diagnostic
            raw = response.read().decode("utf-8", errors="replace")
            payload: Any = None
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = None
            spec = payload.get("spec", {}) if isinstance(payload, dict) else {}
            safety_contract = spec.get("safetyContract", {}) if isinstance(spec, dict) else {}
            return {
                "ok": 200 <= response.status < 400,
                "statusCode": response.status,
                "durationMs": elapsed_ms(started),
                "jsonKind": payload.get("kind") if isinstance(payload, dict) else "",
                "jsonApiVersion": payload.get("apiVersion") if isinstance(payload, dict) else "",
                "accessReviewStatus": spec.get("accessReviewStatus", {}) if isinstance(spec, dict) else {},
                "lightspeedStatus": safety_contract.get("lightspeedStatus", {})
                if isinstance(safety_contract, dict)
                else {},
                "bodyPreview": raw[:300],
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")[:500]
        return {
            "ok": False,
            "statusCode": exc.code,
            "durationMs": elapsed_ms(started),
            "bodyPreview": raw,
        }
    except Exception as exc:  # noqa: BLE001 diagnostic script
        return {"ok": False, "statusCode": 0, "durationMs": elapsed_ms(started), "error": safe_error(exc)}


def parse_host_port(api_server: str) -> tuple[str, int]:
    trimmed = api_server.removeprefix("https://").removeprefix("http://").rstrip("/")
    if ":" in trimmed:
        host, port_text = trimmed.rsplit(":", 1)
        return host, int(port_text)
    return trimmed, 443


def build_wsl_network_snapshot(api_host: str, dns_result: Mapping[str, Any], timeout: int) -> dict[str, Any]:
    addresses = dns_result.get("addresses") if isinstance(dns_result.get("addresses"), list) else []
    target_ip = str(addresses[0]) if addresses else api_host
    route = run_cmd(["ip", "route", "get", target_ip], timeout)
    addr = run_cmd(["ip", "-brief", "addr"], timeout)
    resolv_conf = text_file_preview("/etc/resolv.conf")

    hints: list[str] = []
    route_stdout = str(route.get("stdout") or "")
    if target_ip.startswith(("10.", "172.16.", "172.17.", "172.18.", "172.19.", "172.2", "172.30.", "172.31.", "192.168.")):
        hints.append("target IP is private; WSL must receive the VPN/private-network route.")
    if " dev eth0 " in f" {route_stdout} " and " via " in f" {route_stdout} ":
        hints.append("route uses WSL eth0 gateway; if TCP times out, check VPN route propagation into WSL.")
    if "nameserver 10.255.255.254" in resolv_conf:
        hints.append("WSL DNS is using the WSL-generated resolver; DNS may work even while VPN TCP routing is missing.")

    return {
        "targetIp": target_ip,
        "ipRouteGet": route,
        "ipBriefAddr": addr,
        "resolvConfPreview": resolv_conf,
        "hints": hints,
    }


def build_summary(results: dict[str, Any]) -> dict[str, Any]:
    for key, message in CHECK_ORDER:
        result = results.get(key) or {}
        if result.get("skipped"):
            return {
                "readyForStrictLightspeedGate": False,
                "firstFailingLayer": key,
                "message": message,
            }
        if not result.get("ok"):
            return {
                "readyForStrictLightspeedGate": False,
                "firstFailingLayer": key,
                "message": message,
            }
    return {
        "readyForStrictLightspeedGate": True,
        "firstFailingLayer": "",
        "message": "OCP connectivity ladder passed; run task kugnus:lightspeed:live-verify.",
    }


def fast_fail_if_needed(results: dict[str, Any], key: str, enabled: bool) -> bool:
    if not enabled or (results.get(key) or {}).get("ok"):
        return False

    seen = False
    for check_key, _message in CHECK_ORDER:
        if seen and check_key not in results:
            results[check_key] = {
                "ok": False,
                "skipped": True,
                "reason": f"skipped because {key} failed and fast-fail is enabled",
            }
        if check_key == key:
            seen = True
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-server", default=DEFAULT_API_SERVER)
    parser.add_argument("--gateway", default=DEFAULT_GATEWAY)
    parser.add_argument("--fast-fail", action="store_true")
    parser.add_argument("--timeout", type=int, default=8)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    args = parser.parse_args()

    api_host, api_port = parse_host_port(args.api_server)
    token = ""
    results: dict[str, Any] = {}

    results["dns"] = dns_check(api_host, args.timeout)
    wsl_network = build_wsl_network_snapshot(api_host, results["dns"], args.timeout)
    if fast_fail_if_needed(results, "dns", args.fast_fail):
        token = ""
        goto_report = True
    else:
        goto_report = False

    if not goto_report:
        results["tcp"] = tcp_check(api_host, api_port, args.timeout)
        goto_report = fast_fail_if_needed(results, "tcp", args.fast_fail)

    if not goto_report:
        results["tls"] = tls_check(api_host, api_port, args.timeout)
        goto_report = fast_fail_if_needed(results, "tls", args.fast_fail)

    if not goto_report:
        results["versionEndpoint"] = http_json_request(
            f"{args.api_server.rstrip('/')}/version",
            timeout=args.timeout,
        )
        goto_report = fast_fail_if_needed(results, "versionEndpoint", args.fast_fail)

    if not goto_report:
        oc_server = run_cmd(["oc", "whoami", "--show-server"], args.timeout)
        results["ocServer"] = {
            **oc_server,
            "matchesExpectedServer": oc_server.get("stdout") == args.api_server.rstrip("/"),
        }
        goto_report = fast_fail_if_needed(results, "ocServer", args.fast_fail)

    if not goto_report:
        oc_identity = run_cmd(["oc", "whoami"], args.timeout)
        results["ocIdentity"] = {**oc_identity, "identityPresent": bool(oc_identity.get("stdout"))}
        if not oc_identity.get("stdout"):
            results["ocIdentity"]["ok"] = False
            results["ocIdentity"]["reason"] = "oc whoami returned an empty identity"
        goto_report = fast_fail_if_needed(results, "ocIdentity", args.fast_fail)

    if not goto_report:
        oc_token = run_cmd(["oc", "whoami", "--show-token"], args.timeout)
        token = str(oc_token.get("stdout") or "")
        results["ocToken"] = {
            "ok": bool(token) and bool(oc_token.get("ok")),
            "durationMs": oc_token.get("durationMs"),
            "returnCode": oc_token.get("returnCode"),
            "tokenLength": len(token),
            "timeout": oc_token.get("timeout", False),
            "stderr": oc_token.get("stderr"),
        }
        goto_report = fast_fail_if_needed(results, "ocToken", args.fast_fail)

    if not goto_report:
        if token:
            results["selfSubjectReview"] = http_json_request(
                f"{args.api_server.rstrip('/')}/apis/authentication.k8s.io/v1/selfsubjectreviews",
                token=token,
                method="POST",
                body={"apiVersion": "authentication.k8s.io/v1", "kind": "SelfSubjectReview"},
                timeout=args.timeout,
            )
            goto_report = fast_fail_if_needed(results, "selfSubjectReview", args.fast_fail)
        else:
            results["selfSubjectReview"] = {"ok": False, "skipped": True, "reason": "no oc token"}
            goto_report = fast_fail_if_needed(results, "selfSubjectReview", args.fast_fail)

    if not goto_report:
        if token:
            results["gatewayStatus"] = http_json_request(
                f"{args.gateway.rstrip('/')}/v1/aiops/status",
                token=token,
                timeout=args.timeout,
            )
        else:
            results["gatewayStatus"] = {"ok": False, "skipped": True, "reason": "no oc token"}

    report = {
        "apiVersion": "aiops.komsco/v1alpha1",
        "kind": "OcpConnectivityLadderReport",
        "generatedAt": now_rfc3339(),
        "branch": git_value(["branch", "--show-current"]),
        "headSha": git_value(["rev-parse", "HEAD"]),
        "apiServer": args.api_server.rstrip("/"),
        "gateway": args.gateway.rstrip("/"),
        "timeoutSeconds": args.timeout,
        "summary": build_summary(results),
        "results": results,
        "wslNetwork": wsl_network,
        "note": "Bearer tokens and full response bodies are intentionally not persisted.",
    }

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = report["summary"]
    if summary["readyForStrictLightspeedGate"]:
        print("OCP connectivity ladder: PASS")
    else:
        print("OCP connectivity ladder: FAIL")
        print(f"[FAIL] {summary['firstFailingLayer']}: {summary['message']}")
    print(f"Report: {report_path}")
    return 0 if summary["readyForStrictLightspeedGate"] else 1


if __name__ == "__main__":
    sys.exit(main())
