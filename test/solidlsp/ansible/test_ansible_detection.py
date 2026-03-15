"""
Tests for Ansible project autodetection and path-based routing.

Tests cover:
- ``_is_ansible_path()`` static method (unit tests, no LS required)
- ``AnsibleProjectDetector.detect()`` (filesystem-based, no LS required)
- ``is_ignored_path()`` override (integration, requires running LS)
"""

from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.language_servers.ansible_language_server import AnsibleLanguageServer
from solidlsp.ls_config import AnsibleProjectDetector, Language

REPOS_DIR = Path(__file__).parent.parent.parent / "resources" / "repos"


class TestAnsiblePathDetection:
    """Unit tests for ansible path classification via ``_is_ansible_path``."""

    @pytest.mark.parametrize(
        "path",
        [
            "roles/common/tasks/main.yml",
            "inventory/hosts.yml",
            "group_vars/all.yml",
            "host_vars/webserver.yml",
            "playbook.yml",
            "playbook-deploy.yaml",
            "site.yml",
            "site.yaml",
            "requirements.yml",
            "requirements.yaml",
        ],
    )
    def test_ansible_path_root_level(self, path: str) -> None:
        """Ansible-specific paths at project root are recognized."""
        assert AnsibleLanguageServer._is_ansible_path(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "deploy/ansible/roles/nginx/tasks/main.yml",
            "deploy/ansible/inventory/production.yml",
            "deploy/ansible/group_vars/all.yml",
            "infra/provisioning/host_vars/db.yml",
            "ops/playbooks/deploy.yml",
            "deep/nested/path/roles/app/handlers/main.yml",
            "deploy/ansible/defaults/main.yml",
            "project/meta/main.yml",
        ],
    )
    def test_ansible_path_nested(self, path: str) -> None:
        """Ansible-specific paths nested in subdirectories are recognized."""
        assert AnsibleLanguageServer._is_ansible_path(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "docker-compose.yml",
            "config/database.yml",
            ".github/workflows/ci.yml",
            "k8s/deployment.yaml",
            "helm/values.yml",
            "README.yml",
            "src/config.yaml",
        ],
    )
    def test_non_ansible_path(self, path: str) -> None:
        """Non-ansible YAML files are correctly rejected."""
        assert AnsibleLanguageServer._is_ansible_path(path) is False


class TestAnsibleProjectDetector:
    """Tests for automatic ansible project detection."""

    def test_detect_root_ansible_project(self) -> None:
        """Detect ansible project with markers at root (inventory/ dir)."""
        detector = AnsibleProjectDetector()
        assert detector.detect(str(REPOS_DIR / "ansible" / "test_repo")) is True

    def test_detect_nested_ansible_project(self) -> None:
        """Detect ansible project with markers in nested dirs (roles/ at depth 3)."""
        detector = AnsibleProjectDetector()
        assert detector.detect(str(REPOS_DIR / "ansible" / "test_repo_nested")) is True

    def test_reject_plain_yaml_project(self) -> None:
        """Plain YAML project without ansible markers is not detected."""
        detector = AnsibleProjectDetector()
        assert detector.detect(str(REPOS_DIR / "yaml" / "test_repo")) is False

    def test_reject_non_existent_path(self) -> None:
        """Non-existent path returns False."""
        detector = AnsibleProjectDetector()
        assert detector.detect("/tmp/nonexistent_ansible_test_12345") is False


@pytest.mark.ansible
class TestAnsibleIsIgnoredPath:
    """Integration tests: ansible LS accepts ansible files, rejects non-ansible ones."""

    @pytest.mark.parametrize("language_server", [Language.ANSIBLE], indirect=True)
    @pytest.mark.parametrize(
        "path,expected_ignored",
        [
            # ansible paths → accepted
            ("roles/common/tasks/main.yml", False),
            ("playbook.yml", False),
            ("inventory/hosts.yml", False),
            # non-ansible yml → ignored
            ("docker-compose.yml", True),
            ("config/settings.yml", True),
        ],
    )
    def test_is_ignored_path(self, language_server: SolidLanguageServer, path: str, expected_ignored: bool) -> None:
        assert language_server.is_ignored_path(path) is expected_ignored
