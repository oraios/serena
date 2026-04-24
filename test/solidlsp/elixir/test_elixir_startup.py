"""Unit tests for Elixir Expert language server startup behavior."""

import threading
from unittest.mock import MagicMock

from solidlsp.language_servers.elixir_tools.elixir_tools import ElixirTools


def _make_elixir_tools(tmp_path):
    language_server = object.__new__(ElixirTools)
    language_server.repository_root_path = str(tmp_path)
    language_server.server_ready = threading.Event()
    language_server.request_id = 0
    return language_server


def _make_mock_server():
    server = MagicMock()
    server.send.initialize.return_value = {"capabilities": {"textDocumentSync": {}}}
    return server


class TestElixirToolsStartup:
    """Tests for ElixirTools._start_server() startup behavior — the Expert deadlock fix."""

    def test_sends_did_open_for_mix_exs_after_initialized(self, tmp_path):
        """Expert blocks waiting for a didOpen notification to trigger its build pipeline."""
        (tmp_path / "mix.exs").write_text("defmodule App.MixProject do\n  use Mix.Project\nend\n", encoding="utf-8")

        language_server = _make_elixir_tools(tmp_path)
        server = _make_mock_server()
        language_server.server = server
        language_server.server_ready.set()

        language_server._start_server()

        calls = server.notify.did_open_text_document.call_args_list
        assert len(calls) == 1, f"Expected one didOpen notification for mix.exs, got {len(calls)}"
        text_doc = calls[0][0][0]["textDocument"]
        assert text_doc["uri"].endswith("mix.exs"), f"Expected mix.exs URI, got {text_doc['uri']}"
        assert text_doc["languageId"] == "elixir"

    def test_did_open_contains_mix_exs_content(self, tmp_path):
        """The didOpen notification must include the file content so Expert can parse it."""
        content = "defmodule App.MixProject do\n  use Mix.Project\nend\n"
        (tmp_path / "mix.exs").write_text(content, encoding="utf-8")

        language_server = _make_elixir_tools(tmp_path)
        server = _make_mock_server()
        language_server.server = server
        language_server.server_ready.set()

        language_server._start_server()

        calls = server.notify.did_open_text_document.call_args_list
        assert len(calls) == 1
        text_doc = calls[0][0][0]["textDocument"]
        assert text_doc["text"] == content

    def test_closes_mix_exs_after_server_ready(self, tmp_path):
        """mix.exs is closed after Expert signals readiness so it does not linger open."""
        (tmp_path / "mix.exs").write_text("defmodule App.MixProject do\n  use Mix.Project\nend\n", encoding="utf-8")

        language_server = _make_elixir_tools(tmp_path)
        server = _make_mock_server()
        language_server.server = server
        language_server.server_ready.set()

        language_server._start_server()

        close_calls = server.notify.did_close_text_document.call_args_list
        assert len(close_calls) == 1, f"Expected one didClose for mix.exs, got {len(close_calls)}"
        text_doc = close_calls[0][0][0]["textDocument"]
        assert text_doc["uri"].endswith("mix.exs"), f"Expected mix.exs URI, got {text_doc['uri']}"

    def test_startup_event_order_initialized_then_didopen_then_didclose(self, tmp_path):
        """Initialized → didOpen(mix.exs) → [ready] → didClose(mix.exs) is the required sequence."""
        (tmp_path / "mix.exs").write_text("defmodule App.MixProject do\n  use Mix.Project\nend\n", encoding="utf-8")

        events: list[str] = []

        language_server = _make_elixir_tools(tmp_path)
        server = _make_mock_server()
        language_server.server = server
        language_server.server_ready.set()

        server.notify.initialized.side_effect = lambda *_: events.append("initialized")
        server.notify.did_open_text_document.side_effect = lambda *_: events.append("didOpen")
        server.notify.did_close_text_document.side_effect = lambda *_: events.append("didClose")

        language_server._start_server()

        assert events == ["initialized", "didOpen", "didClose"], f"Unexpected startup event order: {events}"

    def test_no_crash_when_mix_exs_missing(self, tmp_path):
        """_start_server must not crash if mix.exs is absent (non-standard project layout)."""
        language_server = _make_elixir_tools(tmp_path)
        server = _make_mock_server()
        language_server.server = server
        language_server.server_ready.set()

        language_server._start_server()

        server.notify.did_open_text_document.assert_not_called()
