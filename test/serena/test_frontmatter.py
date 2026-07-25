import pytest

from serena.memories.frontmatter import FrontmatterParser


def test_parse_without_frontmatter_returns_content_unchanged() -> None:
    content = "# Memory\n\nBody\n"

    result = FrontmatterParser.parse(content)

    assert result.frontmatter == {}
    assert result.body == content


def test_parse_frontmatter_preserves_body_whitespace() -> None:
    content = '---\nsummary: "Short description"\nurl: https://example.com:443/docs\n---\n\n# Memory\n\nBody\n'

    result = FrontmatterParser.parse(content)

    assert result.frontmatter == {
        "summary": "Short description",
        "url": "https://example.com:443/docs",
    }
    assert result.body == "\n# Memory\n\nBody\n"


def test_parse_empty_frontmatter() -> None:
    result = FrontmatterParser.parse("---\n---\nBody\n")

    assert result.frontmatter == {}
    assert result.body == "Body\n"


@pytest.mark.parametrize(
    "content",
    [
        "---\nsummary: missing closing delimiter\n",
        "---\nnot a scalar field\n---\nBody\n",
        "---\n: missing key\n---\nBody\n",
        " ---\nsummary: indented opening delimiter\n---\nBody\n",
    ],
)
def test_malformed_frontmatter_is_plain_content(content: str) -> None:
    result = FrontmatterParser.parse(content)

    assert result.frontmatter == {}
    assert result.body == content


def test_render_round_trip_is_stable() -> None:
    frontmatter = {
        "summary": "Short description",
        "custom": "value:with:colons",
    }
    body = "\n# Memory\n\nBody with trailing whitespace.\n\n"

    rendered = FrontmatterParser.render(frontmatter, body)
    parsed = FrontmatterParser.parse(rendered)

    assert parsed.frontmatter == frontmatter
    assert parsed.body == body
    assert FrontmatterParser.render(parsed.frontmatter, parsed.body) == rendered


@pytest.mark.parametrize(
    ("frontmatter", "error"),
    [
        ({"": "value"}, "must not be empty"),
        ({"bad:key": "value"}, "must not contain"),
        ({"bad\nkey": "value"}, "single line"),
        ({"summary": "bad\nvalue"}, "single line"),
        ({"summary": "bad\rvalue"}, "single line"),
    ],
)
def test_render_rejects_non_scalar_fields(frontmatter: dict[str, str], error: str) -> None:
    with pytest.raises(ValueError, match=error):
        FrontmatterParser.render(frontmatter, "Body\n")
