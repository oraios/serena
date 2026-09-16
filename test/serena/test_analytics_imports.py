"""The anthropic package must only be loaded when the Anthropic token counter is used (#2012)."""

import subprocess
import sys
from unittest.mock import MagicMock

import pytest

from serena.analytics import AnthropicTokenCount


@pytest.mark.parametrize("module", ["serena.cli", "serena.agent", "serena.analytics"])
def test_importing_serena_does_not_load_anthropic(module: str) -> None:
    code = f"import sys, {module}; print('anthropic' in sys.modules)"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, timeout=120)
    assert result.stdout.strip() == "False", f"importing {module} loaded the anthropic package"


def test_anthropic_token_count_sends_a_plain_user_message() -> None:
    estimator = AnthropicTokenCount.__new__(AnthropicTokenCount)
    estimator._model_name = "claude-sonnet-4-20250514"
    estimator._anthropic_client = MagicMock()
    estimator._anthropic_client.messages.count_tokens.return_value = MagicMock(input_tokens=7)

    assert estimator.estimate_token_count("hello") == 7
    estimator._anthropic_client.messages.count_tokens.assert_called_once_with(
        model="claude-sonnet-4-20250514",
        messages=[{"role": "user", "content": "hello"}],
    )
