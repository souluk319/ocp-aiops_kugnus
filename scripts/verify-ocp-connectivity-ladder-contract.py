#!/usr/bin/env python3
"""Verify the local OCP connectivity ladder interpretation contract.

This does not contact the cluster. It protects the diagnostics that decide
whether the strict Lightspeed gate is blocked by DNS, TCP, Windows VPN routes,
WSL route propagation, or oc auth.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = REPO_ROOT / "docs/Ver.0.1.5/ocp-connectivity-ladder-contract-verification.json"
LADDER_SCRIPT = REPO_ROOT / "scripts/kugnus-ocp-connectivity-ladder.py"


def load_ladder_module() -> Any:
    spec = importlib.util.spec_from_file_location("kugnus_ocp_connectivity_ladder", LADDER_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {LADDER_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def now_rfc3339() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def check(name: str, actual: Any, expected: Any) -> dict[str, Any]:
    ok = actual == expected
    return {"name": name, "ok": ok, "actual": actual, "expected": expected}


def build_tcp_blocked_inputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    summary = {
        "readyForStrictLightspeedGate": False,
        "firstFailingLayer": "tcp",
        "message": "TCP 6443 connection failed",
    }
    results = {"dns": {"ok": True}, "tcp": {"ok": False}}
    wsl_network = {
        "targetIp": "10.0.1.230",
        "ipRouteGet": {"stdout": "10.0.1.230 via 172.29.160.1 dev eth0 src 172.29.163.203"},
    }
    return summary, results, wsl_network


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    args = parser.parse_args()

    ladder = load_ladder_module()
    checks: list[dict[str, Any]] = []

    no_route_output = """===========================================================================
IPv4 Route Table
===========================================================================
Active Routes:
  None
Persistent Routes:
  None
"""
    active_route_output = """===========================================================================
IPv4 Route Table
===========================================================================
Active Routes:
Network Destination        Netmask          Gateway       Interface  Metric
       10.0.1.230  255.255.255.255       10.0.0.1       10.0.0.10     25
Persistent Routes:
  None
"""
    checks.append(
        check("route_print_none_is_not_active", ladder.route_print_has_active_route(no_route_output), False)
    )
    checks.append(
        check("route_print_active_route_detected", ladder.route_print_has_active_route(active_route_output), True)
    )
    sample_mac = " ".join(["98", "fc", "84", "e5", "53", "73"])
    checks.append(
        check(
            "windows_mac_addresses_are_sanitized",
            ladder.sanitize_windows_route_output(f"20...{sample_mac} ......Adapter"),
            "20...<mac> ......Adapter",
        )
    )

    summary, results, wsl_network = build_tcp_blocked_inputs()
    disabled_vpn = {
        "ok": True,
        "activeRoutePresent": False,
        "disabledVpnAdapters": [
            {
                "Name": "이더넷 3",
                "InterfaceDescription": "Fortinet SSL VPN Virtual Ethernet Adapter",
                "Status": "Disabled",
            }
        ],
    }
    route_missing = {"ok": True, "activeRoutePresent": False, "disabledVpnAdapters": []}
    windows_unchecked = {"ok": False}

    checks.append(
        check(
            "disabled_vpn_adapter_cause",
            ladder.build_interpretation(summary, results, wsl_network, disabled_vpn)["likelyCause"],
            "windows_vpn_adapter_disabled_and_private_route_missing",
        )
    )
    checks.append(
        check(
            "windows_route_missing_cause",
            ladder.build_interpretation(summary, results, wsl_network, route_missing)["likelyCause"],
            "windows_host_private_route_missing_or_vpn_disconnected",
        )
    )
    checks.append(
        check(
            "wsl_route_stale_cause_when_windows_unchecked",
            ladder.build_interpretation(summary, results, wsl_network, windows_unchecked)["likelyCause"],
            "wsl_vpn_private_route_missing_or_stale",
        )
    )
    checks.append(
        check(
            "ready_ladder_allows_strict_gate",
            ladder.build_interpretation(
                {"readyForStrictLightspeedGate": True},
                {},
                {"targetIp": "10.0.1.230"},
                {"ok": True, "activeRoutePresent": True},
            )["likelyCause"],
            "none_detected",
        )
    )

    report = {
        "apiVersion": "aiops.komsco/v1alpha1",
        "kind": "OcpConnectivityLadderContractVerification",
        "generatedAt": now_rfc3339(),
        "allPassed": all(item["ok"] for item in checks),
        "checks": checks,
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if report["allPassed"]:
        print(f"pass: wrote {report_path}")
        return 0

    print(f"fail: wrote {report_path}")
    for item in checks:
        if not item["ok"]:
            print(f"[FAIL] {item['name']}: actual={item['actual']!r} expected={item['expected']!r}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
