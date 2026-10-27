# SPDX-License-Identifier: GPL-3.0-or-later

import json
import multiprocessing
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import psutil
from flask import Flask, request
from PIL import Image
from sensai.util import logging

from serena.config.serena_paths import SerenaPaths
from serena.constants import SERENA_DASHBOARD_DIR, SerenaPorts
from serena.dashboard.dashboard_viewer import SerenaDashboardViewer, open_url_in_browser

log = logging.getLogger(__name__)


@dataclass
class TrayManagedInstance:
    """A registered Serena dashboard instance managed by the tray manager."""

    port: int
    """the port on which the dashboard API is listening"""

    parent_process: psutil.Process
    """the process of the Serena agent owning this dashboard instance"""

    dashboard_url: str
    """the full URL to the dashboard frontend"""

    project: str | None
    """the name of the active project, or None if no project is activated"""

    started_at: str
    """ISO 8601 timestamp of when the agent instance was started"""


class SerenaDashboardTrayManager:
    """
    Singleton process managing a system tray icon for all Serena dashboard instances.

    Runs a Flask backend on a fixed port and displays a single tray icon that
    aggregates all running Serena instances. Individual dashboard viewers are
    spawned on demand when the user clicks a menu item.

    The manager is started as a detached process by the first Serena agent that
    needs it and terminates automatically when no dashboard instances remain.
    """

    DEBUG = False

    PORT = SerenaPorts.TRAY_MANAGER_PORT

    HOST = "127.0.0.1"
    """listen address (local only)"""

    TRUSTED_HOSTS = ["localhost", "127.0.0.1"]

    ALIVE_CHECK_INTERVAL_SECONDS = 3
    """interval in seconds between alive checks of registered instances"""

    def __init__(self) -> None:
        """
        NOTE: This constructor is called in `ensure_running` (string execution)
        """
        import pystray

        self._instances: dict[int, TrayManagedInstance] = {}
        self._lock = threading.Lock()
        self._tray_icon: Optional["pystray.Icon"] = None
        self._alive_check_use_pid = True
        """
        whether to use the process ID for alive checks of registered instances.
        If True, the manager will check whether the process with the registered PID is still running.
        If False, the manager will perform an HTTP request to the instance's heartbeat endpoint to check
        if it's alive.
        """
        self._app = Flask(self.__class__.__name__)
        self._app.config["TRUSTED_HOSTS"] = self.TRUSTED_HOSTS
        self._use_pywebview = False
        """
        whether to use pywebview-based viewer applications (separate child processes)
        for opening dashboards; if False, open them directly in the user's default web browser.
        """
        self._setup_routes()

    def _setup_routes(self) -> None:
        @self._app.route("/health", methods=["GET"])
        def health() -> dict[str, str]:
            return {"status": "alive"}

        @self._app.route("/register", methods=["POST"])
        def register() -> dict[str, str]:
            data = request.get_json()
            instance = TrayManagedInstance(
                port=data["port"],
                parent_process=psutil.Process(data["pid"]),
                dashboard_url=data["dashboard_url"],
                project=data.get("project"),
                started_at=data["started_at"],
            )
            log.info("Registering instance on port %d (project=%s)", instance.port, instance.project)
            with self._lock:
                self._instances[instance.port] = instance
            self._update_menu()

            # open a viewer immediately if requested
            if data.get("open_viewer", False):
                self._open_dashboard(instance)

            return {"status": "registered"}

        @self._app.route("/update_project", methods=["POST"])
        def update_project() -> dict[str, str]:
            data = request.get_json()
            port = data["port"]
            project = data.get("project")
            with self._lock:
                if port in self._instances:
                    self._instances[port].project = project
            self._update_menu()
            log.info("Updated project for instance on port %d to '%s'", port, project)
            return {"status": "updated"}

        @self._app.route("/unregister", methods=["POST"])
        def unregister() -> dict[str, str]:
            data = request.get_json()
            port = data["port"]
            with self._lock:
                self._instances.pop(port, None)
            self._update_menu()
            log.info("Unregistered instance on port %d", port)
            return {"status": "unregistered"}

    @staticmethod
    def _run_in_ui_thread(fn: Callable[[], None]) -> None:
        """
        Runs a UI mutation in the thread in which the platform's UI toolkit requires it to run (where necessary).

        On macOS, AppKit demands that mutations of the status item happen on the main thread, and
        recent macOS versions terminate the process with SIGTRAP when they do not. The tray manager
        reaches such mutations from Flask request handlers and from the alive-check thread, so the
        call has to be marshalled. On other platforms it is made directly.

        :param fn: the UI mutation to run
        """
        if sys.platform == "darwin":
            from PyObjCTools import AppHelper  # ty: ignore[unresolved-import]

            AppHelper.callAfter(fn)
        else:
            fn()

    def _update_menu(self) -> None:
        if self._tray_icon:
            self._run_in_ui_thread(self._tray_icon.update_menu)

    def _build_menu_items(self) -> tuple[Any, ...]:
        """
        Callable that returns the current tray menu items.

        Invoked dynamically by pystray each time the menu is shown.
        When there is exactly one instance, it is marked as the default action
        so that a left-click on the tray icon opens the viewer immediately.
        When there are multiple instances, a hidden default item forces the menu
        to appear on left-click (Windows only; macOS always shows the menu).
        """
        from pystray import MenuItem as Item

        with self._lock:
            instances = list(self._instances.values())

        if not instances:
            return (Item("No instances", None, enabled=False),)

        # determine whether a single-instance shortcut applies
        is_single = len(instances) == 1

        items: list[Any] = []

        # for multi-instance: add a hidden default item that opens the menu on left-click
        if not is_single:

            def _force_show_menu(icon: Any, _item: Any) -> None:
                if hasattr(icon, "_show_menu"):
                    icon._show_menu()

            items.append(Item("Instances", _force_show_menu, default=True, visible=False))

        for inst in sorted(instances, key=lambda i: i.started_at):
            label = f"{inst.project or 'SerenaAgent'} ({inst.started_at})"

            # closure to capture the current instance
            def _make_callback(instance: TrayManagedInstance) -> Callable:
                def _callback(_icon: Any, _item: Any) -> None:
                    self._open_dashboard(instance)

                return _callback

            items.append(Item(label, _make_callback(inst), default=is_single))

        return tuple(items)

    def _open_dashboard(self, instance: TrayManagedInstance) -> None:
        """Opens the dashboard of the given instance."""
        if self._use_pywebview:
            # spawn pywebview process showing the dashboard
            process = multiprocessing.Process(
                target=self._run_viewer,
                args=(instance.dashboard_url,),
                daemon=True,
            )
            process.start()
        else:
            open_url_in_browser(instance.dashboard_url)

    @staticmethod
    def _run_viewer(url: str) -> None:
        """Process target for running a dashboard viewer window."""
        SerenaDashboardViewer(url, tray=False, start_minimized=False).run()

    def _alive_check_loop(self) -> None:
        """Periodically check whether registered instances are still reachable.

        Removes unreachable instances and terminates the manager when none remain.
        """
        time.sleep(max(1, 5 - self.ALIVE_CHECK_INTERVAL_SECONDS))  # initial delay to allow instances to start and register

        while True:
            time.sleep(self.ALIVE_CHECK_INTERVAL_SECONDS)

            try:
                dead_ports: list[int] = []

                if self._alive_check_use_pid:
                    with self._lock:
                        ports_and_processes = [(port, inst.parent_process) for port, inst in self._instances.items()]

                    dead_ports = []
                    for port, process in ports_and_processes:
                        is_dead = False
                        try:
                            if not process.is_running():
                                is_dead = True
                        except psutil.NoSuchProcess:
                            # parent process already exited
                            is_dead = True
                        if is_dead:
                            dead_ports.append(port)
                else:
                    # collect ports to check
                    with self._lock:
                        ports_to_check = list(self._instances.keys())

                    # probe each instance
                    for port in ports_to_check:
                        try:
                            url = f"http://127.0.0.1:{port}/heartbeat"
                            req = urllib.request.Request(url, method="GET")
                            urllib.request.urlopen(req, timeout=1)
                        except Exception:
                            dead_ports.append(port)

                # remove dead instances
                if dead_ports:
                    with self._lock:
                        for port in dead_ports:
                            self._instances.pop(port, None)
                            log.info("Removed unreachable instance on port %d", port)
                    self._update_menu()

                # terminate if no instances remain
                with self._lock:
                    remaining = len(self._instances)
                if remaining == 0:
                    log.info("No dashboard instances remaining; shutting down tray manager")
                    if self._tray_icon is not None:
                        self._tray_icon.stop()
                    return

            except Exception as e:
                log.error("Error during alive check loop: %s", e, exc_info=e)

    def run(self) -> None:
        """Run the tray manager (blocking). Starts Flask, alive-check thread, and tray icon."""
        import pystray

        if self.DEBUG:
            logging.configure(level=logging.DEBUG, stream=sys.stderr)
            logging.add_file_logger(SerenaPaths().get_next_log_file_path("tray-manager"))

        log.info("Starting tray manager")

        dashboard_path = Path(SERENA_DASHBOARD_DIR)

        # select the appropriate icon for the platform
        icon_filename = "serena-icon-tray-mac.png" if sys.platform == "darwin" else "serena-icon-48.png"
        icon_img = Image.open(dashboard_path / icon_filename)

        # start Flask in a background thread
        flask_thread = threading.Thread(
            target=lambda: self._app.run(host=self.HOST, port=self.PORT, debug=False, use_reloader=False, threaded=True),
            daemon=True,
        )
        flask_thread.start()

        # start alive-check in a background thread
        alive_thread = threading.Thread(target=self._alive_check_loop, daemon=True)
        alive_thread.start()

        # set up tray icon with a dynamic menu (callable returns items on each open)
        kwargs: dict[str, Any] = {}
        if sys.platform == "darwin":
            from AppKit import NSApplication, NSApplicationActivationPolicyAccessory  # ty: ignore[unresolved-import]  (macOS only)

            nsapp = NSApplication.sharedApplication()
            # run as an accessory app so that only the menu bar icon is shown (no Dock icon)
            nsapp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
            kwargs["darwin_nsapplication"] = nsapp

        self._tray_icon = pystray.Icon(
            "serena_tray_manager",
            icon_img,
            "Serena",
            menu=pystray.Menu(self._build_menu_items),
            **kwargs,
        )

        # blocks until stop() is called
        self._tray_icon.run()

    # ------------------------------------------------------------------
    # Class-level helpers (used by agents to interact with the manager)
    # ------------------------------------------------------------------

    @classmethod
    def is_current_platform_supported(cls) -> bool:
        """
        :return: whether the current platform supports the tray manager
        """
        # supported_platforms = ["win32", "darwin"]
        # return sys.platform in supported_platforms
        # TODO: Enable all platforms for the time being for users to try out (only Windows tested)
        return True

    @classmethod
    def is_running(cls) -> bool:
        """
        :return: True if a tray manager process is already listening on the fixed port
        """
        try:
            url = f"http://{cls.HOST}:{cls.PORT}/health"
            req = urllib.request.Request(url, method="GET")
            urllib.request.urlopen(req, timeout=2)
            return True
        except Exception:
            return False

    @classmethod
    def ensure_running(cls) -> None:
        """Ensure a tray manager process is running, starting one if necessary."""
        log.info("Ensuring dashboard tray manager availability")
        if cls.is_running():
            log.info("Dashboard tray manager is already running")
            return

        # spawn a detached process
        log.info("Starting new dashboard tray manager process")
        cmd = [
            sys.executable,
            "-c",
            "from serena.dashboard.dashboard_tray_manager import SerenaDashboardTrayManager; SerenaDashboardTrayManager().run()",
        ]
        kwargs: dict[str, Any] = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            # CREATE_NO_WINDOW suppresses the console; CREATE_NEW_PROCESS_GROUP
            # isolates the child from the parent's Ctrl+C group.
            # Note: DETACHED_PROCESS must NOT be combined with CREATE_NO_WINDOW.
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            CREATE_NO_WINDOW = 0x08000000
            kwargs["creationflags"] = CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True

        subprocess.Popen(cmd, **kwargs)

        # wait for the manager to become available
        for _ in range(30):
            time.sleep(0.1)
            if cls.is_running():
                log.info("Dashboard tray manager started successfully")
                return
        log.warning("Dashboard tray manager did not start within the expected time")

    @classmethod
    def register_instance(cls, port: int, dashboard_url: str, project: str | None, started_at: str, open_viewer: bool = False) -> None:
        """Register a dashboard instance with the running tray manager.

        :param port: the port of the dashboard API (used for alive checks)
        :param dashboard_url: the full URL to the dashboard frontend
        :param project: the currently active project name, or None
        :param started_at: ISO 8601 timestamp of when the agent was started
        :param open_viewer: whether the tray manager should immediately open a viewer for this instance
        """
        url = f"http://{cls.HOST}:{cls.PORT}/register"
        data = json.dumps(
            {
                "port": port,
                "pid": os.getpid(),
                "dashboard_url": dashboard_url,
                "project": project,
                "started_at": started_at,
                "open_viewer": open_viewer,
            }
        ).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=2)
        except Exception as e:
            log.warning("Failed to register with tray manager: %s", e)

    @classmethod
    def update_project(cls, port: int, project: str | None) -> None:
        """Notify the tray manager of a project change for the given instance.

        :param port: the port of the dashboard API
        :param project: the new active project name, or None
        """
        url = f"http://{cls.HOST}:{cls.PORT}/update_project"
        data = json.dumps({"port": port, "project": project}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=2)
        except Exception as e:
            log.warning("Failed to update project with tray manager: %s", e)

    @classmethod
    def unregister_instance(cls, port: int) -> None:
        """Unregister a dashboard instance from the tray manager.

        :param port: the port of the dashboard API to unregister
        """
        url = f"http://{cls.HOST}:{cls.PORT}/unregister"
        data = json.dumps({"port": port}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=2)
        except Exception as e:
            log.warning("Failed to unregister from tray manager: %s", e)
