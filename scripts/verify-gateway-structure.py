#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPO_ROOT / "komsco-ai-gateway" / "komsco_ai_gateway"
MAIN_PATH = PACKAGE_DIR / "main.py"


@dataclass(frozen=True, slots=True)
class FunctionSize:
    name: str
    start: int
    end: int
    lines: int
    kind: str


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure Gateway entrypoint size and internal import cycles.",
    )
    parser.add_argument("--max-main-lines", type=int)
    parser.add_argument("--max-function-lines", type=int)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args(argv)


def module_name(path: Path) -> str:
    return path.relative_to(PACKAGE_DIR).with_suffix("").as_posix().replace("/", ".")


def local_imports(path: Path, known: set[str]) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    current = module_name(path)
    package = current.rpartition(".")[0]
    imports: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level <= 0:
            continue
        parent_parts = package.split(".") if package else []
        trim = max(node.level - 1, 0)
        base_parts = parent_parts[: len(parent_parts) - trim] if trim else parent_parts
        if node.module:
            candidate = ".".join([*base_parts, node.module]).strip(".")
            if candidate in known:
                imports.add(candidate)
            continue
        for alias in node.names:
            candidate = ".".join([*base_parts, alias.name]).strip(".")
            if candidate in known:
                imports.add(candidate)
    return imports


def import_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    cycles: set[tuple[str, ...]] = set()
    active: list[str] = []
    active_set: set[str] = set()
    visited: set[str] = set()

    def canonical(cycle: list[str]) -> tuple[str, ...]:
        body = cycle[:-1]
        rotations = [tuple(body[index:] + body[:index]) for index in range(len(body))]
        return min(rotations)

    def visit(node: str) -> None:
        if node in active_set:
            start = active.index(node)
            cycles.add(canonical(active[start:] + [node]))
            return
        if node in visited:
            return
        visited.add(node)
        active.append(node)
        active_set.add(node)
        for target in sorted(graph.get(node, ())):
            visit(target)
        active.pop()
        active_set.remove(node)

    for node in sorted(graph):
        visit(node)
    return [list(cycle) + [cycle[0]] for cycle in sorted(cycles)]


def largest_functions(path: Path) -> list[FunctionSize]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    sizes: list[FunctionSize] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        end = getattr(node, "end_lineno", node.lineno)
        sizes.append(
            FunctionSize(
                name=node.name,
                start=node.lineno,
                end=end,
                lines=end - node.lineno + 1,
                kind=type(node).__name__,
            )
        )
    return sorted(sizes, key=lambda item: (-item.lines, item.start))


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    paths = sorted(PACKAGE_DIR.rglob("*.py"))
    modules = {module_name(path): path for path in paths}
    graph = {
        name: local_imports(path, set(modules))
        for name, path in modules.items()
    }
    cycles = import_cycles(graph)
    main_lines = len(MAIN_PATH.read_text(encoding="utf-8").splitlines())
    functions = largest_functions(MAIN_PATH)
    failures: list[str] = []
    if cycles:
        failures.append(f"internal import cycles: {len(cycles)}")
    if args.max_main_lines is not None and main_lines > args.max_main_lines:
        failures.append(f"main.py lines {main_lines} > {args.max_main_lines}")
    if (
        args.max_function_lines is not None
        and functions
        and functions[0].lines > args.max_function_lines
    ):
        failures.append(
            f"largest function {functions[0].name} has {functions[0].lines} lines "
            f"> {args.max_function_lines}"
        )

    result = {
        "mainLines": main_lines,
        "moduleCount": len(modules),
        "importCycles": cycles,
        "largestFunctions": [asdict(item) for item in functions[: args.top]],
        "failures": failures,
    }
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"main.py lines: {main_lines}")
        print(f"gateway modules: {len(modules)}")
        print(f"internal import cycles: {len(cycles)}")
        for cycle in cycles:
            print(f"  cycle: {' -> '.join(cycle)}")
        print("largest main.py symbols:")
        for item in functions[: args.top]:
            print(f"  {item.lines:5d}  {item.start:5d}-{item.end:5d}  {item.name}")
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
