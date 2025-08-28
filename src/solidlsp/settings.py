"""
Defines settings for Solid-LSP
"""

import os
import pathlib
from dataclasses import dataclass


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

    def __post_init__(self):
        os.makedirs(str(self.solidlsp_dir), exist_ok=True)
        os.makedirs(str(self.ls_resources_dir), exist_ok=True)

    @property
    def ls_resources_dir(self):
        return os.path.join(str(self.solidlsp_dir), "language_servers", "static")
