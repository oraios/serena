# SPDX-License-Identifier: GPL-3.0-or-later
"""
Adds SPDX-License-Identifier headers to Python source files according to the component
licensing structure documented in LICENSE.

Idempotent: files that already contain an SPDX identifier are left untouched.
Existing copyright notices and module docstrings are never modified; the identifier is
inserted after any shebang/encoding lines and after a leading module docstring (if present).
"""

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPDX_PREFIX = "# SPDX-License-Identifier:"


@dataclass(frozen=True)
class LicensedTree:
    """A directory tree whose Python files fall under a single license."""

    relative_path: str
    spdx_id: str


TREES = [
    LicensedTree("src/solidlsp", "MIT"),
    LicensedTree("src/serena", "GPL-3.0-or-later"),
    LicensedTree("src/interprompt", "GPL-3.0-or-later"),
    LicensedTree("scripts", "GPL-3.0-or-later"),
]


def _header_end_line(source: str) -> int:
    """
    Determines the 0-based line index at which the SPDX line is to be inserted, i.e. after
    shebang/encoding lines and after a leading module docstring.
    """
    lines = source.splitlines(keepends=True)
    idx = 0
    while idx < len(lines) and (lines[idx].startswith("#!") or (lines[idx].startswith("#") and "coding" in lines[idx])):
        idx += 1
    try:
        module = ast.parse(source)
    except SyntaxError:
        return idx
    if (
        module.body
        and isinstance(module.body[0], ast.Expr)
        and isinstance(module.body[0].value, ast.Constant)
        and isinstance(module.body[0].value.value, str)
    ):
        return max(idx, module.body[0].end_lineno)
    return idx


def add_header(path: Path, spdx_id: str) -> bool:
    """Adds the SPDX header to the given file; returns whether the file was modified."""
    with path.open(encoding="utf-8", newline="") as f:
        source = f.read()
    if SPDX_PREFIX in source:
        return False

    # keep empty files (e.g. package markers) untouched
    if not source.strip():
        return False

    # insert header, keeping the file's newline convention
    newline = "\r\n" if "\r\n" in source else "\n"
    lines = source.splitlines(keepends=True)
    idx = _header_end_line(source)
    header = f"{SPDX_PREFIX} {spdx_id}{newline}"
    if idx < len(lines) and lines[idx].strip() != "":
        header += newline
    lines.insert(idx, header)
    path.write_text("".join(lines), encoding="utf-8", newline="")
    return True


def main() -> None:
    modified = 0
    for tree in TREES:
        for path in sorted((ROOT / tree.relative_path).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            if add_header(path, tree.spdx_id):
                modified += 1
                print(f"{tree.spdx_id:18} {path.relative_to(ROOT)}")
    print(f"{modified} file(s) modified", file=sys.stderr)


if __name__ == "__main__":
    main()
