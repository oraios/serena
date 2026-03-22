import platform
import shlex
import subprocess


def subprocess_kwargs() -> dict:
    """
    Returns a dictionary of keyword arguments for subprocess calls, adding platform-specific
    flags that we want to use consistently.
    """
    kwargs = {}
    if platform.system() == "Windows":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore
    return kwargs


def quote_arg(arg: str) -> str:
    """
    Quotes a shell argument to prevent interpretation of metacharacters.

    Uses :func:`shlex.quote` on POSIX systems for proper escaping of all
    shell-special characters. On Windows, wraps arguments containing spaces
    in double quotes (Windows shell does not interpret single-quoted strings).
    """
    if platform.system() == "Windows":
        if " " not in arg:
            return arg
        return f'"{arg}"'
    return shlex.quote(arg)
