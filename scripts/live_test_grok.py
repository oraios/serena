"""
Live smoke test for Serena's Grok Build integration.

Verifies that the Grok support (``serena setup grok``, the ``grok`` context and the native
``serena-hooks --client=grok`` protocol) works against a *real* ``grok`` CLI installation —
exercising the exact code paths that the unit tests cover with mocks
(``test/serena/config/test_client_setup.py``, ``test/serena/test_hooks.py``, ...).

The test is designed to be safe and free:

* **Zero inference cost.** No Grok session is ever started and no prompt is sent; only
  configuration, discovery, stdio hook invocations and raw MCP handshakes (including one
  read-only Serena tool call) are used.
* **State-preserving.** The Grok user configuration is backed up before the first mutation,
  every ``grok mcp add`` is paired with a removal, and the baseline is verified (and restored
  from backup if necessary) at the end — also on abort. Hook state is written to an isolated,
  temporary ``SERENA_HOME``. The script refuses to run if a ``serena`` MCP server is already
  registered in Grok, so it never clobbers a real setup.
* **Credential-safe.** The config backup (which may carry tokens) is written 0600 inside a private,
  owner-only work directory (a fresh ``mkdtemp`` by default; a supplied ``--work-dir`` is validated
  as non-symlink, owner-owned and not group/world-accessible) and is deleted once the baseline is
  confirmed intact. ``--hooks-only`` never mutates the config and therefore never backs it up.

Per-check evidence files and a Markdown report are written to the work directory (printed at
startup; default: a fresh private 0700 directory created via ``mkdtemp`` under the system tmp,
prefix ``serena-grok-live-``). The exit code is 0 iff no check FAILed.

Usage::

    uv run python scripts/live_test_grok.py               # full run
    uv run python scripts/live_test_grok.py --hooks-only  # pure-local checks only (no Grok config changes)
    uv run python scripts/live_test_grok.py --skip-unit   # skip the pytest smoke run
    uv run python scripts/live_test_grok.py --help        # all options
"""

import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import IO, Optional

CONTEXT_EXCLUDED_TOOLS = ("create_text_file", "execute_shell_command", "find_file", "list_dir", "read_file", "search_for_pattern")
"""tools excluded by the ``grok`` context (mirrors ``src/serena/resources/config/contexts/grok.yml``)"""

REQUIRED_SYMBOLIC_TOOLS = ("find_symbol", "get_symbols_overview", "replace_symbol_body", "find_referencing_symbols")
"""symbolic tools that must be exposed by the MCP server in project mode"""

UNIT_TEST_FILES = (
    "test/serena/test_hooks.py",
    "test/serena/test_cli_setup.py",
    "test/serena/config/test_client_setup.py",
    "test/serena/config/test_context_mode.py",
    "test/serena/config/test_grok_docs.py",
)
"""unit-test files whose mocked assumptions this live test validates"""

LIVE_MCP_SERVER_NAME = "serena-live"
"""name of the temporary MCP server entry registered for connectivity checks"""

STRUCTURED_OUTPUT_PROBE_TOOL = "initial_instructions"
"""read-only project-mode tool (returns a plain string) used to probe the structured-output wire shape"""

HOOKS_JSON = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "grep|read_file|run_terminal_command",
                "hooks": [{"type": "command", "command": "serena-hooks remind --client=grok", "timeout": 5}],
            }
        ],
        "Stop": [{"hooks": [{"type": "command", "command": "serena-hooks cleanup --client=grok", "timeout": 5}]}],
    }
}
"""the hooks configuration recommended in docs/02-usage/030_clients.md (Grok section)"""


class Status(Enum):
    """The outcome category of a single live check."""

    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    INFO = "INFO"
    SKIP = "SKIP"


@dataclass
class CheckResult:
    """The recorded outcome of a single live check."""

    check_id: str
    status: Status
    note: str


@dataclass
class CommandResult:
    """The captured outcome of an executed subprocess."""

    return_code: Optional[int]
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def output(self) -> str:
        return self.stdout + ("\n" + self.stderr if self.stderr else "")


class AbortError(Exception):
    """Raised when the environment makes continuing pointless or unsafe."""


def run_command(
    argv: list[str],
    timeout: float = 60,
    cwd: Optional[Path] = None,
    env_overlay: Optional[dict[str, str]] = None,
    stdin_text: Optional[str] = None,
) -> CommandResult:
    """
    Runs a subprocess without a shell, capturing output and never raising on non-zero exit.

    :param argv: the command and its arguments
    :param timeout: seconds after which the process is killed
    :param cwd: the working directory for the process
    :param env_overlay: environment variables to add on top of the current environment
    :param stdin_text: text to pass on standard input
    :return: the captured result; on timeout, ``timed_out`` is set and ``return_code`` is None
    """
    env = None
    if env_overlay is not None:
        env = {**os.environ, **env_overlay}
    try:
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=env, input=stdin_text, check=False)
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
        return CommandResult(None, stdout, stderr, timed_out=True)
    except FileNotFoundError:
        return CommandResult(127, "", f"executable not found: {argv[0]}")


class McpStdioProbe:
    """
    A minimal MCP client that spawns a stdio server, performs the initialize handshake and
    lists the exposed tools. Uses a reader thread (rather than ``select``) for portability.
    """

    def __init__(self, argv: list[str], cwd: Path, stderr_log: IO[str]) -> None:
        """
        :param argv: the server command line
        :param cwd: the working directory for the server process
        :param stderr_log: an open file receiving the server's stderr (Serena logs to stderr)
        """
        self._process = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr_log, text=True, bufsize=1, cwd=cwd
        )
        self._messages: queue.Queue[dict] = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        assert self._process.stdout is not None
        for line in self._process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._messages.put(json.loads(line))
            except json.JSONDecodeError:
                continue

    def _send(self, message: dict) -> None:
        assert self._process.stdin is not None
        self._process.stdin.write(json.dumps(message) + "\n")
        self._process.stdin.flush()

    def request(self, request_id: int, method: str, params: dict, timeout: float) -> dict:
        """
        Sends a JSON-RPC request and waits for the response with the matching id.

        :param request_id: the JSON-RPC id to send and match on
        :param method: the JSON-RPC method name
        :param params: the JSON-RPC params object
        :param timeout: seconds to wait before giving up
        :return: the raw response message
        :raises AbortError: if the server exits prematurely or the response does not arrive in time
        """
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                raise AbortError(f"MCP server exited prematurely with code {self._process.returncode}")
            try:
                message = self._messages.get(timeout=1.0)
            except queue.Empty:
                continue
            if message.get("id") == request_id:
                return message
        raise AbortError(f"timed out waiting for MCP response to '{method}'")

    def notify(self, method: str) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": {}})

    def close(self) -> None:
        self._process.terminate()
        try:
            self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._process.kill()


@dataclass
class LiveTestConfig:
    """The resolved configuration of a live test run."""

    repo_root: Path
    serena_bin: Path
    serena_hooks_bin: Path
    python_bin: Path
    grok_bin: str
    grok_config_path: Path
    work_dir: Path
    hooks_only: bool = False
    skip_unit: bool = False
    grok_config_explicit: bool = False
    """whether --grok-config was supplied on the command line (enables the config-path/CLI consistency check)"""

    @property
    def evidence_dir(self) -> Path:
        return self.work_dir / "evidence"

    @property
    def hook_home(self) -> Path:
        """An isolated ``SERENA_HOME`` so hook state never touches the user's real one"""
        return self.work_dir / "serena-home"

    @property
    def config_backup_path(self) -> Path:
        return self.work_dir / "config.toml.bak"

    @staticmethod
    def _venv_executable(repo_root: Path, name: str) -> Path:
        if sys.platform == "win32":
            return repo_root / ".venv" / "Scripts" / f"{name}.exe"
        return repo_root / ".venv" / "bin" / name

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "LiveTestConfig":
        """
        :param args: the parsed command-line arguments
        :return: the resolved configuration, with defaults derived from the repository layout
        :raises AbortError: if a required executable cannot be resolved
        """
        repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[1]

        # resolve the executables under test, defaulting to the repository's venv
        serena_bin = Path(args.serena_bin) if args.serena_bin else cls._venv_executable(repo_root, "serena")
        serena_hooks_bin = Path(args.serena_hooks_bin) if args.serena_hooks_bin else cls._venv_executable(repo_root, "serena-hooks")
        python_bin = cls._venv_executable(repo_root, "python")
        for executable in (serena_bin, serena_hooks_bin, python_bin):
            if not executable.exists():
                raise AbortError(f"executable not found: {executable} — run 'uv sync' first (or pass --serena-bin/--serena-hooks-bin)")

        # resolve the grok CLI and its user-level configuration file
        grok_bin = args.grok_bin or shutil.which("grok") or ""
        if not grok_bin:
            raise AbortError("the 'grok' CLI was not found on PATH (override with --grok-bin)")
        grok_config_path = Path(args.grok_config) if args.grok_config else Path.home() / ".grok" / "config.toml"

        # Default to a private, unpredictable work dir (0700, owner-only): it holds a backup of the
        # user's grok config, which may carry credentials. A fixed shared-tmp path would expose those
        # to other local users and invites symlink/pre-creation attacks.
        work_dir = Path(args.work_dir) if args.work_dir else Path(tempfile.mkdtemp(prefix="serena-grok-live-"))
        return cls(
            repo_root=repo_root,
            serena_bin=serena_bin,
            serena_hooks_bin=serena_hooks_bin,
            python_bin=python_bin,
            grok_bin=grok_bin,
            grok_config_path=grok_config_path,
            work_dir=work_dir,
            hooks_only=args.hooks_only,
            skip_unit=args.skip_unit,
            grok_config_explicit=bool(args.grok_config),
        )


class GrokLiveTest:
    """Orchestrates the live checks, evidence capture, cleanup and reporting."""

    def __init__(self, config: LiveTestConfig) -> None:
        self.config = config
        self.results: list[CheckResult] = []
        self.findings: list[str] = []
        self._registered_server_names: list[str] = []
        self._created_global_hooks_file: Optional[Path] = None
        self._cleanup_done = False
        self._baseline_mcp_list = ""
        self._environment_summary = ""

    # ------------------------------------------------------------------ infrastructure

    def _record(self, check_id: str, status: Status, note: str) -> None:
        self.results.append(CheckResult(check_id, status, note))
        print(f"[{status.value}] {check_id} — {note}")

    def _finding(self, text: str) -> None:
        self.findings.append(text)
        print(f"FINDING: {text}")

    @staticmethod
    def _section(title: str) -> None:
        print(f"\n=== {title} ===")

    def _write_evidence(self, name: str, content: str) -> None:
        # Evidence can embed other MCP servers' env/args (a common place for tokens); keep it owner-only.
        path = self.config.evidence_dir / name
        path.write_text(content, encoding="utf-8")
        os.chmod(path, 0o600)

    def _open_evidence(self, name: str) -> IO[str]:
        """Open an evidence file for writing with owner-only (0600) permissions (e.g. server stderr logs)."""
        path = self.config.evidence_dir / name
        path.touch(mode=0o600)
        return open(path, "w", encoding="utf-8")

    def _grok(self, *args: str, timeout: float = 60) -> CommandResult:
        return run_command([self.config.grok_bin, *args], timeout=timeout)

    def _run_hook(self, subcommand: str, payload: dict) -> CommandResult:
        argv = [str(self.config.serena_hooks_bin), subcommand, "--client", "grok"]
        return run_command(argv, timeout=30, env_overlay={"SERENA_HOME": str(self.config.hook_home)}, stdin_text=json.dumps(payload))

    @staticmethod
    def _pre_tool_use_payload(session_id: str, tool_name: str, tool_input: dict, permission_mode: str = "bypassPermissions") -> dict:
        """:return: a PreToolUse payload in Grok's camelCase envelope (mirrors ``test_hooks.py::_grok_input``)"""
        return {
            "hookEventName": "pre_tool_use",
            "sessionId": session_id,
            "toolName": tool_name,
            "toolInput": tool_input,
            "toolInputTruncated": False,
            "permissionMode": permission_mode,
        }

    def _read_grok_mcp_server_section(self, server_name: str) -> dict:
        """:return: the ``[mcp_servers.<server_name>]`` table from the Grok configuration, or an empty dict"""
        import tomllib

        try:
            with open(self.config.grok_config_path, "rb") as f:
                config = tomllib.load(f)
            return config.get("mcp_servers", {}).get(server_name, {})
        except (OSError, tomllib.TOMLDecodeError):
            return {}

    def _verify_config_path_matches_cli(self, mcp_list_output: str) -> None:
        """Abort if ``--grok-config`` points at a file the grok CLI is not actually using.

        The grok CLI offers no alternate-config option (``grok mcp`` knows only the user/project
        scopes), so ``--grok-config`` exists solely for nonstandard Grok homes. If it named a file
        the CLI does not use, every file-level safety measure in this script (backup, restore,
        baseline byte-comparison) would silently protect the wrong file while ``grok mcp
        add/remove`` mutates the real configuration. Cross-check: the ``[mcp_servers.*]`` table
        names in the file must equal the server names reported by ``grok mcp list``.

        :param mcp_list_output: the raw output of ``grok mcp list`` captured for the baseline
        :raises AbortError: on any mismatch, before any mutation has occurred
        """
        if not self.config.grok_config_explicit:
            return
        import tomllib

        try:
            with open(self.config.grok_config_path, "rb") as f:
                file_servers = set(tomllib.load(f).get("mcp_servers", {}).keys())
        except (OSError, tomllib.TOMLDecodeError):
            file_servers = set()
        import re

        cli_servers = set()
        for line in mcp_list_output.splitlines():
            m = re.match(r"^\s*([\w-]+):\s", line)
            if m:
                cli_servers.add(m.group(1))
        if file_servers != cli_servers:
            self._record("P3", Status.FAIL, "--grok-config does not match the configuration the grok CLI actually uses")
            raise AbortError(
                f"--grok-config {self.config.grok_config_path} is not the config the grok CLI uses "
                f"(file declares mcp_servers {sorted(file_servers)}, 'grok mcp list' reports {sorted(cli_servers)}). "
                "This flag is for nonstandard Grok homes only — it cannot isolate the test from the real "
                "configuration, because 'grok mcp' has no alternate-config option. Aborting before any mutation."
            )

    def _insert_startup_timeout_sec(self, seconds: int) -> bool:
        """Add ``startup_timeout_sec`` to the live server's ``[mcp_servers.<name>]`` table, located structurally.

        The table is confirmed to exist (and to lack the key) by parsing the config with ``tomllib``, then the
        key is inserted immediately after the exact table-header line. This avoids a blind substring replace,
        which could match ``[mcp_servers.<name>]`` inside a comment or string value elsewhere in the user's
        config and corrupt it. The rest of the file (comments, formatting) is preserved by editing in place.

        :return: True if the key was inserted, False if the table is absent, already has the key, or is unparsable.
        """
        section = f"[mcp_servers.{LIVE_MCP_SERVER_NAME}]"
        existing = self._read_grok_mcp_server_section(LIVE_MCP_SERVER_NAME)
        if not existing or "startup_timeout_sec" in existing:
            return False
        lines = self.config.grok_config_path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if line.strip() == section:
                lines.insert(i + 1, f"startup_timeout_sec = {seconds}")
                self.config.grok_config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                return True
        return False

    def _cleanup_grok_state(self) -> None:
        """Removes every Grok-side artifact this run created (idempotent, best-effort)."""
        for server_name in list(self._registered_server_names):
            self._grok("mcp", "remove", "--scope", "user", server_name)
            self._registered_server_names.remove(server_name)
        if self._created_global_hooks_file is not None:
            self._created_global_hooks_file.unlink(missing_ok=True)
            try:
                self._created_global_hooks_file.parent.rmdir()
            except OSError:
                pass
            self._created_global_hooks_file = None

    # ------------------------------------------------------------------ phase P: preflight

    def check_p1_environment(self) -> None:
        self._section("P1 — repository, binaries, local-source resolution")

        # gather the facts that every later check relies on
        branch = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=self.config.repo_root).stdout.strip()
        commit = run_command(["git", "log", "--oneline", "-1"], cwd=self.config.repo_root).stdout.strip()
        grok_version = self._grok("--version").stdout.strip()
        module_path = run_command([str(self.config.python_bin), "-c", "import serena; print(serena.__file__)"]).stdout.strip()
        setup_help = run_command([str(self.config.serena_bin), "setup", "--help"]).output
        remind_help = run_command([str(self.config.serena_hooks_bin), "remind", "--help"]).output
        self._environment_summary = f"branch {branch} ({commit}); {grok_version}"

        # validate that the grok CLI works and the serena under test actually has Grok support
        problems = []
        if not grok_version.lower().startswith("grok "):
            problems.append(f"grok CLI not functional: {grok_version!r}")
        expected_module = self.config.repo_root / "src" / "serena" / "__init__.py"
        if Path(module_path) != expected_module:
            problems.append(f"serena resolves to {module_path}, not the repository source ({expected_module}) — run 'uv sync'")
        if "grok" not in setup_help:
            problems.append("'serena setup' does not offer the grok client — is Grok support present on this branch?")
        if "grok" not in remind_help:
            problems.append("'serena-hooks remind --client' does not offer grok")

        if problems:
            self._record("P1", Status.FAIL, "; ".join(problems))
            raise AbortError("environment not usable for the live test")
        self._record("P1", Status.PASS, self._environment_summary)

    @staticmethod
    def _require_private_dir(path: Path) -> None:
        """Ensure ``path`` is a real, owner-owned, non-group/world-accessible directory.

        Guards a user-supplied --work-dir before any credential-bearing backup is written into it,
        and rejects a symlink or another user's pre-created directory.
        """
        info = path.lstat()
        import stat as _stat

        if _stat.S_ISLNK(info.st_mode):
            raise AbortError(f"work dir {path} is a symlink; refusing to write a config backup through it")
        if not path.is_dir():
            raise AbortError(f"work dir {path} exists but is not a directory")
        if info.st_uid != os.getuid():
            raise AbortError(f"work dir {path} is not owned by the current user; refusing to use it")
        if info.st_mode & (_stat.S_IRWXG | _stat.S_IRWXO):
            raise AbortError(f"work dir {path} is group/world-accessible; run 'chmod 700 {path}' or omit --work-dir")

    def _backup_config_private(self) -> None:
        """Copy the grok config into the work dir with 0600 from creation (no world-readable window)."""
        dst = self.config.config_backup_path
        content = self.config.grok_config_path.read_bytes() if self.config.grok_config_path.exists() else b""
        fd = os.open(str(dst), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(content)

    def check_p3_baseline(self) -> None:
        self._section("P3 — work directory, baseline snapshot, config backup")

        # The work dir holds a backup of the possibly-credential-bearing grok config, so it must be
        # private. A default work dir is a fresh 0700 mkdtemp; a user-supplied one is validated.
        if self.config.work_dir.exists():
            self._require_private_dir(self.config.work_dir)
        else:
            self.config.work_dir.mkdir(mode=0o700, parents=True)
        self.config.evidence_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.config.hook_home.mkdir(mode=0o700, parents=True, exist_ok=True)

        # Back up the grok configuration before anything may mutate it — but only when we might mutate
        # it. --hooks-only never touches the config, so it must not copy the credentials at all.
        if self.config.hooks_only:
            self._baseline_mcp_list = self._grok("mcp", "list").output
            self._write_evidence("P3-baseline-mcp-list.txt", self._baseline_mcp_list)
            self._record("P3", Status.PASS, "hooks-only: baseline captured, config left untouched (no backup)")
            return

        self._backup_config_private()

        # snapshot the MCP baseline and refuse to run against a pre-existing serena registration
        baseline = self._grok("mcp", "list")
        self._baseline_mcp_list = baseline.output
        self._write_evidence("P3-baseline-mcp-list.txt", self._baseline_mcp_list)
        print(self._baseline_mcp_list.strip())
        self._verify_config_path_matches_cli(self._baseline_mcp_list)
        if "serena" in self._baseline_mcp_list:
            self._record("P3", Status.FAIL, "a serena MCP entry is already registered in Grok — refusing to touch it")
            raise AbortError(
                "remove it first if it is a leftover:  grok mcp remove --scope user serena  "
                f"(and/or {LIVE_MCP_SERVER_NAME}); if it is your real setup, run with --hooks-only instead"
            )
        self._record("P3", Status.PASS, f"baseline captured, config backed up to {self.config.config_backup_path}")

    def check_p2_unit_smoke(self) -> None:
        self._section("P2 — unit-test smoke (anchors live results to the mocked assumptions)")
        if self.config.skip_unit:
            self._record("P2", Status.SKIP, "--skip-unit")
            return

        result = run_command([str(self.config.python_bin), "-m", "pytest", *UNIT_TEST_FILES, "-q"], timeout=900, cwd=self.config.repo_root)
        agent_result = run_command(
            [str(self.config.python_bin), "-m", "pytest", "test/serena/test_serena_agent.py", "-k", "grok", "-q"],
            timeout=900,
            cwd=self.config.repo_root,
        )
        self._write_evidence("P2-pytest.txt", result.output + "\n" + agent_result.output)
        if result.return_code == 0 and agent_result.return_code == 0:
            self._record("P2", Status.PASS, "all Grok-related unit tests pass")
        else:
            self._record("P2", Status.FAIL, "unit tests failed — live results would be meaningless (see evidence/P2-pytest.txt)")
            raise AbortError("fix the unit tests before live-testing")

    def check_p4_context_loads(self) -> None:
        self._section("P4 — grok context loads from local source")
        code = (
            "from serena.config.context_mode import SerenaAgentContext\n"
            "ctx = SerenaAgentContext.from_name('grok')\n"
            "print(ctx.name); print(ctx.single_project); print(','.join(sorted(ctx.excluded_tools)))"
        )
        result = run_command([str(self.config.python_bin), "-c", code])
        self._write_evidence("P4-context.txt", result.output)
        lines = result.stdout.strip().splitlines()
        expected = [
            "grok",
            "True",
            ",".join(sorted(CONTEXT_EXCLUDED_TOOLS)),
        ]
        if result.return_code == 0 and lines == expected:
            self._record("P4", Status.PASS, "name, single_project and tool exclusions as expected")
        else:
            self._record("P4", Status.FAIL, "context mismatch (see evidence/P4-context.txt)")

    # ------------------------------------------------------------------ phase H: hook protocol

    def _check_remind_burst(
        self, check_id: str, title: str, deny_on_call: int, reason_fragment: str, calls: list[tuple[str, dict]]
    ) -> None:
        """
        Feeds a burst of PreToolUse payloads to the remind hook and asserts that only the
        ``deny_on_call``-th call produces a native Grok deny containing ``reason_fragment``.
        """
        self._section(f"{check_id} — {title}")
        evidence_lines = []
        problem = None
        for index, (tool_name, tool_input) in enumerate(calls, start=1):
            result = self._run_hook("remind", self._pre_tool_use_payload(f"live-{check_id}", tool_name, tool_input))
            evidence_lines.append(f"--- call {index} (tool={tool_name}) rc={result.return_code} ---\n{result.stdout}")
            output = result.stdout.strip()

            # every call must exit cleanly; only the final call may (and must) produce a deny
            if result.return_code != 0:
                problem = f"call {index} exited {result.return_code}"
            elif index < deny_on_call and output:
                problem = f"premature output on call {index}"
            elif index == deny_on_call:
                problem = self._validate_native_deny(output, reason_fragment)
            if problem:
                break
        self._write_evidence(f"{check_id}.txt", "\n".join(evidence_lines))
        if problem is None:
            self._record(check_id, Status.PASS, f"deny on call {deny_on_call} with expected native shape")
        else:
            self._record(check_id, Status.FAIL, f"{problem} (see evidence/{check_id}.txt)")

    @staticmethod
    def _validate_native_deny(output: str, reason_fragment: str) -> Optional[str]:
        """:return: a problem description if ``output`` is not a native Grok deny containing ``reason_fragment``, else None"""
        try:
            decision = json.loads(output)
        except json.JSONDecodeError:
            return f"deny output is not valid JSON: {output!r}"
        if decision.get("decision") != "deny":
            return f"expected a deny, got {output!r}"
        if reason_fragment not in decision.get("reason", ""):
            return f"deny reason lacks {reason_fragment!r}"
        if "hookSpecificOutput" in decision:
            return "Claude-shaped output leaked into the Grok format"
        return None

    def check_h_hook_protocol(self) -> None:
        grep_call = ("grep", {"pattern": "foo", "path": "."})
        read_call = ("read_file", {"target_file": "src/foo.py"})
        shell_grep_call = ("run_terminal_command", {"command": "rg -n foo src/bar.py"})

        self._check_remind_burst("H1", "grep burst → native deny on 3rd call", 3, "Too many consecutive grep calls", [grep_call] * 3)

        self._section("H2 — deny rate-limit window (same session, immediately after H1)")
        result = self._run_hook("remind", self._pre_tool_use_payload("live-H1", "grep", {"pattern": "bar", "path": "."}))
        self._write_evidence("H2.txt", f"rc={result.return_code}\n{result.stdout}")
        if result.return_code == 0 and not result.stdout.strip():
            self._record("H2", Status.PASS, "hook is a no-op within the 120s post-deny window")
        else:
            self._record("H2", Status.FAIL, f"expected silence, got rc={result.return_code} out={result.stdout.strip()!r}")

        self._check_remind_burst(
            "H3", "read_file burst (target_file) → deny on 3rd call", 3, "Too many consecutive read calls", [read_call] * 3
        )
        self._check_remind_burst(
            "H4",
            "run_terminal_command + rg classified as grep → deny on 3rd call",
            3,
            "Too many consecutive grep calls",
            [shell_grep_call] * 3,
        )
        self._check_remind_burst(
            "H5",
            "mixed grep/read burst → combined deny on 4th call",
            4,
            "mixed grep and read",
            [grep_call, read_call, grep_call, read_call],
        )

        self._section("H6 — neutral tools (edit/list) never trigger")
        neutral_calls = [
            ("search_replace", {"target_file": "src/a.py", "instructions": "x"}),
            ("list_dir", {"target_directory": "."}),
            ("search_replace", {"target_file": "src/b.py"}),
        ]
        neutral_outputs = [
            self._run_hook("remind", self._pre_tool_use_payload("live-H6", name, tool_input)) for name, tool_input in neutral_calls
        ]
        self._write_evidence("H6.txt", "\n".join(f"rc={r.return_code} out={r.stdout!r}" for r in neutral_outputs))
        if all(r.return_code == 0 and not r.stdout.strip() for r in neutral_outputs):
            self._record("H6", Status.PASS, "search_replace/list_dir stay silent")
        else:
            self._record("H6", Status.FAIL, "a neutral tool produced output or an error (see evidence/H6.txt)")

        self._section("H7 — auto-approve emits native allow")
        result = self._run_hook(
            "auto-approve", self._pre_tool_use_payload("live-H7", "serena__find_symbol", {}, permission_mode="acceptEdits")
        )
        self._write_evidence("H7.txt", f"rc={result.return_code}\n{result.stdout}")
        if result.return_code == 0 and result.stdout.strip() == '{"decision": "allow"}':
            self._record("H7", Status.PASS, 'exact native allow: {"decision": "allow"}')
        else:
            self._record("H7", Status.FAIL, f"expected exact native allow, got {result.stdout.strip()!r}")

        self._section("H8 — activate accepts camelCase sessionId (informational)")
        result = self._run_hook("activate", {"sessionId": "live-H8"})
        self._write_evidence("H8.txt", f"rc={result.return_code}\n{result.stdout}")
        if result.return_code == 0 and '"hookEventName": "SessionStart"' in result.stdout:
            self._record(
                "H8", Status.INFO, "runs clean; emits the client-agnostic SessionStart shape (Grok setup omits this hook by design)"
            )
        elif result.return_code == 0:
            self._record("H8", Status.WARN, "ran clean but produced unexpected output (see evidence/H8.txt)")
        else:
            self._record("H8", Status.FAIL, f"activate crashed (rc={result.return_code})")

        self._section("H9 — cleanup removes exactly its session's state")
        hook_data_dir = self.config.hook_home / "hook_data"
        if not hook_data_dir.is_dir():
            self._record("H9", Status.FAIL, "no hook state was persisted by the preceding checks — nothing to clean up")
            return
        before = sorted(p.name for p in hook_data_dir.iterdir())
        result = self._run_hook("cleanup", {"sessionId": "live-H1"})
        after = sorted(p.name for p in hook_data_dir.iterdir())
        self._write_evidence("H9.txt", f"before={before}\nafter={after}\nrc={result.return_code}")
        if result.return_code == 0 and not result.stdout.strip() and "live-H1" not in after and "live-H3" in after:
            self._record("H9", Status.PASS, "live-H1 state removed, other sessions untouched")
        else:
            self._record("H9", Status.FAIL, "cleanup did not behave as expected (see evidence/H9.txt)")

    # ------------------------------------------------------------------ phase S: client setup

    def check_s_client_setup(self) -> None:
        self._section("S1 — serena setup grok")
        expected_add_command = "grok mcp add --scope user serena -- serena start-mcp-server --context=grok --project-from-cwd"
        result = run_command([str(self.config.serena_bin), "setup", "grok"], timeout=120, cwd=self.config.repo_root)
        self._write_evidence("S1.txt", result.output)
        expected_fragments = (
            expected_add_command,
            "IMPORTANT: We additionally recommend to set up hooks for Grok",
            "030_clients.html#grok",
            "Serena has been successfully set up for grok.",
        )
        if result.return_code == 0 and all(fragment in result.stdout for fragment in expected_fragments):
            self._registered_server_names.append("serena")
            self._record("S1", Status.PASS, "registered against the real grok CLI with all expected messaging")
        else:
            self._record("S1", Status.FAIL, f"rc={result.return_code}, output diverges (see evidence/S1.txt)")

        self._section("S2 — registration content is exact")
        section = self._read_grok_mcp_server_section("serena")
        list_result = self._grok("mcp", "list")
        self._write_evidence("S2.txt", f"mcp list:\n{list_result.output}\n\n[mcp_servers.serena] = {section!r}")
        registered_tokens = " ".join([str(section.get("command", "")), *section.get("args", [])])
        required_tokens = ("serena", "start-mcp-server", "--context=grok", "--project-from-cwd")
        if "serena" in list_result.output and all(token in registered_tokens for token in required_tokens):
            self._record("S2", Status.PASS, "config registers command 'serena' with the context and project flags")
        else:
            self._record("S2", Status.FAIL, f"registered entry incomplete: {section!r}")

        self._section("S3 — grok inspect discovers the server")
        inspect_result = self._grok("inspect", "--json", timeout=60)
        self._write_evidence("S3-inspect.json", inspect_result.output)
        server_names = self._extract_inspect_mcp_server_names(inspect_result.stdout)
        if "serena" in server_names:
            self._record("S3", Status.PASS, "inspect --json lists serena under mcpServers")
        else:
            self._record("S3", Status.WARN, f"serena not among inspect's mcpServers {server_names} — review evidence/S3-inspect.json")

        self._section("S4 — idempotent re-run")
        rerun = run_command([str(self.config.serena_bin), "setup", "grok"], timeout=120, cwd=self.config.repo_root)
        self._write_evidence("S4.txt", rerun.output)
        if rerun.return_code == 0 and self._read_grok_mcp_server_section("serena"):
            self._record("S4", Status.PASS, "re-run succeeds and the entry remains registered exactly once")
        else:
            self._record("S4", Status.FAIL, f"re-run rc={rerun.return_code}")

        self._section("S5 — negative path: grok missing from PATH → clean refusal")
        minimal_path = "C:\\Windows\\System32" if sys.platform == "win32" else "/usr/bin:/bin"
        result = run_command([str(self.config.serena_bin), "setup", "grok"], env_overlay={"PATH": minimal_path})
        self._write_evidence("S5.txt", f"rc={result.return_code}\n{result.output}")
        if result.return_code == 1 and "Cannot apply setup for client 'grok'" in result.stdout:
            self._record("S5", Status.PASS, "is_applicable()==False path exits 1 with the documented message")
        else:
            self._record("S5", Status.FAIL, f"rc={result.return_code} (expected 1) or message mismatch (see evidence/S5.txt)")

    @staticmethod
    def _extract_inspect_mcp_server_names(inspect_json: str) -> list[str]:
        """:return: the MCP server names listed by ``grok inspect --json``, or an empty list if the output cannot be parsed"""
        try:
            data = json.loads(inspect_json)
            return [server.get("name", "") for server in data.get("mcpServers", [])]
        except (json.JSONDecodeError, AttributeError, TypeError):
            return []

    # ------------------------------------------------------------------ phase M: MCP server

    def _server_argv(self, with_project: bool, context: str = "grok") -> list[str]:
        argv = [str(self.config.serena_bin), "start-mcp-server", "--context", context, "--enable-web-dashboard", "false"]
        if with_project:
            argv.insert(2, "--project-from-cwd")
        return argv

    def _check_mcp_handshake(
        self, check_id: str, title: str, cwd: Path, with_project: bool, required: tuple[str, ...], forbidden: tuple[str, ...]
    ) -> None:
        """
        Starts the MCP server over stdio, performs the initialize handshake, lists tools and
        asserts the presence/absence of the given tool names.
        """
        self._section(f"{check_id} — {title}")
        with self._open_evidence(f"{check_id}-server.log") as stderr_log:
            probe = McpStdioProbe(self._server_argv(with_project), cwd=cwd, stderr_log=stderr_log)
            try:
                init_params = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "serena-live-test", "version": "0.0.0"},
                }
                initialization = probe.request(1, "initialize", init_params, timeout=240)
                probe.notify("notifications/initialized")
                tools_response = probe.request(2, "tools/list", {}, timeout=240)
            except AbortError as e:
                self._record(check_id, Status.FAIL, f"{e} (see evidence/{check_id}-server.log)")
                return
            finally:
                probe.close()

        # evaluate the exposed tool set against the context's contract
        tools = sorted(tool["name"] for tool in tools_response["result"]["tools"])
        server_info = initialization["result"].get("serverInfo", {})
        self._write_evidence(f"{check_id}.txt", f"server: {server_info}\ntool count: {len(tools)}\ntools: {','.join(tools)}")
        leaked = sorted(set(forbidden) & set(tools))
        missing = sorted(set(required) - set(tools))
        if not leaked and not missing:
            self._record(check_id, Status.PASS, f"handshake ok, tool set as expected ({len(tools)} tools)")
        else:
            self._record(check_id, Status.FAIL, f"forbidden tools exposed: {leaked or 'none'}; required tools missing: {missing or 'none'}")

    def check_m_mcp_server(self) -> None:
        no_project_dir = self.config.work_dir / "noproject"
        no_project_dir.mkdir(exist_ok=True)
        self._check_mcp_handshake(
            "M1",
            "MCP handshake, no project (context exclusions over the wire)",
            no_project_dir,
            with_project=False,
            required=(),
            forbidden=CONTEXT_EXCLUDED_TOOLS,
        )
        self._check_mcp_handshake(
            "M2",
            "MCP handshake with --project-from-cwd (single-project mode)",
            self.config.repo_root,
            with_project=True,
            required=REQUIRED_SYMBOLIC_TOOLS,
            forbidden=(*CONTEXT_EXCLUDED_TOOLS, "activate_project"),
        )

        self._section("M3 — grok mcp doctor spawns the real server (absolute serena path)")
        add_result = self._grok(
            "mcp",
            "add",
            "--scope",
            "user",
            LIVE_MCP_SERVER_NAME,
            "--",
            str(self.config.serena_bin),
            "start-mcp-server",
            "--context=grok",
            "--project-from-cwd",
            "--enable-web-dashboard",
            "false",
        )
        if add_result.return_code != 0:
            self._write_evidence("M3.txt", add_result.output)
            self._record("M3", Status.FAIL, f"could not register the {LIVE_MCP_SERVER_NAME} entry (see evidence/M3.txt)")
        else:
            self._registered_server_names.append(LIVE_MCP_SERVER_NAME)
            self._check_m3_doctor()

        self._section("M4 — readiness of the 'serena' command on PATH (informational)")
        self._check_m4_path_serena()

        self._check_m5_structured_output()

        # the production and test entries are no longer needed past this point
        self._cleanup_grok_state()

    def _doctor_looks_healthy(self, result: CommandResult) -> bool:
        return result.return_code == 0 and not any(
            marker in result.output.lower() for marker in ("timeout", "timed out", "failed", "error")
        )

    def _check_m3_doctor(self) -> None:
        evidence = []

        # first attempt, then a plain retry (grok may cache a slow first spawn)
        doctor = self._grok("mcp", "doctor", LIVE_MCP_SERVER_NAME, "--json", timeout=180)
        evidence.append(doctor.output)
        if not self._doctor_looks_healthy(doctor):
            doctor = self._grok("mcp", "doctor", LIVE_MCP_SERVER_NAME, "--json", timeout=180)
            evidence.append("--- retry ---\n" + doctor.output)

        # if the spawn seems to time out, retry with a raised startup timeout (above grok's 30s default);
        # 'grok mcp add' has no flag for it, so it must be inserted into the config directly
        if not self._doctor_looks_healthy(doctor) and self._insert_startup_timeout_sec(60):
            doctor = self._grok("mcp", "doctor", LIVE_MCP_SERVER_NAME, "--json", timeout=180)
            evidence.append("--- with startup_timeout_sec=60 ---\n" + doctor.output)
            if self._doctor_looks_healthy(doctor):
                self._finding(
                    "grok's default MCP startup timeout (30s) was too low for Serena's cold start in this environment; "
                    "raising startup_timeout_sec (e.g. 60) in the TOML fixed it — worth noting for slow environments"
                )

        self._write_evidence("M3-doctor.txt", "\n".join(evidence))
        if self._doctor_looks_healthy(doctor):
            self._record("M3", Status.PASS, "doctor reports the server connectable (heuristic — skim evidence/M3-doctor.txt)")
        else:
            self._record("M3", Status.FAIL, f"doctor rc={doctor.return_code} (see evidence/M3-doctor.txt)")

    def _check_m4_path_serena(self) -> None:
        """Checks whether the ``serena`` resolved via PATH (what the production registration will spawn) supports the grok context."""
        path_serena = shutil.which("serena")
        if path_serena is None:
            self._record("M4", Status.INFO, "no 'serena' on PATH — the production registration requires one (e.g. via uv tool install)")
            return
        if Path(path_serena).resolve() == self.config.serena_bin.resolve():
            self._record(
                "M4", Status.INFO, "PATH resolves 'serena' to the binary under test — production registration will behave like M1-M3"
            )
            return

        # probe the foreign installation briefly: surviving the timeout means the context loaded
        probe = run_command([path_serena, "start-mcp-server", "--context", "grok", "--enable-web-dashboard", "false"], timeout=15)
        self._write_evidence(
            "M4.txt", f"PATH serena: {path_serena}\nrc={probe.return_code} timed_out={probe.timed_out}\n{probe.output[-3000:]}"
        )
        if probe.timed_out:
            self._record(
                "M4", Status.INFO, f"'serena' on PATH ({path_serena}) supports the grok context — production registration is functional"
            )
        else:
            self._record(
                "M4", Status.INFO, f"'serena' on PATH ({path_serena}) cannot start with the grok context — likely a pre-Grok release"
            )
            self._finding(
                "the production registration spawns the bare 'serena' command; it only works once the installation on PATH "
                "includes Grok support (see evidence/M4.txt for the observed failure)"
            )

    def _probe_tool_call(self, check_id: str, context: str) -> Optional[tuple[Optional[dict], dict]]:
        """
        Starts the MCP server with the given context (project mode), calls the read-only probe tool
        and returns its advertised output schema together with the raw ``tools/call`` result.

        :param check_id: the check id (used for evidence file names and FAIL records)
        :param context: the Serena context to start the server with
        :return: ``(output_schema, call_result)``, or None if the probe failed (a FAIL is recorded)
        """
        with self._open_evidence(f"{check_id}-{context}-server.log") as stderr_log:
            probe = McpStdioProbe(self._server_argv(with_project=True, context=context), cwd=self.config.repo_root, stderr_log=stderr_log)
            try:
                init_params = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "serena-live-test", "version": "0.0.0"},
                }
                probe.request(1, "initialize", init_params, timeout=240)
                probe.notify("notifications/initialized")
                tools_response = probe.request(2, "tools/list", {}, timeout=240)
                call_response = probe.request(3, "tools/call", {"name": STRUCTURED_OUTPUT_PROBE_TOOL, "arguments": {}}, timeout=240)
            except AbortError as e:
                self._record(check_id, Status.FAIL, f"{context}: {e} (see evidence/{check_id}-{context}-server.log)")
                return None
            finally:
                probe.close()

        entries = [tool for tool in tools_response["result"]["tools"] if tool["name"] == STRUCTURED_OUTPUT_PROBE_TOOL]
        if not entries:
            self._record(check_id, Status.FAIL, f"{context}: probe tool '{STRUCTURED_OUTPUT_PROBE_TOOL}' not exposed")
            return None
        return entries[0].get("outputSchema"), call_response.get("result", {})

    def _check_m5_structured_output(self) -> None:
        """
        Verifies the structured-tool-output wire shape of the grok context (auto default) against the
        claude-code context (explicit ``false`` workaround): for a string-returning tool, the grok
        context must advertise an output schema and return ``structuredContent`` while claude-code
        must serve plain text only.

        This pins what Serena *serves* under each context; whether Grok Build unpacks
        ``structuredContent`` client-side can only be observed in a real agent session, which is
        out of scope for a zero-inference test.
        """
        self._section("M5 — structured tool output over the wire (grok auto default vs claude-code workaround)")
        grok_probe = self._probe_tool_call("M5", "grok")
        if grok_probe is None:
            return
        claude_probe = self._probe_tool_call("M5", "claude-code")
        if claude_probe is None:
            return
        grok_schema, grok_result = grok_probe
        claude_schema, claude_result = claude_probe

        problems = []
        grok_structured = grok_result.get("structuredContent")
        if grok_result.get("isError"):
            problems.append("grok: probe tool call returned isError")
        if not isinstance(grok_schema, dict):
            problems.append("grok: no outputSchema advertised for the string-returning probe tool")
        if not (isinstance(grok_structured, dict) and isinstance(grok_structured.get("result"), str)):
            problems.append("grok: structuredContent missing or not of shape {'result': str}")
        if claude_result.get("isError"):
            problems.append("claude-code: probe tool call returned isError")
        if claude_schema is not None:
            problems.append("claude-code: unexpectedly advertises an outputSchema despite structured_tool_output=false")
        if claude_result.get("structuredContent") is not None:
            problems.append("claude-code: unexpectedly returns structuredContent despite structured_tool_output=false")

        self._write_evidence(
            "M5.txt",
            f"probe tool: {STRUCTURED_OUTPUT_PROBE_TOOL}\n"
            f"grok outputSchema: {json.dumps(grok_schema)}\n"
            f"grok structuredContent keys: {sorted(grok_structured) if isinstance(grok_structured, dict) else grok_structured!r}\n"
            f"claude-code outputSchema: {json.dumps(claude_schema)}\n"
            f"claude-code structuredContent: {claude_result.get('structuredContent')!r}\n",
        )
        if problems:
            self._record("M5", Status.FAIL, "; ".join(problems))
        else:
            self._record(
                "M5",
                Status.PASS,
                "grok serves outputSchema + structuredContent({'result': str}); claude-code serves plain text only "
                "(auto-default divergence verified on the wire)",
            )

    # ------------------------------------------------------------------ phase D: hook discovery

    def check_d_hook_discovery(self) -> None:
        hooks_json_text = json.dumps(HOOKS_JSON, indent=2)

        self._section("D1 — project-scoped .grok/hooks discovery")
        hook_project = self.config.work_dir / "hookproj"
        hooks_dir = hook_project / ".grok" / "hooks"
        hooks_dir.mkdir(parents=True)
        run_command(["git", "init", "-q", "."], cwd=hook_project)
        (hooks_dir / "serena-hooks.json").write_text(hooks_json_text, encoding="utf-8")
        inspect_result = run_command([self.config.grok_bin, "inspect", "--json"], timeout=60, cwd=hook_project)
        self._write_evidence("D1-inspect.json", inspect_result.output)
        if "serena-hooks" in inspect_result.output:
            self._record("D1", Status.PASS, "grok inspect discovers the docs' hooks JSON in the project's .grok/hooks/")
        else:
            self._record(
                "D1", Status.WARN, "project hooks not visible in inspect output — possibly gated on hook trust (evidence/D1-inspect.json)"
            )
            self._finding(
                "the docs' project-scoped hooks JSON was not surfaced by 'grok inspect --json' in an untrusted project; "
                "Grok requires /hooks-trust before project hooks load (expected; documented in the Grok hooks docs section)"
            )

        self._section("D2 — global hooks directory next to the Grok config (informational)")
        global_hooks_dir = self.config.grok_config_path.parent / "hooks"
        global_hooks_file = global_hooks_dir / "serena-hooks.json"
        if global_hooks_file.exists():
            self._record("D2", Status.SKIP, f"{global_hooks_file} already exists — not probing to avoid touching user state")
            return
        global_hooks_dir.mkdir(exist_ok=True)
        global_hooks_file.write_text(hooks_json_text, encoding="utf-8")
        self._created_global_hooks_file = global_hooks_file
        inspect_result = run_command([self.config.grok_bin, "inspect", "--json"], timeout=60, cwd=self.config.work_dir / "noproject")
        self._write_evidence("D2-inspect.json", inspect_result.output)
        if "serena-hooks" in inspect_result.output:
            self._record("D2", Status.INFO, "global hooks directory IS discovered — the docs' global recommendation works")
        else:
            self._record("D2", Status.INFO, "global hooks directory NOT discovered — the docs' 'globally' wording may need correction")
            self._finding("the docs claim a global hooks file next to the Grok config works; 'grok inspect' did not surface it")
        self._cleanup_grok_state()

    # ------------------------------------------------------------------ phase C: cleanup

    def check_c1_cleanup(self) -> None:
        self._section("C1 — cleanup and baseline verification")
        self._cleanup_grok_state()
        self._cleanup_done = True
        if self._baseline_mcp_list == "":
            self._record("C1", Status.SKIP, "no baseline was captured (aborted before P3)")
            return

        backup_exists = self.config.config_backup_path.exists()
        final_list = self._grok("mcp", "list").output
        self._write_evidence("C1-final-mcp-list.txt", final_list)
        print(final_list.strip())
        if final_list == self._baseline_mcp_list:
            if not backup_exists:
                self._record("C1", Status.PASS, "mcp list matches the baseline; config was not modified (hooks-only, no backup)")
                return
            backup_matches = (
                self.config.grok_config_path.exists()
                and self.config.grok_config_path.read_bytes() == self.config.config_backup_path.read_bytes()
            )
            note = "byte-identical to the backup" if backup_matches else "differs from the backup only in formatting (mcp list matches)"
            self._record("C1", Status.PASS, f"mcp list matches the baseline; config {note}")
            self._discard_config_backup()
            return

        # the removals did not return to baseline: restore the backup outright
        if not backup_exists:
            self._record("C1", Status.FAIL, "state diverged but no config backup exists to restore — MANUAL ATTENTION")
            return
        shutil.copy2(self.config.config_backup_path, self.config.grok_config_path)
        restored_list = self._grok("mcp", "list").output
        if restored_list == self._baseline_mcp_list:
            self._record("C1", Status.PASS, "state diverged after removals; restored the config backup — baseline verified")
            self._discard_config_backup()
        else:
            self._record(
                "C1", Status.FAIL, f"could not restore the baseline — MANUAL ATTENTION, backup at {self.config.config_backup_path}"
            )

    def _discard_config_backup(self) -> None:
        """Remove the config backup once the baseline is confirmed intact, so no credential copy persists."""
        try:
            self.config.config_backup_path.unlink(missing_ok=True)
        except OSError:
            pass

    # ------------------------------------------------------------------ orchestration

    def run(self) -> int:
        """
        Runs all phases, guaranteeing Grok-side cleanup even on abort.

        :return: the process exit code (0 iff no check failed)
        """
        aborted: Optional[str] = None
        try:
            self.check_p1_environment()
            self.check_p3_baseline()
            self.check_p2_unit_smoke()
            self.check_p4_context_loads()
            self.check_h_hook_protocol()
            if self.config.hooks_only:
                for check_id in ("S1", "S2", "S3", "S4", "S5", "M1", "M2", "M3", "M4", "M5", "D1", "D2"):
                    self._record(check_id, Status.SKIP, "--hooks-only")
            else:
                self.check_s_client_setup()
                self.check_m_mcp_server()
                self.check_d_hook_discovery()
        except AbortError as e:
            aborted = str(e)
            print(f"\nABORTED: {e}")
        finally:
            self.check_c1_cleanup()

        report_path = self._write_report(aborted)
        print(f"\nreport written to {report_path}")
        failed = sum(1 for result in self.results if result.status == Status.FAIL)
        return 1 if failed or aborted else 0

    def _write_report(self, aborted: Optional[str]) -> Path:
        counts = {status: sum(1 for r in self.results if r.status == status) for status in Status}
        lines = [
            "# Grok Live Test Report",
            "",
            f"- Date: {datetime.now().isoformat(timespec='seconds')}",
            f"- Environment: {self._environment_summary or 'n/a'}",
            f"- Mode: {'hooks-only' if self.config.hooks_only else 'full'}" + (", unit tests skipped" if self.config.skip_unit else ""),
            f"- Totals: {counts[Status.PASS]} pass / {counts[Status.FAIL]} fail / {counts[Status.WARN]} warn"
            f" / {counts[Status.INFO]} info / {counts[Status.SKIP]} skipped",
            "- Cost: zero inference (no Grok session was started)",
        ]
        if aborted:
            lines.append(f"- **ABORTED**: {aborted}")
        lines += ["", "| ID | Status | Observation |", "|----|--------|-------------|"]
        lines += [f"| {r.check_id} | {r.status.value} | {r.note} |" for r in self.results]
        lines += ["", "## Findings", ""]
        lines += [f"{i}. {finding}" for i, finding in enumerate(self.findings, start=1)] or ["None."]
        lines += ["", f"Evidence: {self.config.evidence_dir}/", ""]
        report_path = self.config.work_dir / "report.md"
        report_path.write_text("\n".join(lines), encoding="utf-8")
        os.chmod(report_path, 0o600)
        return report_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Live (zero-inference) smoke test of Serena's Grok Build integration against a real grok CLI.",
        epilog="Backs up the Grok config before any change and restores the baseline afterwards; "
        "refuses to run if a 'serena' MCP entry is already registered in Grok.",
    )
    parser.add_argument("--hooks-only", action="store_true", help="run only the pure-local checks; never touches the Grok configuration")
    parser.add_argument("--skip-unit", action="store_true", help="skip the pytest smoke run (phase P2)")
    parser.add_argument("--work-dir", help="directory for evidence and reports (default: a fresh private mkdtemp under the system tmp)")
    parser.add_argument("--repo-root", help="Serena repository root (default: derived from this script's location)")
    parser.add_argument("--serena-bin", help="serena executable under test (default: <repo>/.venv)")
    parser.add_argument("--serena-hooks-bin", help="serena-hooks executable under test (default: <repo>/.venv)")
    parser.add_argument("--grok-bin", help="grok executable (default: resolved from PATH)")
    parser.add_argument(
        "--grok-config",
        help="Grok user config file, for nonstandard Grok homes (default: ~/.grok/config.toml). NOT an isolation "
        "mechanism: 'grok mcp' has no alternate-config option, so this must be the config the CLI actually uses — "
        "verified against 'grok mcp list' at startup, mismatch aborts before any mutation",
    )
    args = parser.parse_args()

    try:
        config = LiveTestConfig.from_args(args)
    except AbortError as e:
        print(f"ABORTED: {e}")
        return 1
    print(f"work directory: {config.work_dir}")
    return GrokLiveTest(config).run()


if __name__ == "__main__":
    sys.exit(main())
