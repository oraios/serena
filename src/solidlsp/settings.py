"""
Defines settings for Solid-LSP
"""

import logging
import os
import pathlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sensai.util.string import ToStringMixin

if TYPE_CHECKING:
    from murena.config.murena_config import PerformanceConfig
    from solidlsp.ls_config import Language

log = logging.getLogger(__name__)


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
    ls_specific_settings: dict["Language", dict[str, Any]] = field(default_factory=dict)
    """
    Advanced configuration option allowing to configure language server implementation specific options.
    Have a look at the docstring of the constructors of the corresponding LS implementations within solidlsp to see which options are available.
    No documentation on options means no options are available.
    """
    performance: "PerformanceConfig | None" = None
    """
    Performance optimization settings. If None, a default PerformanceConfig will be created.
    """

    def __post_init__(self) -> None:
        os.makedirs(str(self.solidlsp_dir), exist_ok=True)
        os.makedirs(str(self.ls_resources_dir), exist_ok=True)

        # Create default PerformanceConfig if not provided
        if self.performance is None:
            from murena.config.murena_config import PerformanceConfig

            self.performance = PerformanceConfig()

    @property
    def ls_resources_dir(self) -> str:
        return os.path.join(str(self.solidlsp_dir), "language_servers", "static")

    class CustomLSSettings(ToStringMixin):
        def __init__(self, settings: dict[str, Any] | None) -> None:
            self.settings = settings or {}

        def get(self, key: str, default_value: Any = None) -> Any:
            """
            Returns the custom setting for the given key or the default value if not set.
            If a custom value is set for the given key, the retrieval is logged.

            :param key: the key
            :param default_value: the default value to use if no custom value is set
            :return: the value
            """
            if key in self.settings:
                value = self.settings[key]
                log.info("Using custom LS setting %s for key '%s'", value, key)
            else:
                value = default_value
            return value

    def get_ls_specific_settings(self, language: "Language") -> CustomLSSettings:
        """
        Get the language server specific settings for the given language.

        :param language: The programming language.
        :return: A dictionary of settings for the language server.
        """
        return self.CustomLSSettings(self.ls_specific_settings.get(language))
