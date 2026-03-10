"""
Minimal frontmatter parsing utilities for memory files.

Supports a simple YAML-like frontmatter block at the top of a file.

Example:

---
summary: Some short text
author: Mehdi
priority: high
---

Body content...
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class FrontmatterParseResult:
    frontmatter: Dict[str, str]
    body: str


class FrontmatterParser:
    """
    Minimal YAML-like frontmatter parser.

    It extracts key/value pairs from a frontmatter block at the top of a file and
    returns the remaining body content.
    """

    @staticmethod
    def parse(content: str) -> FrontmatterParseResult:
        frontmatter: Dict[str, str] = {}

        if not content.startswith("---"):
            return FrontmatterParseResult(frontmatter=frontmatter, body=content)

        lines = content.splitlines()
        if len(lines) < 3:
            return FrontmatterParseResult(frontmatter=frontmatter, body=content)

        if lines[0].strip() != "---":
            return FrontmatterParseResult(frontmatter=frontmatter, body=content)

        closing_index = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                closing_index = i
                break

        if closing_index is None:
            return FrontmatterParseResult(frontmatter=frontmatter, body=content)

        for line in lines[1:closing_index]:
            if ":" not in line:
                continue

            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip('"')
            frontmatter[key] = value

        body = "\n".join(lines[closing_index + 1 :])
        return FrontmatterParseResult(frontmatter=frontmatter, body=body)


def parse_frontmatter(content: str) -> Tuple[Dict[str, str], str]:
    """
    Backwards-compatible functional wrapper.

    Returns:
        (frontmatter_dict, body_content)
    """
    result = FrontmatterParser.parse(content)
    return result.frontmatter, result.body
