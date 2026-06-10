import shutil


def _test_dexter_available() -> str:
    """Test if Dexter is available and return error reason if not."""
    if shutil.which("dexter") is None:
        return "dexter binary not found in PATH (install from https://github.com/remoteoss/dexter)"
    return ""  # No error, Dexter should be available


DEXTER_UNAVAILABLE_REASON = _test_dexter_available()
DEXTER_UNAVAILABLE = bool(DEXTER_UNAVAILABLE_REASON)
