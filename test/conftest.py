import logging
import os
import platform
import re
import shutil as _sh
import subprocess
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
from .solidlsp.elixir import EXPERT_UNAVAILABLE
from .solidlsp.erlang import ERLANG_LS_UNAVAILABLE

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
    Language.PHP_PHPANTOM: Language.PHP,
    Language.PYTHON_JEDI: Language.PYTHON,
    Language.PYTHON_TY: Language.PYTHON,
    Language.RUBY_SOLARGRAPH: Language.RUBY,
    Language.PYTHON_TY: Language.PYTHON,
    Language.PYTHON_PYREFLY: Language.PYTHON,
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
    workspace_folders: list[str] | None = None,
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
        workspace_folders=workspace_folders or ["."],
        additional_workspace_folders=additional_workspace_folders or [],
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
        ),
    )


@contextmanager
def start_ls_context(
    language: Language,
    repo_path: str | None = None,
    ignored_paths: list[str] | None = None,
    trace_lsp_communication: bool = False,
    ls_specific_settings: dict[Language, dict[str, Any]] | None = None,
    workspace_folders: list[str] | None = None,
    additional_workspace_folders: list[str] | None = None,
    solidlsp_dir: Path | None = None,
) -> Iterator[SolidLanguageServer]:
    ls = _create_ls(
        language,
        repo_path,
        ignored_paths,
        trace_lsp_communication,
        ls_specific_settings,
        workspace_folders,
        additional_workspace_folders,
        solidlsp_dir,
    )
    log.info(f"Starting language server for {language} {repo_path}")
    with ls.start_server_context():
        yield ls


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
is_macos = platform.system() == "Darwin"


_LANGUAGE_PYTEST_MARKERS: dict[Language, list[MarkDecorator | Mark]] = {
    Language.ADA: [pytest.mark.ada],
    Language.CLOJURE: [pytest.mark.clojure],
    Language.CPP: [pytest.mark.cpp],
    Language.CPP_CCLS: [pytest.mark.cpp],
    Language.CUE: [pytest.mark.cue],
    Language.CSHARP: [pytest.mark.csharp],
    Language.FSHARP: [pytest.mark.fsharp],
    Language.GO: [pytest.mark.go],
    Language.HAXE: [pytest.mark.haxe],
    Language.JAVA: [pytest.mark.java],
    Language.KOTLIN: [pytest.mark.kotlin],
    Language.LEAN4: [pytest.mark.lean4],
    Language.LATEX: [pytest.mark.latex],
    Language.MSL: [pytest.mark.msl],
    Language.PHP: [pytest.mark.php],
    Language.PHP_PHPACTOR: [pytest.mark.php],
    Language.PHP_PHPANTOM: [pytest.mark.php],
    Language.POWERSHELL: [pytest.mark.powershell],
    Language.PYTHON: [pytest.mark.python],
    Language.PYTHON_JEDI: [pytest.mark.python],
    Language.PYTHON_TY: [pytest.mark.python],
    Language.PYTHON_PYREFLY: [pytest.mark.python],
    Language.RUST: [pytest.mark.rust],
    Language.TYPESCRIPT: [pytest.mark.typescript],
    Language.BSL: [pytest.mark.bsl],
    Language.SVELTE: [pytest.mark.svelte],
    Language.ANGULAR: [pytest.mark.angular],
    Language.HTML: [pytest.mark.html],
    Language.SCSS: [pytest.mark.scss],
}


def get_pytest_markers(language: Language) -> list[MarkDecorator | Mark]:
    """Pytest markers for a language.

    Returns the primary language marker plus the central enablement skip derived from
    ``language_tests_enabled()`` -- so per-language availability/reliability lives in exactly one
    place (``_determine_disabled_languages``) instead of being duplicated per marker or per test file.
    """
    return [
        *_LANGUAGE_PYTEST_MARKERS[language],
        pytest.mark.skipif(not language_tests_enabled(language), reason=f"{language.value} tests are disabled in this environment"),
    ]


def _is_perl_language_server_available() -> bool:
    """
    Whether Perl::LanguageServer is installed.

    Perl itself ships with most base systems, so checking for the ``perl`` binary is not enough;
    we verify that the ``Perl::LanguageServer`` module can be loaded -- which is exactly what the
    Perl language server launcher requires to start.
    """
    if _sh.which("perl") is None:
        return False
    try:
        return subprocess.run(["perl", "-MPerl::LanguageServer", "-e", "1"], capture_output=True, timeout=30, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _is_matlab_available() -> bool:
    """Whether a MATLAB installation can be located (env var or a known install path)."""
    if os.environ.get("MATLAB_PATH") is not None:
        return True
    return any(
        os.path.exists(p)
        for p in (
            "/Applications/MATLAB_R2024b.app",
            "/Applications/MATLAB_R2025b.app",
            "/Volumes/S1/Applications/MATLAB_R2024b.app",
            "/Volumes/S1/Applications/MATLAB_R2025b.app",
        )
    )


def _is_r_language_server_available() -> bool:
    """Whether R *and* its ``languageserver`` package are installed.

    The R binary alone is not enough -- the language server runs as ``R -e "languageserver::run()"``,
    which fails (RuntimeError) if the package is missing -- so check the package, not just ``which("R")``.
    """
    if _sh.which("R") is None:
        return False
    try:
        return (
            subprocess.run(
                ["R", "--vanilla", "-e", 'quit(status = as.integer(!requireNamespace("languageserver", quietly = TRUE)))'],
                capture_output=True,
                timeout=60,
                check=False,
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


def _is_ocaml_lsp_available() -> bool:
    """Whether opam *and* the ``ocaml-lsp-server`` (``ocamllsp``) are installed.

    opam alone is not enough -- the language server is launched via ``opam exec -- ocamllsp`` and
    raises if the package is missing -- so verify ocamllsp resolves in the active switch.
    """
    if _sh.which("opam") is None:
        return False
    try:
        return (
            subprocess.run(
                ["opam", "exec", "--", "ocamllsp", "--version"],
                capture_output=True,
                timeout=60,
                check=False,
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


def _determine_disabled_languages() -> list[Language]:
    """
    Determine which language tests are disabled in the current environment.

    Every language falls into exactly ONE of the categories below; a language that is not appended
    here is **category 4 (enabled everywhere)**, e.g. python, typescript, go, java, kotlin-locally.

    1. ALWAYS DISABLED -- flaky/broken; not worth running anywhere.
    2. DISABLED OFF-CI when a precondition (toolchain/LS) is missing, but EXPECTED ON CI -- guarded
       with ``and not is_ci`` so a missing tool *on CI* fails loudly (catches a CI setup regression)
       instead of silently skipping.
    3. DISABLED WHEREVER the precondition is missing, INCLUDING on CI -- the precondition may or may
       not be provided on CI (e.g. via the maximal container, see Dockerfile.maximal); if it isn't,
       the tests just skip gracefully rather than fail.
    4. ENABLED EVERYWHERE -- not listed in this function at all.
    5. DISABLED ONLY ON CI (resource/stability reasons) even though the precondition holds locally.
    """
    result: list[Language] = []

    # === 1. Always disabled (flaky / broken everywhere) ===
    result.append(Language.BSL)  # 1C:Enterprise; niche and the tests are slow and flaky
    result.append(Language.FSHARP)  # F# language server is currently unreliable

    # === 2. Disabled off-CI if the precondition is missing; expected to be present on CI ===
    if _sh.which("terraform") is None and not is_ci:
        result.append(Language.TERRAFORM)
    if _sh.which("regal") is None and not is_ci:
        result.append(Language.REGO)
    if _sh.which("elm") is None and not is_ci:
        result.append(Language.ELM)

    # === 3. Disabled wherever the precondition is missing (including on CI) ===
    # 3a. Platform precondition: these language servers have no native Windows support.
    if is_windows:
        result.append(Language.ANSIBLE)  # ansible-language-server has no native Windows support
    if not is_macos:
        result.append(Language.SWIFT)  # swiftly toolchain is only set up on the macOS native batch
    # 3b. Toolchain / language-server availability (the LS/compiler must be on PATH or installed).
    if _sh.which("clangd") is None:
        result.append(Language.CPP)
    if _sh.which("ccls") is None or is_windows:  # no recent ccls binary is available for Windows
        result.append(Language.CPP_CCLS)
    if _sh.which("php") is None:
        result.append(Language.PHP_PHPACTOR)
        result.append(Language.PHP_PHPANTOM)
    if not is_clojure_cli_available():
        result.append(Language.CLOJURE)
    if _sh.which("verible-verilog-ls") is None:
        result.append(Language.SYSTEMVERILOG)
    if not _is_matlab_available():
        result.append(Language.MATLAB)
    if ERLANG_LS_UNAVAILABLE:  # no Erlang-OTP / no rebar3 / Windows -- see test/solidlsp/erlang
        result.append(Language.ERLANG)
    if EXPERT_UNAVAILABLE:  # Elixir not installed -- see test/solidlsp/elixir
        result.append(Language.ELIXIR)
    if _sh.which("lean") is None:
        result.append(Language.LEAN4)
    if _sh.which("crystalline") is None:
        result.append(Language.CRYSTAL)
    if _sh.which("julia") is None:  # LanguageServer.jl is auto-installed by the LS when julia is present
        result.append(Language.JULIA)
    if _sh.which("nixd") is None:
        result.append(Language.NIX)
    if _sh.which("haskell-language-server-wrapper") is None:
        result.append(Language.HASKELL)
    if not _is_r_language_server_available():  # `which("R")` isn't enough -- needs the languageserver package
        result.append(Language.R)
    if not _is_ocaml_lsp_available():  # opam alone isn't enough -- needs the ocaml-lsp-server package
        result.append(Language.OCAML)
    if not _is_perl_language_server_available():  # perl ships with the OS; the LS module is the real signal
        result.append(Language.PERL)

    # === 4. Enabled everywhere: every language NOT listed in this function (python, go, java, ...) ===

    # === 5. Disabled only on CI (works locally; too unstable/costly on the CI runners) ===
    if is_ci:
        result.append(Language.KOTLIN)  # IntelliJ-based Kotlin LSP crashes on JVM restart under CI memory limits

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
