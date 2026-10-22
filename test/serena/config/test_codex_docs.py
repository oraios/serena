import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _extract_codex_hook_config(markdown: str) -> dict:
    section_match = re.search(r"\n## Codex \(CLI and App\)\n(.*?)(?=\n## |\Z)", markdown, re.DOTALL)
    assert section_match is not None

    config_match = re.search(r"```json\n(\{.*?\})\n```", section_match.group(1), re.DOTALL)
    assert config_match is not None
    return json.loads(config_match.group(1))


def _handlers_by_command(config: dict) -> dict[str, dict]:
    handlers_by_command = {}
    for event, groups in config["hooks"].items():
        for group in groups:
            for handler in group["hooks"]:
                handlers_by_command[handler["command"]] = {
                    "event": event,
                    "matcher": group.get("matcher"),
                    "statusMessage": handler.get("statusMessage"),
                    "timeout": handler.get("timeout"),
                }
    return handlers_by_command


def test_codex_hook_example_configures_plan_awareness_and_preserves_existing_timeouts():
    clients_doc = (PROJECT_ROOT / "docs/02-usage/030_clients.md").read_text()
    handlers = _handlers_by_command(_extract_codex_hook_config(clients_doc))

    assert handlers["serena-hooks remind --client=codex"] == {
        "event": "PreToolUse",
        "matcher": "Bash",
        "statusMessage": "Checking Serena tool usage",
        "timeout": 5,
    }
    assert handlers["serena-hooks plan-guard --client=codex"] == {
        "event": "PreToolUse",
        "matcher": "^mcp__serena__",
        "statusMessage": "Checking Serena plan-mode permissions",
        "timeout": 5,
    }
    assert handlers["serena-hooks activate --client=codex"] == {
        "event": "SessionStart",
        "matcher": "startup|resume",
        "statusMessage": "Activating Serena project",
        "timeout": 5,
    }
    assert handlers["serena-hooks plan-context --client=codex"] == {
        "event": "UserPromptSubmit",
        "matcher": None,
        "statusMessage": "Applying Serena plan context",
        "timeout": 5,
    }
    assert handlers["serena-hooks cleanup --client=codex"] == {
        "event": "SessionEnd",
        "matcher": None,
        "statusMessage": "Cleaning up Serena hook state",
        "timeout": 3,
    }
