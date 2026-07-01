from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Self, cast

from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams

if TYPE_CHECKING:
    from solidlsp import SolidLanguageServer


class InitializeParamsBuilder(ABC):
    def __init__(self):
        self._options = {}

    def with_base_options(self, options: dict) -> Self:
        self._options.update(options)
        return self

    @abstractmethod
    def _apply_updates(self) -> None:
        """
        Applies implementation-specific updates to the options.
        """

    def build(self) -> InitializeParams:
        self._apply_updates()
        return cast(InitializeParams, self._options)


class DefaultInitializeParamsBuilder(InitializeParamsBuilder):
    def __init__(self, ls: "SolidLanguageServer"):
        super().__init__()
        self._ls = ls

    def _apply_updates(self):
        pass
