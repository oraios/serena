"""
Defines settings for Solid-LSP
"""

import os
import pathlib
from dataclasses import dataclass


@dataclass
class SolidLSPSettings:
    solidlsp_dir: str = str(pathlib.Path.home() / ".solidlsp")

    def __post_init__(self):
        os.makedirs(str(self.solidlsp_dir), exist_ok=True)
        os.makedirs(str(self.ls_resources_dir), exist_ok=True)

    @property
    def ls_resources_dir(self):
        return os.path.join(str(self.solidlsp_dir), "language_servers", "static")
