"""
Provides Svelte-specific instantiation of the LanguageServer class using
``svelte-language-server`` from Svelte Language Tools.
"""

from __future__ import annotations

import logging
import os
import pathlib
import shutil
from typing import Any, cast

from overrides import override

from solidlsp import ls_types
from solidlsp.language_servers.common import (
    RuntimeDependency,
    RuntimeDependencyCollection,
    build_npm_install_command,
)
from solidlsp.ls import (
    LanguageServerDependencyProvider,
    LanguageServerDependencyProviderSinglePath,
    SolidLanguageServer,
)
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_utils import PathUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams, RenameFilesParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class SvelteLanguageServer(SolidLanguageServer):
    """
    Svelte language server using ``svelte-language-server``.

    ``ls_specific_settings["svelte"]`` keys:
        * ``svelte_language_server_version``: version of ``svelte-language-server``
          to install (default: ``0.18.0``).
        * ``npm_registry``: optional alternative npm-compatible registry URL.
        * ``initialization_options_configuration``: optional dict merged into
          ``initializeParams.initializationOptions.configuration`` (same top-level keys as in
          Svelte Language Tools: ``svelte``, ``prettier``, ``typescript``, …).
    """

    _TS_EXT = frozenset({".ts", ".tsx", ".mts", ".cts"})
    _JS_EXT = frozenset({".js", ".jsx", ".mjs", ".cjs"})
    _SVELTE_EXT = frozenset({".svelte"})

    @staticmethod
    def _is_ts_file(uri: str) -> bool:
        return uri.lower().endswith(tuple(SvelteLanguageServer._TS_EXT | SvelteLanguageServer._JS_EXT))

    @staticmethod
    def _is_svelte_file(uri: str) -> bool:
        return uri.lower().endswith(tuple(SvelteLanguageServer._SVELTE_EXT))

    @staticmethod
    def _edit_new_text_is_svelte_path(edit: Any) -> bool:
        """True if this LSP ``TextEdit``'s replacement text ends with ``.svelte`` (import path update)."""
        if not isinstance(edit, dict):
            return False
        new_text = edit.get("newText")
        return isinstance(new_text, str) and new_text.endswith(".svelte")

    @staticmethod
    def _filter_file_rename_workspace_edit(
        workspace_edit: ls_types.WorkspaceEdit,
        typescript_plugin_enabled: bool,
    ) -> ls_types.WorkspaceEdit:
        """Drop TS/JS-only import updates when the Svelte TS plugin handles them; keep ``.svelte`` path edits."""
        raw_changes = workspace_edit.get("documentChanges")
        if not isinstance(raw_changes, list) or not raw_changes:
            return workspace_edit

        filtered: list[dict[str, Any]] = []
        for change in raw_changes:
            if not isinstance(change, dict):
                continue

            text_document = change.get("textDocument")
            edits_in = change.get("edits")
            if not isinstance(text_document, dict) or not isinstance(edits_in, list):
                continue

            doc_uri = text_document.get("uri")
            if not isinstance(doc_uri, str):
                continue

            is_ts_js = SvelteLanguageServer._is_ts_file(doc_uri)
            if is_ts_js and not any(SvelteLanguageServer._edit_new_text_is_svelte_path(e) for e in edits_in):
                continue

            ts_without_plugin_filters_edits = is_ts_js and not typescript_plugin_enabled
            kept_edits = [
                edit
                for edit in edits_in
                if isinstance(edit, dict)
                and (not ts_without_plugin_filters_edits or SvelteLanguageServer._edit_new_text_is_svelte_path(edit))
            ]

            if kept_edits:
                ch = dict(change)
                ch["edits"] = kept_edits
                filtered.append(ch)

        out = dict(workspace_edit)
        out["documentChanges"] = filtered
        return cast(ls_types.WorkspaceEdit, out)

    @staticmethod
    def _patch_rename_provider_export_let_regex_line(text: str) -> str:
        if "_solidlspEscapedVar" in text:
            return text
        prefix = r"        const regex = new RegExp(`export\\s+let\\s+${this.getVariableAtPosition(tsDoc, lang, position)"
        new_lines: list[str] = []
        patched = False
        for line in text.splitlines(keepends=True):
            if line.startswith(prefix):
                new_lines.append(
                    "        const _solidlspEscapedVar = this.getVariableAtPosition(tsDoc, lang, position)"
                    ".replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');\n"
                )
                new_lines.append(
                    r"        const regex = new RegExp(`export\\s+let\\s+${_solidlspEscapedVar}($|\\s|;|:|\\/\\*|\\/\\/)`);" + "\n"
                )
                patched = True
            else:
                new_lines.append(line)
        if not patched:
            log.warning("RenameProvider.js: export-let regex line not found; skipping that patch")
        return "".join(new_lines)

    @staticmethod
    def _patch_rename_provider_match_generated_export_let(text: str) -> str:
        if "_solidlspLetFrag" in text:
            return text
        start_sig = "    matchGeneratedExportLet(snapshot, updatePropLocation) {"
        end_sig = "    findLocationWhichWantsToUpdatePropName"
        try:
            start = text.index(start_sig)
            end = text.index(end_sig, start)
        except ValueError:
            log.warning("RenameProvider.js: matchGeneratedExportLet block not found; skipping that patch")
            return text
        new_block = (
            "    matchGeneratedExportLet(snapshot, updatePropLocation) {\n"
            "        const _solidlspLetFrag = snapshot\n"
            "            .getFullText()\n"
            "            .substring(updatePropLocation.textSpan.start, updatePropLocation.textSpan.start + updatePropLocation.textSpan.length)\n"
            "            .replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');\n"
            "        const regex = new RegExp(\n"
            "        // no 'export let', only 'let', because that's what it's translated to in svelte2tsx\n"
            "        // '//' and '/*' for comments (`let bla/*Ωignore_startΩ*/`)\n"
            r"        `\\s+let\\s+(${_solidlspLetFrag})($|\\s|;|:|\\/\\*|\\/\\/)`);"
            "\n"
            "        const match = snapshot.getFullText().match(regex);\n"
            "        return match;\n"
            "    }\n"
        )
        return text[:start] + new_block + text[end:]

    @staticmethod
    def _patch_svelte_rename_provider_interpolated_regex(install_dir: str) -> None:
        """Patch RenameProvider.js bundled with ``svelte-language-server`` 0.18.0.

        Unescaped text interpolated into ``RegExp`` breaks ``textDocument/rename`` for some TS symbols.
        SolidLSP applies local fixes until npm ships an upstream release with proper escaping.
        """
        rename_js = os.path.join(
            install_dir,
            "node_modules",
            "svelte-language-server",
            "dist",
            "src",
            "plugins",
            "typescript",
            "features",
            "RenameProvider.js",
        )
        if not os.path.isfile(rename_js):
            return
        path = pathlib.Path(rename_js)
        original = path.read_text(encoding="utf-8")
        patched = SvelteLanguageServer._patch_rename_provider_match_generated_export_let(
            SvelteLanguageServer._patch_rename_provider_export_let_regex_line(original)
        )
        if patched != original:
            path.write_text(patched, encoding="utf-8")
            log.info("Applied SolidLSP RenameProvider.js patches under %s", install_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            assert shutil.which("node") is not None, "node is not installed or isn't in PATH. Please install NodeJS and try again."
            assert shutil.which("npm") is not None, "npm is not installed or isn't in PATH. Please install npm and try again."

            package_version = self._custom_settings.get("svelte_language_server_version", "0.18.0")
            npm_registry = self._custom_settings.get("npm_registry")
            typescript_version = self._custom_settings.get("typescript_version", "6.0.3")

            # versioned install dir avoids silently reusing stale language-server binaries
            install_dir = os.path.join(self._ls_resources_dir, f"svelte-lsp-{package_version}")
            executable_path = os.path.join(install_dir, "node_modules", ".bin", "svelteserver")
            if os.name == "nt":
                executable_path += ".cmd"

            if not os.path.exists(executable_path):
                expected_version = f"svelte-language-server@{package_version}"
                log.info("Installing %s (and typescript) with npm...", expected_version)
                runtime_deps = [
                    RuntimeDependency(
                        id="svelte-language-server",
                        description="Svelte language server",
                        command=build_npm_install_command("svelte-language-server", package_version, npm_registry),
                        platform_id="any",
                    ),
                    RuntimeDependency(
                        id="typescript",
                        description="TypeScript language service",
                        command=build_npm_install_command("typescript", typescript_version, npm_registry),
                        platform_id="any",
                    ),
                ]
                deps = RuntimeDependencyCollection(runtime_deps)
                deps.install(install_dir)

            if not os.path.exists(executable_path):
                raise FileNotFoundError(
                    f"executable not found at {executable_path}; "
                    f"npm install of svelte-language-server@{package_version} (and typescript) did not produce the expected binary."
                )
            SvelteLanguageServer._patch_svelte_rename_provider_interpolated_regex(install_dir)
            return executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            # stdio suits SolidLSP's subprocess RPC; other hosts may use a different transport.
            return [core_path, "--stdio"]

    @override
    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    def __init__(self, config: LanguageServerConfig, repo_path: str, solidlsp_settings: SolidLSPSettings):
        resolved_root = os.path.abspath(repo_path)
        super().__init__(
            config,
            resolved_root,
            None,
            "svelte",
            solidlsp_settings,
        )
        self.repo_path: str = resolved_root
        # Define the tsdk property for TypeScript SDK path for Svelte LS
        self.tsdk_path = self._get_tsdk_path()

    def _get_tsdk_path(self) -> str:
        """
        Compute the local typescript/lib path for the Svelte language server.
        Asserts if not found, since DependencyProvider guarantees install.
        """
        package_version = self._custom_settings.get("svelte_language_server_version", "0.18.0")
        install_dir = os.path.join(self._ls_resources_dir, f"svelte-lsp-{package_version}")
        tsdk_candidate = os.path.join(install_dir, "node_modules", "typescript", "lib")
        assert os.path.isdir(tsdk_candidate), (
            f"TypeScript SDK not found at expected path: {tsdk_candidate}. Installation via DependencyProvider failed or version mismatch."
        )
        return tsdk_candidate

    def _wrap_notify_send_for_ts_js_mirror(self) -> None:
        """Mirror TS/JS didChange via ``$/onDidChangeTsOrJsFile`` so the server updates TS snapshots."""
        _orig_notify_send = self.server.notify.send_notification

        def send_notification_wrapped(method: str, params: dict | None = None) -> None:
            _orig_notify_send(method, params)
            if method != "textDocument/didChange" or not params:
                return
            text_document = params.get("textDocument")
            if not text_document:
                return
            uri = text_document.get("uri")
            if not uri:
                return
            fb = self.open_file_buffers.get(uri)
            if fb is None or fb.language_id not in ("typescript", "javascript"):
                return
            changes = params.get("contentChanges")
            if changes is None:
                return
            _orig_notify_send("$/onDidChangeTsOrJsFile", {"uri": uri, "changes": changes})

        self.server.notify.send_notification = send_notification_wrapped  # type: ignore[method-assign]

    def _get_initialize_params(self) -> InitializeParams:
        """
        Returns the initialize params for the Svelte Language Server.
        """
        root_uri = pathlib.Path(self.repo_path).as_uri()
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
                    "codeAction": {"dynamicRegistration": True},
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                    "implementation": {"dynamicRegistration": True},
                    "typeDefinition": {"dynamicRegistration": True},
                    "diagnostic": {"dynamicRegistration": True},
                    "publishDiagnostics": {"relatedInformation": True},
                },
                "workspace": {
                    "applyEdit": True,
                    "configuration": True,
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "didChangeWatchedFiles": {"dynamicRegistration": True, "relativePatternSupport": True},
                    "symbol": {"dynamicRegistration": True},
                    "diagnostics": {"refreshSupport": True},
                    "fileOperations": {"didRename": True},
                },
            },
            "initializationOptions": {
                "isTrusted": True,
                "dontFilterIncompleteCompletions": True,
                "configuration": {
                    "svelte": {},
                    "javascript": {"tsdk": self.tsdk_path},
                    "typescript": {"tsdk": self.tsdk_path},
                },
            },
            "processId": os.getpid(),
            "rootPath": self.repo_path,
            "rootUri": root_uri,
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(self.repo_path),
                }
            ],
        }
        return initialize_params

    def _start_server(self) -> None:
        def window_log_message(msg: dict) -> None:
            log.info("LSP: window/logMessage: %s", msg)

        def register_capability_handler(params: dict) -> None:
            assert "registrations" in params

        def configuration_handler(params: dict) -> list:
            items = params.get("items", [])
            return [{} for _ in items]

        def workspace_apply_edit_handler(_params: dict) -> dict[str, Any]:
            return {"applied": False}

        def work_done_progress_create(_params: dict) -> dict:
            return {}

        def do_nothing(_params: dict) -> None:
            pass

        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("window/workDoneProgress/create", work_done_progress_create)
        self.server.on_request("workspace/applyEdit", workspace_apply_edit_handler)
        self.server.on_request("workspace/configuration", configuration_handler)
        self.server.on_request("workspace/diagnostic/refresh", do_nothing)
        self.server.on_request("workspace/inlayHints/refresh", do_nothing)
        self.server.on_request("workspace/semanticTokens/refresh", do_nothing)
        self._wrap_notify_send_for_ts_js_mirror()
        self.server.start()

        init_params = self._get_initialize_params()
        init_response = self.server.send.initialize(init_params)

        assert "documentSymbolProvider" in init_response["capabilities"], "Svelte LSP did not advertise documentSymbolProvider"
        assert "definitionProvider" in init_response["capabilities"], "Svelte LSP did not advertise definitionProvider"

        self.server.notify.initialized({})

    @staticmethod
    def _merge_reference_locations(a: list[ls_types.Location], b: list[ls_types.Location]) -> list[ls_types.Location]:
        seen = {(loc["uri"], loc["range"]["start"]["line"], loc["range"]["start"]["character"]) for loc in a}
        out = list(a)
        for loc in b:
            key = (loc["uri"], loc["range"]["start"]["line"], loc["range"]["start"]["character"])
            if key not in seen:
                seen.add(key)
                out.append(loc)
        return out

    @override
    def request_references(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        """
        Combine standard ``textDocument/references`` with Svelte LS ``$/getFileReferences``
        / ``$/getComponentReferences`` (see ``docs/svelte-language-tools-cross-file.md``)
        so TS/JS and Svelte modules get full cross-file reference coverage.
        """
        symbol_refs = super().request_references(relative_file_path, line, column)
        normalize_helper = self.ReferencesLocationRequest(self, relative_file_path, line, column)

        if self._is_ts_file(relative_file_path):
            raw = self.server.send_request("$/getFileReferences", cast(Any, self._resolve_file_uri(relative_file_path)))
            file_refs = normalize_helper.normalize_response(raw if isinstance(raw, list) else [])
            symbol_refs = self._merge_reference_locations(symbol_refs, file_refs)
        elif self._is_svelte_file(relative_file_path):
            raw = self.server.send_request("$/getComponentReferences", cast(Any, self._resolve_file_uri(relative_file_path)))
            comp_refs = normalize_helper.normalize_response(raw if isinstance(raw, list) else [])
            symbol_refs = self._merge_reference_locations(symbol_refs, comp_refs)

        return symbol_refs

    def notify_did_rename_files(self, old_relative: str, new_relative: str) -> None:
        """Send ``workspace/didRenameFiles`` after an on-disk rename (before import-fix edits)."""
        if not self.server_started:
            log.error("notify_did_rename_files called before Language Server started")
            raise SolidLSPException("Language Server not started")
        params: RenameFilesParams = {
            "files": [
                {"oldUri": self._resolve_file_uri(old_relative), "newUri": self._resolve_file_uri(new_relative)},
            ]
        }
        self.server.notify.did_rename_files(params)

    def _relative_path_from_document_uri(self, uri: str) -> str:
        return os.path.relpath(PathUtils.uri_to_path(uri), self.repo_path)

    def _apply_workspace_edit_text_changes(self, workspace_edit: ls_types.WorkspaceEdit) -> int:
        """Apply ``changes`` / ``TextDocumentEdit`` entries using :meth:`apply_text_edits_to_file`."""
        count = 0
        if "changes" in workspace_edit:
            for uri, edits in workspace_edit["changes"].items():
                rel = self._relative_path_from_document_uri(uri)
                self.apply_text_edits_to_file(rel, edits)
                count += 1
        for change in workspace_edit.get("documentChanges") or []:
            if "textDocument" in change and "edits" in change:
                uri = change["textDocument"]["uri"]
                rel = self._relative_path_from_document_uri(uri)
                self.apply_text_edits_to_file(rel, change["edits"])
                count += 1
            elif "kind" in change:
                raise ValueError(f"Unsupported workspace documentChange kind in import rename edit: {change}")
        return count

    def rename_file_and_fix_imports(
        self,
        old_relative: str,
        new_relative: str,
        *,
        typescript_plugin_enabled: bool = True,
    ) -> str:
        """
        Rename a project file on disk, notify the Svelte LS, then apply filtered ``$/getEditsForFileRename`` edits.

        The old path must not be open in :attr:`open_file_buffers`.
        """
        root = pathlib.Path(self.repo_path).resolve()
        old_path = (root / old_relative).resolve()
        new_path = (root / new_relative).resolve()
        try:
            old_path.relative_to(root)
            new_path.relative_to(root)
        except ValueError as e:
            raise ValueError(f"Rename paths must stay within the project root {root}") from e

        if not old_path.is_file():
            raise ValueError(f"Not an existing file: {old_relative}")
        if new_path.exists():
            raise ValueError(f"Target already exists: {new_relative}")

        old_uri = self._resolve_file_uri(old_relative)
        if old_uri in self.open_file_buffers:
            raise ValueError(f"Cannot rename '{old_relative}': file is open in the language server; finish or close active edits first.")

        os.rename(old_path, new_path)
        self.notify_did_rename_files(old_relative, new_relative)

        workspace_edit = self.request_workspace_edit_for_file_rename(
            old_relative,
            new_relative,
            typescript_plugin_enabled=typescript_plugin_enabled,
        )
        num_ops = self._apply_workspace_edit_text_changes(workspace_edit) if workspace_edit else 0

        return f"Renamed '{old_relative}' → '{new_relative}' ({num_ops} workspace edit operation(s) applied for import updates)"

    def request_workspace_edit_for_file_rename(
        self,
        old_relative: str,
        new_relative: str,
        typescript_plugin_enabled: bool = True,
    ) -> ls_types.WorkspaceEdit | None:
        """Import-fix workspace edit after a rename/move.

        Sends ``$/getEditsForFileRename`` with ``{ oldUri, newUri }``, then post-filters ``documentChanges``
        so TS/JS-only import edits may be omitted when the Svelte TS plugin delegates those updates
        to the TypeScript language service.

        Call after the file exists at ``new_relative`` on disk (after ``workspace/didRenameFiles``).
        """
        old_uri = self._resolve_file_uri(old_relative)
        if any(ext.lower() in old_uri for ext in self._TS_EXT | self._JS_EXT | self._SVELTE_EXT):
            return None

        params = {"oldUri": self._resolve_file_uri(old_relative), "newUri": self._resolve_file_uri(new_relative)}
        raw = self.server.send_request("$/getEditsForFileRename", params)

        if raw is None:
            return None

        workspace_edit = cast(ls_types.WorkspaceEdit, raw)
        return self._filter_file_rename_workspace_edit(
            workspace_edit,
            typescript_plugin_enabled,
        )

    @override
    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        ext = os.path.splitext(relative_file_path)[1].lower()
        if ext in self._TS_EXT:
            return "typescript"
        if ext in self._JS_EXT:
            return "javascript"
        return self.language_id

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["dist", "build", "coverage"]
