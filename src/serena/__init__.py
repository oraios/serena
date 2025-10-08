__version__ = "0.1.4"

import logging

# Import patches to install import hooks for patched dependencies
# This must happen before any other imports that might use patched packages
import serena.patches  # noqa: F401

log = logging.getLogger(__name__)


def serena_version() -> str:
    """
    :return: the version of the package, including git status if available.
    """
    from serena.util.git import get_git_status

    version = __version__
    try:
        git_status = get_git_status()
        if git_status is not None:
            version += f"-{git_status.commit[:8]}"
            if not git_status.is_clean:
                version += "-dirty"
    except:
        pass
    return version
