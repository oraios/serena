import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from solidlsp.language_servers.gdscript_language_server import GDScriptLanguageServer
from solidlsp.ls_config import Language
from solidlsp.settings import SolidLSPSettings


def test_gdscript_language_registration() -> None:
    assert Language.GDSCRIPT.value == "gdscript"
    matcher = Language.GDSCRIPT.get_source_fn_matcher()
    assert matcher.is_relevant_filename("player.gd")
    assert not matcher.is_relevant_filename("player.py")
    assert Language.GDSCRIPT.get_ls_class() is GDScriptLanguageServer


def test_gdscript_dependency_provider_default_command(tmp_path: Path) -> None:
    provider = GDScriptLanguageServer.DependencyProvider(SolidLSPSettings.CustomLSSettings({}), str(tmp_path))
    cmd = provider.create_launch_command()
    assert cmd[0] == sys.executable
    assert cmd[1:3] == ["-m", "solidlsp.language_servers.gdscript_tcp_proxy"]
    assert cmd[cmd.index("--host") + 1] == "127.0.0.1"
    assert cmd[cmd.index("--port") + 1] == "6005"
    assert cmd[cmd.index("--connect-timeout") + 1] == "10.0"


def test_gdscript_dependency_provider_custom_values(tmp_path: Path) -> None:
    settings = {
        "host": "192.168.1.10",
        "port": 7001,
        "connect_timeout": 2.5,
        "python_path": "python-custom",
    }
    provider = GDScriptLanguageServer.DependencyProvider(SolidLSPSettings.CustomLSSettings(settings), str(tmp_path))
    cmd = provider.create_launch_command()
    assert cmd[0] == "python-custom"
    assert cmd[cmd.index("--host") + 1] == "192.168.1.10"
    assert cmd[cmd.index("--port") + 1] == "7001"
    assert cmd[cmd.index("--connect-timeout") + 1] == "2.5"


@pytest.mark.parametrize("bad_port", ["abc", 0, 70000, -1])
def test_gdscript_dependency_provider_rejects_bad_port(tmp_path: Path, bad_port: object) -> None:
    provider = GDScriptLanguageServer.DependencyProvider(
        SolidLSPSettings.CustomLSSettings({"port": bad_port}),
        str(tmp_path),
    )
    with pytest.raises(ValueError):
        provider.create_launch_command()


def test_gdscript_tcp_proxy_roundtrip() -> None:
    recv_data: list[bytes] = []
    server_payload = b"server->client"
    client_payload = b"client->server"

    srv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv_sock.bind(("127.0.0.1", 0))
    srv_sock.listen(1)
    port = srv_sock.getsockname()[1]

    def server_thread() -> None:
        conn, _ = srv_sock.accept()
        try:
            recv_data.append(conn.recv(4096))
            conn.sendall(server_payload)
            conn.shutdown(socket.SHUT_WR)
        finally:
            conn.close()
            srv_sock.close()

    t = threading.Thread(target=server_thread, daemon=True)
    t.start()

    cmd = [
        sys.executable,
        "-m",
        "solidlsp.language_servers.gdscript_tcp_proxy",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--connect-timeout",
        "2",
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate(input=client_payload, timeout=5)
    t.join(timeout=2)

    assert proc.returncode == 0, stderr.decode("utf-8", errors="replace")
    assert recv_data == [client_payload]
    assert stdout == server_payload

