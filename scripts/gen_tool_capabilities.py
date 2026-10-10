"""Generate lightweight tool-capability metadata for hook processes."""

from pathlib import Path

from serena.constants import REPO_ROOT
from serena.tools import ToolRegistry

TARGET_PATH = Path(REPO_ROOT) / "src" / "serena" / "generated" / "tool_capabilities.py"


def _render_tool_capabilities(edit_capable_tool_names: list[str]) -> str:
    entries = "\n".join(f'        "{tool_name}",' for tool_name in edit_capable_tool_names)
    return f'''"""Generated tool-capability metadata. Do not edit manually."""

EDIT_CAPABLE_TOOL_NAMES: frozenset[str] = frozenset(
    {{
{entries}
    }}
)
'''


def main() -> None:
    # derive the manifest exclusively from registered tool metadata
    registry = ToolRegistry()
    edit_capable_tool_names = sorted(
        tool_class.get_name_from_cls() for tool_class in registry.get_all_tool_classes() if tool_class.can_edit()
    )

    # replace the generated module deterministically
    TARGET_PATH.write_text(_render_tool_capabilities(edit_capable_tool_names))


if __name__ == "__main__":
    main()
