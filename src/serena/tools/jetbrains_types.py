from typing import NotRequired, TypedDict

# TODO or not TODO: in principle, we could autogenerate these from the java code. For now not worth the effort.


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


class SymbolCollectionResponse(TypedDict):
    symbols: list[SymbolDTO]
    documentation: NotRequired[str]
    """Docstring of the collection (if applicable - usually present only if the collection is from a single file), 
    as HTML string."""


class TypeHierarchyNodeDTO(TypedDict):
    symbol: SymbolDTO
    children: NotRequired[list["TypeHierarchyNodeDTO"]]


class TypeHierarchyResponse(TypedDict):
    symbol: NotRequired[SymbolDTO]
    hierarchy: NotRequired[list[TypeHierarchyNodeDTO]]
    error: NotRequired[str]
    num_levels_not_included: NotRequired[int]
