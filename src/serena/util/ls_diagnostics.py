import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from solidlsp import ls_types
from solidlsp.lsp_protocol_handler.lsp_types import DiagnosticSeverity

if TYPE_CHECKING:
    from serena.symbol import LanguageServerSymbolRetriever


@dataclass(frozen=True)
class EditedFilePath:
    before_relative_path: str
    after_relative_path: str


@dataclass(frozen=True)
class DiagnosticIdentity:
    message: str
    start_line: int
    start_character: int
    end_line: int
    end_character: int
    severity: int | None
    code_repr: str | None
    source: str | None

    @classmethod
    def from_diagnostic(cls, diagnostic: ls_types.Diagnostic) -> "DiagnosticIdentity":
        diagnostic_range = diagnostic["range"]
        start = diagnostic_range["start"]
        end = diagnostic_range["end"]
        return DiagnosticIdentity(
            message=diagnostic["message"],
            start_line=start["line"],
            start_character=start["character"],
            end_line=end["line"],
            end_character=end["character"],
            severity=diagnostic.get("severity"),
            code_repr=cls._diagnostic_code_repr(diagnostic.get("code")),
            source=diagnostic.get("source"),
        )

    @staticmethod
    def _diagnostic_code_repr(code: Any) -> str | None:
        if code is None:
            return None
        try:
            return json.dumps(code, sort_keys=True, ensure_ascii=False)
        except TypeError:
            return repr(code)


class PublishedDiagnosticsSnapshot:
    def __init__(self, edited_file_paths: Iterable[EditedFilePath], symbol_retriever: "LanguageServerSymbolRetriever"):
        generation_by_after_path: dict[str, int] = {}
        warning_identities_by_before_path: dict[str, set[DiagnosticIdentity]] = {}

        for edited_file_path in edited_file_paths:
            try:
                language_server = symbol_retriever.get_language_server(edited_file_path.after_relative_path)
            except Exception:
                continue

            generation_by_after_path[edited_file_path.after_relative_path] = language_server.get_published_diagnostics_generation(
                edited_file_path.after_relative_path
            )

            cached_diagnostics = language_server.get_cached_published_text_document_diagnostics(
                edited_file_path.before_relative_path,
                min_severity=2,
            )
            if cached_diagnostics is None:
                try:
                    cached_diagnostics = language_server.request_text_document_diagnostics(
                        edited_file_path.before_relative_path,
                        min_severity=2,
                    )
                except Exception:
                    cached_diagnostics = []
            warning_identities_by_before_path[edited_file_path.before_relative_path] = {
                DiagnosticIdentity.from_diagnostic(diagnostic) for diagnostic in cached_diagnostics or []
            }

        self.generation_by_after_path = generation_by_after_path
        self.warning_identities_by_before_path = warning_identities_by_before_path


class GroupedDiagnostics:
    def __init__(self) -> None:
        self._grouped_diagnostics: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = {}

    def add(self, relative_path: str, name_path: str, diagnostic: ls_types.Diagnostic) -> None:
        severity_name = self._diagnostic_severity_name(diagnostic.get("severity"))
        self._grouped_diagnostics.setdefault(relative_path, {}).setdefault(severity_name, {}).setdefault(name_path, []).append(
            self._diagnostic_output_dict(diagnostic)
        )

    def get_dict(self) -> dict[str, dict[str, dict[str, list[dict[str, Any]]]]]:
        """
        Returns a nested dictionary of the form:
        {
            relative_file_path: {
                severity_name: {
                    name_path: [
                        diagnostic_dict,
                        ...
                    ],
                    ...
                },
                ...
            },
            ...
        }
        where:
        - relative_file_path is the relative path of the file containing the diagnostic
        - severity_name is the name of the diagnostic severity (e.g. "Warning", "Error")
        - name_path is the name path of the symbol that owns the diagnostic (or "<file>" if no owner symbol was found)
        - diagnostic_dict is a dictionary containing the diagnostic's message, range, and optionally code and source
        """
        return self._grouped_diagnostics

    @staticmethod
    def _diagnostic_severity_name(severity: int | None) -> str:
        if severity is None:
            return "Unknown"
        try:
            return DiagnosticSeverity(severity).name
        except ValueError:
            return f"Severity_{severity}"

    @staticmethod
    def _diagnostic_output_dict(diagnostic: ls_types.Diagnostic) -> dict[str, Any]:
        result: dict[str, Any] = {
            "message": diagnostic["message"],
            "range": diagnostic["range"],
        }
        if "code" in diagnostic:
            result["code"] = diagnostic["code"]
        if "source" in diagnostic:
            result["source"] = diagnostic["source"]
        return result


class DiagnosticsDiff:
    def __init__(
        self,
        before_snapshot: PublishedDiagnosticsSnapshot,
        edited_files: Iterable[EditedFilePath],
        symbol_retriever: "LanguageServerSymbolRetriever",
    ):
        grouped_diagnostics = GroupedDiagnostics()

        for edited_file_path in edited_files:
            try:
                language_server = symbol_retriever.get_language_server(edited_file_path.after_relative_path)
            except:
                continue

            published_diagnostics = language_server.request_published_text_document_diagnostics(
                relative_file_path=edited_file_path.after_relative_path,
                after_generation=before_snapshot.generation_by_after_path.get(edited_file_path.after_relative_path, -1),
                timeout=2.5,
                min_severity=2,
                allow_cached=True,
            )
            if not published_diagnostics:
                try:
                    published_diagnostics = language_server.request_text_document_diagnostics(
                        edited_file_path.after_relative_path,
                        min_severity=2,
                    )
                except:
                    published_diagnostics = None
            if published_diagnostics is None:
                continue

            existing_warning_identities = before_snapshot.warning_identities_by_before_path.get(
                edited_file_path.before_relative_path, set()
            )
            new_warning_identities: set[DiagnosticIdentity] = set()

            for diagnostic in published_diagnostics:
                diagnostic_identity = DiagnosticIdentity.from_diagnostic(diagnostic)
                if diagnostic_identity in existing_warning_identities or diagnostic_identity in new_warning_identities:
                    continue
                new_warning_identities.add(diagnostic_identity)

                diagnostic_start = diagnostic["range"]["start"]
                owner_symbol = symbol_retriever.find_diagnostic_owner_symbol(
                    relative_file_path=edited_file_path.after_relative_path,
                    line=diagnostic_start["line"],
                    column=diagnostic_start["character"],
                )
                name_path = owner_symbol.get_name_path() if owner_symbol is not None else "<file>"
                grouped_diagnostics.add(edited_file_path.after_relative_path, name_path, diagnostic)

        self._grouped_diagnostics = grouped_diagnostics

    def get_grouped_diagnostics(self) -> GroupedDiagnostics:
        return self._grouped_diagnostics
