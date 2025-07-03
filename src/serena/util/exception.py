import os
import sys

from serena.agent import log


def is_headless_environment() -> bool:
    """
    Detect if we're running in a headless environment where GUI operations would fail.

    Returns True if:
    - No DISPLAY variable on Linux/Unix
    - Running in SSH session
    - Running in WSL without X server
    - Running in Docker container
    """
    # Check if we're on Windows - GUI usually works there
    if sys.platform == "win32":
        return False

    # Check for DISPLAY variable (required for X11)
    if not os.environ.get("DISPLAY"):
        return True

    # Check for SSH session
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT"):
        return True

    # Check for common CI/container environments
    if os.environ.get("CI") or os.environ.get("CONTAINER") or os.path.exists("/.dockerenv"):
        return True

    # Check for WSL
    if "microsoft" in os.uname().release.lower():
        # In WSL, even with DISPLAY set, X server might not be running
        # This is a simplified check - could be improved
        return True

    return False


def show_fatal_exception_safe(e: Exception) -> None:
    """
    Shows the given exception in the GUI log viewer on the main thread and ensures that the exception is logged or at
    least printed to stderr.
    """
    # Log the error and print it to stderr
    log.error(f"Fatal exception: {e}", exc_info=e)
    print(f"Fatal exception: {e}", file=sys.stderr)

    # Don't attempt GUI in headless environments
    if is_headless_environment():
        log.debug("Skipping GUI error display in headless environment")
        return

    # attempt to show the error in the GUI
    try:
        # NOTE: The import can fail on macOS if Tk is not available (depends on Python interpreter installation, which uv
        #   used as a base); while tkinter as such is always available, its dependencies can be unavailable on macOS.
        from serena.gui_log_viewer import show_fatal_exception

        show_fatal_exception(e)
    except Exception as gui_error:
        log.debug(f"Failed to show GUI error dialog: {gui_error}")
