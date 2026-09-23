"""
Defines settings for Solid-LSP
"""
# SPDX-License-Identifier: MIT

import logging
import os
import pathlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Union

from sensai.util.helper import count_not_none
from sensai.util.string import ToStringMixin

if TYPE_CHECKING:
    from solidlsp.ls_config import LanguageServerId, LanguageServerIdLike

log = logging.getLogger(__name__)


SOLIDLSP_RESOURCES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources")


@dataclass
class SolidLSPSettings:
    """
    Configures SolidLSP-specific data storage as well as global settings.

    Note: Server instance-specific settings belong in LanguageServerConfig, not here.
    """

    solidlsp_dir: str = str(pathlib.Path.home() / ".solidlsp")
    """
    Path to the directory in which to store global Solid-LSP data (which is not project-specific)
    """
    project_data_path: str = ""
    """
    Absolute path to a directory where Solid-LSP can store project-specific data, e.g. cache files.
    For instance, if this is "/home/user/myproject/.solidlsp",
    then Solid-LSP will store project-specific data (e.g. caches) in that directory.
    """
    ls_specific_settings: dict[Union[str, "LanguageServerId"], dict[str, Any]] = field(default_factory=dict)
    """
    Advanced configuration option allowing to configure language server implementation specific options.
    Maps language server identifiers or their string keys to a dictionary of options for that language server.
    See constructors of the corresponding LS implementations within SolidLSP to see which options are available.
    Some options are centrally supported. See Serena's documentation for details.
    """

    def __post_init__(self) -> None:
        os.makedirs(str(self.solidlsp_dir), exist_ok=True)
        os.makedirs(str(self.ls_resources_dir), exist_ok=True)

    @property
    def ls_resources_dir(self) -> str:
        return os.path.join(str(self.solidlsp_dir), "language_servers", "static")

    class CustomLSSettings(ToStringMixin):
        """
        Represents custom (user-specified) settings for a specific language server.
        """

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

    def get_ls_specific_settings(self, ls_id: "LanguageServerIdLike") -> CustomLSSettings:
        """
        Gets the custom settings for the given language server

        :param ls_id: the language server identifier for which to retrieve settings
        :return: a dictionary of settings for the language server
        """
        from solidlsp.ls_config import LanguageServerId

        settings_dict = self.ls_specific_settings.get(ls_id.get_key())
        if isinstance(ls_id, LanguageServerId):
            settings_dict2 = self.ls_specific_settings.get(ls_id)
            if count_not_none(settings_dict, settings_dict2) > 1:
                raise ValueError(f"Duplicate LS-specific settings for {ls_id.get_key()}: Found keys {ls_id.get_key()} and {ls_id}")
            settings_dict = settings_dict or settings_dict2
        return self.CustomLSSettings(settings_dict)
