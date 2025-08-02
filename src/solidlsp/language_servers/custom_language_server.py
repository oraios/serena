import os

import yaml

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo


class CustomLanguageServer(SolidLanguageServer):
    def __init__(
        self,
        config: LanguageServerConfig,
        logger: LanguageServerLogger,
        repository_root_path: str,
    ):
        custom_lsp_config_path = os.path.join(repository_root_path, ".serena", "custom_lsp.yml")
        if not os.path.exists(custom_lsp_config_path):
            raise FileNotFoundError("Custom language server requires a .serena/custom_lsp.yml file")

        with open(custom_lsp_config_path) as f:
            custom_lsp_config = yaml.safe_load(f)

        start_command = custom_lsp_config.get("start_command")
        if not start_command:
            raise ValueError("start_command not found in .serena/custom_lsp.yml")

        self.initialization_options = custom_lsp_config.get("initialization_options", {})

        language_id = custom_lsp_config.get("language_id", "custom")

        process_launch_info = ProcessLaunchInfo(
            cmd=start_command.split(),
            cwd=repository_root_path,
        )
        super().__init__(config, logger, repository_root_path, process_launch_info, language_id)

    def _start_server(self):
        self.server.start(
            initialization_options=self.initialization_options,
            root_uri=f"file://{self.repository_root_path}",
        )
