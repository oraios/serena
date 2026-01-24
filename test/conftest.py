import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from sensai.util.logging import configure

from murena.config.murena_config import MurenaPaths
from murena.constants import MURENA_MANAGED_DIR_NAME
from murena.project import Project
from murena.util.file_system import GitignoreParser
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.settings import SolidLSPSettings

from .solidlsp.clojure import is_clojure_cli_available

configure(level=logging.INFO)

log = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def resources_dir() -> Path:
    """Path to the test resources directory."""
    current_dir = Path(__file__).parent
    return current_dir / "resources"


class LanguageParamRequest:
    param: Language


def get_repo_path(language: Language) -> Path:
    return Path(__file__).parent / "resources" / "repos" / language / "test_repo"


def _create_ls(
    language: Language,
    repo_path: str | None = None,
    ignored_paths: list[str] | None = None,
    trace_lsp_communication: bool = False,
    ls_specific_settings: dict[Language, dict[str, Any]] | None = None,
    solidlsp_dir: Path | None = None,
) -> SolidLanguageServer:
    ignored_paths = ignored_paths or []
    if repo_path is None:
        repo_path = str(get_repo_path(language))
    gitignore_parser = GitignoreParser(str(repo_path))
    for spec in gitignore_parser.get_ignore_specs():
        ignored_paths.extend(spec.patterns)
    config = LanguageServerConfig(code_language=language, ignored_paths=ignored_paths, trace_lsp_communication=trace_lsp_communication)
    effective_solidlsp_dir = solidlsp_dir if solidlsp_dir is not None else MurenaPaths().serena_user_home_dir
    return SolidLanguageServer.create(
        config,
        repo_path,
        solidlsp_settings=SolidLSPSettings(
            solidlsp_dir=effective_solidlsp_dir,
            project_data_relative_path=MURENA_MANAGED_DIR_NAME,
            ls_specific_settings=ls_specific_settings or {},
        ),
    )


@contextmanager
def start_ls_context(
    language: Language,
    repo_path: str | None = None,
    ignored_paths: list[str] | None = None,
    trace_lsp_communication: bool = False,
    ls_specific_settings: dict[Language, dict[str, Any]] | None = None,
    solidlsp_dir: Path | None = None,
) -> Iterator[SolidLanguageServer]:
    ls = _create_ls(language, repo_path, ignored_paths, trace_lsp_communication, ls_specific_settings, solidlsp_dir)
    log.info(f"Starting language server for {language} {repo_path}")
    ls.start()
    try:
        log.info(f"Language server started for {language} {repo_path}")
        yield ls
    finally:
        log.info(f"Stopping language server for {language} {repo_path}")
        try:
            ls.stop(shutdown_timeout=5)
        except Exception as e:
            log.warning(f"Warning: Error stopping language server: {e}")
            # try to force cleanup
            if hasattr(ls, "server") and hasattr(ls.server, "process"):
                try:
                    ls.server.process.terminate()
                except:
                    pass


@contextmanager
def start_default_ls_context(language: Language) -> Iterator[SolidLanguageServer]:
    with start_ls_context(language) as ls:
        yield ls


def _create_default_project(language: Language) -> Project:
    repo_path = str(get_repo_path(language))
    return Project.load(repo_path)


@pytest.fixture(scope="session")
def repo_path(request: LanguageParamRequest) -> Path:
    """Get the repository path for a specific language.

    This fixture requires a language parameter via pytest.mark.parametrize:

    Example:
    ```
    @pytest.mark.parametrize("repo_path", [Language.PYTHON], indirect=True)
    def test_python_repo(repo_path):
        assert (repo_path / "src").exists()
    ```

    """
    if not hasattr(request, "param"):
        raise ValueError("Language parameter must be provided via pytest.mark.parametrize")

    language = request.param
    return get_repo_path(language)


# Note: using module scope here to avoid restarting LS for each test function but still terminate between test modules
@pytest.fixture(scope="module")
def language_server(request: LanguageParamRequest):
    """Create a language server instance configured for the specified language.

    This fixture requires a language parameter via pytest.mark.parametrize:

    Example:
    ```
    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_python_server(language_server: SyncLanguageServer) -> None:
        # Use the Python language server
        pass
    ```

    You can also test multiple languages in a single test:
    ```
    @pytest.mark.parametrize("language_server", [Language.PYTHON, Language.TYPESCRIPT], indirect=True)
    def test_multiple_languages(language_server: SyncLanguageServer) -> None:
        # This test will run once for each language
        pass
    ```

    """
    if not hasattr(request, "param"):
        raise ValueError("Language parameter must be provided via pytest.mark.parametrize")

    language = request.param
    with start_default_ls_context(language) as ls:
        yield ls


@pytest.fixture(scope="module")
def project(request: LanguageParamRequest):
    """Create a Project for the specified language.

    This fixture requires a language parameter via pytest.mark.parametrize:

    Example:
    ```
    @pytest.mark.parametrize("project", [Language.PYTHON], indirect=True)
    def test_python_project(project: Project) -> None:
        # Use the Python project to test something
        pass
    ```

    You can also test multiple languages in a single test:
    ```
    @pytest.mark.parametrize("project", [Language.PYTHON, Language.TYPESCRIPT], indirect=True)
    def test_multiple_languages(project: SyncLanguageServer) -> None:
        # This test will run once for each language
        pass
    ```

    """
    if not hasattr(request, "param"):
        raise ValueError("Language parameter must be provided via pytest.mark.parametrize")

    language = request.param
    project = _create_default_project(language)
    yield project
    project.shutdown(timeout=5)


is_ci = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"
"""
Flag indicating whether the tests are running in the GitHub CI environment.
"""


def _determine_disabled_languages() -> list[Language]:
    """
    Determine which language tests should be disabled (based on the environment)

    :return: the list of disabled languages
    """
    result: list[Language] = []

    java_tests_enabled = True
    if not java_tests_enabled:
        result.append(Language.JAVA)

    clojure_tests_enabled = is_clojure_cli_available()
    if not clojure_tests_enabled:
        result.append(Language.CLOJURE)

    al_tests_enabled = True
    if not al_tests_enabled:
        result.append(Language.AL)

    return result


_disabled_languages = _determine_disabled_languages()


def language_tests_enabled(language: Language) -> bool:
    """
    Check if tests for the given language are enabled in the current environment.

    :param language: the language to check
    :return: True if tests for the language are enabled, False otherwise
    """
    return language not in _disabled_languages
