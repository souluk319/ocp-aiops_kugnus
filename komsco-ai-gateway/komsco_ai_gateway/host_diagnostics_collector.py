from __future__ import annotations

import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .aiops_core import get_host_diagnostic_collector
from .security import now_rfc3339, redact_text

DEFAULT_HOST_ROOT = Path("/host")
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_LINES = 50000


def parse_int_env(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def host_path(host_root: Path, absolute_path: str) -> Path:
    return host_root / absolute_path.removeprefix("/")


def bounded_text_file(path: Path, *, max_bytes: int, tail_lines: int | None = None) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "status": "missing"}
    if not path.is_file():
        return {"path": str(path), "status": "not_file"}

    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if tail_lines is None:
                data = handle.read(max_bytes + 1)
                truncated = len(data) > max_bytes
                data = data[:max_bytes]
            else:
                offset = max(size - max_bytes, 0)
                handle.seek(offset)
                data = handle.read(max_bytes)
                truncated = offset > 0
                if offset > 0 and b"\n" in data:
                    data = data.split(b"\n", 1)[1]
    except OSError as exc:
        return {"path": str(path), "status": "read_error", "reason": str(exc)}

    text = data.decode("utf-8", errors="replace")
    if tail_lines is not None:
        lines = text.splitlines()[-tail_lines:]
        text = "\n".join(lines)
    else:
        lines = text.splitlines()

    return {
        "path": str(path),
        "status": "collected",
        "bytesRead": len(data),
        "lineCount": len(lines),
        "truncated": truncated,
        "content": redact_text(text),
    }


def collect_named_files(
    host_root: Path,
    paths: Iterable[str],
    *,
    max_bytes_per_file: int,
    tail_lines: int | None = None,
) -> list[dict[str, Any]]:
    return [
        bounded_text_file(host_path(host_root, path), max_bytes=max_bytes_per_file, tail_lines=tail_lines)
        for path in paths
    ]


def collect_statvfs(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "status": "missing"}
    try:
        stat = os.statvfs(path)
    except OSError as exc:
        return {"path": str(path), "status": "stat_error", "reason": str(exc)}

    total = stat.f_frsize * stat.f_blocks
    free = stat.f_frsize * stat.f_bavail
    used = max(total - free, 0)
    return {
        "path": str(path),
        "status": "collected",
        "bytesTotal": total,
        "bytesAvailable": free,
        "bytesUsed": used,
        "usedPercent": round((used / total) * 100, 2) if total else 0,
    }


def collect_os_triage(host_root: Path, *, max_bytes: int, max_lines: int) -> list[dict[str, Any]]:
    max_bytes_per_file = max(4096, min(max_bytes // 16, 512 * 1024))
    max_tail_lines = max(50, min(max_lines // 20, 1000))
    return [
        {
            "name": "kernel_summary",
            "kind": "file_samples",
            "items": collect_named_files(
                host_root,
                [
                    "/proc/loadavg",
                    "/proc/uptime",
                    "/proc/meminfo",
                    "/proc/pressure/cpu",
                    "/proc/pressure/memory",
                    "/proc/pressure/io",
                    "/proc/sys/kernel/hostname",
                    "/proc/sys/kernel/tainted",
                ],
                max_bytes_per_file=max_bytes_per_file,
            ),
        },
        {
            "name": "disk_pressure_summary",
            "kind": "filesystem_stats",
            "items": [
                collect_statvfs(host_path(host_root, "/var/log")),
                collect_statvfs(host_path(host_root, "/sys")),
            ],
        },
        {
            "name": "host_log_tail",
            "kind": "bounded_log_tail",
            "items": collect_named_files(
                host_root,
                [
                    "/var/log/messages",
                    "/var/log/kubelet/kubelet.log",
                    "/var/log/crio/crio.log",
                ],
                max_bytes_per_file=max_bytes_per_file,
                tail_lines=max_tail_lines,
            ),
        },
    ]


def collect_runtime_triage(host_root: Path) -> list[dict[str, Any]]:
    crio_socket = host_path(host_root, "/run/crio/crio.sock")
    kubelet_root = host_path(host_root, "/var/lib/kubelet")
    socket_status: dict[str, Any] = {"path": str(crio_socket), "exists": crio_socket.exists()}
    try:
        socket_status["mode"] = oct(crio_socket.stat().st_mode) if crio_socket.exists() else None
    except OSError as exc:
        socket_status["status"] = "stat_error"
        socket_status["reason"] = str(exc)

    pods_dir_status: dict[str, Any] = {"path": str(kubelet_root / "pods"), "exists": (kubelet_root / "pods").exists()}
    try:
        pods_dir_status["entrySample"] = sorted(item.name for item in (kubelet_root / "pods").iterdir())[:50]
    except OSError as exc:
        pods_dir_status["status"] = "list_error"
        pods_dir_status["reason"] = str(exc)

    return [
        {
            "name": "runtime_readonly_summary",
            "kind": "runtime_socket_and_kubelet_state",
            "items": [socket_status, pods_dir_status],
        },
    ]


def collect_host_diagnostics(
    *,
    request_id: str,
    collector: str,
    target_node_name: str,
    target_node_uid: str,
    host_root: Path = DEFAULT_HOST_ROOT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_lines: int = DEFAULT_MAX_LINES,
) -> dict[str, Any]:
    profile = get_host_diagnostic_collector(collector)
    if collector == "node_os_readonly_triage":
        sections = collect_os_triage(host_root, max_bytes=max_bytes, max_lines=max_lines)
    elif collector == "node_runtime_readonly_triage":
        sections = collect_runtime_triage(host_root)
    else:
        sections = []

    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "HostDiagnosticEvidence",
        "metadata": {
            "name": request_id,
            "collectedAt": now_rfc3339(),
        },
        "spec": {
            "requestId": request_id,
            "targetNode": {
                "name": target_node_name,
                "uid": target_node_uid,
            },
            "collector": {
                "name": collector,
                "version": profile["collectorVersion"],
                "profile": profile["collectorProfile"],
                "arbitraryCommandInputAllowed": profile["arbitraryCommandInputAllowed"],
            },
            "limits": {
                "maxBytes": max_bytes,
                "maxLines": max_lines,
            },
            "sections": sections,
        },
    }


def main() -> None:
    evidence = collect_host_diagnostics(
        request_id=os.getenv("AIOPS_DIAGNOSTIC_REQUEST_ID", "diag-unknown"),
        collector=os.getenv("AIOPS_COLLECTOR", "node_os_readonly_triage"),
        target_node_name=os.getenv("AIOPS_TARGET_NODE_NAME", "unknown-node"),
        target_node_uid=os.getenv("AIOPS_TARGET_NODE_UID", "unknown-uid"),
        host_root=Path(os.getenv("AIOPS_HOST_ROOT", str(DEFAULT_HOST_ROOT))),
        max_bytes=parse_int_env("AIOPS_MAX_BYTES", DEFAULT_MAX_BYTES),
        max_lines=parse_int_env("AIOPS_MAX_LINES", DEFAULT_MAX_LINES),
    )
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
