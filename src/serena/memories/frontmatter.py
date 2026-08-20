from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass(frozen=True)
class _FrontmatterField:
    key: str
    line_index: int
    value_start: int
    value_end: int


@dataclass(frozen=True)
class FrontmatterParseResult:
    frontmatter: dict[str, str]
    body: str
    prefix: str | None = None
    _fields: tuple[_FrontmatterField, ...] = field(default=(), repr=False)

    @property
    def is_managed(self) -> bool:
        return self.prefix is not None

    def with_body(self, body: str) -> str:
        if self.prefix is None:
            return body
        return self.prefix + body


class FrontmatterParser:
    """Parser and byte-preserving updater for Serena scalar frontmatter."""

    DELIMITER = "---"
    VERSION_KEY = "serena_frontmatter_version"
    VERSION = "1"
    TYPE_KEY = "type"
    DEFAULT_TYPE = "Serena Memory"

    @staticmethod
    def _line_ending(line: str) -> str:
        if line.endswith("\r\n"):
            return "\r\n"
        if line.endswith("\n"):
            return "\n"
        if line.endswith("\r"):
            return "\r"
        return ""

    @classmethod
    def _without_line_ending(cls, line: str) -> str:
        ending = cls._line_ending(line)
        return line[: -len(ending)] if ending else line

    @staticmethod
    def _validate_field(key: str, value: str) -> None:
        if not key:
            raise ValueError("Frontmatter key must not be empty")
        if key != key.strip():
            raise ValueError("Frontmatter key must not have surrounding whitespace")
        if ":" in key:
            raise ValueError("Frontmatter key must not contain ':'")
        if "\n" in key or "\r" in key:
            raise ValueError("Frontmatter key must be a single line")
        if "\n" in value or "\r" in value:
            raise ValueError("Frontmatter value must be a single line")

    @staticmethod
    def _parse_value(value: str, line_number: int) -> str:
        token = value.strip()
        if not token:
            return ""

        if token.startswith('"') or token.endswith('"'):
            try:
                decoded = json.loads(token)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Malformed quoted frontmatter value on line {line_number}: {exc.msg}") from exc
            if not isinstance(decoded, str):
                raise ValueError(f"Quoted frontmatter value on line {line_number} must decode to a string")
            return decoded

        if token.startswith("'") or token.endswith("'"):
            raise ValueError(f"Single-quoted frontmatter values are unsupported on line {line_number}; use JSON double quotes")

        return token

    @classmethod
    def _parse_field(cls, line: str, line_index: int) -> tuple[_FrontmatterField, str]:
        raw = cls._without_line_ending(line)
        if ":" not in raw:
            raise ValueError(f"Malformed frontmatter field on line {line_index + 1}: expected 'key: value'")

        colon_index = raw.index(":")
        key = raw[:colon_index].strip()
        if not key:
            raise ValueError(f"Malformed frontmatter field on line {line_index + 1}: key must not be empty")

        value_part = raw[colon_index + 1 :]
        leading_length = len(value_part) - len(value_part.lstrip())
        trailing_length = len(value_part) - len(value_part.rstrip())
        value_start = colon_index + 1 + leading_length
        value_end = len(raw) - trailing_length if trailing_length else len(raw)
        if not value_part.strip():
            value_end = value_start
        value = cls._parse_value(value_part, line_index + 1)
        return _FrontmatterField(key, line_index, value_start, value_end), value

    @classmethod
    def parse(cls, content: str) -> FrontmatterParseResult:
        lines = content.splitlines(keepends=True)
        if not lines or cls._without_line_ending(lines[0]) != cls.DELIMITER or len(lines) < 2:
            return FrontmatterParseResult(frontmatter={}, body=content)

        marker_index: int | None = None
        for index, line in enumerate(lines[1:], start=1):
            if cls._without_line_ending(line).strip():
                marker_index = index
                break
        if marker_index is None:
            return FrontmatterParseResult(frontmatter={}, body=content)

        first_raw = cls._without_line_ending(lines[marker_index])
        if ":" not in first_raw:
            if first_raw.strip().startswith(cls.VERSION_KEY):
                raise ValueError("Malformed Serena frontmatter version marker: expected 'serena_frontmatter_version: 1'")
            return FrontmatterParseResult(frontmatter={}, body=content)

        first_key, first_value = first_raw.split(":", 1)
        if first_key.strip() != cls.VERSION_KEY:
            return FrontmatterParseResult(frontmatter={}, body=content)
        if first_value.strip() != cls.VERSION:
            raise ValueError(f"Unsupported Serena frontmatter version {first_value.strip()!r}; expected {cls.VERSION}")

        closing_index: int | None = None
        for index, line in enumerate(lines[marker_index + 1 :], start=marker_index + 1):
            if cls._without_line_ending(line) == cls.DELIMITER:
                closing_index = index
                break
        if closing_index is None:
            raise ValueError("Malformed Serena frontmatter: missing closing '---' delimiter")

        frontmatter: dict[str, str] = {}
        fields: list[_FrontmatterField] = []
        seen_keys: set[str] = set()
        for index, line in enumerate(lines[1:closing_index], start=1):
            raw = cls._without_line_ending(line)
            if not raw.strip():
                continue
            parsed_field, value = cls._parse_field(line, index)
            if parsed_field.key in seen_keys:
                raise ValueError(f"Duplicate frontmatter key {parsed_field.key!r} on line {index + 1}")
            seen_keys.add(parsed_field.key)
            fields.append(parsed_field)

            if parsed_field.key == cls.VERSION_KEY:
                if index != marker_index or value != cls.VERSION:
                    raise ValueError(f"Unsupported Serena frontmatter version {value!r}; expected {cls.VERSION}")
                continue
            frontmatter[parsed_field.key] = value

        memory_type = frontmatter.get(cls.TYPE_KEY)
        if memory_type is None:
            raise ValueError("Marked Serena frontmatter must contain a non-empty 'type' field")
        if not memory_type.strip():
            raise ValueError("Marked Serena frontmatter 'type' field must not be empty")

        prefix = "".join(lines[: closing_index + 1])
        body = "".join(lines[closing_index + 1 :])
        return FrontmatterParseResult(frontmatter=frontmatter, body=body, prefix=prefix, _fields=tuple(fields))

    @classmethod
    def render(cls, frontmatter: dict[str, str], body: str, newline: str = "\n") -> str:
        if newline not in {"\n", "\r\n"}:
            raise ValueError("Frontmatter newline must be either LF or CRLF")
        if cls.VERSION_KEY in frontmatter:
            raise ValueError(f"Frontmatter key {cls.VERSION_KEY!r} is reserved and cannot be updated")

        metadata = dict(frontmatter)
        metadata.setdefault(cls.TYPE_KEY, cls.DEFAULT_TYPE)
        for key, value in metadata.items():
            cls._validate_field(key, value)
        if not metadata[cls.TYPE_KEY].strip():
            raise ValueError("Marked Serena frontmatter 'type' field must not be empty")

        ordered_fields = [(cls.TYPE_KEY, metadata.pop(cls.TYPE_KEY)), *metadata.items()]
        lines = [cls.DELIMITER, f"{cls.VERSION_KEY}: {cls.VERSION}"]
        lines.extend(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in ordered_fields)
        lines.append(cls.DELIMITER)
        return newline.join(lines) + newline + body

    @classmethod
    def upsert(cls, parsed: FrontmatterParseResult, key: str, value: str) -> str:
        cls._validate_field(key, value)
        if key == cls.VERSION_KEY:
            raise ValueError(f"Frontmatter key {cls.VERSION_KEY!r} is reserved and cannot be updated")

        if not parsed.is_managed:
            return cls.render({key: value}, parsed.body)

        assert parsed.prefix is not None
        prefix_lines = parsed.prefix.splitlines(keepends=True)
        rendered_value = json.dumps(value, ensure_ascii=False)
        field = next((item for item in parsed._fields if item.key == key), None)
        if field is not None:
            line = prefix_lines[field.line_index]
            prefix_lines[field.line_index] = line[: field.value_start] + rendered_value + line[field.value_end :]
        else:
            newline = next((cls._line_ending(line) for line in prefix_lines if cls._line_ending(line)), "\n")
            prefix_lines.insert(len(prefix_lines) - 1, f"{key}: {rendered_value}{newline}")

        updated = "".join(prefix_lines) + parsed.body
        cls.parse(updated)
        return updated
