"""Tests for locating the AL language server executable within the VS Code extension.

The AL extension ships the executable in two different directory layouts depending on its build,
so both must be resolved without downloading the extension (see #2069).
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from solidlsp.language_servers.al_language_server import ALLanguageServer
from solidlsp.ls_config import LanguageServerConfig, LanguageServerId
from solidlsp.settings import SolidLSPSettings

pytestmark = pytest.mark.al

# the name the AL extension ships in its `bin` directory, independent of Serena's constant
HOST_EXECUTABLE_NAME = "Microsoft.Dynamics.Nav.EditorServices.Host"

_PLATFORM_SUBDIR = {"Windows": "win32", "Linux": "linux", "Darwin": "darwin"}


def _executable_name(system: str) -> str:
    return HOST_EXECUTABLE_NAME + (".exe" if system == "Windows" else "")


def _create_host(extension_root: Path, system: str, *, layout: str) -> Path:
    """Create a stub executable in either the versioned platform subdirectory or the flat `bin`
    directory of the given extension root, returning its path.
    """
    subdir = _PLATFORM_SUBDIR[system] if layout == "platform-subdir" else ""
    host_path = extension_root.joinpath("bin", subdir, _executable_name(system))
    host_path.parent.mkdir(parents=True, exist_ok=True)
    host_path.write_bytes(b"stub")
    return host_path


def _setup(extension_root: Path, system: str) -> str:
    with (
        patch("solidlsp.language_servers.al_language_server.platform.system", return_value=system),
        patch.object(ALLanguageServer, "_find_al_extension", return_value=str(extension_root)),
    ):
        config = LanguageServerConfig(ls_id=LanguageServerId.AL)
        return ALLanguageServer._setup_runtime_dependencies(config, SolidLSPSettings())


@pytest.mark.parametrize("system", sorted(_PLATFORM_SUBDIR))
@pytest.mark.parametrize("layout", ["platform-subdir", "flat"])
def test_executable_is_resolved_in_either_extension_layout(tmp_path: Path, system: str, layout: str) -> None:
    """Regression test for #2069: builds >= 18.0.2732683 place the executable directly in `bin`,
    while the layout up to 18.0.2242655 keeps it in a platform subdirectory.
    """
    host_path = _create_host(tmp_path, system, layout=layout)

    command = _setup(tmp_path, system)

    assert str(host_path) in command


@pytest.mark.parametrize("system", sorted(_PLATFORM_SUBDIR))
def test_platform_subdir_layout_takes_precedence_when_both_are_present(tmp_path: Path, system: str) -> None:
    flat_host = _create_host(tmp_path, system, layout="flat")
    versioned_host = _create_host(tmp_path, system, layout="platform-subdir")

    command = _setup(tmp_path, system)

    assert str(versioned_host) in command
    assert str(flat_host) not in command


def test_missing_executable_reports_every_candidate_layout(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="AL Language Server executable not found") as exc_info:
        _setup(tmp_path, "Windows")

    message = str(exc_info.value)
    assert str(tmp_path / "bin" / "win32" / f"{HOST_EXECUTABLE_NAME}.exe") in message
    assert str(tmp_path / "bin" / f"{HOST_EXECUTABLE_NAME}.exe") in message


def test_unsupported_platform_is_rejected(tmp_path: Path) -> None:
    _create_host(tmp_path, "Windows", layout="flat")

    with pytest.raises(RuntimeError, match="Unsupported platform: FreeBSD"):
        _setup(tmp_path, "FreeBSD")
