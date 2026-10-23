"""
Provides Pkl specific instantiation of the LanguageServer class, using Apple's Pkl Language Server
(https://github.com/apple/pkl-lsp), which is expected as an executable named ``pkl-lsp`` on PATH.

The server implements a strict subset of the Language Server Protocol: hover, definition,
completion, code actions, formatting and diagnostics. It implements neither
``textDocument/documentSymbol`` nor ``textDocument/references``, which Serena's symbol tools are
built on, so those tools report an empty result for Pkl sources. It answers both methods with an
internal error (-32603) rather than an unsupported-method error (-32601), so the server declares
the corresponding capabilities as absent instead of letting the requests reach it.

You can configure the following options in ls_specific_settings (in serena_config.yml):

    ls_specific_settings:
      pkl:
        ls_path: '/path/to/pkl-lsp'   # use an existing executable instead of the one on PATH
"""
# SPDX-License-Identifier: MIT

import logging
import os
import re
import shutil
import subprocess

from overrides import override

from solidlsp.ls import (
    LanguageServerDependencyProvider,
    LanguageServerDependencyProviderSinglePath,
    SolidLanguageServer,
)
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.settings import SolidLSPSettings
from solidlsp.util.subprocess_util import convert_shell_cmd, subprocess_run

log = logging.getLogger(__name__)

#: the capabilities whose absence Serena tolerates; the server is known not to implement them
_ABSENT_CAPABILITIES = ("documentSymbolProvider", "referencesProvider", "workspaceSymbolProvider")

#: the capabilities the server must provide for the remaining features to be usable
_REQUIRED_CAPABILITIES = ("hoverProvider", "definitionProvider", "textDocumentSync")

#: the release this implementation was written and tested against; older releases are not supported.
#: Bumping this requires matching the version installed in CI (``PKL_LSP_VERSION`` in
#: .github/workflows/pytest.yml) and re-running the Pkl tests against the new release first: every
#: release up to at least 0.8.0 announces identical capabilities, so neither the initialize
#: handshake nor the test suite can tell a supported release from an unsupported one.
MINIMUM_SUPPORTED_VERSION: tuple[int, int, int] = (0, 8, 0)

#: matches the release number in the output of ``pkl-lsp --version``, capturing major, minor and patch
_VERSION_PATTERN = re.compile(r"pkl-lsp version (\d+)\.(\d+)\.(\d+)")


def _format_version(version: tuple[int, ...]) -> str:
    """
    :param version: a version as a tuple of numbers, as reported by the server or as a minimum
    :return: the version in dotted notation
    """
    return ".".join(str(part) for part in version)


class PklLanguageServer(SolidLanguageServer):
    """
    Provides Pkl specific instantiation of the LanguageServer class.

    Uses the Pkl Language Server (https://github.com/apple/pkl-lsp), which must be installed and
    available on PATH as ``pkl-lsp``; see https://pkl-lang.org/lsp/current/index.html for
    installation instructions.

    The server has no document-symbol and no find-references support (neither capability is
    advertised, and both requests fail with an internal error), so Serena's symbol tools return
    empty results for Pkl sources. Definition, hover, formatting and diagnostics work.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(config, repository_root_path, None, "pkl", solidlsp_settings)

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """
            Locates the Pkl Language Server executable on PATH.

            :return: the path to the ``pkl-lsp`` executable
            :raises FileNotFoundError: if no executable is available
            """
            pkl_lsp_binary = shutil.which("pkl-lsp")
            if pkl_lsp_binary is None:
                raise FileNotFoundError(
                    "The Pkl Language Server is not installed or not in PATH.\n"
                    "Install it so that a 'pkl-lsp' executable is available on your PATH: take a release from "
                    "https://github.com/apple/pkl-lsp/releases (upstream publishes a JAR, which needs Java 23+ "
                    "and therefore a launcher script) or use a package provided by your system's package "
                    "manager."
                )
            return pkl_lsp_binary

        def _create_launch_command(self, core_path: str) -> list[str]:
            # the version is checked here rather than during discovery, since this is the one step a path
            # configured via ls_path passes through as well
            self._check_version(core_path)
            return [core_path]

        @staticmethod
        def _check_version(pkl_lsp_binary: str) -> None:
            """
            Verifies that the executable is recent enough to be usable.

            The server reports its version on stderr or stdout as ``pkl-lsp version X.Y.Z``. A version that
            cannot be determined is accepted, since only a demonstrably old release is known to be unusable.
            A non-zero exit status is rejected, since it means that the executable cannot start at all (for
            example because no sufficiently recent Java runtime is available).

            :param pkl_lsp_binary: the executable to interrogate
            :raises SolidLSPException: if the executable cannot be started or reports an unsupported version
            """
            # Upstream publishes only a JAR, so on Windows the executable a user supplies is typically a
            # ``.cmd`` or ``.bat`` launcher, which cannot be spawned from a plain argument vector; the
            # command is therefore assembled as a shell command, exactly as the server itself is launched.
            try:
                result = subprocess_run(
                    convert_shell_cmd([pkl_lsp_binary, "--version"]),
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                    cwd=os.path.dirname(os.path.abspath(pkl_lsp_binary)),
                )
            except (OSError, subprocess.TimeoutExpired) as e:
                raise SolidLSPException(f"The Pkl Language Server at '{pkl_lsp_binary}' could not be started: {e}") from e

            output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
            if result.returncode != 0:
                raise SolidLSPException(
                    f"The Pkl Language Server at '{pkl_lsp_binary}' failed to report its version (exit status "
                    f"{result.returncode}): {output}. A release taken from https://github.com/apple/pkl-lsp/releases "
                    "needs Java 23 or newer."
                )

            reported_version = _VERSION_PATTERN.search(output)
            if reported_version is None:
                log.warning("Could not determine the Pkl Language Server version from '%s'; proceeding", pkl_lsp_binary)
                return

            version = tuple(int(part) for part in reported_version.groups())
            if version < MINIMUM_SUPPORTED_VERSION:
                raise SolidLSPException(
                    f"The Pkl Language Server at '{pkl_lsp_binary}' is version {_format_version(version)}, but at "
                    f"least {_format_version(MINIMUM_SUPPORTED_VERSION)} is required: that is the release this "
                    "implementation was written and tested against; older releases are not supported. Install "
                    "it from https://github.com/apple/pkl-lsp/releases."
                )
            log.info("Using Pkl Language Server version %s at %s", _format_version(version), pkl_lsp_binary)

    def _create_base_initialize_params(self) -> dict:
        """
        Returns the initialize params for the Pkl Language Server.

        Only the features the server implements are requested; see the module docstring.
        """
        return {
            "capabilities": {
                "textDocument": {
                    "synchronization": {"dynamicRegistration": True},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True}},
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "codeAction": {"dynamicRegistration": True},
                    "formatting": {"dynamicRegistration": True},
                    "publishDiagnostics": {"relatedInformation": True},
                },
                "workspace": {"workspaceFolders": True, "configuration": True},
            },
        }

    @override
    def _supports_pull_diagnostics(self) -> bool:
        """The server does not implement textDocument/diagnostic; only pushed diagnostics are available."""
        return False

    def _start_server(self) -> None:
        """Starts the Pkl Language Server."""

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info("LSP: window/logMessage: %s", msg)

        def workspace_configuration(params: dict) -> list:
            # no Pkl-specific settings are managed by Serena; null lets the server apply its own defaults
            return [None for _ in params.get("items", [])]

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_request("workspace/configuration", workspace_configuration)
        self.server.on_notification("window/logMessage", window_log_message)
        # diagnostics are recorded by the base class from any notification; registering the method
        # explicitly keeps it from being logged as unhandled
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Pkl language server process")
        self.server.start()

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(self._create_initialize_params())
        announced = init_response.get("capabilities")
        capabilities = announced if isinstance(announced, dict) else {}

        missing_required = [
            capability for capability in _REQUIRED_CAPABILITIES if not PklLanguageServer._is_capability_enabled(capabilities, capability)
        ]
        if missing_required:
            raise SolidLSPException(f"The Pkl Language Server lacks required capabilities: {missing_required}")
        absent = [
            capability for capability in _ABSENT_CAPABILITIES if not PklLanguageServer._is_capability_enabled(capabilities, capability)
        ]
        log.debug("Pkl Language Server does not implement %s; symbol and reference tools are unavailable", absent)

        self.server.notify.initialized({})

    @staticmethod
    def _is_capability_enabled(capabilities: dict, capability: str) -> bool:
        """
        Determines whether a capability announced during initialization is actually enabled.

        An optional capability may be absent, ``False`` or an options object whose features are all
        disabled. ``textDocumentSync`` is the exception: it announces a synchronization kind, or ``None``.

        :param capabilities: the capabilities announced in the initialize result
        :param capability: the name of the capability within them
        :return: whether the server effectively provides the capability
        """
        value = capabilities.get(capability)
        if not isinstance(value, dict):
            return bool(value)
        if capability == "textDocumentSync":
            return bool(value.get("openClose") or value.get("change"))
        return True

    @override
    def _supports_document_symbols(self) -> bool:
        return False

    @override
    def _supports_references(self) -> bool:
        return False
