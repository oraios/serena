"""
The Serena Model Context Protocol (MCP) Server
"""
# SPDX-License-Identifier: GPL-3.0-or-later

import os
from datetime import datetime
from pathlib import Path

from sensai.util import logging
from sensai.util.logging import datetime_tag

from serena.constants import (
    REPO_ROOT,
    RESOURCES_DIR,
    SERENA_MANAGED_DIR_NAME,
)

from ..util.class_decorators import singleton

log = logging.getLogger(__name__)


@singleton
class SerenaPaths:
    """
    Provides paths to various Serena-related directories and files.
    """

    def __init__(self) -> None:
        home_dir = os.getenv("SERENA_HOME")
        if home_dir is None or home_dir.strip() == "":
            home_dir = str(Path.home() / SERENA_MANAGED_DIR_NAME)
        else:
            home_dir = home_dir.strip()
        self.resources_dir: str = RESOURCES_DIR
        """
        the resources directory (within the `serena` package) 
        """
        self.serena_user_home_dir: str = home_dir
        """
        the path to the Serena home directory, where the user's configuration/data is stored.
        This is ~/.serena by default, but it can be overridden via the SERENA_HOME environment variable.
        """
        self.user_prompt_templates_dir: str = os.path.join(self.serena_user_home_dir, "prompt_templates")
        """
        directory containing prompt templates defined by the user.
        Prompts defined by the user take precedence over Serena's built-in prompt templates.
        """
        self.user_contexts_dir: str = os.path.join(self.serena_user_home_dir, "contexts")
        """
        directory containing contexts defined by the user. 
        If a name of a context matches a name of a context in SERENAS_OWN_CONTEXT_YAMLS_DIR, 
        the user context will override the default context definition.
        """
        self.user_modes_dir: str = os.path.join(self.serena_user_home_dir, "modes")
        """
        directory containing modes defined by the user.
        If a name of a mode matches a name of a mode in SERENAS_OWN_MODES_YAML_DIR,
        the user mode will override the default mode definition.
        """
        self.news_legacy_last_read_id_file: str = os.path.join(self.serena_user_home_dir, "last_read_news_snippet_id.txt")
        """
        file containing the ID of the last read news snippet
        """
        self.news_read_items_file: str = os.path.join(self.serena_user_home_dir, "news_read.pkl")
        """
        file containing the ID of the last read news snippet
        """
        self.news_etag_file: str = os.path.join(self.serena_user_home_dir, "news_etag.txt")
        """
        file containing the ETag of the last fetched remote news JSON
        """
        self.news_file: str = os.path.join(self.serena_user_home_dir, "news.json")
        """
        local cache of the remote news JSON file
        """
        self.news_dir: str = os.path.join(REPO_ROOT, "news")
        """
        repository news directory containing the source HTML snippets and generated news.json
        """
        global_memories_path = Path(os.path.join(self.serena_user_home_dir, "memories", "global"))
        global_memories_path.mkdir(parents=True, exist_ok=True)
        self.global_memories_path = global_memories_path
        """
        directory where global memories are stored, i.e. memories that are available across all projects
        """
        self.last_returned_log_file_path: str | None = None
        """
        the path to the last log file returned by `get_next_log_file_path`. If this is not None, the logs
        are currently being written to this file
        """

    def get_next_log_file_path(self, prefix: str) -> str:
        """
        :param prefix: the filename prefix indicating the type of the log file
        :return: the full path to the log file to use
        """
        log_dir = os.path.join(self.serena_user_home_dir, "logs", datetime.now().strftime("%Y-%m-%d"))
        os.makedirs(log_dir, exist_ok=True)
        self.last_returned_log_file_path = os.path.join(log_dir, prefix + "_" + datetime_tag() + f"_{os.getpid()}" + ".txt")
        return self.last_returned_log_file_path

    def get_resource_path(self, *path_elems: str) -> Path:
        return Path(os.path.join(self.resources_dir, *path_elems))

    # TODO: Paths from constants.py should be moved here
