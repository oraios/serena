"""
Defines settings for Solid-LSP
"""

import os
import pathlib
from dataclasses import dataclass


@dataclass
class SolidLSPSettings:
    solidlsp_dir: str = str(pathlib.Path.home() / ".solidlsp")

    # Lean 4 specific settings
    lean4_dependency_timeout: float = 1800.0  # 30 minutes
    lean4_max_restart_attempts: int = 3
    lean4_restart_cooldown_seconds: float = 5.0
    lean4_health_check_timeout: float = 2.0

    def __post_init__(self):
        os.makedirs(str(self.solidlsp_dir), exist_ok=True)
        os.makedirs(str(self.ls_resources_dir), exist_ok=True)

    @property
    def ls_resources_dir(self):
        return os.path.join(str(self.solidlsp_dir), "language_servers", "static")
