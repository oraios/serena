import inspect
import json
import re
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from serena.config.client_setup import ClientSetupHandlerGrok
from serena.hooks import HookClient, PreToolUseRemindAboutSymbolicToolsHook

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _extract_section(markdown: str, heading: str) -> str:
    """Extract the content under a top-level ## heading (simple and sufficient for our docs)."""
    pattern = rf"\n## {re.escape(heading)}\n(.*?)(?=\n## |\Z)"
    match = re.search(pattern, markdown, re.DOTALL)
    return match.group(1) if match else ""


def _grok_payload(tool_name: str, tool_input: dict) -> dict:
    return {
        "hookEventName": "pre_tool_use",
        "sessionId": f"docs-{tool_name}",
        "toolName": tool_name,
        "toolInput": tool_input,
        "toolInputTruncated": False,
        "permissionMode": "bypassPermissions",
    }


def test_grok_docs_are_consistent():
    clients_doc = (PROJECT_ROOT / "docs/02-usage/030_clients.md").read_text()
    config_doc = (PROJECT_ROOT / "docs/02-usage/050_configuration.md").read_text()
    handler_source = inspect.getsource(ClientSetupHandlerGrok.apply)

    assert "\n## Grok\n" in clients_doc
    grok_section = _extract_section(clients_doc, "Grok")

    assert "030_clients.html#grok" in handler_source
    assert "serena setup grok" in grok_section
    assert "serena-hooks remind --client=grok" in grok_section
    assert "serena-hooks cleanup --client=grok" in grok_section

    assert "* `grok`: Optimized for use with xAI's Grok Build CLI." in config_doc
    assert "contexts `ide`, `claude-code`, and `grok` are **single-project contexts**" in config_doc


def test_grok_hook_matcher_docs_match_code(tmp_path: Path):
    clients_doc = (PROJECT_ROOT / "docs/02-usage/030_clients.md").read_text()
    grok_section = _extract_section(clients_doc, "Grok")

    matcher = re.search(r'"matcher": "([^"]+)"', grok_section)
    assert matcher is not None
    matcher_tools = set(matcher.group(1).split("|"))
    assert matcher_tools == {"grep", "read_file", "run_terminal_command"}

    payloads = {
        "grep": _grok_payload("grep", {"pattern": "foo", "path": "."}),
        "read_file": _grok_payload("read_file", {"target_file": "src/foo.py"}),
        "run_terminal_command": _grok_payload("run_terminal_command", {"command": "rg -n foo README.md"}),
    }
    for tool_name in matcher_tools:
        with patch("sys.stdin", StringIO(json.dumps(payloads[tool_name]))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            hook = PreToolUseRemindAboutSymbolicToolsHook(HookClient.GROK)

        assert hook.is_grep_call() or hook.is_read_call() or hook._is_shell_command_call()
