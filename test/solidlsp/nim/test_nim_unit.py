"""
Unit tests for Nim language server components that don't require a running language server.
"""

import json
import os
from io import BytesIO
from unittest.mock import MagicMock

import pytest

from solidlsp.language_servers.nim_language_server import (
    NimLanguageServer,
    NimLanguageServerProcess,
)
from solidlsp.ls_config import Language
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo


@pytest.mark.nim
class TestNimLanguageServerProcessSendPayload:
    """Test that NimLanguageServerProcess sends Content-Length but not Content-Type."""

    def test_send_payload_has_content_length_no_content_type(self) -> None:
        """Verify that _send_payload sends Content-Length header but omits Content-Type."""
        process_launch_info = ProcessLaunchInfo(cmd="echo", cwd="/tmp")
        proc = NimLanguageServerProcess(
            process_launch_info,
            language=Language.NIM,
            determine_log_level=lambda _: 20,
            start_independent_lsp_process=False,
        )

        # Mock the process and stdin
        mock_stdin = BytesIO()
        mock_process = MagicMock()
        mock_process.stdin = mock_stdin
        proc.process = mock_process

        payload = {"jsonrpc": "2.0", "method": "test", "id": 1}
        proc._send_payload(payload)

        output = mock_stdin.getvalue()
        output_str = output.decode("utf-8")

        assert "Content-Length:" in output_str, "Should include Content-Length header"
        assert "Content-Type" not in output_str, "Should NOT include Content-Type header"

        # Verify the body is valid JSON
        header_end = output_str.index("\r\n\r\n") + 4
        body = output_str[header_end:]
        parsed = json.loads(body)
        assert parsed["method"] == "test"

    def test_send_payload_no_process(self) -> None:
        """Verify _send_payload is a no-op when process is None."""
        process_launch_info = ProcessLaunchInfo(cmd="echo", cwd="/tmp")
        proc = NimLanguageServerProcess(
            process_launch_info,
            language=Language.NIM,
            determine_log_level=lambda _: 20,
            start_independent_lsp_process=False,
        )
        proc.process = None
        # Should not raise
        proc._send_payload({"jsonrpc": "2.0", "method": "test", "id": 1})


@pytest.mark.nim
class TestNimCreateConfigIfNeeded:
    """Test _create_nim_config_if_needed with various filesystem states."""

    def _make_server(self, tmp_path: str) -> NimLanguageServer:
        """Create a NimLanguageServer instance with mocked internals for config testing."""
        server = object.__new__(NimLanguageServer)
        server.repository_root_path = tmp_path
        return server

    def test_creates_nimsuggest_cfg_when_absent(self, tmp_path: str) -> None:
        """Should create nimsuggest.cfg when it doesn't exist."""
        server = self._make_server(str(tmp_path))
        server._create_nim_config_if_needed()

        cfg_path = os.path.join(str(tmp_path), "nimsuggest.cfg")
        assert os.path.exists(cfg_path)
        with open(cfg_path) as f:
            content = f.read()
        assert "-d:nimsuggest" in content

    def test_does_not_overwrite_existing_nimsuggest_cfg(self, tmp_path: str) -> None:
        """Should not overwrite existing nimsuggest.cfg."""
        cfg_path = os.path.join(str(tmp_path), "nimsuggest.cfg")
        with open(cfg_path, "w") as f:
            f.write("# custom config")

        server = self._make_server(str(tmp_path))
        server._create_nim_config_if_needed()

        with open(cfg_path) as f:
            content = f.read()
        assert content == "# custom config"

    def test_creates_nim_cfg_with_nimble_file(self, tmp_path: str) -> None:
        """Should create nim.cfg when .nimble file exists and nim.cfg doesn't."""
        # Create a .nimble file
        with open(os.path.join(str(tmp_path), "myproject.nimble"), "w") as f:
            f.write("# Package\n")

        server = self._make_server(str(tmp_path))
        server._create_nim_config_if_needed()

        cfg_path = os.path.join(str(tmp_path), "nim.cfg")
        assert os.path.exists(cfg_path)
        with open(cfg_path) as f:
            content = f.read()
        assert '--path:"."' in content

    def test_nim_cfg_includes_src_and_tests_paths(self, tmp_path: str) -> None:
        """Should include src and tests path hints when those directories exist."""
        os.makedirs(os.path.join(str(tmp_path), "src"))
        os.makedirs(os.path.join(str(tmp_path), "tests"))
        with open(os.path.join(str(tmp_path), "myproject.nimble"), "w") as f:
            f.write("# Package\n")

        server = self._make_server(str(tmp_path))
        server._create_nim_config_if_needed()

        cfg_path = os.path.join(str(tmp_path), "nim.cfg")
        with open(cfg_path) as f:
            content = f.read()
        assert '--path:"src"' in content
        assert '--path:"tests"' in content

    def test_no_nim_cfg_without_nimble_file(self, tmp_path: str) -> None:
        """Should not create nim.cfg when no .nimble file exists."""
        server = self._make_server(str(tmp_path))
        server._create_nim_config_if_needed()

        cfg_path = os.path.join(str(tmp_path), "nim.cfg")
        assert not os.path.exists(cfg_path)

    def test_does_not_overwrite_existing_nim_cfg(self, tmp_path: str) -> None:
        """Should not overwrite existing nim.cfg even if .nimble file exists."""
        cfg_path = os.path.join(str(tmp_path), "nim.cfg")
        with open(cfg_path, "w") as f:
            f.write("# custom nim.cfg")
        with open(os.path.join(str(tmp_path), "myproject.nimble"), "w") as f:
            f.write("# Package\n")

        server = self._make_server(str(tmp_path))
        server._create_nim_config_if_needed()

        with open(cfg_path) as f:
            content = f.read()
        assert content == "# custom nim.cfg"
