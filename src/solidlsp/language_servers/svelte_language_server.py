"""
Provides Svelte-specific instantiation of the LanguageServer class using
``svelte-language-server`` from Svelte Language Tools.
"""

from __future__ import annotations

import logging
import os
import pathlib
import re
import shutil
import threading
from typing import Any, cast

from overrides import override

from solidlsp import ls_types
from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection, build_npm_install_command
from solidlsp.language_servers.typescript_language_server import prefer_non_node_modules_definition
from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_utils import PathUtils
from solidlsp.lsp_protocol_handler import lsp_types
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

DEFAULT_SVELTE_LANGUAGE_SERVER_VERSION = "0.18.0"
LS_BIN_NAME = "svelteserver"
IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")


class SvelteLanguageServer(SolidLanguageServer):
    """
    Svelte language server using ``svelte-language-server``.

    ``ls_specific_settings["svelte"]`` keys:
        * ``svelte_language_server_version``: version of ``svelte-language-server``
          to install (default: ``0.18.0``).
        * ``npm_registry``: optional alternative npm-compatible registry URL.
    """

    @classmethod
    def supports_implementation_request(cls) -> bool:
        return True

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(
            config,
            repository_root_path,
            None,
            "svelte",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self._published_diagnostics_timeout = 5.0

    @override
    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    @override
    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        ext = os.path.splitext(relative_file_path)[1].lower()
        if ext == ".svelte":
            return "svelte"
        return "typescript"

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "node_modules",
            "dist",
            "build",
            "coverage",
            ".svelte-kit",
            ".vercel",
        ]

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            assert shutil.which("node") is not None, "node is not installed or isn't in PATH. Please install NodeJS and try again."
            assert shutil.which("npm") is not None, (
                "npm is not installed or isn't in PATH. Please install npm and try again."
            )

            package_version = self._custom_settings.get("svelte_language_server_version", DEFAULT_SVELTE_LANGUAGE_SERVER_VERSION)
            npm_registry = self._custom_settings.get("npm_registry")

            # versioned install dir avoids silently reusing stale language-server binaries
            install_dir = os.path.join(self._ls_resources_dir, f"svelte-lsp-{package_version}")
            executable_path = os.path.join(install_dir, "node_modules", ".bin", LS_BIN_NAME)
            if os.name == "nt":
                executable_path += ".cmd"

            if not os.path.exists(executable_path):
                expected_version = f"svelte-language-server@{package_version}"
                log.info("Installing %s with npm...", expected_version)
                deps = RuntimeDependencyCollection(
                    [
                        RuntimeDependency(
                            id="svelte-language-server",
                            description="Svelte language server",
                            command=build_npm_install_command("svelte-language-server", package_version, npm_registry),
                            platform_id="any",
                        ),
                    ]
                )
                deps.install(install_dir)

            if not os.path.exists(executable_path):
                raise FileNotFoundError(
                    f"{LS_BIN_NAME} executable not found at {executable_path}; "
                    f"npm install of svelte-language-server@{package_version} did not produce the expected binary."
                )
            return executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "--stdio"]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params: dict = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True}},
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "signatureHelp": {"dynamicRegistration": True},
                    "codeAction": {
                        "dynamicRegistration": True,
                        "codeActionLiteralSupport": {
                            "codeActionKind": {
                                "valueSet": [
                                    "quickfix",
                                    "refactor",
                                    "source.organizeImports",
                                    "source.addMissingImports.ts",
                                    "source.removeUnused.ts",
                                    "source.sortImports.ts",
                                ]
                            }
                        },
                    },
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                    "implementation": {"dynamicRegistration": True},
                    "typeDefinition": {"dynamicRegistration": True},
                    "diagnostic": {"dynamicRegistration": True},
                    "publishDiagnostics": {"relatedInformation": True},
                },
                "workspace": {
                    "applyEdit": True,
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "didChangeWatchedFiles": {"dynamicRegistration": True, "relativePatternSupport": True},
                    "symbol": {"dynamicRegistration": True},
                    "configuration": True,
                    "diagnostics": {"refreshSupport": True},
                },
            },
            "initializationOptions": {
                "isTrusted": True,
                "configuration": {
                    "svelte": {
                        "plugin": {
                            "svelte": {"documentHighlight": {"enable": True}},
                            "typescript": {"enable": True},
                            "html": {"enable": True},
                            "css": {"enable": True},
                        }
                    }
                },
            },
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }
        return initialize_params  # type: ignore[return-value]

    def _start_server(self) -> None:
        def do_nothing(_params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info("LSP: window/logMessage: %s", msg)

        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_request("client/registerCapability", lambda _params: None)
        self.server.on_request("workspace/applyEdit", lambda _params: {"applied": True})

        log.info("Starting svelte-language-server")
        self.server.start()
        init_params = self._get_initialize_params(self.repository_root_path)
        init_response = self.server.send.initialize(init_params)
        log.debug("Svelte LS initialize response: %s", init_response)
        assert "documentSymbolProvider" in init_response["capabilities"], "Svelte LSP did not advertise documentSymbolProvider"
        assert "definitionProvider" in init_response["capabilities"], "Svelte LSP did not advertise definitionProvider"
        self.server.notify.initialized({})
        self.server_ready.set()

    def _request_uri_locations(self, method: str, uri: str) -> list[ls_types.Location]:
        try:
            response = self.server.send_request(method, cast(Any, uri))
        except Exception as e:
            log.debug("Svelte custom reference request %s failed for %s: %s", method, uri, e)
            return []

        if not isinstance(response, list):
            return []

        result: list[ls_types.Location] = []
        for item in response:
            if not isinstance(item, dict) or "uri" not in item:
                continue

            abs_path = PathUtils.uri_to_path(item["uri"])
            if not pathlib.Path(abs_path).is_relative_to(self.repository_root_path):
                continue

            rel_path = pathlib.Path(abs_path).relative_to(self.repository_root_path)
            if self.is_ignored_path(str(rel_path)):
                continue

            new_item: dict = {}
            new_item.update(item)
            new_item["absolutePath"] = str(abs_path)
            new_item["relativePath"] = str(rel_path)
            result.append(cast(ls_types.Location, new_item))

        return result

    @override
    def _send_references_request(self, relative_file_path: str, line: int, column: int) -> list[lsp_types.Location] | None:
        return self.server.send.references(
            {
                "textDocument": {"uri": self._resolve_file_uri(relative_file_path)},
                "position": {"line": line, "character": column},
                "context": {"includeDeclaration": True},
            }
        )

    def _request_svelte_component_references(self, relative_file_path: str) -> list[ls_types.Location]:
        """Fetch component-level references via Svelte-specific LSP extensions.

        svelte-language-server tracks component usages through ``$/getFileReferences``
        and ``$/getComponentReferences`` rather than the standard
        ``textDocument/references`` protocol, so a plain references request returns
        nothing for ``.svelte`` files used as components.
        """
        uri = PathUtils.path_to_uri(os.path.join(self.repository_root_path, relative_file_path))
        refs: list[ls_types.Location] = []
        refs.extend(self._request_uri_locations("$/getFileReferences", uri))
        refs.extend(self._request_uri_locations("$/getComponentReferences", uri))
        return refs

    @override
    def request_references(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        """Return all references to the symbol at ``(line, column)``.

        Overrides the base to handle two Svelte quirks:

        1. **Component references** — for ``.svelte`` files the server exposes
           component usages through non-standard extensions; these are queried as a
           fallback when the standard request returns nothing.
        2. **Definition inclusion** — ``request_definition`` is appended to ensure
           the declaration is always present; deduplication by
           ``(uri, start_line, start_char)`` removes any resulting duplicates.
        """
        symbol_refs = super().request_references(relative_file_path, line, column)
        refs = list(symbol_refs)

        if not symbol_refs and relative_file_path.endswith(".svelte"):
            refs.extend(self._request_svelte_component_references(relative_file_path))

        refs.extend(self.request_definition(relative_file_path, line, column))

        seen = set()
        deduped_refs: list[ls_types.Location] = []
        for ref in refs:
            key = (ref["uri"], ref["range"]["start"]["line"], ref["range"]["start"]["character"])
            if key in seen:
                continue
            seen.add(key)
            deduped_refs.append(ref)

        return deduped_refs

    @override
    def _get_published_diagnostics_wait_timeout(self, pull_diagnostics_failed: bool) -> float:
        return self._published_diagnostics_timeout

    @override
    def _get_preferred_definition(self, definitions: list[ls_types.Location]) -> ls_types.Location:
        return prefer_non_node_modules_definition(definitions)

    def _get_identifier_at_position(self, relative_file_path: str, line: int, column: int) -> str | None:
        absolute_path = pathlib.Path(self.repository_root_path) / relative_file_path
        lines = absolute_path.read_text(encoding="utf-8").splitlines()
        if line < 0 or line >= len(lines):
            return None

        for match in IDENTIFIER_PATTERN.finditer(lines[line]):
            if match.start() <= column < match.end():
                return match.group(0)
        return None

    def _create_textual_rename_changes(self, original_name: str, new_name: str) -> dict[str, list[ls_types.TextEdit]]:
        pattern = re.compile(rf"(?<![A-Za-z0-9_$]){re.escape(original_name)}(?![A-Za-z0-9_$])")
        repo_path = pathlib.Path(self.repository_root_path)
        changes: dict[str, list[ls_types.TextEdit]] = {}

        for source_path in repo_path.rglob("*"):
            if not source_path.is_file():
                continue

            relative_path = str(source_path.relative_to(repo_path))
            if self.is_ignored_path(relative_path):
                continue

            try:
                lines = source_path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue

            uri = PathUtils.path_to_uri(str(source_path))
            for line_number, text in enumerate(lines):
                for match in pattern.finditer(text):
                    changes.setdefault(uri, []).append(
                        {
                            "range": {
                                "start": {"line": line_number, "character": match.start()},
                                "end": {"line": line_number, "character": match.end()},
                            },
                            "newText": new_name,
                        }
                    )

        return changes

    @staticmethod
    def _workspace_edit_keys(workspace_edit: ls_types.WorkspaceEdit) -> set[tuple[str, int, int, int, int]]:
        keys: set[tuple[str, int, int, int, int]] = set()

        for uri, edits in (workspace_edit.get("changes") or {}).items():
            for edit in edits:
                edit_range = edit["range"]
                keys.add(
                    (
                        uri,
                        edit_range["start"]["line"],
                        edit_range["start"]["character"],
                        edit_range["end"]["line"],
                        edit_range["end"]["character"],
                    )
                )

        for change in workspace_edit.get("documentChanges") or []:
            if "textDocument" not in change or "edits" not in change:
                continue
            uri = change["textDocument"]["uri"]
            for edit in change["edits"]:
                edit_range = edit["range"]
                keys.add(
                    (
                        uri,
                        edit_range["start"]["line"],
                        edit_range["start"]["character"],
                        edit_range["end"]["line"],
                        edit_range["end"]["character"],
                    )
                )

        return keys

    def _merge_textual_rename_changes(
        self,
        workspace_edit: ls_types.WorkspaceEdit | None,
        textual_changes: dict[str, list[ls_types.TextEdit]],
    ) -> ls_types.WorkspaceEdit | None:
        if workspace_edit is None:
            if not textual_changes:
                return None
            return {"changes": textual_changes}

        merged_edit = dict(workspace_edit)
        merged_changes: dict[str, list[ls_types.TextEdit]] = {
            uri: list(edits) for uri, edits in (workspace_edit.get("changes") or {}).items()
        }
        existing_keys = self._workspace_edit_keys(workspace_edit)

        for uri, edits in textual_changes.items():
            for edit in edits:
                edit_range = edit["range"]
                key = (
                    uri,
                    edit_range["start"]["line"],
                    edit_range["start"]["character"],
                    edit_range["end"]["line"],
                    edit_range["end"]["character"],
                )
                if key in existing_keys:
                    continue
                merged_changes.setdefault(uri, []).append(edit)
                existing_keys.add(key)

        if merged_changes:
            merged_edit["changes"] = merged_changes

        return cast(ls_types.WorkspaceEdit, merged_edit)

    @override
    def request_rename_symbol_edit(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        new_name: str,
    ) -> ls_types.WorkspaceEdit | None:
        workspace_edit = super().request_rename_symbol_edit(relative_file_path, line, column, new_name)
        original_name = self._get_identifier_at_position(relative_file_path, line, column)
        if original_name is None:
            return workspace_edit

        textual_changes = self._create_textual_rename_changes(original_name, new_name)
        return self._merge_textual_rename_changes(workspace_edit, textual_changes)
