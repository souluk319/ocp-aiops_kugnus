#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
SELF_PATH: Final = "scripts/verify-refactor-scope.py"

EXACT_PROTECTED: Final = frozenset({
    "docs/version-progress-book.html",
    "docs/aiops-beginner-guide.html",
    "docs/Ver.0.1.8/aiops-llm-strategy-brief.html",
    "docs/Ver.0.3.0/refactoring-harness.md",
    "docs/Komsco_ai_agent_final.pdf",
    "docs/AIOps-For-OCP.pdf",
})

FORBIDDEN_ACTIONS: Final = (
    re.compile(r"\bKOMSCO_AIOPS_APPROVE_(?:PUBLISH|INSTALL|REDEPLOY|CLUSTER_WRITE)=cywell-aiops\b"),
    re.compile(r"\btask\s+kugnus:(?:publish|install|company:(?:publish|install|redeploy))\b"),
    re.compile(r"\btask\s+aiops:(?:publish|install|company:(?:publish|install|redeploy))\b"),
    re.compile(r"\btask\s+olm:(?:catalog|install|deploy|release)\b"),
    re.compile(r"(?:^|\s)\./scripts/olm-deploy\.sh\s+(?:catalog|install|deploy)\b"),
    re.compile(r"(?:^|\s)\./scripts/olm-release-images\.sh\s+deploy\b"),
    re.compile(r"(?:^|\s)\./scripts/kugnus-olm\.sh\s+(?:publish|install)\b"),
)


@dataclass(frozen=True, slots=True)
class DiffFile:
    path: str
    added_lines: tuple[str, ...]
    deleted: bool


@dataclass(frozen=True, slots=True)
class StatusChange:
    path: str
    status: str


@dataclass(frozen=True, slots=True)
class Violation:
    path: str
    reason: str


def clean_path(raw: str) -> str:
    path = raw.strip()
    for prefix in ("a/", "b/", "./"):
        if path.startswith(prefix):
            return path.removeprefix(prefix)
    return path


def protected_reason(path: str) -> str | None:
    lower = path.lower()
    name = Path(path).name.lower()

    if path in EXACT_PROTECTED:
        return "protected source artifact"
    if path.startswith("docs/contracts/"):
        return "contract document"
    if path.startswith("evals/aiops-scenarios/") and path.endswith(".json"):
        return "Claude scenario JSON"
    if path.startswith(".claude/"):
        return "Claude handoff note"
    if path.startswith("demo/") or path.startswith(".tmp-kugnus-demo/"):
        return "demo material"
    if not path.startswith("docs/"):
        return None
    if "mock-customer" in lower or "customer-customization" in lower or "demo" in lower:
        return "mock customer or demo material"
    if "beginner" in name or "webbook" in name or "editorial" in name:
        return "beginner/editorial document"
    if "strategy" in name:
        return "strategy document"
    if "progress" in name:
        return "progress document"
    return None


def run_git(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip()
        raise RuntimeError(stderr or f"git {' '.join(args)} failed") from exc
    return result.stdout


def status_changes(base: str) -> tuple[StatusChange, ...]:
    stdout = run_git(["diff", "--name-status", "--diff-filter=ACDMRTUXB", base, "--"])
    changes: list[StatusChange] = []
    for line in stdout.splitlines():
        fields = line.split("\t")
        if len(fields) < 2:
            continue
        status = fields[0]
        for raw_path in fields[1:]:
            changes.append(StatusChange(path=clean_path(raw_path), status=status))
    return tuple(changes)


def parse_diff_files(diff_text: str) -> tuple[DiffFile, ...]:
    files: list[DiffFile] = []
    current_old = ""
    current_new = ""
    added: list[str] = []
    deleted = False

    def flush() -> None:
        nonlocal added, current_new, current_old, deleted
        if not current_old and not current_new:
            return
        path = current_new if current_new and current_new != "/dev/null" else current_old
        if path:
            files.append(DiffFile(path=clean_path(path), added_lines=tuple(added), deleted=deleted))
        current_old = ""
        current_new = ""
        added = []
        deleted = False

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            flush()
            parts = line.split()
            if len(parts) >= 4:
                current_old = clean_path(parts[2])
                current_new = clean_path(parts[3])
            continue
        if line.startswith("deleted file mode"):
            deleted = True
            continue
        if line.startswith("--- "):
            raw = line[4:].strip()
            current_old = raw if raw == "/dev/null" else clean_path(raw)
            continue
        if line.startswith("+++ "):
            raw = line[4:].strip()
            current_new = raw if raw == "/dev/null" else clean_path(raw)
            if raw == "/dev/null":
                deleted = True
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
    flush()
    return tuple(files)


def find_action(line: str) -> str | None:
    for pattern in FORBIDDEN_ACTIONS:
        match = pattern.search(line)
        if match:
            return match.group(0).strip()
    return None


def violations(
    status_items: tuple[StatusChange, ...],
    diff_items: tuple[DiffFile, ...],
    allowed: frozenset[str],
) -> tuple[Violation, ...]:
    found: list[Violation] = []
    for item in status_items:
        if item.path in allowed:
            continue
        reason = protected_reason(item.path)
        if reason:
            action = "deleted" if item.status.startswith("D") else "changed"
            found.append(Violation(item.path, f"{action} {reason}"))

    for item in diff_items:
        if item.path not in allowed:
            reason = protected_reason(item.path)
            if reason:
                action = "deleted" if item.deleted else "changed"
                found.append(Violation(item.path, f"{action} {reason}"))
        if item.path == SELF_PATH:
            continue
        for line in item.added_lines:
            action = find_action(line)
            if action:
                found.append(Violation(item.path, f"forbidden company-server action: {action}"))
    return tuple(dict.fromkeys(found))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Guard refactor PRs from protected artifact scope drift.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--base", help="Git base revision for current tracked diff")
    source.add_argument("--fixture", type=Path, help="Unified diff fixture to inspect")
    parser.add_argument("--allow", nargs="*", default=[], help="Exact changed paths explicitly in scope")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    allowed = frozenset(clean_path(path) for path in args.allow)

    try:
        if args.fixture:
            diff_text = args.fixture.read_text(encoding="utf-8")
            status_items: tuple[StatusChange, ...] = ()
        else:
            status_items = status_changes(args.base)
            diff_text = run_git(["diff", "--no-ext-diff", "--unified=0", args.base, "--"])
    except (RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    found = violations(status_items, parse_diff_files(diff_text), allowed)
    if found:
        for item in found:
            print(f"FAIL: {item.path}: {item.reason}")
        return 1
    if allowed:
        print("OK: protected artifacts unchanged or explicitly allowed.")
    else:
        print("OK: no protected scope violations found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
