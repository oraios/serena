import logging
import os
import pathlib
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Self, cast

from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams, WorkspaceFolder

if TYPE_CHECKING:
    from solidlsp import SolidLanguageServer


log = logging.getLogger(__name__)


class InitializeParamsBuilder(ABC):
    def __init__(self):
        self._params = {}

    def with_base_options(self, options: dict | InitializeParams) -> Self:
        self._params.update(options)
        return self

    def _set(self, key: str, value: Any) -> None:
        if key in self._params:
            log.debug("Overriding existing option '%s' with new value: %s (old value: %s)", key, value, self._params[key])
        self._params[key] = value

    @abstractmethod
    def _apply_updates(self) -> None:
        """
        Applies implementation-specific updates to the options.
        """

    def build(self) -> InitializeParams:
        self._apply_updates()
        return cast(InitializeParams, self._params)


class DefaultInitializeParamsBuilder(InitializeParamsBuilder):
    def __init__(self, ls: "SolidLanguageServer", set_workspace_folders: bool = True):
        super().__init__()
        self._ls = ls
        self._set_workspace_folders = set_workspace_folders

    @staticmethod
    def _create_workspace_folder_entry(path: str) -> WorkspaceFolder:
        abs_path = os.path.abspath(path)
        return {"uri": pathlib.Path(abs_path).as_uri(), "name": os.path.basename(abs_path)}

    def _apply_updates(self):
        root_abs_path = self._ls.repository_root_path
        self._set("processId", os.getpid())
        self._set("rootPath", root_abs_path)
        self._set("rootUri", pathlib.Path(root_abs_path).as_uri())
        self._set("clientInfo", {"name": "Serena"})
        if self._set_workspace_folders:
            self._set("workspaceFolders", [self._create_workspace_folder_entry(root_abs_path)])
