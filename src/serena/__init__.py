__version__ = "2025-04-07"


def serena_root_path() -> str:
    from pathlib import Path

    return str(Path(__file__).parent.parent.parent.absolute())


def serena_version() -> str:
    """
    :return: the version of the package, including git status if available.
    """
    version = __version__
    try:
        from sensai.util.git import git_status
        from sensai.util.logging import LoggingDisabledContext

        with LoggingDisabledContext():
            git_status = git_status()
        version += f"-{git_status.commit[:8]}"
        if not git_status.is_clean:
            version += "-dirty"
    except:
        pass
    return version
