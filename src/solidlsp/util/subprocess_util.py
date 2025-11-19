import platform
import subprocess


def subprocess_kwargs():
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
    Adds quotes around an argument if it contains spaces.
    """
    if " " not in arg:
        return arg
    return f'"{arg}"'
