"""
Module with assignment statements of various shapes, whose symbol bodies must cover the entire statement.
"""

from dataclasses import dataclass, field
from typing import Annotated, NamedTuple

from pydantic import BaseModel, Field

TriageRationale = Annotated[
    str,
    Field(
        description=(
            "Shown to the developer in the decision log."
        )
    ),
]

SINGLE_LINE_CONSTANT = 42  # trailing comment

CONTINUED_SUM = 1 + \
    2

IMPLICIT_CONCATENATION = (
    "first part, "
    "second part"
)

TYPED_TABLE: dict[str, int] = {
    "alpha": 1,
    "beta": 2,
}

declared_only: int

chained_first = chained_second = "chained"

unpacked_first, unpacked_second = divmod(7, 2)


class EscalateCall(BaseModel):
    why_escalated: str = Field(
        description=(
            "One sentence shown to the developer."
        )
    )
    declared_field: int


@dataclass
class DataclassWithFields:
    default_field: list[str] = field(default_factory=list)
    plain_field: int = 0


class NamedTupleWithFields(NamedTuple):
    required_item: int
    defaulted_item: str = "default"


def function_after_assignments() -> int:
    return SINGLE_LINE_CONSTANT
