def _check_pascal_available() -> bool:
    """Check if Pascal language server (pasls) is available.

    Note: pasls will be auto-downloaded if not present, so Pascal
    support is always available.
    """
    return True


PASCAL_AVAILABLE = _check_pascal_available()


def is_pascal_available() -> bool:
    """Return True if Pascal language server can be used."""
    return PASCAL_AVAILABLE
