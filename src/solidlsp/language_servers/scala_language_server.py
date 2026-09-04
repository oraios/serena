"""
Provides Scala specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Scala.
"""

import logging
import os
import shutil
import subprocess
import threading
import time
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
DEFAULT_AUTO_IMPORT_BUILD = True
DEFAULT_PROJECT_ROOT_SCAN_DEPTH = 3
DEFAULT_INDEXING_TIMEOUT = 180.0
DEFAULT_INDEXING_START_GRACE = 15.0
DEFAULT_INDEXING_QUIET_PERIOD = 3.0

# The `window/showMessageRequest` actions Serena answers affirmatively: the ones standing between
# an un-imported workspace and a build server. Everything else is dismissed, since a prompt we do
# not recognise is one whose consequences we cannot judge — `Messages.OldBloopVersionRunning`
# offers to kill a process, `Messages.NewScalaProject` to open a window. "Don't show again" is
# never chosen: Metals persists that dismissal in the project's own state.
# (scala/meta/internal/metals/Messages.scala, at `ImportBuild`, `ImportBuildChanges`,
# `GenerateBspAndConnect`.)
#
# Not answered, deliberately: `Messages.ChooseBuildTool` ("Multiple build definitions found. Which
# would you like to use?"), whose actions are the build tools' own executable names. It precedes
# the import prompt in a workspace holding more than one kind of build, so such a workspace is
# still not imported — but choosing a build tool for the user is a guess of a different order, and
# Metals offers no way to say "whichever you would have picked".
BUILD_IMPORT_PROMPT_ACTIONS = ("Import build", "Import changes", "Connect")

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


class IndexingOutcome(Enum):
    """How a wait for Metals' outstanding work ended."""

    NO_WORK = "no-work"
    """Metals reported nothing at all within the start grace — it may not report progress."""

    IDLE = "idle"
    """Every task Metals reported has finished."""

    TIMEOUT = "timeout"
    """Work was still outstanding when the timeout expired."""


class MetalsProgressTracker:
    """
    Tracks the work-done progress Metals reports, so that a cross-file query can wait for its
    import, indexing and compilation rather than for a fixed period. References in particular
    are served from SemanticDB, which only exists once the build server has compiled the
    sources, and that finishes well after indexing does.

    Metals keeps reporting progress for the rest of the session — it loads a presentation
    compiler for essentially every file it is asked about — so the tracker answers "is anything
    outstanding right now", never "has the server finished for good".
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: dict[str, str] = {}
        self._seen_work = False
        self._idle = threading.Event()
        self._idle.set()

    def expect_work(self) -> None:
        """
        Mark the tracker busy ahead of an action that is expected to make Metals do something,
        so that a wait started before the first token arrives blocks rather than returning at once.
        """
        self._idle.clear()

    def on_create(self, params: dict) -> dict:
        """
        Handle `window/workDoneProgress/create`, which precedes the token's first notification.

        Tracking from creation rather than from `begin` means work announced just before a query
        is waited for even if it has not started yet.

        :param params: the request's `WorkDoneProgressCreateParams`
        :return: the empty result the request expects
        """
        with self._lock:
            self._active.setdefault(str(params.get("token", "")), "")
            self._seen_work = True
            self._idle.clear()
        return {}

    def on_progress(self, params: dict) -> None:
        """
        Handle a `$/progress` notification, tracking the token's title for diagnostics.

        :param params: the notification's `ProgressParams`
        """
        token = str(params.get("token", ""))
        value = params.get("value") or {}
        kind = value.get("kind")
        if kind == "begin":
            title = str(value.get("title", ""))
            with self._lock:
                self._active[token] = title
                self._seen_work = True
                self._idle.clear()
            log.info(f"Metals progress [{token}] started: {title}")
        elif kind == "end":
            with self._lock:
                title = self._active.pop(token, "")
                if not self._active:
                    self._idle.set()
            log.info(f"Metals progress [{token}] ended: {title}")

    def wait_until_idle(self, timeout: float, start_grace: float, quiet_period: float) -> IndexingOutcome:
        """
        Wait for everything Metals is doing to finish.

        Metals hands off between its phases rather than overlapping them — the import ends, then
        indexing begins, then a compilation per module — so its set of tokens empties for a
        second or so in between. Readiness is therefore "nothing outstanding for `quiet_period`",
        not "nothing outstanding", which would return in the first such gap.

        :param timeout: how long to wait, in seconds, once work is known to be outstanding
        :param start_grace: how long to wait, in seconds, for work to appear at all
        :param quiet_period: how long, in seconds, Metals must report nothing to count as finished
        :return: how the wait ended
        """
        grace_deadline = time.monotonic() + start_grace
        while time.monotonic() < grace_deadline:
            with self._lock:
                if self._active or self._seen_work:
                    break
            time.sleep(0.05)

        with self._lock:
            if not self._active and not self._seen_work:
                self._idle.set()
                return IndexingOutcome.NO_WORK

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self._idle.wait(timeout=remaining):
                return IndexingOutcome.TIMEOUT
            if self._stays_idle(quiet_period, deadline):
                return IndexingOutcome.IDLE

    def _stays_idle(self, quiet_period: float, deadline: float) -> bool:
        """
        :param quiet_period: how long, in seconds, nothing new must be reported
        :param deadline: the monotonic time at which to give up regardless
        :return: whether the tracker stayed idle for the whole quiet period
        """
        quiet_end = time.monotonic() + quiet_period
        while time.monotonic() < min(quiet_end, deadline):
            if not self._idle.is_set():
                return False
            time.sleep(0.05)
        return self._idle.is_set()

    def describe(self) -> str:
        """:return: compact diagnostic state of Metals' outstanding work."""
        with self._lock:
            titles = sorted(title for title in self._active.values() if title)
            idle = self._idle.is_set()
        return f"idle={idle}, active={', '.join(titles) or '<none>'}"


class StaleLockMode(Enum):
    """Mode for handling stale Metals H2 database locks."""

    AUTO_CLEAN = "auto-clean"
    """Automatically remove stale lock files (default, recommended)."""

    WARN = "warn"
    """Log a warning but proceed; may result in degraded experience."""

    FAIL = "fail"
    """Raise an error and refuse to start."""


def choose_show_message_request_action(params: dict, auto_import_build: bool = DEFAULT_AUTO_IMPORT_BUILD) -> dict | None:
    """
    Choose Serena's answer to a `window/showMessageRequest`, which Metals uses to ask whether to
    import the build.

    :param params: the request's `ShowMessageRequestParams`
    :param auto_import_build: whether to answer the build-import prompts affirmatively
    :return: the action to select, or None to select none — which is what the LSP spec provides
        for, and what leaving the request unanswered fails to say
    """
    message = params.get("message", "")
    actions = params.get("actions") or []
    if auto_import_build:
        for action in actions:
            if isinstance(action, dict) and action.get("title") in BUILD_IMPORT_PROMPT_ACTIONS:
                log.info(f"Metals asked: {message!r}; answering {action['title']!r}")
                return action
    offered = [action.get("title") for action in actions if isinstance(action, dict)]
    log.info(f"Metals asked: {message!r}; dismissing (offered: {offered})")
    return None


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


def _parse_positive_float(value: object, name: str, default: float) -> float:
    """
    Validate a positive-number setting, falling back to the default if it is unusable.
    """
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        log.warning(f"Invalid {name} value {value!r}, expected a positive number; using {default}")
        return default
    return float(value)


def _get_scala_settings(solidlsp_settings: SolidLSPSettings) -> dict[str, object]:
    """
    Extract Scala-specific settings with defaults applied.

    Returns a dictionary with keys:
        - metals_version: str
        - client_name: str
        - on_stale_lock: StaleLockMode
        - log_multi_instance_notice: bool
        - auto_import_build: bool
        - project_roots: list[str] | None
        - project_root_scan_depth: int
        - indexing_timeout: float
        - indexing_start_grace: float
        - indexing_quiet_period: float
    """
    from solidlsp.ls_config import LanguageServerId

    defaults: dict[str, object] = {
        "metals_version": DEFAULT_METALS_VERSION,
        "client_name": DEFAULT_CLIENT_NAME,
        "on_stale_lock": StaleLockMode.AUTO_CLEAN,
        "log_multi_instance_notice": DEFAULT_LOG_MULTI_INSTANCE_NOTICE,
        "auto_import_build": DEFAULT_AUTO_IMPORT_BUILD,
        "project_roots": None,
        "project_root_scan_depth": DEFAULT_PROJECT_ROOT_SCAN_DEPTH,
        "indexing_timeout": DEFAULT_INDEXING_TIMEOUT,
        "indexing_start_grace": DEFAULT_INDEXING_START_GRACE,
        "indexing_quiet_period": DEFAULT_INDEXING_QUIET_PERIOD,
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
        "auto_import_build": scala_settings.get("auto_import_build", DEFAULT_AUTO_IMPORT_BUILD),
        "project_roots": _parse_project_roots(scala_settings.get("project_roots")),
        "project_root_scan_depth": _parse_project_root_scan_depth(scala_settings.get("project_root_scan_depth")),
        "indexing_timeout": _parse_positive_float(scala_settings.get("indexing_timeout"), "indexing_timeout", DEFAULT_INDEXING_TIMEOUT),
        "indexing_start_grace": _parse_positive_float(
            scala_settings.get("indexing_start_grace"), "indexing_start_grace", DEFAULT_INDEXING_START_GRACE
        ),
        "indexing_quiet_period": _parse_positive_float(
            scala_settings.get("indexing_quiet_period"), "indexing_quiet_period", DEFAULT_INDEXING_QUIET_PERIOD
        ),
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
            # Answer Metals' build-import prompts affirmatively, which lets it run the project's
            # build tool (e.g. sbt bloopInstall). Set false to leave the build un-imported.
            auto_import_build: true
            # Build roots to serve, relative to the repository root; when unset, they are
            # auto-detected (see find_build_roots)
            project_roots: ['backend', 'tooling/plugin']
            # How many levels below the repository root auto-detection searches
            project_root_scan_depth: 3
            # How long to wait, in seconds, for Metals to finish indexing and compiling
            # before the first cross-file query (see "Indexing")
            indexing_timeout: 180
            # How long to wait for that work to *begin* before concluding there is none
            indexing_start_grace: 15
            # How long Metals must report nothing for its work to count as finished
            indexing_quiet_period: 3

    Indexing:
        Metals reports its import, indexing and compilation as LSP work-done progress, and
        references are only complete once the build server has compiled the sources that
        produce SemanticDB. The first cross-file query of a session therefore waits for that
        work rather than for a fixed period; `indexing_timeout` bounds the wait, after which
        the query proceeds against whatever Metals has so far.

    Build import:
        Metals asks, via `window/showMessageRequest`, whether to import a workspace it has not
        seen before; until that is answered it has no build server and so no build target, and
        every cross-file query is served by the fallback presentation compiler.

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

        settings = _get_scala_settings(solidlsp_settings)
        self._auto_import_build: bool = settings["auto_import_build"]  # type: ignore[assignment]
        self._indexing_timeout: float = settings["indexing_timeout"]  # type: ignore[assignment]
        self._indexing_start_grace: float = settings["indexing_start_grace"]  # type: ignore[assignment]
        self._indexing_quiet_period: float = settings["indexing_quiet_period"]  # type: ignore[assignment]

        self._progress = MetalsProgressTracker()

        scala_lsp_executable_path = self._setup_runtime_dependencies(config, solidlsp_settings)
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=scala_lsp_executable_path, cwd=repository_root_path),
            "scala",
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
            "capabilities": {
                "textDocument": {"documentSymbol": {"hierarchicalDocumentSymbolSupport": True}},
                # without this Metals never reports what it is doing, so there is nothing to
                # wait on before the first cross-file query
                "window": {"workDoneProgress": True},
            },
        }
        return initialize_params

    def _answer_show_message_request(self, params: dict) -> dict | None:
        return choose_show_message_request_action(params, auto_import_build=self._auto_import_build)

    @override
    def _pre_open_for_cross_file_references(self) -> None:
        if not self._has_waited_for_cross_file_references:
            self._progress.expect_work()

    @override
    def _wait_for_cross_file_references_if_needed(self) -> None:
        if self._has_waited_for_cross_file_references:
            return

        # Opening a file is what makes Metals connect to its build server, so the work only
        # begins after the didOpen that precedes this call.
        outcome = self._progress.wait_until_idle(
            timeout=self._indexing_timeout,
            start_grace=self._indexing_start_grace,
            quiet_period=self._indexing_quiet_period,
        )
        if outcome == IndexingOutcome.NO_WORK:
            log.info(f"Metals reported no work within {self._indexing_start_grace:.0f}s; proceeding")
        elif outcome == IndexingOutcome.IDLE:
            log.info("Metals indexing complete")
        else:
            log.warning(
                "Metals was still working after %.0fs; proceeding, so cross-file results may be incomplete (%s)",
                self._indexing_timeout,
                self._progress.describe(),
            )
        self._has_waited_for_cross_file_references = True

    def _start_server(self) -> None:
        """
        Starts the Scala Language Server
        """
        self.server.on_request("window/showMessageRequest", self._answer_show_message_request)
        self.server.on_request("window/workDoneProgress/create", self._progress.on_create)
        self.server.on_notification("$/progress", self._progress.on_progress)

        log.info("Starting Scala server process")
        self.server.start()

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")

        initialize_params = self._create_initialize_params()
        self.server.send.initialize(initialize_params)
        self.server.notify.initialized({})
