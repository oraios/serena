__version__ = "1.2.0"

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
        if git_status is not None:
            version += f"-{git_status.commit[:8]}"
            if not git_status.is_clean:
                version += "-dirty"
    except:
        pass
    return version


def _init_log_configuration() -> None:
    from sensai.util import logging

    def _configure() -> None:
        logging.getLogger("PIL").setLevel(logging.WARNING)

    logging.set_configure_callback(_configure)


_init_log_configuration()
