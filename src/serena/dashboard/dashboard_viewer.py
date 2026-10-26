# SPDX-License-Identifier: GPL-3.0-or-later

import subprocess
import sys
import threading
from pathlib import Path

from sensai.util import logging

from serena.config.serena_paths import SerenaPaths
from serena.constants import SERENA_DASHBOARD_DIR
from serena.util.pywebview import WebViewWithTray

log = logging.getLogger(__name__)


def open_url_in_browser(url: str, use_subprocess: bool = False) -> None:
    """
    Opens the given URL in the user's default web browser,
    optionally using a subprocess to ensure that no output is written to stdout
    (highly problematic when run within a stdio MCP server context)

    :param url: the URL to open
    :param use_subprocess: whether to use a subprocess to opening the URL, making stdio contamination impossible
    """
    if use_subprocess:
        # Use a subprocess to avoid any output from webbrowser.open being written to stdout
        try:
            p = subprocess.Popen(
                [sys.executable, "-c", f"import webbrowser; webbrowser.open({url!r})"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=False,
            )
            threading.Thread(target=p.wait, daemon=True).start()
        except Exception as e:
            # Subprocess creation can fail in rare cases (e.g. on some Linux systems; possibly subprocess/glibc bug)
            # See #1363
            log.error("Failed to open URL (%s) in subprocess; %s", url, e)
    else:
        import webbrowser

        webbrowser.open(url)


class SerenaDashboardViewer(WebViewWithTray):
    """
    Minimal pywebview wrapper that opens a dashboard in a native window with optional system tray.
    """

    DEBUG = False

    def __init__(
        self,
        url: str,
        *,
        width: int = 1400,
        height: int = 900,
        start_minimized: bool = False,
        parent_process_id: int | None = None,
        tray: bool = True,
    ):
        """
        :param url: the URL to open
        :param width: the width of the window
        :param height: the height of the window
        :param start_minimized: whether to start the window minimized (to the tray if tray is enabled)
        :param parent_process_id: the process ID of the parent Serena agent process, which is monitored for termination,
            automatically closing the dashboard when the parent process dies
        :param tray: whether to use a system tray icon (which the app minimizes to when the window is closed)
        """
        dashboard_path = Path(SERENA_DASHBOARD_DIR)

        # .ico is Windows-only; macOS expects a PNG for the window/dock icon.
        app_icon_filename = "serena.ico" if sys.platform == "win32" else "serena-icon-1024-mac.png"
        app_icon_path = str(dashboard_path / app_icon_filename)

        tray_icon_filename = "serena-icon-tray-mac.png" if sys.platform == "darwin" else "serena-icon-48.png"
        tray_icon_path = str(dashboard_path / tray_icon_filename)

        super().__init__(
            url,
            title="Serena Dashboard",
            tray=tray,
            width=width,
            height=height,
            start_minimized=start_minimized,
            parent_process_id=parent_process_id,
            app_id="oraios.serena",
            app_icon_path=app_icon_path,
            tray_icon_path=tray_icon_path,
        )

    @staticmethod
    def is_current_platform_supported() -> bool:
        """
        :return: whether the current platform supports the native dashboard viewer (and tray manager).
        """
        # supported on Windows and macOS; Linux support is problematic
        # (see https://github.com/oraios/serena/pull/1117#issuecomment-4128753943)
        supported_platforms = [
            "win32",
            "darwin",
        ]
        return sys.platform in supported_platforms

    def run(self) -> None:
        if self.DEBUG:
            logging.configure(level=logging.DEBUG, stream=sys.stderr)
            logging.add_file_logger(SerenaPaths().get_next_log_file_path("dashboard-viewer"))

        super().run()
