#!/usr/bin/env python3
"""Collect Cypress browser proof for the official Ver.0.1.3 Evidence RCA scene."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "komsco-ai-console-plugin"
SCREENSHOT_ROOT = PLUGIN_ROOT / "integration-tests/screenshots/screenshots"
DEFAULT_REPORT = REPO_ROOT / "docs/Ver.0.1.3/official-evidence-rca-browser-verification.json"
DEFAULT_SCREENSHOT = REPO_ROOT / "docs/Ver.0.1.3/official-evidence-rca-browser-screen.png"
OFFICIAL_QUESTION = "어제 새벽에 default namespace Pod가 왜 재시작됐어?"


def now_rfc3339() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def git_value(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def latest_screenshot() -> Path | None:
    candidates = sorted(
        SCREENSHOT_ROOT.glob("**/official-evidence-rca-screen*.png"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="JSON report path")
    parser.add_argument("--screenshot", default=str(DEFAULT_SCREENSHOT), help="Destination screenshot path")
    args = parser.parse_args()

    report_path = Path(args.report)
    screenshot_path = Path(args.screenshot)
    source = latest_screenshot()
    checks: list[dict[str, Any]] = []

    checks.append(
        {
            "evidence": {"root": str(SCREENSHOT_ROOT.relative_to(REPO_ROOT))},
            "name": "cypress_screenshot_found",
            "ok": source is not None,
        }
    )

    if source:
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, screenshot_path)
        size = screenshot_path.stat().st_size
    else:
        size = 0

    checks.append(
        {
            "evidence": {
                "path": str(screenshot_path.relative_to(REPO_ROOT)),
                "sizeBytes": size,
            },
            "name": "official_screenshot_copied_to_docs",
            "ok": screenshot_path.exists() and size > 0,
        }
    )

    report = {
        "apiVersion": "aiops.komsco/v1alpha1",
        "generatedAt": now_rfc3339(),
        "kind": "OfficialEvidenceRcaBrowserVerification",
        "metadata": {
            "baseRef": git_value(["merge-base", "HEAD", "origin/main"])
            or git_value(["merge-base", "HEAD", "upstream/main"]),
            "branch": git_value(["branch", "--show-current"]),
            "captureMethod": "cypress-electron",
            "cypressRuntimeDependencyNote": "Requires Cypress/Electron OS libraries such as libnspr4.so in WSL.",
            "headSha": git_value(["rev-parse", "HEAD"]),
            "name": "ver-0.1.3-official-evidence-rca-browser-proof",
            "sourceSpec": "komsco-ai-console-plugin/integration-tests/tests/official-evidence-rca.cy.ts",
        },
        "spec": {
            "checks": checks,
            "claim": "browser_screen_proof_for_official_question_staged_in_local_console",
            "officialQuestion": OFFICIAL_QUESTION,
            "screenshot": str(screenshot_path.relative_to(REPO_ROOT)) if screenshot_path.exists() else "",
            "sourceScreenshot": str(source.relative_to(REPO_ROOT)) if source else "",
        },
        "status": "pass" if all(check["ok"] for check in checks) else "fail",
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{report['status']}: wrote {report_path}")
    if source:
        print(f"{report['status']}: copied {source} -> {screenshot_path}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
