import pytest

from interprompt.jinja_template import JinjaTemplate
from serena.config.context_mode import SerenaAgentContext

GROK_EXCLUDED_TOOLS = {
    "create_text_file",
    "read_file",
    "execute_shell_command",
    "find_file",
    "list_dir",
    "search_for_pattern",
}

BUILTIN_RUNTIME_CONTEXT_NAMES = [
    name for name in SerenaAgentContext.list_registered_context_names(include_user_contexts=False) if name != "context.template"
]


def _render_context_prompt(context: SerenaAgentContext) -> str:
    """Render with the same template variables SerenaAgent._format_prompt provides.

    Note: context YAMLs (e.g. grok.yml) are currently static (no Jinja), but the variables
    match exactly what _format_prompt supplies. The outer system prompt template uses them.
    """
    # Provide non-empty values so any future Jinja in a context prompt would still be exercised.
    return JinjaTemplate(context.prompt).render(
        available_tools=["find_symbol", "get_symbols_overview", "replace_content"],
        available_markers=["ToolMarkerSymbolicRead"],
        tool_names={"find_symbol": "find_symbol", "get_symbols_overview": "get_symbols_overview"},
    )


def test_grok_context_loads():
    context = SerenaAgentContext.from_name("grok")

    assert context.name == "grok"
    assert context.single_project is True
    assert context.structured_tool_output is None
    assert set(context.excluded_tools) == GROK_EXCLUDED_TOOLS


def test_grok_context_prompt_renders():
    context = SerenaAgentContext.from_name("grok")

    rendered_prompt = _render_context_prompt(context)

    assert rendered_prompt.strip()
    assert "Serena's code intelligence tools" in rendered_prompt


@pytest.mark.parametrize("context_name", BUILTIN_RUNTIME_CONTEXT_NAMES)
def test_builtin_contexts_load_and_prompt_templates_render(context_name: str):
    context = SerenaAgentContext.from_name(context_name)

    rendered_prompt = _render_context_prompt(context)

    assert context.name == context_name
    assert isinstance(context.excluded_tools, list)
    assert rendered_prompt == "" or rendered_prompt.strip()
