#!/usr/bin/env python3
"""
Extract class name + language_id from changed solidlsp language server files.

Usage:
  python scripts/extract_ls_language_ids.py                      # diff vs HEAD
  python scripts/extract_ls_language_ids.py --base main          # diff vs main
  python scripts/extract_ls_language_ids.py path/to/file.py      # explicit files
  python scripts/extract_ls_language_ids.py --format github ...  # write to GITHUB_OUTPUT
"""

import ast
import json
import os
import sys
from pathlib import Path

_LS_DIR_PARTS = ("src", "solidlsp", "language_servers")
_TEST_ROOT = Path("test/solidlsp")

# test directory name differs from language_id for these
_TEST_DIR_OVERRIDES: dict[str, str] = {
    "html": "html_ls",
    "json": "json_ls",
    "yaml": "yaml_ls",
}


def _test_path(language_id: str) -> str | None:
    dir_name = _TEST_DIR_OVERRIDES.get(language_id, language_id)
    p = _TEST_ROOT / dir_name
    return p.as_posix() if p.exists() else None


def _get_changed_files(base: str) -> list[Path]:
    import subprocess

    result = subprocess.run(
        ["git", "diff", "--name-only", base],
        capture_output=True,
        text=True,
        check=True,
    )
    paths = []
    for line in result.stdout.splitlines():
        p = Path(line)
        if p.suffix == ".py" and p.parts[: len(_LS_DIR_PARTS)] == _LS_DIR_PARTS:
            paths.append(p)
    return paths


def extract_language_ids(filepath: Path) -> list[tuple[str, str]]:
    """Return [(class_name, language_id)] for every class in filepath."""
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except (OSError, SyntaxError) as exc:
        print(f"skip {filepath}: {exc}", file=sys.stderr)
        return []

    results: list[tuple[str, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue

        for item in node.body:
            if not (isinstance(item, ast.FunctionDef) and item.name == "__init__"):
                continue

            for stmt in ast.walk(item):
                if not isinstance(stmt, ast.Call):
                    continue

                # Match super().__init__(...)
                func = stmt.func
                if not (
                    isinstance(func, ast.Attribute)
                    and func.attr == "__init__"
                    and isinstance(func.value, ast.Call)
                    and isinstance(func.value.func, ast.Name)
                    and func.value.func.id == "super"
                ):
                    continue

                # 4th positional arg (index 3) is language_id
                if len(stmt.args) >= 4:
                    arg = stmt.args[3]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        results.append((node.name, arg.value))
                        break  # one super().__init__ per __init__ is enough

    return results


def collect(files: list[Path]) -> tuple[list[str], list[str]]:
    """Return (unique_language_ids, unique_test_paths) across all files."""
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()

    for filepath in files:
        if not filepath.exists():
            continue
        for _cls, lang_id in extract_language_ids(filepath):
            if lang_id not in seen_ids:
                seen_ids.add(lang_id)
                tp = _test_path(lang_id)
                if tp:
                    seen_paths.add(tp)

    return sorted(seen_ids), sorted(seen_paths)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Extract language_id from changed LS files")
    parser.add_argument(
        "--base",
        default="HEAD",
        help="git ref to diff against (default: HEAD for uncommitted changes)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "github"],
        default="text",
        help="output format: 'text' (human) or 'github' (write to GITHUB_OUTPUT)",
    )
    parser.add_argument("files", nargs="*", help="Explicit .py paths (skips git diff)")
    args = parser.parse_args()

    if args.files:
        files = [Path(f) for f in args.files if Path(f).suffix == ".py"]
    else:
        files = _get_changed_files(args.base)

    if args.format == "text":
        if not files:
            print("No changed language server files found.")
            return
        for filepath in files:
            if not filepath.exists():
                continue
            for class_name, language_id in extract_language_ids(filepath):
                print(f"{class_name}: {language_id}")
        return

    # github format: write to GITHUB_OUTPUT
    lang_ids, test_paths = collect(files)
    any_changed = bool(lang_ids)

    output_file = os.environ.get("GITHUB_OUTPUT", "")
    lines = [
        f"language_ids={json.dumps(lang_ids)}",
        f"test_paths={' '.join(test_paths)}",
        f"any_changed={'true' if any_changed else 'false'}",
    ]

    if output_file:
        with open(output_file, "a") as f:
            f.write("\n".join(lines) + "\n")
    else:
        # fallback: print to stdout (useful for local testing)
        for line in lines:
            print(line)


if __name__ == "__main__":
    main()
