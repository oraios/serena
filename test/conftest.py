import logging
import os
import platform
import re
import shutil as _sh
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from _pytest.mark import Mark, MarkDecorator
from sensai.util.logging import configure

from serena.config.serena_config import SerenaConfig, SerenaPaths
from serena.constants import SERENA_MANAGED_DIR_NAME
from serena.project import Project
from serena.util.file_system import GitignoreParser
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


_LANGUAGE_REPO_ALIASES: dict[Language, Language] = {
    Language.CPP_CCLS: Language.CPP,
    Language.PHP_PHPACTOR: Language.PHP,
    Language.PYTHON_JEDI: Language.PYTHON,
    Language.PYTHON_TY: Language.PYTHON,
    Language.RUBY_SOLARGRAPH: Language.RUBY,
    Language.PYTHON_TY: Language.PYTHON,
}

PYTHON_LANGUAGE_BACKENDS = [Language.PYTHON, Language.PYTHON_TY]


def get_repo_path(language: Language) -> Path:
    repo_language = _LANGUAGE_REPO_ALIASES.get(language, language)
    return Path(__file__).parent / "resources" / "repos" / repo_language / "test_repo"


def _create_ls(
    language: Language,
    repo_path: str | None = None,
    ignored_paths: list[str] | None = None,
    trace_lsp_communication: bool = False,
    ls_specific_settings: dict[Language, dict[str, Any]] | None = None,
    additional_workspace_folders: list[str] | None = None,
    solidlsp_dir: Path | None = None,
) -> SolidLanguageServer:
    ignored_paths = ignored_paths or []
    if repo_path is None:
        repo_path = str(get_repo_path(language))
    gitignore_parser = GitignoreParser(str(repo_path))
    for spec in gitignore_parser.get_ignore_specs():
        ignored_paths.extend(spec.patterns)
    config = LanguageServerConfig(
        code_language=language,
        ignored_paths=ignored_paths,
        trace_lsp_communication=trace_lsp_communication,
    )
    effective_solidlsp_dir = solidlsp_dir if solidlsp_dir is not None else SerenaPaths().serena_user_home_dir
    project_data_path = os.path.join(repo_path, SERENA_MANAGED_DIR_NAME)
    return SolidLanguageServer.create(
        config,
        repo_path,
        solidlsp_settings=SolidLSPSettings(
            solidlsp_dir=effective_solidlsp_dir,
            project_data_path=project_data_path,
            ls_specific_settings=ls_specific_settings or {},
            additional_workspace_folders=additional_workspace_folders or [],
        ),
    )


@contextmanager
def start_ls_context(
    language: Language,
    repo_path: str | None = None,
    ignored_paths: list[str] | None = None,
    trace_lsp_communication: bool = False,
    ls_specific_settings: dict[Language, dict[str, Any]] | None = None,
    additional_workspace_folders: list[str] | None = None,
    solidlsp_dir: Path | None = None,
) -> Iterator[SolidLanguageServer]:
    ls = _create_ls(
        language, repo_path, ignored_paths, trace_lsp_communication, ls_specific_settings, additional_workspace_folders, solidlsp_dir
    )
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


def create_default_serena_config():
    return SerenaConfig(gui_log_window=False, web_dashboard=False)


def _create_default_project(language: Language, repo_root_override: str | None = None) -> Project:
    repo_path = str(get_repo_path(language)) if repo_root_override is None else repo_root_override
    return Project.load(repo_path, serena_config=create_default_serena_config())


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


@contextmanager
def project_context(language: Language, repo_root_override: str | None = None) -> Iterator[Project]:
    """Context manager that creates a Project for the specified language and ensures proper cleanup."""
    project = _create_default_project(language, repo_root_override)
    try:
        yield project
    finally:
        project.shutdown(timeout=5)


@pytest.fixture(scope="module")
def project(request: LanguageParamRequest, repo_root_override: str | None = None) -> Iterator[Project]:
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
    with project_context(language, repo_root_override) as project:
        yield project


@contextmanager
def project_with_ls_context(language: Language, repo_root_override: str | None = None) -> Iterator[Project]:
    """Context manager that creates a Project with an active language server for the specified language."""
    with project_context(language, repo_root_override) as project:
        project.create_language_server_manager()
        yield project


@pytest.fixture(scope="module")
def project_with_ls(request: LanguageParamRequest) -> Iterator[Project]:
    if not hasattr(request, "param"):
        raise ValueError("Language parameter must be provided via pytest.mark.parametrize")
    language = request.param
    with project_with_ls_context(language) as project:
        yield project


is_ci = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"
"""
Flag indicating whether the tests are running in the GitHub CI environment.
"""

is_windows = platform.system() == "Windows"


_LANGUAGE_PYTEST_MARKERS: dict[Language, list[MarkDecorator | Mark]] = {
    Language.CLOJURE: [
        pytest.mark.clojure,
        pytest.mark.skipif(not is_clojure_cli_available(), reason="clojure CLI is not installed"),
    ],
    Language.CPP: [pytest.mark.cpp],
    Language.CPP_CCLS: [pytest.mark.cpp],
    Language.CSHARP: [pytest.mark.csharp],
    Language.FSHARP: [pytest.mark.fsharp],
    Language.GO: [pytest.mark.go],
    Language.HAXE: [pytest.mark.haxe],
    Language.JAVA: [pytest.mark.java],
    Language.KOTLIN: [pytest.mark.kotlin, pytest.mark.skipif(is_ci, reason="Kotlin LSP JVM crashes on restart in CI")],
    Language.LEAN4: [pytest.mark.lean4, pytest.mark.skipif(_sh.which("lean") is None, reason="Lean is not installed")],
    Language.MSL: [pytest.mark.msl],
    Language.PHP: [pytest.mark.php],
    Language.PHP_PHPACTOR: [pytest.mark.php],
    Language.POWERSHELL: [pytest.mark.powershell],
    Language.PYTHON: [pytest.mark.python],
    Language.PYTHON_JEDI: [pytest.mark.python],
    Language.PYTHON_TY: [pytest.mark.python],
    Language.RUST: [pytest.mark.rust],
    Language.TYPESCRIPT: [pytest.mark.typescript],
    Language.ANGULAR: [pytest.mark.angular],
    Language.HTML: [pytest.mark.html],
    Language.SCSS: [pytest.mark.scss],
}


def get_pytest_markers(language: Language) -> list[MarkDecorator | Mark]:
    """Pytest markers for a language.

    The returned list contains the primary language marker and any
    environment-dependent skip markers shared across the test suite.
    """
    return _LANGUAGE_PYTEST_MARKERS[language]


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

    # Disable CPP_CCLS tests if ccls is not available
    ccls_tests_enabled = _sh.which("ccls") is not None
    # Skip ccls tests on Windows since no recent binary is available and version
    # 0.20220729 from chocolatey crashes when parsing the test files.
    ccls_tests_enabled = ccls_tests_enabled and not is_windows
    if not ccls_tests_enabled:
        result.append(Language.CPP_CCLS)

    # Disable CPP (clangd) tests if clangd is not available
    clangd_tests_enabled = _sh.which("clangd") is not None
    if not clangd_tests_enabled:
        result.append(Language.CPP)

    # Disable PHP_PHPACTOR tests if php is not available
    php_tests_enabled = _sh.which("php") is not None
    if not php_tests_enabled:
        result.append(Language.PHP_PHPACTOR)

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


def language_supports_implementation(language: Language) -> bool:
    return language.supports_implementation_request()


def languages_supporting_implementation(*languages: Language) -> list[Language]:
    return [language for language in languages if language_supports_implementation(language)]


_VERIFIED_IMPLEMENTATION_LANGUAGES = {
    Language.ANGULAR,
    Language.CSHARP,
    Language.GO,
    Language.JAVA,
    Language.RUST,
    Language.TYPESCRIPT,
}


def language_has_verified_implementation_support(language: Language) -> bool:
    """
    True only for languages where the server advertises implementation support and
    the repo fixtures contain a verified working go-to-implementation scenario.
    """
    return language in _VERIFIED_IMPLEMENTATION_LANGUAGES and language_supports_implementation(language)


def find_identifier_position(file_path: Path, identifier: str) -> tuple[int, int] | None:
    pattern = re.compile(r"\b" + re.escape(identifier) + r"\b")
    with file_path.open(encoding="utf-8") as f:
        for line_idx, line in enumerate(f):
            match = pattern.search(line)
            if match:
                return line_idx, match.start()
    return None


def find_identifier_pos(
    file_path: Path,
    identifier: str,
    occurrence_index: int = 0,
    column_offset: int = 0,
) -> tuple[int, int] | None:
    if occurrence_index < 0:
        raise ValueError("occurrence_index must be non-negative")
    if column_offset < 0:
        raise ValueError("column_offset must be non-negative")

    pattern = re.compile(r"\b" + re.escape(identifier) + r"\b")
    current_index = 0
    with file_path.open(encoding="utf-8") as f:
        for line_idx, line in enumerate(f):
            for match in pattern.finditer(line):
                if current_index == occurrence_index:
                    return line_idx, match.start() + column_offset
                current_index += 1
    return None
