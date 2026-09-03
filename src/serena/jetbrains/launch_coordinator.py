"""
Coordinates the launching of JetBrains IDE instances triggered by Serena's own
`jetbrains_launch_command`, so that concurrent Serena sessions activating different
projects at (nearly) the same time do not race each other into the same IDE launch.
"""

import hashlib
import logging
import subprocess
import tempfile
import time
from pathlib import Path

from filelock import FileLock, Timeout

from serena.jetbrains import jetbrains_plugin_client
from serena.project import Project
from solidlsp.util import subprocess_util

log = logging.getLogger(__name__)

LOCK_ACQUIRE_TIMEOUT = 90.0
"""
How long a session waits for another session's IDE launch (for the same launch command) to
finish before giving up on launching its own instance.
"""

PLUGIN_SERVER_WAIT_TIMEOUT = 60.0
"""How long to poll for the plugin server to become reachable after the launch command exits."""

PLUGIN_SERVER_POLL_INTERVAL = 1.0
"""The interval at which we poll for the plugin server while waiting for it to come up."""


def _lock_path_for_launch_command(launch_command: str) -> Path:
    """
    :param launch_command: the configured `jetbrains_launch_command`
    :return: a stable, cross-process lock file path for the given launch command, so that
        concurrent Serena sessions configured with the same launch command serialize on the
        same file regardless of which project each of them is activating
    """
    digest = hashlib.sha256(launch_command.encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"serena-jetbrains-launch-{digest}.lock"


def find_plugin_server(project: Project) -> "jetbrains_plugin_client.JetBrainsPluginClient | None":
    """
    :param project: the project to find a matching, already-running plugin server for
    :return: the matching plugin server client, or None if none is currently reachable
    """
    try:
        return jetbrains_plugin_client.JetBrainsPluginClient.from_project(project, log_warning=False)
    except jetbrains_plugin_client.ServerNotFoundError:
        return None


def launch_and_wait_for_plugin_server(
    project: Project,
    launch_command: str,
    lock_acquire_timeout: float = LOCK_ACQUIRE_TIMEOUT,
    plugin_server_wait_timeout: float = PLUGIN_SERVER_WAIT_TIMEOUT,
    plugin_server_poll_interval: float = PLUGIN_SERVER_POLL_INTERVAL,
) -> None:
    """
    Launches the JetBrains IDE for `project` via `launch_command`, serialized across concurrent
    Serena sessions that share the same launch command, and waits for the plugin server to
    become reachable before returning.

    Without serialization, several sessions activating different projects at once each
    independently find no running plugin server and race the same launch command against the
    same IDE config directory; only one IDE process wins the JetBrains-side directory lock, and
    the others fail with a native modal dialog that never surfaces as a subprocess exit code.
    Re-checking for the plugin server both before and after acquiring the lock means every
    session but the first either finds the IDE already launching (and waits for it here, rather
    than in a failed tool call) or finds it already serving (and returns immediately).

    :param project: the project being activated
    :param launch_command: the configured `jetbrains_launch_command`
    :param lock_acquire_timeout: how long to wait for another session's launch to finish before
        giving up on launching our own instance
    :param plugin_server_wait_timeout: how long to poll for the plugin server to become
        reachable after the launch command exits
    :param plugin_server_poll_interval: the interval at which to poll while waiting
    """
    lock = FileLock(str(_lock_path_for_launch_command(launch_command)), timeout=lock_acquire_timeout)
    try:
        with lock:
            if find_plugin_server(project) is not None:
                # another session launched the IDE while we were waiting for the lock
                return

            cmd = subprocess_util.convert_shell_cmd([launch_command, project.project_root])
            log.info("Launching IDE with command: %s", cmd)
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            stdout, stderr = p.communicate()
            if p.returncode != 0:
                log.error("Failed to launch JetBrains IDE: %s", stderr.decode("utf-8"))
                return

            deadline = time.monotonic() + plugin_server_wait_timeout
            while True:
                if find_plugin_server(project) is not None:
                    return
                if time.monotonic() >= deadline:
                    log.warning(
                        "JetBrains IDE launch command exited but no Serena plugin server became reachable "
                        "for project %s within %.0fs; the IDE may still be starting.",
                        project.project_name,
                        plugin_server_wait_timeout,
                    )
                    return
                time.sleep(plugin_server_poll_interval)
    except Timeout:
        log.warning(
            "Timed out after %.0fs waiting for another Serena session's JetBrains IDE launch to finish "
            "for project %s; not launching a second instance.",
            lock_acquire_timeout,
            project.project_name,
        )
