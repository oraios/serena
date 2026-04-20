"""Vue language server tests."""

import shutil


def _test_npm_available() -> str:
    """Test if npm is available and return error reason if not."""
    # Check if npm is installed
    if not shutil.which("npm"):
        return "npm is not installed or not in PATH"
    return ""  # No error, npm is available


NPM_UNAVAILABLE_REASON = _test_npm_available()
NPM_UNAVAILABLE = bool(NPM_UNAVAILABLE_REASON)
