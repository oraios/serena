"""
Provides Scala specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Scala.
"""

import logging
import os
import shutil
import subprocess
from enum import Enum

from overrides import override

from solidlsp.initialize_params import DefaultInitializeParamsBuilder, InitializeParamsBuilder
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_utils import PlatformUtils
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings
from solidlsp.util.subprocess_util import subprocess_run

if not PlatformUtils.get_platform_id().value.startswith("win"):
    pass


log = logging.getLogger(__name__)

# Default configuration constants
DEFAULT_METALS_VERSION = "1.6.4"
DEFAULT_CLIENT_NAME = "Serena"
DEFAULT_ON_STALE_LOCK = "auto-clean"
DEFAULT_LOG_MULTI_INSTANCE_NOTICE = True
DEFAULT_PROJECT_ROOT_SCAN_DEPTH = 3

# Files whose presence marks a directory as the root of a build Metals can import, following the
# per-build-tool probes in Metals' `BuildTools` (scala/meta/internal/builds/BuildTools.scala) and
# `BazelBuildTool.workspaceSupportsBsp`. Deliberately partial: the probes that need to read a file's
# contents (scala-cli's BSP scope) are left out, since missing a build root only returns us to the
# previous behaviour, whereas a false positive would hide the real builds beneath it.
BUILD_ROOT_MARKER_FILES = (
    "MODULE.bazel",
    "WORKSPACE",
    "build.gradle",
    "build.gradle.kts",
    "build.mill",
    "build.mill.scala",
    "build.mill.yaml",
    "build.sbt",
    "build.sc",
    "deder.pkl",
    "mill",
    "mill.bat",
    "pom.xml",
    "project.scala",
    "settings.gradle",
    "settings.gradle.kts",
)

# Directories which, when they hold a JSON file, mark an already-configured Metals project
# (`BuildTools.hasJsonFile`). An empty one is a leftover, not a build.
BUILD_ROOT_MARKER_JSON_DIRS = (".bloop", ".bsp")

# Directories not worth descending into when scanning for build roots: build output, dependencies,
# and the directories belonging to a build we would have recognised at their parent. They are still
# probed themselves — only the descent below them is skipped.
BUILD_ROOT_SCAN_SKIP_DIRS = frozenset({"node_modules", "out", "project", "src", "target", "venv"})


class StaleLockMode(Enum):
    """Mode for handling stale Metals H2 database locks."""

    AUTO_CLEAN = "auto-clean"
    """Automatically remove stale lock files (default, recommended)."""

    WARN = "warn"
    """Log a warning but proceed; may result in degraded experience."""

    FAIL = "fail"
    """Raise an error and refuse to start."""


def _contains_json_file(path: str) -> bool:
    try:
        return any(entry.name.endswith(".json") for entry in os.scandir(path))
    except OSError:
        return False


def _is_build_root(path: str) -> bool:
    """
    Whether `path` is the root of a build that Metals can import.
    """
    if any(os.path.isfile(os.path.join(path, name)) for name in BUILD_ROOT_MARKER_FILES):
        return True
    if any(_contains_json_file(os.path.join(path, name)) for name in BUILD_ROOT_MARKER_JSON_DIRS):
        return True
    # sbt allows the build to be defined entirely under project/, with no build.sbt
    build_properties = os.path.join(path, "project", "build.properties")
    if os.path.isfile(build_properties):
        try:
            with open(build_properties, encoding="utf-8", errors="replace") as f:
                return any(line.lstrip().startswith("sbt.version") for line in f)
        except OSError:
            return False
    return False


def find_build_roots(repository_root_path: str, max_depth: int = DEFAULT_PROJECT_ROOT_SCAN_DEPTH) -> list[str]:
    """
    Find the roots of the builds contained in the given repository.

    Metals serves one build per workspace folder, so a repository holding several builds
    (or a single build below its root) must name those directories rather than the repository root.

    :param repository_root_path: the repository root
    :param max_depth: how many directory levels below the repository root to search;
        the search does not descend into a directory that is itself a build root
    :return: the absolute paths of the build roots found, or `[repository_root_path]` if there are none
        (which leaves Metals' own behaviour unchanged)
    """
    if _is_build_root(repository_root_path):
        return [repository_root_path]

    roots: list[str] = []
    visited: set[str] = set()

    def scan(directory: str, depth: int) -> None:
        # symlinks are followed, as Metals' own search does, so guard against cycles
        real_path = os.path.realpath(directory)
        if depth > max_depth or real_path in visited:
            return
        visited.add(real_path)
        try:
            entries = sorted(os.scandir(directory), key=lambda e: e.name)
        except OSError:
            return
        for entry in entries:
            if entry.name.startswith(".") or not entry.is_dir():
                continue
            if _is_build_root(entry.path):
                roots.append(entry.path)
            elif entry.name not in BUILD_ROOT_SCAN_SKIP_DIRS:
                scan(entry.path, depth + 1)

    scan(repository_root_path, 1)
    return roots or [repository_root_path]


class ScalaInitializeParamsBuilder(DefaultInitializeParamsBuilder):
    """
    Sends the repository's build roots as the workspace folders, so that Metals creates one
    service per build (see `MetalsLanguageServer.initialize`), in place of `ls_workspace_folders`,
    which is about what SolidLSP indexes and is shared across a project's language servers.

    `ls_additional_workspace_folders` is still honoured: those folders can lie outside the
    repository and so could never be detected, which is the whole point of the setting.
    """

    def __init__(self, ls: SolidLanguageServer, build_roots: list[str]):
        super().__init__(ls, set_workspace_folders=False)
        self._build_roots = build_roots

    @override
    def _apply_updates(self) -> None:
        super()._apply_updates()
        folders = list(self._build_roots)
        for path in self._ls.config.get_absolute_additional_workspace_folders(self._ls.repository_root_path):
            if path not in folders:
                folders.append(path)
        log.info("Workspace folders sent to Metals: %s", folders)
        self._set("workspaceFolders", [self._create_workspace_folder_entry(path) for path in folders])


def _parse_project_roots(value: object) -> list[str] | None:
    """
    Validate the `project_roots` setting, returning None (i.e. detect them) if it is unusable.
    """
    if value is None:
        return None
    if isinstance(value, str) or not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        log.warning(f"Invalid project_roots value {value!r}, expected a list of paths; detecting the build roots instead")
        return None
    roots: list[str] = [item for item in value if isinstance(item, str)]
    if not roots:
        log.warning("Empty project_roots; detecting the build roots instead")
        return None
    return roots


def _parse_project_root_scan_depth(value: object) -> int:
    """
    Validate the `project_root_scan_depth` setting, falling back to the default if it is unusable.
    """
    if value is None:
        return DEFAULT_PROJECT_ROOT_SCAN_DEPTH
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        log.warning(
            f"Invalid project_root_scan_depth value {value!r}, expected a positive integer; using {DEFAULT_PROJECT_ROOT_SCAN_DEPTH}"
        )
        return DEFAULT_PROJECT_ROOT_SCAN_DEPTH
    return value


def _get_scala_settings(solidlsp_settings: SolidLSPSettings) -> dict[str, object]:
    """
    Extract Scala-specific settings with defaults applied.

    Returns a dictionary with keys:
        - metals_version: str
        - client_name: str
        - on_stale_lock: StaleLockMode
        - log_multi_instance_notice: bool
        - project_roots: list[str] | None
        - project_root_scan_depth: int
    """
    from solidlsp.ls_config import LanguageServerId

    defaults: dict[str, object] = {
        "metals_version": DEFAULT_METALS_VERSION,
        "client_name": DEFAULT_CLIENT_NAME,
        "on_stale_lock": StaleLockMode.AUTO_CLEAN,
        "log_multi_instance_notice": DEFAULT_LOG_MULTI_INSTANCE_NOTICE,
        "project_roots": None,
        "project_root_scan_depth": DEFAULT_PROJECT_ROOT_SCAN_DEPTH,
    }

    if not solidlsp_settings.ls_specific_settings:
        return defaults

    scala_settings = solidlsp_settings.get_ls_specific_settings(LanguageServerId.SCALA)

    # Parse stale lock mode with validation
    on_stale_lock_str = scala_settings.get("on_stale_lock", DEFAULT_ON_STALE_LOCK)
    try:
        on_stale_lock = StaleLockMode(on_stale_lock_str)
    except ValueError:
        log.warning(f"Invalid on_stale_lock value '{on_stale_lock_str}', using '{DEFAULT_ON_STALE_LOCK}'")
        on_stale_lock = StaleLockMode.AUTO_CLEAN

    return {
        "metals_version": scala_settings.get("metals_version", DEFAULT_METALS_VERSION),
        "client_name": scala_settings.get("client_name", DEFAULT_CLIENT_NAME),
        "on_stale_lock": on_stale_lock,
        "log_multi_instance_notice": scala_settings.get("log_multi_instance_notice", DEFAULT_LOG_MULTI_INSTANCE_NOTICE),
        "project_roots": _parse_project_roots(scala_settings.get("project_roots")),
        "project_root_scan_depth": _parse_project_root_scan_depth(scala_settings.get("project_root_scan_depth")),
    }


class ScalaLanguageServer(SolidLanguageServer):
    """
    Provides Scala specific instantiation of the LanguageServer class.
    Contains various configurations and settings specific to Scala.

    Configurable options in ls_specific_settings (in serena_config.yml):

        ls_specific_settings:
          scala:
            # Stale lock handling: auto-clean | warn | fail
            on_stale_lock: 'auto-clean'
            # Log notice when another Metals instance is detected
            log_multi_instance_notice: true
            # Metals version to bootstrap (default: DEFAULT_METALS_VERSION)
            metals_version: '1.6.4'
            # Client identifier sent to Metals (default: DEFAULT_CLIENT_NAME)
            client_name: 'Serena'
            # Build roots to serve, relative to the repository root; when unset, they are
            # auto-detected (see find_build_roots)
            project_roots: ['backend', 'tooling/plugin']
            # How many levels below the repository root auto-detection searches
            project_root_scan_depth: 3

    Monorepo support:
        Metals serves one build per workspace folder, so the build roots — not the repository
        root — are what it must be given. They are detected automatically; `project_roots`
        overrides the detection where it guesses wrong.

    Multi-instance support:
        Metals uses H2 AUTO_SERVER mode (enabled by default) to support multiple
        concurrent instances sharing the same database. Running Serena's Metals
        alongside VS Code's Metals is designed to work. The only issue is stale
        locks from crashed processes, which this class can detect and clean up.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a ScalaLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        self._build_roots = self._resolve_build_roots(repository_root_path, solidlsp_settings)
        log.info(f"Metals will be given these build roots as workspace folders: {self._build_roots}")

        # Check for stale locks before setting up dependencies (fail-fast)
        for build_root in self._build_roots:
            self._check_metals_db_status(build_root, solidlsp_settings)

        scala_lsp_executable_path = self._setup_runtime_dependencies(config, solidlsp_settings)
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=scala_lsp_executable_path, cwd=repository_root_path),
            config.ls_id.value,
            solidlsp_settings,
        )

    @staticmethod
    def _resolve_build_roots(repository_root_path: str, solidlsp_settings: SolidLSPSettings) -> list[str]:
        """
        Determine the build roots to serve, from the `project_roots` setting if given and by
        detection otherwise.
        """
        settings = _get_scala_settings(solidlsp_settings)
        configured_roots: list[str] | None = settings["project_roots"]  # type: ignore[assignment]
        if configured_roots is None:
            scan_depth: int = settings["project_root_scan_depth"]  # type: ignore[assignment]
            return find_build_roots(repository_root_path, scan_depth)

        roots = []
        for root in configured_roots:
            abs_root = os.path.abspath(os.path.join(repository_root_path, root))
            if os.path.isdir(abs_root):
                roots.append(abs_root)
            else:
                log.warning(f"Configured Scala project root does not exist, skipping: {abs_root}")
        if not roots:
            log.error("No configured Scala project root exists; detecting the build roots instead")
            return find_build_roots(repository_root_path, settings["project_root_scan_depth"])  # type: ignore[arg-type]
        return roots

    @override
    def _create_initialize_params_builder(self) -> InitializeParamsBuilder:
        return ScalaInitializeParamsBuilder(self, self._build_roots)

    def _check_metals_db_status(self, build_root_path: str, solidlsp_settings: SolidLSPSettings) -> None:
        """
        Check the Metals H2 database status of one build root and handle stale locks.

        This method is called before setting up runtime dependencies to fail-fast
        if there's a stale lock that the user has configured to fail on.
        """
        from pathlib import Path

        from solidlsp.ls_exceptions import MetalsStaleLockError
        from solidlsp.util.metals_db_utils import (
            MetalsDbStatus,
            check_metals_db_status,
            cleanup_stale_lock,
        )

        project_path = Path(build_root_path)
        status, lock_info = check_metals_db_status(project_path)

        # Get settings using the shared helper function
        settings = _get_scala_settings(solidlsp_settings)
        on_stale_lock: StaleLockMode = settings["on_stale_lock"]  # type: ignore[assignment]
        log_multi_instance_notice: bool = settings["log_multi_instance_notice"]  # type: ignore[assignment]

        if status == MetalsDbStatus.ACTIVE_INSTANCE:
            if log_multi_instance_notice and lock_info:
                log.info(
                    f"Another Metals instance detected (PID: {lock_info.pid}). "
                    "This is fine - Metals supports multiple instances via H2 AUTO_SERVER. "
                    "Both instances will share the database and Bloop build server."
                )

        elif status == MetalsDbStatus.STALE_LOCK:
            lock_path = lock_info.lock_path if lock_info else project_path / ".metals" / "metals.mv.db.lock.db"
            lock_path_str = str(lock_path)

            if on_stale_lock == StaleLockMode.AUTO_CLEAN:
                log.info(f"Stale Metals lock detected, cleaning up: {lock_path_str}")
                cleanup_success = cleanup_stale_lock(lock_path)
                if not cleanup_success:
                    log.warning(
                        f"Failed to clean up stale lock at {lock_path_str}. "
                        "Metals may fall back to in-memory database (degraded experience)."
                    )

            elif on_stale_lock == StaleLockMode.WARN:
                log.warning(
                    f"Stale Metals lock detected at {lock_path_str}. "
                    "A previous Metals process may have crashed. "
                    "Metals will fall back to in-memory database (degraded experience). "
                    "Consider removing the lock file manually or setting on_stale_lock='auto-clean'."
                )

            elif on_stale_lock == StaleLockMode.FAIL:
                raise MetalsStaleLockError(lock_path_str)

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            ".bloop",
            ".metals",
            "target",
        ]

    @classmethod
    def _setup_runtime_dependencies(cls, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings) -> list[str]:
        """
        Setup runtime dependencies for Scala Language Server and return the command to start the server.
        """
        assert shutil.which("java") is not None, "JDK is not installed or not in PATH."

        # Check if metals is available globally in PATH
        global_metals = shutil.which("metals")
        if global_metals:
            log.info(f"Found metals in PATH: {global_metals}")
            return [global_metals]

        # Get settings using the shared helper function
        settings = _get_scala_settings(solidlsp_settings)
        metals_version: str = settings["metals_version"]  # type: ignore[assignment]
        client_name: str = settings["client_name"]  # type: ignore[assignment]

        metals_home = os.path.join(cls.ls_resources_dir(solidlsp_settings), "metals-lsp")
        os.makedirs(metals_home, exist_ok=True)
        metals_executable = os.path.join(metals_home, metals_version, "metals")

        if not os.path.exists(metals_executable):
            coursier_command_path = shutil.which("coursier")
            cs_command_path = shutil.which("cs")
            assert cs_command_path is not None or coursier_command_path is not None, "coursier is not installed or not in PATH."

            if not cs_command_path:
                assert coursier_command_path is not None
                log.info("'cs' command not found. Trying to install it using 'coursier'.")
                try:
                    log.info("Running 'coursier setup --yes' to install 'cs'...")
                    subprocess_run([coursier_command_path, "setup", "--yes"], check=True, capture_output=True, text=True)
                except subprocess.CalledProcessError as e:
                    raise RuntimeError(f"Failed to set up 'cs' command with 'coursier setup'. Stderr: {e.stderr}")

                cs_command_path = shutil.which("cs")
                if not cs_command_path:
                    raise RuntimeError(
                        "'cs' command not found after running 'coursier setup'. Please check your PATH or install it manually."
                    )
                log.info("'cs' command installed successfully.")

            log.info(f"metals executable not found at {metals_executable}, bootstrapping...")
            subprocess_run(["mkdir", "-p", os.path.join(metals_home, metals_version)], check=True, capture_output=False)
            artifact = f"org.scalameta:metals_2.13:{metals_version}"
            cmd = [
                cs_command_path,
                "bootstrap",
                "--java-opt",
                "-XX:+UseG1GC",
                "--java-opt",
                "-XX:+UseStringDeduplication",
                "--java-opt",
                "-Xss4m",
                "--java-opt",
                "-Xms100m",
                "--java-opt",
                f"-Dmetals.client={client_name}",
                artifact,
                "-o",
                metals_executable,
                "-f",
            ]
            log.info("Bootstrapping metals...")
            subprocess_run(cmd, cwd=metals_home, check=True, capture_output=False)
            log.info("Bootstrapping metals finished.")
        return [metals_executable]

    def _create_base_initialize_params(self) -> dict:
        """
        Returns the initialize params for the Scala Language Server.
        """
        initialize_params = {
            "locale": "en",
            "initializationOptions": {
                "compilerOptions": {
                    "completionCommand": None,
                    "isCompletionItemDetailEnabled": True,
                    "isCompletionItemDocumentationEnabled": True,
                    "isCompletionItemResolve": True,
                    "isHoverDocumentationEnabled": True,
                    "isSignatureHelpDocumentationEnabled": True,
                    "overrideDefFormat": "ascli",
                    "snippetAutoIndent": False,
                },
                "debuggingProvider": True,
                "decorationProvider": False,
                "didFocusProvider": False,
                "doctorProvider": False,
                "executeClientCommandProvider": False,
                "globSyntax": "uri",
                "icons": "unicode",
                "inputBoxProvider": False,
                "isVirtualDocumentSupported": False,
                "isExitOnShutdown": True,
                "isHttpEnabled": True,
                "openFilesOnRenameProvider": False,
                "quickPickProvider": False,
                "renameFileThreshold": 200,
                "statusBarProvider": "false",
                "treeViewProvider": False,
                "testExplorerProvider": False,
                "openNewWindowProvider": False,
                "copyWorksheetOutputProvider": False,
                "doctorVisibilityProvider": False,
            },
            "capabilities": {"textDocument": {"documentSymbol": {"hierarchicalDocumentSymbolSupport": True}}},
        }
        return initialize_params

    def _start_server(self) -> None:
        """
        Starts the Scala Language Server
        """
        log.info("Starting Scala server process")
        self.server.start()

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")

        initialize_params = self._create_initialize_params()
        self.server.send.initialize(initialize_params)
        self.server.notify.initialized({})

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 5
