from typing import Literal, NotRequired, TypedDict


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
    """Quick info text (e.g., type signature) for the symbol, as HTML string."""
    documentation: NotRequired[str]
    """Documentation text for the symbol (if available), as HTML string."""
    text_range: NotRequired[TextRangeDTO]
    children: NotRequired[list["SymbolDTO"]]
    num_usages: NotRequired[int]


SymbolDTOKey = Literal["name_path", "relative_path", "type", "body", "quick_info", "documentation", "text_range", "children", "num_usages"]


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
