import logging
import os
import sys
import threading
import time
from typing import Any

import psutil
import webview
from PIL import Image

log = logging.getLogger(__name__)


class WebViewWithTray:
    """
    Web view window with optional system tray.
    """

    DEBUG = False

    def __init__(
        self,
        url: str,
        *,
        title: str,
        start_minimized: bool = False,
        width: int = 1400,
        height: int = 900,
        tray: bool = False,
        parent_process_id: int | None = None,
        app_id: str | None = None,
        app_icon_path: str | None = None,
        tray_icon_path: str | None = None,
    ):
        """
        :param url: the URL to be show in the web view
        :param title: the title of the window
        :param start_minimized: whether to show the window minimised on startup (if `tray` is enabled, minimised to tray)
        :param width: width of the window in pixels
        :param height: height of the window in pixels
        :param tray: whether to enable the system tray icon and functionality.
            If this is enabled, closing the window will minimise it to tray instead of quitting the application.
        :param parent_process_id: the PID of the parent process to monitor; if specified, the viewer will automatically
            shut itself down when the parent process exits.
        :param app_id: the application ID to use for the viewer to ensure that the window is grouped separately (with separate
            icon) in the taskbar
        """
        self._url = url
        self._use_tray = tray
        self._title = title
        self._start_minimized = start_minimized
        self._parent_process_id = parent_process_id
        self._app_id = app_id

        self.window: webview.Window
        self._tray_icon: Any
        self._quitting = False
        self._app_icon_path = app_icon_path
        self._tray_icon_path = tray_icon_path

        # Create hidden to avoid flash; show/restore/minimize in start callback.
        window = webview.create_window(
            self._title,
            self._url,
            width=width,
            height=height,
            hidden=self._start_minimized,
            text_select=True,
            zoomable=True,
        )
        assert window is not None
        self.window = window

    def run(self) -> None:
        # set app id (avoid app being lumped together with other Python-based apps in Windows taskbar)
        if self._app_id is not None and sys.platform == "win32":
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("oraios.serena")

        if self._use_tray:
            self.window.events.closing += self._on_closing
            self._start_tray()

        def _start_callback() -> None:
            if self._start_minimized:
                self._hide_window()
            else:
                self._show_window()

        # start a thread to monitor the parent process
        if self._parent_process_id is not None:
            threading.Thread(target=self._monitor_parent_process, daemon=True).start()

        webview.start(_start_callback, icon=self._app_icon_path)

    def _monitor_parent_process(self) -> None:
        """
        Monitors the parent process and shuts down the dashboard viewer if the parent process exits.
        """
        pid = self._parent_process_id
        log.info("Starting parent process monitor thread (parent_pid=%d, pid=%s)", pid, os.getpid())
        try:
            parent_process = psutil.Process(pid)
            while parent_process.is_running():
                time.sleep(1)
        except psutil.NoSuchProcess:
            pass  # Parent process already exited
        log.info("Parent process (pid=%d) has exited, shutting down dashboard viewer", pid)
        self._terminate()

    def _show_window(self) -> None:
        if not self.window:
            return

        if sys.platform == "darwin":
            from PyObjCTools.AppHelper import callAfter

            callAfter(self._show_window_on_macos)
        else:
            self.window.show()
            self.window.restore()

    def _hide_window(self) -> None:
        if not self.window:
            return

        if sys.platform == "darwin":
            from PyObjCTools.AppHelper import callAfter

            callAfter(self._hide_window_on_macos)
        else:
            self.window.hide()

    def _show_window_on_macos(self) -> None:
        from AppKit import (
            NSApplication,
            NSApplicationActivationPolicyRegular,
        )
        from PyObjCTools.AppHelper import callLater

        ns_app = NSApplication.sharedApplication()
        ns_app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        self._set_macos_app_icon(ns_app)
        ns_app.unhide_(None)
        ns_app.activateIgnoringOtherApps_(True)
        # Give the status item menu a beat to close before restoring the window.
        callLater(0.1, self._restore_window_on_macos)

    def _restore_window_on_macos(self) -> None:
        self.window.show()
        self.window.restore()

    def _hide_window_on_macos(self) -> None:
        from AppKit import (
            NSApplication,
            NSApplicationActivationPolicyAccessory,
        )

        self.window.hide()
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    def _set_macos_app_icon(self, ns_app: Any) -> None:
        if not self._app_icon_path:
            return

        from AppKit import NSImage

        ns_image = NSImage.alloc().initByReferencingFile_(self._app_icon_path)
        if ns_image is not None:
            ns_app.setApplicationIconImage_(ns_image)

    def _on_closing(self) -> bool:
        """Intercept window close: hide window instead of quitting (macOS standard behavior)."""
        if self._quitting:
            return True
        self._hide_window()
        return False  # prevent the window from actually closing

    def _terminate(self) -> None:
        """
        Terminates the viewer application and the tray icon
        """
        self._quitting = True
        try:
            if self._tray_icon:
                self._tray_icon.stop()
        finally:
            if self.window:
                self.window.destroy()

    def _start_tray(self) -> None:
        # import pystray locally, because the import fails when there is no display!
        import pystray
        from pystray import MenuItem as Item
        from pystray._base import Icon as TrayIcon

        icon_img = None
        if self._tray_icon_path is not None:
            icon_img = Image.open(self._tray_icon_path)

        def show(_icon: TrayIcon, _item: Item) -> None:
            self._show_window()

        def hide(_icon: TrayIcon, _item: Item) -> None:
            self._hide_window()

        def quit_app(_icon: TrayIcon, _item: Item) -> None:
            self._terminate()

        menu = pystray.Menu(
            Item("Open", show, default=True),
            Item("Hide", hide),
            Item("Quit", quit_app),
        )

        kwargs: dict[str, Any] = {}
        if sys.platform == "darwin":
            # Passing darwin_nsapplication integrates pystray with the NSApplication
            # run loop that webview.start() is about to enter.  sharedApplication()
            # is idempotent; pywebview will reuse the same singleton.
            from AppKit import NSApplication

            kwargs["darwin_nsapplication"] = NSApplication.sharedApplication()

        self._tray_icon = pystray.Icon("dashboard_viewer", icon_img, self._title, menu, **kwargs)

        # On Windows/Linux, run_detached spawns pystray's own internal thread and
        # returns immediately.  On macOS it hooks into the NSApplication run loop
        # that webview.start() is about to enter (run_detached is always called
        # before webview.start() on macOS — see run()).
        self._tray_icon.run_detached()
