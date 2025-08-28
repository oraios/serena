"""Go test utilities for checking gopls availability."""

import subprocess


def _get_gopls_version():
    """Get the installed gopls version or None if not found."""
    try:
        result = subprocess.run(["gopls", "version"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        return None
    return None


def check_gopls_available():
    """Check if gopls is available and return a tuple (is_unavailable, reason)."""
    try:
        gopls_version = _get_gopls_version()
        if not gopls_version:
            return True, "gopls is not installed"
        return False, ""
    except Exception as e:
        return True, f"Error checking gopls: {e}"


GOPLS_UNAVAILABLE, GOPLS_UNAVAILABLE_REASON = check_gopls_available()
