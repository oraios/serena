import logging
from pathlib import Path
from typing import cast

import pytest
from sensai.util.logging import configure

from multilspy.language_server import SyncLanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from serena.constants import USE_SOLID_LSP
from serena.util.file_system import GitignoreParser
from solidlsp.ls import SolidLanguageServer

configure(level=logging.DEBUG)


@pytest.fixture(scope="session")
def resources_dir() -> Path:
    """Path to the test resources directory."""
    current_dir = Path(__file__).parent
    return current_dir / "resources"


class LanguageParamRequest:
    param: Language


def get_repo_path(language: Language) -> Path:
    return Path(__file__).parent / "resources" / "repos" / language / "test_repo"


def create_ls(
    language: Language,
    repo_path: str | None = None,
    ignored_paths: list[str] | None = None,
    trace_lsp_communication: bool = False,
    log_level: int = logging.INFO,
) -> SyncLanguageServer:
    ignored_paths = ignored_paths or []
    if repo_path is None:
        repo_path = str(get_repo_path(language))
    gitignore_parser = GitignoreParser(str(repo_path))
    for spec in gitignore_parser.get_ignore_specs():
        ignored_paths.extend(spec.patterns)
    config = MultilspyConfig(code_language=language, ignored_paths=ignored_paths, trace_lsp_communication=trace_lsp_communication)
    logger = MultilspyLogger(log_level=log_level)

    if USE_SOLID_LSP:
        ls = SolidLanguageServer.create(config, logger, repo_path)
        return cast(SyncLanguageServer, ls)  # TODO: Fix type
    else:
        return SyncLanguageServer.create(config, logger, repo_path)


def create_default_ls(language: Language) -> SyncLanguageServer:
    repo_path = str(get_repo_path(language))
    return create_ls(language, repo_path)


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


@pytest.fixture(scope="session")
def language_server(request: LanguageParamRequest):
    """Create a SyncLanguageServer instance configured for the specified language.

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
    server = create_default_ls(language)
    server.start()
    try:
        yield server
    finally:
        server.stop()
