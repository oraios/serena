"""
Android Language Server that supports mixed Java and Kotlin projects.
Uses delegation to existing Java (Eclipse JDTLS) and Kotlin language servers.
"""

import dataclasses
import logging
from typing import Any

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_types import UnifiedSymbolInformation
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


@dataclasses.dataclass
class AndroidRuntimeDependencyPaths:
    """
    Stores the paths to the runtime dependencies of Android Language Server
    """

    java_ls_dependencies: Any
    kotlin_ls_dependencies: Any


class AndroidLanguageServer(SolidLanguageServer):
    """
    Android Language Server that supports mixed Java and Kotlin projects.
    Delegates requests to appropriate language servers based on file extensions.
    """

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        """
        Creates an Android Language Server instance with Java and Kotlin delegates.
        This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        self.logger = logger
        self.repository_root_path = repository_root_path
        self.solidlsp_settings = solidlsp_settings

        # Initialize delegate language servers
        self._setup_delegate_servers(config, logger, repository_root_path, solidlsp_settings)

        # Create a dummy ProcessLaunchInfo for the Android language server
        # We'll handle the actual server communication through our delegates
        dummy_launch_info = ProcessLaunchInfo(cmd=["echo", "Android Language Server Wrapper"], env={}, cwd=repository_root_path)

        # Use dummy launch info since we delegate to actual language servers
        super().__init__(
            config,
            logger,
            repository_root_path,
            dummy_launch_info,
            "android",
            solidlsp_settings=solidlsp_settings,
        )

    def _setup_delegate_servers(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        """Setup Java and Kotlin language server delegates"""
        # Create Java language server (Eclipse JDTLS)
        from solidlsp.language_servers.eclipse_jdtls import EclipseJDTLS

        java_config = LanguageServerConfig(
            code_language=Language.JAVA,
            trace_lsp_communication=config.trace_lsp_communication,
            start_independent_lsp_process=config.start_independent_lsp_process,
            ignored_paths=config.ignored_paths,
        )
        self.java_ls = EclipseJDTLS(java_config, logger, repository_root_path, solidlsp_settings)

        # Create Kotlin language server
        from solidlsp.language_servers.kotlin_language_server import KotlinLanguageServer

        kotlin_config = LanguageServerConfig(
            code_language=Language.KOTLIN,
            trace_lsp_communication=config.trace_lsp_communication,
            start_independent_lsp_process=config.start_independent_lsp_process,
            ignored_paths=config.ignored_paths,
        )
        self.kotlin_ls = KotlinLanguageServer(kotlin_config, logger, repository_root_path, solidlsp_settings)

    def _route_request_by_file(self, file_path: str) -> SolidLanguageServer:
        """Route requests to appropriate language server based on file extension"""
        if file_path.endswith((".kt", ".kts")):
            return self.kotlin_ls
        elif file_path.endswith(".java"):
            return self.java_ls
        else:
            # Default to Java for unknown files (e.g., build files, resources)
            return self.java_ls

    def _is_kotlin_file(self, file_path: str) -> bool:
        """Check if file is a Kotlin file"""
        return file_path.endswith((".kt", ".kts"))

    def _is_java_file(self, file_path: str) -> bool:
        """Check if file is a Java file"""
        return file_path.endswith(".java")

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        """
        Android-specific directory ignore patterns in addition to base patterns.
        """
        android_ignored = {
            "build",  # Gradle build output
            ".gradle",  # Gradle cache
            ".idea",  # IntelliJ IDEA files
            "app/build",  # Android app build output
            ".externalNativeBuild",  # NDK build artifacts
            "generated",  # Generated source files
        }
        return super().is_ignored_dirname(dirname) or dirname in android_ignored

    # Delegate LSP operations to appropriate language servers

    def request_document_symbols(self, file_path: str) -> list[list[UnifiedSymbolInformation]]:
        """Get document symbols from appropriate language server"""
        delegate_ls = self._route_request_by_file(file_path)
        self.logger.log(f"AndroidLS: Routing {file_path} to {delegate_ls.__class__.__name__}", logging.DEBUG)
        result = delegate_ls.request_document_symbols(file_path)
        self.logger.log(f"AndroidLS: Got symbols result {type(result)} with length {len(result) if result else 'None'}", logging.DEBUG)
        return result

    def request_full_symbol_tree(
        self, within_relative_path: str | None = None, include_body: bool = False
    ) -> list[UnifiedSymbolInformation]:
        """Get full symbol tree from appropriate language servers based on file type"""
        # If no specific path is provided, delegate to both servers
        if within_relative_path is None:
            java_symbols = self.java_ls.request_full_symbol_tree(within_relative_path=None, include_body=include_body)
            kotlin_symbols = self.kotlin_ls.request_full_symbol_tree(within_relative_path=None, include_body=include_body)
            return java_symbols + kotlin_symbols

        # If a specific file path is provided, route to appropriate language server
        if self._is_kotlin_file(within_relative_path):
            # Only delegate to Kotlin language server for .kt/.kts files
            return self.kotlin_ls.request_full_symbol_tree(within_relative_path=within_relative_path, include_body=include_body)
        elif self._is_java_file(within_relative_path):
            # Only delegate to Java language server for .java files
            return self.java_ls.request_full_symbol_tree(within_relative_path=within_relative_path, include_body=include_body)
        else:
            # For directories or unknown file types, delegate to both servers
            java_symbols = self.java_ls.request_full_symbol_tree(within_relative_path=within_relative_path, include_body=include_body)
            kotlin_symbols = self.kotlin_ls.request_full_symbol_tree(within_relative_path=within_relative_path, include_body=include_body)
            return java_symbols + kotlin_symbols

    def request_references(self, file_path: str, line: int, character: int) -> list[dict[str, Any]]:
        """
        Get references from appropriate language server with cross-language support.

        For Android projects, we need to find references across both Java and Kotlin files
        since they can reference each other's symbols (Java interop).

        Strategy:
        1. Get references from the primary language server (based on current file)
        2. For potential cross-language symbols, query the secondary server too
        3. Merge and deduplicate results
        4. Filter out invalid references
        """
        try:
            primary_ls = self._route_request_by_file(file_path)
            primary_refs = primary_ls.request_references(file_path, line, character)

            # Convert to consistent format if needed
            normalized_refs = self._normalize_reference_format(primary_refs)

            # For cross-language reference finding, try the other language server too
            secondary_refs = self._find_cross_language_references(file_path, line, character, primary_ls)

            # Merge references from both servers
            all_refs = normalized_refs + secondary_refs

            # Remove duplicates and invalid references
            unique_refs = self._deduplicate_references(all_refs)

            # Filter out references in ignored directories
            filtered_refs = self._filter_ignored_references(unique_refs)

            self.logger.log(
                f"Found {len(filtered_refs)} references for {file_path}:{line}:{character} "
                f"({len(normalized_refs)} from primary, {len(secondary_refs)} from secondary)",
                logging.DEBUG,
            )

            return filtered_refs

        except Exception as e:
            self.logger.log(f"Error finding references for {file_path}:{line}:{character}: {e}", logging.WARNING)
            # Fallback to primary language server only
            primary_ls = self._route_request_by_file(file_path)
            return primary_ls.request_references(file_path, line, character)

    def _find_cross_language_references(
        self, file_path: str, line: int, character: int, primary_ls: SolidLanguageServer
    ) -> list[dict[str, Any]]:
        """
        Try to find cross-language references by querying the other language server.
        This is useful for Android projects where Java and Kotlin code interoperate.
        """
        secondary_refs = []

        try:
            # Determine which language server to use as secondary
            if primary_ls == self.java_ls:
                secondary_ls = self.kotlin_ls
                cross_lang_name = "Kotlin"
            else:
                secondary_ls = self.java_ls
                cross_lang_name = "Java"

            # Only attempt cross-language lookup for common interop patterns
            if self._should_attempt_cross_language_lookup(file_path, line, character):
                self.logger.log(
                    f"Attempting cross-language reference lookup in {cross_lang_name} for {file_path}:{line}:{character}", logging.DEBUG
                )

                # Try to find the symbol in the secondary language server
                # This might find Java classes referenced from Kotlin or vice versa
                try:
                    cross_refs = secondary_ls.request_references(file_path, line, character)
                    if cross_refs:
                        secondary_refs.extend(self._normalize_reference_format(cross_refs))
                        self.logger.log(f"Found {len(cross_refs)} cross-language references", logging.DEBUG)
                except Exception as cross_e:
                    # Cross-language lookup failed, which is expected for many cases
                    self.logger.log(f"Cross-language lookup failed (expected): {cross_e}", logging.DEBUG)

        except Exception as e:
            self.logger.log(f"Error in cross-language reference lookup: {e}", logging.DEBUG)

        return secondary_refs

    def _should_attempt_cross_language_lookup(self, file_path: str, line: int, character: int) -> bool:
        """
        Determine if we should attempt cross-language reference lookup.
        Only worth trying for symbols that are likely to be shared across languages.
        """
        # For now, always attempt cross-language lookup in Android projects
        # since Java-Kotlin interop is very common
        # Future optimization: parse the symbol at the position to determine if it's likely cross-language
        return True

    def _normalize_reference_format(self, refs: Any) -> list[dict[str, Any]]:
        """
        Normalize reference format from different language servers to a consistent format.
        """
        if not refs:
            return []

        normalized = []
        for ref in refs:
            if isinstance(ref, dict):
                # Already in dict format
                normalized.append(ref)
            elif hasattr(ref, "__dict__"):
                # Convert object to dict
                normalized.append(vars(ref))
            elif hasattr(ref, "uri") and hasattr(ref, "range"):
                # LSP Location object
                normalized.append(
                    {
                        "uri": getattr(ref, "uri", ""),
                        "range": getattr(ref, "range", {}),
                        "absolutePath": getattr(ref, "absolutePath", ""),
                        "relativePath": getattr(ref, "relativePath", None),
                    }
                )
            else:
                # Try to convert to string representation
                normalized.append({"raw": str(ref)})

        return normalized

    def _deduplicate_references(self, refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Remove duplicate references based on file path and position.
        """
        seen = set()
        unique_refs = []

        for ref in refs:
            # Create a unique key based on location
            key = None
            if "uri" in ref and "range" in ref:
                range_info = ref["range"]
                if isinstance(range_info, dict) and "start" in range_info:
                    start = range_info["start"]
                    if isinstance(start, dict):
                        key = (ref["uri"], start.get("line", 0), start.get("character", 0))
            elif "absolutePath" in ref:
                key = ref["absolutePath"]
            elif "relativePath" in ref:
                key = ref["relativePath"]

            if key and key not in seen:
                seen.add(key)
                unique_refs.append(ref)
            elif not key:
                # Keep references we can't deduplicate
                unique_refs.append(ref)

        return unique_refs

    def _filter_ignored_references(self, refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Filter out references in ignored directories (build, .gradle, etc.)
        """
        filtered = []
        for ref in refs:
            should_include = True

            # Check various path fields
            paths_to_check = []
            if "absolutePath" in ref:
                paths_to_check.append(ref["absolutePath"])
            if ref.get("relativePath"):
                paths_to_check.append(ref["relativePath"])
            if "uri" in ref:
                uri = ref["uri"]
                if uri.startswith("file://"):
                    paths_to_check.append(uri[7:])  # Remove file:// prefix

            # Check if any path should be ignored
            for path in paths_to_check:
                if self._should_ignore_reference_path(path):
                    should_include = False
                    break

            if should_include:
                filtered.append(ref)

        return filtered

    def _should_ignore_reference_path(self, path: str) -> bool:
        """
        Check if a reference path should be ignored based on Android-specific patterns.
        """
        if not path:
            return False

        # Android-specific ignore patterns
        ignore_patterns = [
            "/build/",
            "/.gradle/",
            "/generated/",
            "/.externalNativeBuild/",
            "/app/build/",
            "/intermediates/",
            "/tmp/",
        ]

        # Check for ignored directory patterns
        for pattern in ignore_patterns:
            if pattern in path:
                return True

        # Check individual directory names
        path_parts = path.split("/")
        for part in path_parts:
            if self.is_ignored_dirname(part):
                return True

        return False

    def request_definition(self, file_path: str, line: int, character: int) -> Any:
        """Get definition from appropriate language server"""
        delegate_ls = self._route_request_by_file(file_path)
        return delegate_ls.request_definition(file_path, line, character)

    def request_hover(self, file_path: str, line: int, character: int) -> Any:
        """Get hover information from appropriate language server"""
        delegate_ls = self._route_request_by_file(file_path)
        return delegate_ls.request_hover(file_path, line, character)

    def request_completions(self, file_path: str, line: int, character: int) -> Any:
        """Get completions from appropriate language server"""
        delegate_ls = self._route_request_by_file(file_path)
        return delegate_ls.request_completions(file_path, line, character)

    def _start_server(self):
        """
        Start both delegate language servers and coordinate their initialization
        """
        self.logger.log("Starting Android Language Server with Java and Kotlin delegates", logging.INFO)

        # Start Java delegate server first
        try:
            self.java_ls.start()
            self.logger.log("Java language server delegate started", logging.DEBUG)
        except Exception as e:
            self.logger.log(f"Failed to start Java language server: {e}", logging.ERROR)
            raise

        # Start Kotlin delegate server
        try:
            self.kotlin_ls.start()
            self.logger.log("Kotlin language server delegate started", logging.DEBUG)
        except Exception as e:
            self.logger.log(f"Failed to start Kotlin language server: {e}", logging.ERROR)
            raise

        # Set up the server state - we act as a proxy to the delegates
        self.server = self.java_ls.server  # Use Java server as primary
        self.completions_available = self.java_ls.completions_available

        self.logger.log("Android Language Server delegates started successfully", logging.INFO)

    def shutdown(self):
        """Shutdown both delegate language servers"""
        try:
            self.java_ls.shutdown()
        except Exception as e:
            self.logger.log(f"Error shutting down Java language server: {e}", logging.WARNING)

        try:
            self.kotlin_ls.shutdown()
        except Exception as e:
            self.logger.log(f"Error shutting down Kotlin language server: {e}", logging.WARNING)

        super().shutdown()
