import logging

import pytest

from serena.config.serena_config import SerenaConfig
from serena.mcp import SerenaMCPFactory
from serena.tools.tools_base import ToolRegistry


@pytest.mark.parametrize("context", ("chatgpt", "codex", "oaicompat-agent"))
def test_all_tool_parameters_have_type(context):
    """
    For every tool exposed by Serena, ensure that the generated
    Open‑AI schema contains a ``type`` entry for each parameter.
    """
    cfg = SerenaConfig(gui_log_window=False, web_dashboard=False, log_level=logging.ERROR)
    registry = ToolRegistry()
    cfg.included_optional_tools = tuple(registry.get_tool_names_optional())
    factory = SerenaMCPFactory(context=context)
    # Initialize the agent so that the tools are available
    factory.agent = factory._create_serena_agent(cfg)
    tools = list(factory._iter_tools())

    for tool in tools:
        mcp_tool = factory.make_mcp_tool(tool, openai_tool_compatible=True)
        params = mcp_tool.parameters

        # Collect any parameter that lacks a type
        issues = []
        print(f"Checking tool {tool}")

        if "properties" not in params:
            issues.append(f"Tool {tool.get_name()!r} missing properties section")
        else:
            for pname, prop in params["properties"].items():
                if "type" not in prop:
                    issues.append(f"Tool {tool.get_name()!r} parameter {pname!r} missing 'type'")
        if issues:
            raise AssertionError("\n".join(issues))
