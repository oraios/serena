"""
Minimal frontmatter parsing utilities for memory files.

Currently supports a very small subset of YAML-like syntax:
---
summary: "Some short text"
---
"""

from typing import Tuple, Dict


def parse_frontmatter(content: str) -> Tuple[Dict[str, str], str]:
    """
    Parses a minimal YAML-like frontmatter block at the top of a file.

    Expected format:

    ---
    summary: "Some text"
    ---
    Body content...

    Returns:
        (frontmatter_dict, body_content)
    """

    frontmatter: Dict[str, str] = {}

    if not content.startswith("---"):
        return frontmatter, content

    lines = content.splitlines()
    if len(lines) < 3:
        return frontmatter, content

    # First line must be ---
    if lines[0].strip() != "---":
        return frontmatter, content

    # Find closing ---
    closing_index = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            closing_index = i
            break

    if closing_index is None:
        return frontmatter, content

    # Parse lines between the two ---
    for line in lines[1:closing_index]:
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"')

        # Only support "summary" for now
        if key == "summary":
            frontmatter[key] = value

    body = "\n".join(lines[closing_index + 1 :])

    return frontmatter, body