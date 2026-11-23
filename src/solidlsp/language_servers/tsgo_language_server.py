# SPDX-License-Identifier: MIT

import glob
import logging
import os
import shutil
from typing import Any

from overrides import override
from sensai.util.logging import LogTime

from solidlsp.ls import LanguageServerDependencyProviderSinglePath
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_utils import PathUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeResult, Location, TextDocumentSyncKind

from .common import RuntimeDependency, RuntimeDependencyCollection, build_npm_install_command
from .typescript_language_server import TypeScriptLanguageServer

log = logging.getLogger(__name__)

DEFAULT_TYPESCRIPT_VERSION = "7.0.2"


class TsgoLanguageServer(TypeScriptLanguageServer):
    """
    Provides TypeScript support via the native language server of TypeScript 7 (``tsc --lsp --stdio``).

    You can pass the following entries in ls_specific_settings["typescript_tsgo"]:
        - typescript_version: Version of the typescript npm package to install (default: "7.0.2")
        - npm_registry: npm registry to install the typescript package from
        - indexing_timeout: float, timeout in seconds for project indexing (default: 30.0)
        - indexing_start_grace: float, timeout in seconds to wait for indexing progress to *start*
          before the first cross-file reference query (default: 0.0)
    """

    INDEXING_START_GRACE = 0.0

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            typescript_version = self._custom_settings.get("typescript_version", DEFAULT_TYPESCRIPT_VERSION)
            install_dir = os.path.join(self._ls_resources_dir, f"typescript-{typescript_version}")
            executable_path = self._find_executable(install_dir)
            if executable_path is not None:
                return executable_path

            if shutil.which("npm") is None:
                raise SolidLSPException("npm is not installed or isn't in PATH. Please install NodeJS and try again.")
            deps = RuntimeDependencyCollection(
                [
                    RuntimeDependency(
                        id="typescript",
                        description="typescript package",
                        command=build_npm_install_command("typescript", typescript_version, self._custom_settings.get("npm_registry")),
                        platform_id="any",
                    )
                ]
            )
            with LogTime(f"Installation of typescript@{typescript_version}", logger=log):
                deps.install(install_dir)

            executable_path = self._find_executable(install_dir)
            if executable_path is None:
                raise FileNotFoundError(
                    f"No native TypeScript executable found in {install_dir} after installing typescript@{typescript_version}"
                )
            return executable_path

        @staticmethod
        def _find_executable(install_dir: str) -> str | None:
            executable_name = "tsc.exe" if os.name == "nt" else "tsc"
            pattern = os.path.join(install_dir, "node_modules", "**", "@typescript", "typescript-*", "lib", executable_name)
            matches = glob.glob(pattern, recursive=True)
            return matches[0] if matches else None

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "--lsp", "--stdio"]

    @override
    def _create_tsserver_initialization_options(self) -> dict[str, Any]:
        return {}

    @override
    def _verify_initialize_response(self, init_response: InitializeResult) -> None:
        text_document_sync = init_response["capabilities"].get("textDocumentSync")
        change_kind = text_document_sync.get("change") if isinstance(text_document_sync, dict) else text_document_sync
        if change_kind != TextDocumentSyncKind.Incremental:
            raise SolidLSPException(f"tsc --lsp does not support incremental document sync: textDocumentSync={text_document_sync!r}")

    @override
    def _wait_for_server_ready(self) -> None:
        self.server_ready.set()

    @override
    def _signal_expect_indexing(self) -> None:
        pass

    @override
    def _send_references_request(self, relative_file_path: str, line: int, column: int) -> list[Location] | None:
        """
        Requests the references including declarations and removes the location at the queried position,
        which is expected to be the identifier of the symbol's declaration.

        Unlike tsserver, which only omits definitions, ``tsc --lsp`` also treats import and export specifiers
        and implementing members as declarations of the symbol, so a request without declarations would omit them.
        """
        uri = self._resolve_file_uri(relative_file_path)
        locations = self.server.send.references(
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": column},
                "context": {"includeDeclaration": True},
            }
        )
        if locations is None:
            return None
        return [location for location in locations if not self._is_location_at_position(location, uri, line, column)]

    @staticmethod
    def _is_location_at_position(location: Location, uri: str, line: int, column: int) -> bool:
        """
        :return: whether the location lies in the file with the given URI and its range contains the given position
        """
        if os.path.normcase(PathUtils.uri_to_path(location["uri"])) != os.path.normcase(PathUtils.uri_to_path(uri)):
            return False
        start, end = location["range"]["start"], location["range"]["end"]
        return (start["line"], start["character"]) <= (line, column) <= (end["line"], end["character"])
