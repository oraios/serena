"""
Defines settings for Solid-LSP
"""

import os
import pathlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from solidlsp.ls_config import Language


@dataclass
class SolidLSPSettings:
    solidlsp_dir: str = str(pathlib.Path.home() / ".solidlsp")
    """
    Path to the directory in which to store global Solid-LSP data (which is not project-specific)
    """
    project_data_relative_path: str = ".solidlsp"
    """
    Relative path within each project directory where Solid-LSP can store project-specific data, e.g. cache files.
    For instance, if this is ".solidlsp" and the project is located at "/home/user/myproject",
    then Solid-LSP will store project-specific data in "/home/user/myproject/.solidlsp".
    """
    ls_specific_settings: dict["Language", Any] = field(default_factory=dict)
    """
    Advanced configuration option allowing to configure language server implementation specific options.
    Have a look at the docstring of the constructors of the corresponding LS implementations within solidlsp to see which options are available.
    No documentation on options means no options are available.
    """

    def __post_init__(self):
        os.makedirs(str(self.solidlsp_dir), exist_ok=True)
        os.makedirs(str(self.ls_resources_dir), exist_ok=True)

    @property
    def ls_resources_dir(self):
        return os.path.join(str(self.solidlsp_dir), "language_servers", "static")
