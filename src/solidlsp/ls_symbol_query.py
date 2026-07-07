"""
Symbol query service (Phase 5 deep module).

Owns:
- SymbolLocationRequest and its subclasses (DefinitionLocationRequest,
  ImplementationLocationRequest, ReferencesLocationRequest)
- request_definition / request_implementation / request_references
- request_referencing_symbols / request_containing_symbol / request_container_of_symbol
- request_defining_symbol / request_implementing_symbols / request_symbol_at_location
- Internal helpers for symbol location resolution and refinement.

The service collaborates with:
- OpenDocuments (via facade.open_file / _open_file_context)
- DocumentSymbolRepository (via facade.request_document_symbols)
- Facade policy hooks (_get_preferred_definition, _pre_open_for_cross_file_references,
  _wait_for_cross_file_references_if_needed, _send_*_request, etc.)

The facade retains thin delegators for all public request_* signatures and preserves
all current adapter override hook names.
"""

from __future__ import annotations

import logging
import os
import pathlib
from abc import ABC, abstractmethod
from collections.abc import Iterator
from copy import copy
from time import perf_counter
from typing import TYPE_CHECKING, cast

from solidlsp import ls_types
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_symbol_model import ReferenceInSymbol, SymbolBodyFactory
from solidlsp.ls_utils import FileUtils, PathUtils
from solidlsp.lsp_protocol_handler.lsp_constants import LSPConstants
from solidlsp.lsp_protocol_handler.server import LSPError

if TYPE_CHECKING:
    from solidlsp.ls import SolidLanguageServer

log = logging.getLogger(__name__)

_debug_enabled = log.isEnabledFor(logging.DEBUG)


# ------------------------------------------------------------------
# Location request base and subclasses
# These remain instantiable via SolidLanguageServer.* for adapter compatibility
# (e.g., svelte adapter uses self.ReferencesLocationRequest(...) for normalization).
# ------------------------------------------------------------------


class SymbolLocationRequest(ABC):
    def __init__(
        self,
        language_server: "SolidLanguageServer",
        relative_file_path: str,
        line: int,
        column: int,
        *,
        request_name: str,
    ) -> None:
        self.language_server = language_server
        self.relative_file_path = relative_file_path
        self.line = line
        self.column = column
        self.request_name = request_name
        self.skip_ignored_paths = True

    def execute(self) -> list[ls_types.Location]:
        self._ensure_server_started()

        t0 = perf_counter() if _debug_enabled else None
        # arm indexing tracking before didOpen so that the subsequent wait can
        # observe the indexing progress triggered by opening the file
        self.language_server._pre_open_for_cross_file_references()
        with self.language_server.open_file(self.relative_file_path):
            self.language_server._wait_for_cross_file_references_if_needed()
            try:
                response = self.send_request()
            except Exception as e:
                mapped_exception = self.map_exception(e)
                if mapped_exception is not None:
                    raise mapped_exception from e
                raise

        result = self.normalize_response(response)
        if t0 is not None:
            self.log_perf_result(t0, result)
        return result

    def _ensure_server_started(self) -> None:
        if not self.language_server.server_started:
            log.error("%s called before language server started", self.request_name)
            raise SolidLSPException("Language Server not started")

    @abstractmethod
    def send_request(self) -> object | None:
        pass

    def map_exception(self, error: Exception) -> Exception | None:
        if isinstance(error, LSPError) and getattr(error, "code", None) == -32603:
            return RuntimeError(
                f"LSP internal error (-32603) when requesting {self.request_name} for "
                f"{self.relative_file_path}:{self.line}:{self.column}. "
                "This often occurs when requesting a symbol in a way the language server cannot resolve."
            )
        return None

    @abstractmethod
    def normalize_response(self, response: object | None) -> list[ls_types.Location]:
        pass

    def convert_location_item(self, item: dict[str, object], *, allow_location_links: bool = False) -> ls_types.Location | None:
        if LSPConstants.URI in item and LSPConstants.RANGE in item:
            uri = cast(str, item[LSPConstants.URI])
            range_d = cast(ls_types.Range, item[LSPConstants.RANGE])
        elif (
            allow_location_links
            and LSPConstants.TARGET_URI in item
            and LSPConstants.TARGET_RANGE in item
            and LSPConstants.TARGET_SELECTION_RANGE in item
        ):
            uri = cast(str, item[LSPConstants.TARGET_URI])
            range_d = cast(ls_types.Range, item[LSPConstants.TARGET_SELECTION_RANGE])
        else:
            raise AssertionError(f"Unexpected response from Language Server: {item}")

        abs_path = PathUtils.uri_to_path(uri)
        rel_path_str = PathUtils.get_relative_path(abs_path, self.language_server.repository_root_path)

        if rel_path_str is None:
            log.warning(
                "Found a %s in a path outside the repository, probably the LS is parsing things in installed packages or in the standardlib! "
                "Path: %s. This is a bug but we currently simply skip these locations.",
                self.request_name,
                abs_path,
            )
            return None

        if self.skip_ignored_paths and self.language_server.is_ignored_path(rel_path_str):
            log.info("%s found symbol in ignored path: %s", self.request_name, rel_path_str)
            return None

        return ls_types.Location(uri=uri, range=range_d, absolutePath=str(abs_path), relativePath=rel_path_str)

    def log_perf_result(self, t0: float, result: list[ls_types.Location]) -> None:
        return


class DefinitionLocationRequest(SymbolLocationRequest):
    def __init__(
        self,
        language_server: "SolidLanguageServer",
        relative_file_path: str,
        line: int,
        column: int,
        *,
        request_name: str = "request_definition",
    ) -> None:
        super().__init__(
            language_server,
            relative_file_path,
            line,
            column,
            request_name=request_name,
        )

    def send_request(self) -> object | None:
        return self.language_server._send_definition_request(
            self.language_server._create_text_document_position_params(self.relative_file_path, self.line, self.column)
        )

    def normalize_response(self, response: object | None) -> list[ls_types.Location]:
        if response is None:
            log.warning(
                "Language server returned None for %s request at %s:%s:%s",
                self.request_name,
                self.relative_file_path,
                self.line,
                self.column,
            )
            return []
        ret: list[ls_types.Location] = []
        if isinstance(response, list):
            for item in response:
                assert isinstance(item, dict), f"Unexpected response from Language Server (expected dict, got {type(item)}): {item}"
                if location := self.convert_location_item(cast(dict[str, object], item), allow_location_links=True):
                    ret.append(location)
            return ret

        if isinstance(response, dict):
            if location := self.convert_location_item(cast(dict[str, object], response), allow_location_links=True):
                ret.append(location)
            return ret

        assert False, f"Unexpected response from Language Server: {response}"


class ImplementationLocationRequest(DefinitionLocationRequest):
    def __init__(self, language_server: "SolidLanguageServer", relative_file_path: str, line: int, column: int) -> None:
        super().__init__(
            language_server,
            relative_file_path,
            line,
            column,
            request_name="request_implementation",
        )

    def send_request(self) -> object | None:
        return self.language_server._send_implementation_request(
            self.language_server._create_text_document_position_params(self.relative_file_path, self.line, self.column),
        )


class ReferencesLocationRequest(SymbolLocationRequest):
    def __init__(self, language_server: "SolidLanguageServer", relative_file_path: str, line: int, column: int) -> None:
        super().__init__(
            language_server,
            relative_file_path,
            line,
            column,
            request_name="request_references",
        )

    def send_request(self) -> object | None:
        return self.language_server._send_references_request(self.relative_file_path, line=self.line, column=self.column)

    def normalize_response(self, response: object | None) -> list[ls_types.Location]:
        if response is None:
            return []
        assert isinstance(response, list), f"Unexpected response from Language Server (expected list, got {type(response)}): {response}"
        ret: list[ls_types.Location] = []
        for item in response:
            assert isinstance(item, dict), f"Unexpected response from Language Server (expected dict, got {type(item)}): {item}"
            if location := self.convert_location_item(cast(dict[str, object], item)):
                ret.append(location)
        return ret

    def log_perf_result(self, t0: float, result: list[ls_types.Location]) -> None:
        elapsed_ms = (perf_counter() - t0) * 1000
        if not result:
            log.debug("perf: request_references path=%s elapsed_ms=%.2f count=0", self.relative_file_path, elapsed_ms)
            return

        unique_files = len({r["relativePath"] for r in result})
        log.debug(
            "perf: request_references path=%s elapsed_ms=%.2f count=%d unique_files=%d",
            self.relative_file_path,
            elapsed_ms,
            len(result),
            unique_files,
        )


# ------------------------------------------------------------------
# Static helpers moved from the facade (used by higher-level symbol semantics)
# ------------------------------------------------------------------


def _get_range_from_file_content(file_content: str) -> ls_types.Range:
    """Get the range for the given file."""
    lines = file_content.split("\n")
    end_line = len(lines)
    end_column = len(lines[-1])
    return ls_types.Range(start=ls_types.Position(line=0, character=0), end=ls_types.Position(line=end_line, character=end_column))


def _position_matches_range(range_d: ls_types.Range, line: int, column: int | None = None) -> bool:
    start = range_d["start"]
    end = range_d["end"]
    if not (start["line"] <= line <= end["line"]):
        return False
    if column is None:
        return True
    if line == start["line"] and column < start["character"]:
        return False
    if line == end["line"] and column > end["character"]:
        return False
    return True


def _symbol_match_sort_key(symbol: ls_types.UnifiedSymbolInformation, match_priority: int) -> tuple[int, int, int, int, int]:
    location = symbol["location"]
    symbol_range = location["range"]
    start = symbol_range["start"]
    end = symbol_range["end"]
    line_span = end["line"] - start["line"]
    character_span = end["character"] - start["character"] if line_span == 0 else end["character"]
    return match_priority, line_span, character_span, start["line"], start["character"]


def _iter_symbol_descendants(symbol: ls_types.UnifiedSymbolInformation) -> Iterator[ls_types.UnifiedSymbolInformation]:
    """Yield descendant symbols in depth-first order."""
    for child in symbol.get("children", []):
        yield child
        yield from _iter_symbol_descendants(child)


# ------------------------------------------------------------------
# SymbolQueryService (deep module)
# ------------------------------------------------------------------


class SymbolQueryService:
    """
    Deep module owning location-based queries and higher-level symbol semantics.

    The service is constructed with the owning SolidLanguageServer facade and
    delegates to it for:
    - Low-level LSP senders (_send_definition_request, etc.)
    - Open document management (open_file)
    - Document symbol retrieval (request_document_symbols)
    - Body creation (create_symbol_body)
    - Path/URI helpers and ignore checks
    - Policy hooks (_get_preferred_definition, pre-open/wait hooks)

    Public request_* methods on the facade remain as thin delegators.
    """

    def __init__(self, owner: "SolidLanguageServer") -> None:
        self._owner = owner

    # ------------------------------------------------------------------
    # Primitive location requests (thin orchestration over the request classes)
    # ------------------------------------------------------------------

    def request_definition(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        request = self._owner.DefinitionLocationRequest(self._owner, relative_file_path, line, column)
        return request.execute()

    def request_implementation(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        request = self._owner.ImplementationLocationRequest(self._owner, relative_file_path, line, column)
        return request.execute()

    def request_references(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        request = self._owner.ReferencesLocationRequest(self._owner, relative_file_path, line, column)
        return request.execute()

    # ------------------------------------------------------------------
    # Higher-level symbol semantics
    # ------------------------------------------------------------------

    def request_referencing_symbols(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        include_imports: bool = True,
        include_self: bool = False,
        include_body: bool = False,
        include_file_symbols: bool = False,
    ) -> list[ReferenceInSymbol]:
        """
        Finds all symbols that reference the symbol at the given location.
        This is similar to request_references but filters to only include symbols
        (functions, methods, classes, etc.) that reference the target symbol.
        """
        if not self._owner.server_started:
            log.error("request_referencing_symbols called before Language Server started")
            raise SolidLSPException("Language Server not started")

        # First, get all references to the symbol
        references = self.request_references(relative_file_path, line, column)
        if not references:
            return []

        debug_enabled = log.isEnabledFor(logging.DEBUG)
        t0_loop = perf_counter() if debug_enabled else 0.0
        # For each reference, find the containing symbol
        result = []
        incoming_symbol = None
        for ref in references:
            ref_path = ref["relativePath"]
            assert ref_path is not None
            ref_line = ref["range"]["start"]["line"]
            ref_col = ref["range"]["start"]["character"]

            with self._owner.open_file(ref_path) as file_data:
                body_factory = SymbolBodyFactory(file_data)

                # Get the containing symbol for this reference
                containing_symbol = self.request_containing_symbol(
                    ref_path, ref_line, ref_col, include_body=include_body, body_factory=body_factory
                )
                if containing_symbol is None:
                    # TODO: HORRIBLE HACK! I don't know how to do it better for now...
                    # THIS IS BOUND TO BREAK IN MANY CASES! IT IS ALSO SPECIFIC TO PYTHON!
                    # Background:
                    # When a variable is used to change something, like
                    #
                    # instance = MyClass()
                    # instance.status = "new status"
                    #
                    # we can't find the containing symbol for the reference to `status`
                    # since there is no container on the line of the reference
                    # The hack is to try to find a variable symbol in the containing module
                    # by using the text of the reference to find the variable name (In a very heuristic way)
                    # and then look for a symbol with that name and kind Variable
                    ref_text = file_data.contents.split("\n")[ref_line]
                    if "." in ref_text:
                        containing_symbol_name = ref_text.split(".")[0]
                        document_symbols = self._owner.request_document_symbols(ref_path)
                        for symbol in document_symbols.iter_symbols():
                            if symbol["name"] == containing_symbol_name and symbol["kind"] == ls_types.SymbolKind.Variable:
                                containing_symbol = copy(symbol)
                                containing_symbol["location"] = ref
                                containing_symbol["range"] = ref["range"]
                                break

                # We failed retrieving the symbol, falling back to creating a file symbol
                if containing_symbol is None and include_file_symbols:
                    log.warning(f"Could not find containing symbol for {ref_path}:{ref_line}:{ref_col}. Returning file symbol instead")
                    fileRange = _get_range_from_file_content(file_data.contents)
                    ref_abs_path = os.path.join(self._owner.repository_root_path, ref_path)
                    if self._owner._path_contains_dots(ref_path):
                        ref_abs_path = str(pathlib.Path(ref_abs_path).resolve())
                    location = ls_types.Location(
                        uri=self._owner._resolve_file_uri(ref_path),
                        range=fileRange,
                        absolutePath=ref_abs_path,
                        relativePath=ref_path,
                    )
                    name = os.path.splitext(os.path.basename(ref_path))[0]

                    containing_symbol = ls_types.UnifiedSymbolInformation(
                        kind=ls_types.SymbolKind.File,
                        range=fileRange,
                        selectionRange=fileRange,
                        location=location,
                        name=name,
                        children=[],
                    )

                    if include_body:
                        containing_symbol["body"] = self._owner.create_symbol_body(containing_symbol, factory=body_factory)

                if containing_symbol is None or (not include_file_symbols and containing_symbol["kind"] == ls_types.SymbolKind.File):
                    continue

                assert "location" in containing_symbol
                assert "selectionRange" in containing_symbol

                # Checking for self-reference
                if (
                    containing_symbol["location"]["relativePath"] == relative_file_path
                    and containing_symbol["selectionRange"]["start"]["line"] == ref_line
                    and containing_symbol["selectionRange"]["start"]["character"] == ref_col
                ):
                    incoming_symbol = containing_symbol
                    if include_self:
                        result.append(ReferenceInSymbol(symbol=containing_symbol, line=ref_line, character=ref_col))
                        continue
                    log.debug(f"Found self-reference for {incoming_symbol['name']}, skipping it since {include_self=}")
                    continue

                # checking whether reference is an import
                # This is neither really safe nor elegant, but if we don't do it,
                # there is no way to distinguish between definitions and imports as import is not a symbol-type
                # and we get the type referenced symbol resulting from imports...
                if (
                    not include_imports
                    and incoming_symbol is not None
                    and containing_symbol["name"] == incoming_symbol["name"]
                    and containing_symbol["kind"] == incoming_symbol["kind"]
                ):
                    log.debug(
                        f"Found import of referenced symbol {incoming_symbol['name']}"
                        f"in {containing_symbol['location']['relativePath']}, skipping"
                    )
                    continue

                result.append(ReferenceInSymbol(symbol=containing_symbol, line=ref_line, character=ref_col))

        if debug_enabled:
            loop_elapsed_ms = (perf_counter() - t0_loop) * 1000
            unique_files = len({r.symbol["location"]["relativePath"] for r in result})
            log.debug(
                "perf: request_referencing_symbols path=%s loop_elapsed_ms=%.2f ref_count=%d result_count=%d unique_files=%d",
                relative_file_path,
                loop_elapsed_ms,
                len(references),
                len(result),
                unique_files,
            )

        return result

    def request_containing_symbol(
        self,
        relative_file_path: str,
        line: int,
        column: int | None = None,
        strict: bool = False,
        include_body: bool = False,
        body_factory: SymbolBodyFactory | None = None,
    ) -> ls_types.UnifiedSymbolInformation | None:
        """
        Finds the first symbol containing the position for the given file.
        For Python, container symbols are considered to be those with kinds corresponding to
        functions, methods, or classes (typically: Function (12), Method (6), Class (5)).

        The method operates as follows:
          - Request the document symbols for the file.
          - Filter symbols to those that start at or before the given line.
          - From these, first look for symbols whose range contains the (line, column).
          - If one or more symbols contain the position, return the one with the greatest starting position
            (i.e. the innermost container).
          - If none (strictly) contain the position, return the symbol with the greatest starting position
            among those above the given line.
          - If no container candidates are found, return None.
        """
        # checking if the line is empty, unfortunately ugly and duplicating code, but I don't want to refactor
        with self._owner.open_file(relative_file_path):
            absolute_file_path = os.path.join(self._owner.repository_root_path, relative_file_path)
            if self._owner._path_contains_dots(relative_file_path):
                absolute_file_path = str(pathlib.Path(absolute_file_path).resolve())
            content = FileUtils.read_file(absolute_file_path, self._owner._encoding)
            if content.split("\n")[line].strip() == "":
                log.error(f"Passing empty lines to request_container_symbol is currently not supported, {relative_file_path=}, {line=}")
                return None

        document_symbols = self._owner.request_document_symbols(relative_file_path)

        # make jedi and pyright api compatible
        # the former has no location, the later has no range
        # we will just always add location of the desired format to all symbols
        for symbol in document_symbols.iter_symbols():
            if "location" not in symbol:
                range = symbol["range"]
                location = ls_types.Location(
                    uri=f"file:/{absolute_file_path}",
                    range=range,
                    absolutePath=absolute_file_path,
                    relativePath=relative_file_path,
                )
                symbol["location"] = location
            else:
                location = symbol["location"]
                assert "range" in location
                location["absolutePath"] = absolute_file_path
                location["relativePath"] = relative_file_path
                location["uri"] = pathlib.Path(absolute_file_path).as_uri()

        # Allowed container kinds, currently only for Python
        container_symbol_kinds = {ls_types.SymbolKind.Method, ls_types.SymbolKind.Function, ls_types.SymbolKind.Class}

        def is_position_in_range(line: int, range_d: ls_types.Range) -> bool:
            start = range_d["start"]
            end = range_d["end"]

            column_condition = True
            if strict:
                line_condition = end["line"] >= line > start["line"]
                if column is not None and line == start["line"]:
                    column_condition = column > start["character"]
            else:
                line_condition = end["line"] >= line >= start["line"]
                if column is not None and line == start["line"]:
                    column_condition = column >= start["character"]
            return line_condition and column_condition

        # Only consider containers that are not one-liners (otherwise we may get imports)
        candidate_containers = [
            s
            for s in document_symbols.iter_symbols()
            if s["kind"] in container_symbol_kinds and s["location"]["range"]["start"]["line"] != s["location"]["range"]["end"]["line"]
        ]
        var_containers = [s for s in document_symbols.iter_symbols() if s["kind"] == ls_types.SymbolKind.Variable]
        candidate_containers.extend(var_containers)

        if not candidate_containers:
            return None

        # From the candidates, find those whose range contains the given position.
        containing_symbols = []
        for symbol in candidate_containers:
            s_range = symbol["location"]["range"]
            if not is_position_in_range(line, s_range):
                continue
            containing_symbols.append(symbol)

        if containing_symbols:
            # Return the one with the greatest starting position (i.e. the innermost container).
            containing_symbol = max(containing_symbols, key=lambda s: s["location"]["range"]["start"]["line"])
            if include_body:
                containing_symbol["body"] = self._owner.create_symbol_body(containing_symbol, factory=body_factory)
            return containing_symbol
        else:
            return None

    def request_container_of_symbol(
        self, symbol: ls_types.UnifiedSymbolInformation, include_body: bool = False
    ) -> ls_types.UnifiedSymbolInformation | None:
        """
        Finds the container of the given symbol if there is one. If the parent attribute is present, the parent is returned
        without further searching.
        """
        if "parent" in symbol:
            return symbol["parent"]
        assert "location" in symbol, f"Symbol {symbol} has no location and no parent attribute"
        return self.request_containing_symbol(
            symbol["location"]["relativePath"],  # type: ignore
            symbol["location"]["range"]["start"]["line"],
            symbol["location"]["range"]["start"]["character"],
            strict=True,
            include_body=include_body,
        )

    def _get_document_symbols_with_locations(self, relative_file_path: str) -> list[ls_types.UnifiedSymbolInformation]:
        abs_path = os.path.join(self._owner.repository_root_path, relative_file_path)
        if self._owner._path_contains_dots(relative_file_path):
            abs_path = str(pathlib.Path(abs_path).resolve())
        document_symbols = self._owner.request_document_symbols(relative_file_path)
        symbols = list(document_symbols.iter_symbols())

        # Make SymbolInformation and DocumentSymbol shapes consistent by ensuring every
        # symbol exposes a normalized location/range in the current workspace.
        for symbol in symbols:
            location = symbol["location"]
            location["absolutePath"] = abs_path
            location["relativePath"] = relative_file_path
            location["uri"] = self._owner._resolve_file_uri(relative_file_path)
        return symbols

    def _request_symbol_at_location(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        include_body: bool = False,
        body_factory: SymbolBodyFactory | None = None,
    ) -> ls_types.UnifiedSymbolInformation | None:
        candidates: list[tuple[tuple[int, int, int, int, int], ls_types.UnifiedSymbolInformation]] = []
        for symbol in self._get_document_symbols_with_locations(relative_file_path):
            location = symbol["location"]
            symbol_range = location["range"]
            selection_range = symbol.get("selectionRange") or symbol_range

            match_priority: int | None = None
            if _position_matches_range(selection_range, line, column):
                match_priority = 0
            elif _position_matches_range(symbol_range, line, column):
                match_priority = 1
            else:
                selection_start = selection_range["start"]
                symbol_start = symbol_range["start"]
                if (selection_start["line"], selection_start["character"]) == (line, column):
                    match_priority = 2
                elif (symbol_start["line"], symbol_start["character"]) == (line, column):
                    match_priority = 3
                elif selection_start["line"] == line and column <= selection_start["character"]:
                    match_priority = 4
                elif symbol_start["line"] == line and column <= symbol_start["character"]:
                    match_priority = 5

            if match_priority is None:
                continue
            candidates.append((_symbol_match_sort_key(symbol, match_priority), symbol))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0])
        best_symbol = candidates[0][1]
        if include_body:
            best_symbol["body"] = self._owner.create_symbol_body(best_symbol, factory=body_factory)
        return best_symbol

    def _refine_implementing_symbol(
        self,
        target_symbol: ls_types.UnifiedSymbolInformation | None,
        implementing_symbol: ls_types.UnifiedSymbolInformation,
        include_body: bool = False,
    ) -> ls_types.UnifiedSymbolInformation:
        """Resolve member-level implementation symbols when the LS returns a containing type."""
        if target_symbol is None:
            return implementing_symbol

        target_kind = target_symbol["kind"]
        if target_kind not in (ls_types.SymbolKind.Method, ls_types.SymbolKind.Function):
            return implementing_symbol

        if implementing_symbol["kind"] == target_kind and implementing_symbol.get("name") == target_symbol.get("name"):
            return implementing_symbol

        candidate_descendants: list[ls_types.UnifiedSymbolInformation] = []
        for descendant in _iter_symbol_descendants(implementing_symbol):
            if descendant.get("name") != target_symbol.get("name"):
                continue
            if descendant["kind"] != target_kind:
                continue
            candidate_descendants.append(descendant)

        if not candidate_descendants:
            return implementing_symbol

        refined_symbol = min(
            candidate_descendants,
            key=lambda symbol: _symbol_match_sort_key(symbol, match_priority=0),
        )
        if include_body:
            refined_symbol["body"] = self._owner.create_symbol_body(refined_symbol)
        return refined_symbol

    def request_symbol_at_location(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        include_body: bool = False,
    ) -> ls_types.UnifiedSymbolInformation | None:
        """
        Finds the symbol at the given position, preferring exact identifier matches and otherwise
        falling back to the innermost symbol whose body contains the position.
        """
        if not self._owner.server_started:
            log.error("request_symbol_at_location called before language server started")
            raise SolidLSPException("Language Server not started")
        return self._request_symbol_at_location(relative_file_path, line, column, include_body=include_body)

    def request_defining_symbol(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        include_body: bool = False,
    ) -> ls_types.UnifiedSymbolInformation | None:
        """
        Finds the symbol that defines the symbol at the given location.

        This method first finds the definition of the symbol at the given position,
        then retrieves the full symbol information for that definition.
        """
        if not self._owner.server_started:
            log.error("request_defining_symbol called before language server started")
            raise SolidLSPException("Language Server not started")

        # Get the definition location(s)
        definitions = self.request_definition(relative_file_path, line, column)
        if not definitions:
            return None

        # Select the preferred definition (subclasses can override _get_preferred_definition on the owner)
        definition = self._owner._get_preferred_definition(definitions)
        def_path = definition["relativePath"]
        if def_path is None:
            return None
        def_line = definition["range"]["start"]["line"]
        def_col = definition["range"]["start"]["character"]

        return self._request_symbol_at_location(
            def_path,
            def_line,
            def_col,
            include_body=include_body,
        )

    def request_implementing_symbols(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        include_body: bool = False,
    ) -> list[ls_types.UnifiedSymbolInformation]:
        """
        Finds the symbols that implement the symbol at the given location.

        This method first finds implementation locations for the symbol at the given position,
        then retrieves the full symbol information for each implementation and de-duplicates
        results that map to the same containing symbol.
        """
        if not self._owner.server_started:
            log.error("request_implementing_symbols called before language server started")
            raise SolidLSPException("Language Server not started")

        target_symbol = self._request_symbol_at_location(relative_file_path, line, column, include_body=False)
        implementation_locations = self.request_implementation(relative_file_path, line, column)
        if not implementation_locations:
            return []

        result: list[ls_types.UnifiedSymbolInformation] = []
        seen_keys: set[tuple[str, int, int, int]] = set()
        for implementation in implementation_locations:
            implementation_path = implementation["relativePath"]
            assert implementation_path is not None
            implementation_line = implementation["range"]["start"]["line"]
            implementation_col = implementation["range"]["start"]["character"]
            implementing_symbol = self._request_symbol_at_location(
                implementation_path,
                implementation_line,
                implementation_col,
                include_body=include_body,
                body_factory=None,
            )
            if implementing_symbol is None:
                continue
            implementing_symbol = self._refine_implementing_symbol(target_symbol, implementing_symbol, include_body=include_body)
            if "location" not in implementing_symbol:
                continue
            symbol_location = implementing_symbol["location"]
            symbol_key = (
                cast(str, symbol_location["relativePath"]),
                symbol_location["range"]["start"]["line"],
                symbol_location["range"]["start"]["character"],
                implementing_symbol["kind"],
            )
            if symbol_key in seen_keys:
                continue
            seen_keys.add(symbol_key)
            result.append(implementing_symbol)

        return result
