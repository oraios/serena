import shutil


def _check_pascal_available() -> bool:
    """Check if Pascal language server (pasls) or Free Pascal Compiler (fpc) is available."""
    # Check for pasls in PATH
    if shutil.which("pasls"):
        return True
    # Check for fpc (required to build pasls)
    if shutil.which("fpc"):
        return True
    return False


PASCAL_AVAILABLE = _check_pascal_available()


def is_pascal_available() -> bool:
    """Return True if Pascal language server can be used."""
    return PASCAL_AVAILABLE
