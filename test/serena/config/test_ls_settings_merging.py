import shutil
import tempfile
from pathlib import Path

import pytest

from serena.config.serena_config import ProjectConfig, SerenaConfig
from serena.project import Project
from solidlsp.ls_config import Language


class TestLSSettingsOverride:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.tmp_dir)
        (self.project_root / ".serena").mkdir()

        # Create a dummy python file for indexing
        (self.project_root / "test.py").write_text("print('hello')")

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_settings_override(self):
        # 1. Global config with some settings
        global_config = SerenaConfig()
        global_config.ls_specific_settings = {
            "python": {"global_key": "global_val", "override_key": "global_val"},
            "cpp": {"cpp_global": "val"},
        }

        # 2. Project config with overrides
        # We test that python settings are COMPLETELY overridden, not merged
        project_yaml = """
project_name: test_project
languages: [python]
ls_specific_settings:
  python:
    override_key: project_val
    project_key: project_val
"""
        yaml_path = self.project_root / ".serena" / "project.yml"
        yaml_path.write_text(project_yaml)

        project_config = ProjectConfig.load(self.project_root)
        project = Project(project_root=str(self.project_root), project_config=project_config, serena_config=global_config)

        try:
            # 3. Check merged settings
            merged_settings = project.get_ls_specific_settings()

            # Check Python settings - should NOT contain "global_key" because of full override
            python_settings = merged_settings.get(Language.PYTHON, {})
            assert "global_key" not in python_settings
            assert python_settings.get("override_key") == "project_val"
            assert python_settings.get("project_key") == "project_val"

            # Check CPP settings (should persist from global)
            cpp_settings = merged_settings.get(Language.CPP, {})
            assert cpp_settings.get("cpp_global") == "val"
        finally:
            project.shutdown()

    def test_ls_path_config_case_insensitivity(self):
        # Verify that 'CPP' or 'cpp' in YAML both map to Language.CPP
        project_yaml = """
project_name: test_project
languages: [cpp]
ls_specific_settings:
  CPP:
    ls_path: /custom/path
"""
        yaml_path = self.project_root / ".serena" / "project.yml"
        yaml_path.write_text(project_yaml)

        project_config = ProjectConfig.load(self.project_root)
        project = Project(project_root=str(self.project_root), project_config=project_config, serena_config=SerenaConfig())
        try:
            merged_settings = project.get_ls_specific_settings()

            assert Language.CPP in merged_settings
            assert merged_settings[Language.CPP]["ls_path"] == "/custom/path"
        finally:
            project.shutdown()

    def test_fail_fast_on_invalid_language(self):
        global_config = SerenaConfig()
        project_yaml = """
project_name: test_project
languages: [python]
ls_specific_settings:
  invalid_lang_tag:
    key: val
"""
        yaml_path = self.project_root / ".serena" / "project.yml"
        yaml_path.write_text(project_yaml)

        project_config = ProjectConfig.load(self.project_root)
        project = Project(project_root=str(self.project_root), project_config=project_config, serena_config=global_config)

        try:
            with pytest.raises(ValueError, match="Invalid language 'invalid_lang_tag'"):
                project.get_ls_specific_settings()
        finally:
            project.shutdown()
