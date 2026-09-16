# SPDX-License-Identifier: GPL-3.0-or-later

"""Benchmark for search_text line-coordinate resolution (see PR "perf(search_text): precompute line offsets").

Reproduces the before/after numbers quoted in the PR description:

- "before" resolves each match's line number via ``TextUtils.get_line_from_index``,
  which walks a TextStepper from index 0 (O(n) per match, O(n*m) for m matches)
- "after" precomputes line start offsets once (O(n)) and resolves each match via
  binary search (O(log n) per match)

The content is fully synthetic and generated with a fixed seed: it contains no
code from any real project. Both paths must produce identical results; the script
asserts that before timing anything.

Usage: uv run python scripts/profile_search_text.py [num_lines] [num_matches]
"""

import random
import re
import sys
import time

import solidlsp  # noqa: F401  # imported first: solidlsp must resolve before serena.util.text_utils (known circular-import window)
from solidlsp.ls_utils import TextCoordinates, TextUtils


def generate_synthetic_content(num_lines: int, match_identifier: str, match_frequency: float = 0.15) -> str:
    """
    Generates synthetic pseudo-code content with a fixed seed.

    :param num_lines: number of lines to generate
    :param match_identifier: the identifier the benchmark pattern will search for
    :param match_frequency: fraction of lines that reference the match identifier
    :return: the synthetic content as a single string
    """
    rng = random.Random(1234)  # fixed seed for reproducibility
    filler_identifiers = ["var_global_contador", "otra_funcion_aleatoria", "gestion_operaciones", "ajuste_niveles"]
    lines = []
    for i in range(num_lines):
        kind = rng.random()
        if kind < match_frequency:
            lines.append(f"    double resultado_{i} = {match_identifier}({rng.randint(1, 999)});")
        elif kind < match_frequency + 0.15:
            lines.append(f"    if ({filler_identifiers[rng.randrange(len(filler_identifiers))]} > {rng.randint(0, 100)}) {{")
        elif kind < match_frequency + 0.25:
            lines.append("    }")
        elif kind < match_frequency + 0.40:
            lines.append(f"// comment line {i} with filler text {rng.randint(1000, 9999)}")
        else:
            lines.append(f"    int local_variable_{i} = {rng.randint(0, 5000)};")
    return "\n".join(lines) + "\n"


def resolve_before(content: str, compiled_pattern: re.Pattern) -> list[tuple[int, int]]:
    """Resolves line coordinates the way upstream currently does (TextStepper from index 0 per match)."""
    results = []
    for match in compiled_pattern.finditer(content):
        start_pos, end_pos = match.start(), match.end()
        start_line_num = TextUtils.get_line_from_index(content, start_pos)
        end_line_num = TextUtils.get_line_from_index(content, end_pos)
        if end_line_num > start_line_num and TextUtils.get_line_col_from_index(content, end_pos)[1] == 0:
            end_line_num -= 1
        results.append((start_line_num, end_line_num))
    return results


def resolve_after(content: str, compiled_pattern: re.Pattern) -> list[tuple[int, int]]:
    """Resolves line coordinates the way this PR proposes (cached line starts + binary search)."""
    coordinates = TextCoordinates(content)
    results = []
    for match in compiled_pattern.finditer(content):
        start_pos, end_pos = match.start(), match.end()
        s = coordinates.line_col_at_index(start_pos).line
        end_loc = coordinates.line_col_at_index(end_pos)
        e = end_loc.line
        if e > s and end_loc.col == 0:
            e -= 1
        results.append((s, e))
    return results


def main() -> None:
    num_lines = int(sys.argv[1]) if len(sys.argv) > 1 else 12000
    match_identifier = "funcion_calcula_parametro"
    content = generate_synthetic_content(num_lines, match_identifier)
    compiled_pattern = re.compile(match_identifier)

    num_matches = len(list(compiled_pattern.finditer(content)))
    print(f"synthetic file: {content.count(chr(10)):,} lines, {len(content):,} chars, {num_matches} matches")

    before = resolve_before(content, compiled_pattern)
    after = resolve_after(content, compiled_pattern)
    assert before == after, "implementations disagree; this script only measures identical work"
    print(f"results identical: OK ({len(before)} matches)")

    for name, fn in [
        ("before (TextStepper, O(n) per match)", lambda: resolve_before(content, compiled_pattern)),
        ("after (bisect, O(log n) per match)", lambda: resolve_after(content, compiled_pattern)),
    ]:
        times = []
        for _ in range(5):
            t0 = time.perf_counter()
            fn()
            times.append(time.perf_counter() - t0)
        print(f"{name}: {min(times) * 1000:.2f} ms (best of 5)")


if __name__ == "__main__":
    main()
