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
import ipaddress
import json
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


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


def run_cmd(args: list[str], timeout: int, max_chars: int = 1000) -> dict[str, Any]:
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
            "stdout": result.stdout.strip()[:max_chars],
            "stderr": result.stderr.strip()[:max_chars],
            "timeoutSeconds": timeout,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returnCode": None,
            "durationMs": elapsed_ms(started),
            "stdout": (exc.stdout or "").strip()[:max_chars] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "").strip()[:max_chars] if isinstance(exc.stderr, str) else "",
            "timeout": True,
            "timeoutSeconds": timeout,
        }


def text_file_preview(path: str, max_chars: int = 1200) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")[:max_chars]
    except OSError as exc:
        return f"unavailable: {safe_error(exc)}"


def is_private_ip(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_private
    except ValueError:
        return False


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
    if is_private_ip(target_ip):
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


def route_print_has_active_route(stdout: str) -> bool:
    if "Active Routes:" not in stdout:
        return False
    active_section = stdout.split("Active Routes:", 1)[1].split("Persistent Routes:", 1)[0].strip()
    return bool(active_section) and active_section.lower() != "none"


def sanitize_windows_route_output(stdout: str) -> str:
    return re.sub(r"\b(?:[0-9a-fA-F]{2}\s){5}[0-9a-fA-F]{2}\b", "<mac>", stdout)


def normalize_json_array(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def run_powershell_json(command: str, timeout: int) -> dict[str, Any]:
    result = run_cmd(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        timeout,
        max_chars=8000,
    )
    stdout = str(result.get("stdout") or "")
    payload: Any = None
    if stdout:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            result["jsonError"] = safe_error(exc)
    result["json"] = payload
    return result


def build_windows_network_snapshot(target_ip: str, timeout: int) -> dict[str, Any]:
    if not target_ip:
        return {"ok": False, "skipped": True, "reason": "no target IP"}
    if not is_private_ip(target_ip):
        return {"ok": False, "skipped": True, "reason": "target IP is not private", "targetIp": target_ip}

    command = (
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::UTF8; "
        f"route print {target_ip}"
    )
    route_print = run_cmd(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        timeout,
        max_chars=6000,
    )
    route_print["stdout"] = sanitize_windows_route_output(str(route_print.get("stdout") or ""))
    stdout = str(route_print.get("stdout") or "")
    active_route_present = route_print_has_active_route(stdout)
    adapter_command = (
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::UTF8; "
        "Get-NetAdapter | "
        "Where-Object { $_.InterfaceDescription -match 'VPN|Tunnel|Fortinet|Tailscale' -or $_.Name -match 'VPN|Tailscale' } | "
        "Select-Object Name,InterfaceDescription,Status,ifIndex | "
        "ConvertTo-Json -Depth 3 -Compress"
    )
    adapter_result = run_powershell_json(adapter_command, timeout)
    vpn_adapters = normalize_json_array(adapter_result.get("json"))
    disabled_vpn_adapters = [
        adapter
        for adapter in vpn_adapters
        if str(adapter.get("Status") or "").lower() == "disabled"
    ]
    up_vpn_adapters = [
        adapter
        for adapter in vpn_adapters
        if str(adapter.get("Status") or "").lower() == "up"
    ]
    hints: list[str] = []
    if route_print.get("ok") and not active_route_present:
        hints.append(
            "Windows route print has no active route for the private OCP API IP; verify VPN/private route on Windows first."
        )
    elif route_print.get("ok") and active_route_present:
        hints.append(
            "Windows has an active route for the OCP API IP; if WSL TCP still times out, check WSL route propagation or VPN/firewall policy."
        )
    for adapter in disabled_vpn_adapters:
        description = str(adapter.get("InterfaceDescription") or adapter.get("Name") or "VPN adapter")
        hints.append(f"VPN-like adapter is disabled on Windows: {description}.")
    if up_vpn_adapters and not active_route_present:
        names = ", ".join(str(adapter.get("InterfaceDescription") or adapter.get("Name")) for adapter in up_vpn_adapters)
        hints.append(f"VPN-like adapter(s) are up but do not provide the OCP private route: {names}.")

    return {
        "ok": bool(route_print.get("ok")),
        "targetIp": target_ip,
        "activeRoutePresent": active_route_present,
        "routePrint": route_print,
        "vpnAdapters": vpn_adapters,
        "disabledVpnAdapters": disabled_vpn_adapters,
        "upVpnAdapters": up_vpn_adapters,
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


def build_interpretation(
    summary: dict[str, Any],
    results: dict[str, Any],
    wsl_network: dict[str, Any],
    windows_network: dict[str, Any],
) -> dict[str, Any]:
    first_failing_layer = str(summary.get("firstFailingLayer") or "")
    target_ip = str(wsl_network.get("targetIp") or "")
    route_stdout = str((wsl_network.get("ipRouteGet") or {}).get("stdout") or "")
    dns_ok = bool((results.get("dns") or {}).get("ok"))
    tcp_ok = bool((results.get("tcp") or {}).get("ok"))
    windows_route_checked = bool(windows_network.get("ok"))
    windows_active_route = bool(windows_network.get("activeRoutePresent"))
    disabled_vpn_adapters = normalize_json_array(windows_network.get("disabledVpnAdapters"))

    if summary.get("readyForStrictLightspeedGate"):
        return {
            "likelyCause": "none_detected",
            "confidence": "high",
            "explanation": "All connectivity ladder checks passed; strict Lightspeed verification can run.",
            "nextActions": ["Run task kugnus:lightspeed:live-verify."],
        }

    if dns_ok and not tcp_ok and first_failing_layer == "tcp" and is_private_ip(target_ip):
        if windows_route_checked and not windows_active_route and disabled_vpn_adapters:
            adapter_names = ", ".join(
                str(adapter.get("InterfaceDescription") or adapter.get("Name") or "VPN adapter")
                for adapter in disabled_vpn_adapters
            )
            return {
                "likelyCause": "windows_vpn_adapter_disabled_and_private_route_missing",
                "confidence": "high",
                "explanation": (
                    "DNS resolves the company OCP API to a private IP, but TCP 6443 times out. "
                    "Windows route print shows no active route for that target, and at least one "
                    f"VPN-like adapter is disabled: {adapter_names}. The next practical check is "
                    "the Windows-side company VPN client before WSL or Gateway code."
                ),
                "nextActions": [
                    "Connect the Windows-side company VPN client that owns the OCP private route.",
                    "Confirm Windows route print for the OCP private IP shows an active route.",
                    "After the Windows route exists, restart or reopen WSL if the WSL route remains stale.",
                    "Rerun task kugnus:ocp:doctor and check that firstFailingLayer is no longer tcp.",
                    "Only after readyForStrictLightspeedGate=true, rerun task kugnus:demo:resume or task kugnus:lightspeed:live-verify.",
                ],
                "notCodeBlocker": True,
                "importantDistinctions": [
                    "A VPN adapter being present is not the same as being connected.",
                    "DNS PASS does not mean Windows has a route to the private IP.",
                    "Windows route missing is earlier than WSL route propagation.",
                    "Gateway health does not prove access to the company OCP API.",
                ],
            }

        if windows_route_checked and not windows_active_route:
            return {
                "likelyCause": "windows_host_private_route_missing_or_vpn_disconnected",
                "confidence": "high",
                "explanation": (
                    "DNS resolves the company OCP API to a private IP, but TCP 6443 times out and "
                    "Windows route print shows no active route for that target. The next practical "
                    "check is the Windows-side VPN/private route, before WSL or Gateway code."
                ),
                "nextActions": [
                    "Verify the Windows-side VPN/private network is connected and owns a route to the OCP private IP.",
                    "After the Windows route exists, restart or reopen WSL if the WSL route remains stale.",
                    "Rerun task kugnus:ocp:doctor and check that firstFailingLayer is no longer tcp.",
                    "Only after readyForStrictLightspeedGate=true, rerun task kugnus:demo:resume or task kugnus:lightspeed:live-verify.",
                ],
                "notCodeBlocker": True,
                "importantDistinctions": [
                    "DNS PASS does not mean Windows has a route to the private IP.",
                    "Windows route missing is earlier than WSL route propagation.",
                    "Gateway health does not prove access to the company OCP API.",
                ],
            }

        next_actions = [
            "Verify that the Windows-side VPN/private network that owns the OCP route is connected.",
            "After VPN changes, restart or reopen WSL if it did not inherit the private route.",
            "Rerun task kugnus:ocp:doctor and check that firstFailingLayer is no longer tcp.",
            "Only after readyForStrictLightspeedGate=true, rerun task kugnus:demo:resume or task kugnus:lightspeed:live-verify.",
        ]
        explanation = (
            "DNS resolves the company OCP API to a private IP, but TCP 6443 times out. "
            "That means name resolution is not the blocker; the live network path from WSL to the private OCP API is. "
            "If the route leaves through WSL eth0, the next practical check is whether the Windows VPN route is being propagated into WSL."
        )
        return {
            "likelyCause": "wsl_vpn_private_route_missing_or_stale",
            "confidence": "high"
            if " dev eth0 " in f" {route_stdout} " and not windows_route_checked
            else "medium",
            "explanation": explanation,
            "nextActions": next_actions,
            "notCodeBlocker": True,
            "importantDistinctions": [
                "DNS PASS does not mean TCP route PASS.",
                "oc whoami --show-server can PASS by reading kubeconfig even when the API is unreachable.",
                "A token length alone does not prove live OpenShift authentication.",
            ],
        }

    if first_failing_layer in {"ocIdentity", "ocToken", "selfSubjectReview"}:
        return {
            "likelyCause": "oc_login_or_auth_session_invalid",
            "confidence": "medium",
            "explanation": "The network path reached later layers, but live oc identity/token/auth review failed.",
            "nextActions": [
                "Run oc login in WSL, then rerun task kugnus:ocp:doctor.",
                "Do not commit tokens, kubeconfig, or .env files.",
            ],
            "notCodeBlocker": True,
        }

    return {
        "likelyCause": f"{first_failing_layer or 'unknown'}_failure",
        "confidence": "medium",
        "explanation": "The first failing ladder layer should be fixed before rerunning the strict Lightspeed gate.",
        "nextActions": ["Rerun task kugnus:ocp:doctor after fixing the first failing layer."],
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
    windows_network = build_windows_network_snapshot(str(wsl_network.get("targetIp") or ""), args.timeout)
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

    summary = build_summary(results)
    interpretation = build_interpretation(summary, results, wsl_network, windows_network)
    report = {
        "apiVersion": "aiops.komsco/v1alpha1",
        "kind": "OcpConnectivityLadderReport",
        "generatedAt": now_rfc3339(),
        "branch": git_value(["branch", "--show-current"]),
        "headSha": git_value(["rev-parse", "HEAD"]),
        "apiServer": args.api_server.rstrip("/"),
        "gateway": args.gateway.rstrip("/"),
        "timeoutSeconds": args.timeout,
        "summary": summary,
        "interpretation": interpretation,
        "results": results,
        "wslNetwork": wsl_network,
        "windowsNetwork": windows_network,
        "note": "Bearer tokens and full response bodies are intentionally not persisted.",
    }

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if summary["readyForStrictLightspeedGate"]:
        print("OCP connectivity ladder: PASS")
    else:
        print("OCP connectivity ladder: FAIL")
        print(f"[FAIL] {summary['firstFailingLayer']}: {summary['message']}")
        print(f"[INTERPRETATION] {interpretation['likelyCause']}: {interpretation['explanation']}")
    print(f"Report: {report_path}")
    return 0 if summary["readyForStrictLightspeedGate"] else 1


if __name__ == "__main__":
    sys.exit(main())
