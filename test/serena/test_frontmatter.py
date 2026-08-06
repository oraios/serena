import json

import pytest

from serena.memories.frontmatter import FrontmatterParser


def _marked(*fields: str, body: str = "Body\n", newline: str = "\n") -> str:
    lines = [
        "---",
        "serena_frontmatter_version: 1",
        'type: "Serena Memory"',
        *fields,
        "---",
    ]
    return newline.join(lines) + newline + body


def test_parse_without_frontmatter_returns_content_unchanged() -> None:
    content = "# Memory\n\nBody\n"

    result = FrontmatterParser.parse(content)

    assert result.frontmatter == {}
    assert result.body == content
    assert not result.is_managed


@pytest.mark.parametrize(
    "content",
    [
        "---\ndescription: Valid-looking legacy metadata\n---\nBody\n",
        "---\n---\nBody\n",
        "---\ndescription: missing closing delimiter\n",
        "---\nnot a scalar field\n---\nBody\n",
        "---\n: missing key\n---\nBody\n",
        "---\ndescription: legacy\nserena_frontmatter_version: 1\n---\nBody\n",
        " ---\nserena_frontmatter_version: 1\ntype: Serena Memory\n---\nBody\n",
    ],
)
def test_unmarked_legacy_delimiters_are_plain_content(content: str) -> None:
    result = FrontmatterParser.parse(content)

    assert result.frontmatter == {}
    assert result.body == content
    assert not result.is_managed


def test_parse_marked_frontmatter_preserves_prefix_and_body_whitespace() -> None:
    content = _marked(
        'description: " Short description "',
        "url: https://example.com:443/docs",
        r'note: "A quote: \"hello\" and a backslash: \\ "',
        body="\n# Memory\n\nBody\n",
    )

    result = FrontmatterParser.parse(content)

    assert result.frontmatter == {
        "type": "Serena Memory",
        "description": " Short description ",
        "url": "https://example.com:443/docs",
        "note": 'A quote: "hello" and a backslash: \\ ',
    }
    assert "serena_frontmatter_version" not in result.frontmatter
    assert result.prefix == content[: -len(result.body)]
    assert result.body == "\n# Memory\n\nBody\n"


def test_marker_is_first_field_even_after_blank_lines() -> None:
    content = '---\n\nserena_frontmatter_version: 1\ntype: "Serena Memory"\n---\nBody\n'

    result = FrontmatterParser.parse(content)

    assert result.is_managed
    assert result.body == "Body\n"
    assert result.with_body(result.body) == content


@pytest.mark.parametrize(
    ("content", "error"),
    [
        ("---\nserena_frontmatter_version 1\ntype: Serena Memory\n---\nBody\n", "version marker"),
        ("---\nserena_frontmatter_version: 2\ntype: Serena Memory\n---\nBody\n", "Unsupported"),
        ("---\nserena_frontmatter_version: 1\ntype: Serena Memory\n", "closing"),
        ("---\nserena_frontmatter_version: 1\ntype: Serena Memory\ninvalid\n---\nBody\n", "Malformed"),
        ("---\nserena_frontmatter_version: 1\ndescription: Missing type\n---\nBody\n", "type"),
        ('---\nserena_frontmatter_version: 1\ntype: "  "\n---\nBody\n', "type"),
        (
            "---\nserena_frontmatter_version: 1\ntype: Serena Memory\ndescription: one\n description : two\n---\nBody\n",
            "Duplicate",
        ),
        ('---\nserena_frontmatter_version: 1\ntype: Serena Memory\ndescription: "unterminated\n---\nBody\n', "Malformed quoted"),
        ("---\nserena_frontmatter_version: 1\ntype: 'Serena Memory'\n---\nBody\n", "Single-quoted"),
    ],
)
def test_malformed_marked_frontmatter_is_rejected(content: str, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        FrontmatterParser.parse(content)


def test_render_uses_marker_default_type_and_reversible_json_strings() -> None:
    frontmatter = {
        "description": 'Short "description"',
        "custom": "value:with:colons\\and\\slashes",
    }
    body = "\n# Memory\n\nBody with trailing whitespace.\n\n"

    rendered = FrontmatterParser.render(frontmatter, body)
    parsed = FrontmatterParser.parse(rendered)

    assert rendered.startswith('---\nserena_frontmatter_version: 1\ntype: "Serena Memory"\n')
    assert parsed.frontmatter == {"type": "Serena Memory", **frontmatter}
    assert parsed.body == body
    assert parsed.with_body(parsed.body) == rendered


def test_upsert_replaces_only_selected_value_bytes() -> None:
    content = (
        "---\r\n"
        "serena_frontmatter_version: 1\r\n"
        'type :  "Serena Memory"  \r\n'
        "description  :   old:value   \r\n"
        'custom:\t"keep:me"\r\n'
        "---\r\n"
        "\r\nBody\r\n"
    )
    value = 'New "quoted" value \\ path:part'

    updated = FrontmatterParser.upsert(FrontmatterParser.parse(content), "description", value)

    expected = content.replace("old:value", json.dumps(value, ensure_ascii=False))
    assert updated == expected
    assert FrontmatterParser.parse(updated).frontmatter["description"] == value


def test_upsert_inserts_before_closing_delimiter_without_reserializing() -> None:
    content = _marked('description : "Keep formatting"  ', body="\nBody\n")

    updated = FrontmatterParser.upsert(FrontmatterParser.parse(content), "owner", "team:core")

    assert updated == content.replace("---\n\nBody", 'owner: "team:core"\n---\n\nBody', 1)


@pytest.mark.parametrize(
    ("frontmatter", "error"),
    [
        ({"": "value"}, "must not be empty"),
        ({" bad": "value"}, "surrounding whitespace"),
        ({"bad:key": "value"}, "must not contain"),
        ({"bad\nkey": "value"}, "single line"),
        ({"description": "bad\nvalue"}, "single line"),
        ({"description": "bad\rvalue"}, "single line"),
        ({"type": ""}, "type"),
        ({"serena_frontmatter_version": "1"}, "reserved"),
    ],
)
def test_render_rejects_invalid_fields(frontmatter: dict[str, str], error: str) -> None:
    with pytest.raises(ValueError, match=error):
        FrontmatterParser.render(frontmatter, "Body\n")


def test_upsert_rejects_reserved_version_and_empty_type() -> None:
    parsed = FrontmatterParser.parse(_marked(body="Body\n"))

    with pytest.raises(ValueError, match="reserved"):
        FrontmatterParser.upsert(parsed, "serena_frontmatter_version", "2")
    with pytest.raises(ValueError, match="type"):
        FrontmatterParser.upsert(parsed, "type", "   ")
