from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FrontmatterParseResult:
    frontmatter: dict[str, str]
    body: str


class FrontmatterParser:
    """Parser and renderer for simple scalar frontmatter fields."""

    DELIMITER = "---"

    @staticmethod
    def _validate_field(key: str, value: str) -> None:
        if not key:
            raise ValueError("Frontmatter key must not be empty")
        if ":" in key:
            raise ValueError("Frontmatter key must not contain ':'")
        if "\n" in key or "\r" in key:
            raise ValueError("Frontmatter key must be a single line")
        if "\n" in value or "\r" in value:
            raise ValueError("Frontmatter value must be a single line")

    @classmethod
    def parse(cls, content: str) -> FrontmatterParseResult:
        lines = content.splitlines(keepends=True)
        if not lines or lines[0].rstrip("\r\n") != cls.DELIMITER:
            return FrontmatterParseResult(frontmatter={}, body=content)

        closing_index: int | None = None
        for index, line in enumerate(lines[1:], start=1):
            if line.rstrip("\r\n") == cls.DELIMITER:
                closing_index = index
                break

        if closing_index is None:
            return FrontmatterParseResult(frontmatter={}, body=content)

        frontmatter: dict[str, str] = {}
        for line in lines[1:closing_index]:
            field = line.rstrip("\r\n")
            if not field:
                continue
            if ":" not in field:
                return FrontmatterParseResult(frontmatter={}, body=content)

            key, value = field.split(":", 1)
            key = key.strip()
            if not key:
                return FrontmatterParseResult(frontmatter={}, body=content)

            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            frontmatter[key] = value

        body = "".join(lines[closing_index + 1 :])
        return FrontmatterParseResult(frontmatter=frontmatter, body=body)

    @classmethod
    def render(cls, frontmatter: dict[str, str], body: str) -> str:
        if not frontmatter:
            return body

        for key, value in frontmatter.items():
            cls._validate_field(key, value)

        fields = "\n".join(f"{key}: {value}" for key, value in frontmatter.items())
        return f"{cls.DELIMITER}\n{fields}\n{cls.DELIMITER}\n{body}"
