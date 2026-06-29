"""
Smoke test for the activation_command feature.

Creates a temporary project whose project.yml declares an activation_command,
activates it via SerenaAgent (no LLM or language server required), then verifies
the command ran before the backend initialised.

Run with:
    uv run python scripts/smoke_test_activation_command.py
"""

import sys
import tempfile
from pathlib import Path

from serena.agent import SerenaAgent
from serena.config.serena_config import SerenaConfig
from serena.constants import SERENA_MANAGED_DIR_NAME


def make_project(root: Path, activation_command: str, trusted: bool) -> None:
    serena_dir = root / SERENA_MANAGED_DIR_NAME
    serena_dir.mkdir()
    (serena_dir / "project.yml").write_text(
        f"""\
project_name: smoke-test
languages: []
activation_command: "{activation_command}"
activation_command_timeout: 30
"""
    )
    gitignore = serena_dir / ".gitignore"
    gitignore.write_text("project.local.yml\n")


def run_scenario(label: str, trusted: bool, expect_sentinel: bool) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        sentinel = root / "sentinel.txt"
        make_project(root, activation_command="touch sentinel.txt", trusted=trusted)

        serena_config = SerenaConfig(
            gui_log_window=False,
            web_dashboard=False,
            trusted_project_path_patterns=["**"] if trusted else [],
        )

        agent = SerenaAgent(project=str(root), serena_config=serena_config)

        # Queue a no-op task behind init_project_services so we block until it finishes.
        agent.execute_task(lambda: None, name="wait-for-init")

        ok = sentinel.exists() == expect_sentinel
        status = "PASS" if ok else "FAIL"
        detail = "sentinel present" if sentinel.exists() else "sentinel absent"
        print(f"[{status}] {label}: {detail}")
        return ok


def main() -> None:
    results = [
        run_scenario("trusted project  → command runs", trusted=True, expect_sentinel=True),
        run_scenario("untrusted project → command skipped", trusted=False, expect_sentinel=False),
    ]
    if all(results):
        print("\nAll smoke tests passed.")
        sys.exit(0)
    else:
        print("\nSome smoke tests FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
