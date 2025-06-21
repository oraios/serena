__version__ = "2025-05-21"

import logging

log = logging.getLogger(__name__)


def serena_version() -> str:
    """
    :return: the version of the package, including git status if available.
    """
    from serena.util.git import get_git_status

    version = __version__
    try:
        git_status = get_git_status()
        version += f"-{git_status.commit[:8]}"
        if not git_status.is_clean:
            version += "-dirty"
    except:
        pass
    return version
