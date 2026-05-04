from typing import Literal, NotRequired, TypedDict

JB_EXTERNAL_FILE_PREFIX = "<ext:"
"""
Prefix used for in relative paths of symbols that are from external libraries (i.e., not defined in the user's codebase).
"""


class PluginStatusDTO(TypedDict):
    project_root: str
    plugin_version: str


class PositionDTO(TypedDict):
    line: int
    col: int


class TextRangeDTO(TypedDict):
    start_pos: PositionDTO
    end_pos: PositionDTO


class SymbolDTO(TypedDict):
    name_path: str
    relative_path: str
    type: str
    body: NotRequired[str]
    quick_info: NotRequired[str]
    """quick info text (e.g., type signature) for the symbol, as HTML string."""
    documentation: NotRequired[str]
    """documentation text for the symbol (if available), as HTML string."""
    text_range: NotRequired[TextRangeDTO]
    children: NotRequired[list["SymbolDTO"]]
    num_usages: NotRequired[int]
    reference_line_no: NotRequired[int]
    """
    for the case where this is a reference, the line number of the reference (0-based, relative to the file where the symbol is defined).
    """

    # --- Python-side extensions, i.e. fields that are not returned by the plugin but set later by the Python code ---

    context: NotRequired[str]
    """
    context around the symbol/reference, e.g., a few lines of code before and after the symbol definition or reference, 
    to provide additional context for the LLM.
    """


SymbolDTOKey = Literal[
    "name_path",
    "relative_path",
    "type",
    "body",
    "quick_info",
    "documentation",
    "text_range",
    "children",
    "num_usages",
    "reference_line_no",
    "context",
]


class SymbolDTOUtil:
    @staticmethod
    def is_external_symbol(symbol_dto: SymbolDTO) -> bool:
        """
        Checks if a symbol is an external symbol (i.e., from a library) based on its relative path.
        """
        return symbol_dto["relative_path"].startswith(JB_EXTERNAL_FILE_PREFIX)


class SymbolCollectionResponse(TypedDict):
    symbols: list[SymbolDTO]


class GetSymbolsOverviewResponse(SymbolCollectionResponse):
    documentation: NotRequired[str]
    """Docstring of the collection (if applicable - usually present only if the collection is from a single file), 
    as HTML string."""


class TypeHierarchyNodeDTO(TypedDict):
    symbol: SymbolDTO
    children: NotRequired[list["TypeHierarchyNodeDTO"]]


class TypeHierarchyResponse(TypedDict):
    hierarchy: NotRequired[list[TypeHierarchyNodeDTO]]
    num_levels_not_included: NotRequired[int]


class InspectionResultDTO(TypedDict):
    inspection_name: str
    severity: str
    message: str
    relative_path: str
    start_line: int
    end_line: int
    start_col: NotRequired[int]
    end_col: NotRequired[int]
    quick_fix_available: NotRequired[bool]


class RunInspectionsResponse(TypedDict):
    inspections: list[InspectionResultDTO]


class InspectionInfoDTO(TypedDict):
    name: str
    group_path: str
    language: NotRequired[str]
    description: NotRequired[str]


class ListInspectionsResponse(TypedDict):
    inspections: list[InspectionInfoDTO]
