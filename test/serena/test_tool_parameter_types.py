import pytest
from serena.mcp import SerenaMCPFactorySingleProcess
from serena.config.serena_config import SerenaConfig


def load_agent():
    """
    Load a minimal agent to expose the default set of tools.
    The tests run inside the container so a very small config file
    is sufficient.  The default SerenaConfig reads the config
    from ``src/serena/resources/config/contexts/<context>.yml``.
    """
    cfg = SerenaConfig.from_config_file()
    # Enable every optional tool in the configuration
    from serena.tools.tools_base import ToolRegistry

    registry = ToolRegistry()
    cfg.included_optional_tools = tuple(registry.get_tool_names_optional())
    cfg.excluded_tools = tuple()
    return cfg


@pytest.mark.parametrize("context", ("chatgpt", "codex", "openai-agent"))
def test_all_tool_parameters_have_type(context):
    """
    For every tool exposed by Serena, ensure that the generated
    Open‑AI schema contains a ``type`` entry for each parameter.
    """
    cfg = load_agent()
    factory = SerenaMCPFactorySingleProcess(context=context)
    # Initialize the agent so that the tools are available
    factory._instantiate_agent(cfg, [])
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
