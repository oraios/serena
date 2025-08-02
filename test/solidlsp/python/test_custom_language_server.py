import os
import shutil
import tempfile

import yaml

from solidlsp.ls_config import Language
from test.solidlsp.python.test_python_basic import TestLanguageServerBasics


class TestCustomLanguageServer(TestLanguageServerBasics):
    def setUp(self):
        super().setUp()
        self.repo_root = tempfile.mkdtemp()
        shutil.copytree(self.get_repo_root_for_language(Language.PYTHON), self.repo_root, dirs_exist_ok=True)

        # Create custom_lsp.yml
        custom_lsp_config = {
            "start_command": "pyright-langserver --stdio",
            "language_id": "python",
            "initialization_options": {},
        }
        os.makedirs(os.path.join(self.repo_root, ".serena"), exist_ok=True)
        with open(os.path.join(self.repo_root, ".serena", "custom_lsp.yml"), "w") as f:
            yaml.dump(custom_lsp_config, f)

        # Create project.yml
        project_config = {
            "project_name": "test_custom_lsp",
            "language": "custom",
        }
        with open(os.path.join(self.repo_root, ".serena", "project.yml"), "w") as f:
            yaml.dump(project_config, f)

    def tearDown(self):
        super().tearDown()
        shutil.rmtree(self.repo_root)

    def get_repo_root_for_language(self, language: Language) -> str:
        return self.repo_root
