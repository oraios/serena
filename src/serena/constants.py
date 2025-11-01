from pathlib import Path

_repo_root_path = Path(__file__).parent.parent.parent.resolve()
_serena_pkg_path = Path(__file__).parent.resolve()

SERENA_MANAGED_DIR_NAME = ".serena"
_serena_in_home_managed_dir = Path.home() / ".serena"

SERENA_MANAGED_DIR_IN_HOME = str(_serena_in_home_managed_dir)

# TODO: Path-related constants should be moved to SerenaPaths; don't add further constants here.
REPO_ROOT = str(_repo_root_path)
PROMPT_TEMPLATES_DIR_INTERNAL = str(_serena_pkg_path / "resources" / "config" / "prompt_templates")
PROMPT_TEMPLATES_DIR_IN_USER_HOME = str(_serena_in_home_managed_dir / "prompt_templates")
SERENAS_OWN_CONTEXT_YAMLS_DIR = str(_serena_pkg_path / "resources" / "config" / "contexts")
"""The contexts that are shipped with the Serena package, i.e. the default contexts."""
USER_CONTEXT_YAMLS_DIR = str(_serena_in_home_managed_dir / "contexts")
"""Contexts defined by the user. If a name of a context matches a name of a context in SERENAS_OWN_CONTEXT_YAMLS_DIR, the user context will override the default one."""
SERENAS_OWN_MODE_YAMLS_DIR = str(_serena_pkg_path / "resources" / "config" / "modes")
"""The modes that are shipped with the Serena package, i.e. the default modes."""
USER_MODE_YAMLS_DIR = str(_serena_in_home_managed_dir / "modes")
"""Modes defined by the user. If a name of a mode matches a name of a mode in SERENAS_OWN_MODE_YAMLS_DIR, the user mode will override the default one."""
INTERNAL_MODE_YAMLS_DIR = str(_serena_pkg_path / "resources" / "config" / "internal_modes")
"""Internal modes, never overridden by user modes."""
SERENA_DASHBOARD_DIR = str(_serena_pkg_path / "resources" / "dashboard")
SERENA_ICON_DIR = str(_serena_pkg_path / "resources" / "icons")

DEFAULT_SOURCE_FILE_ENCODING = "utf-8"
"""The default encoding assumed for project source files."""
DEFAULT_CONTEXT = "desktop-app"
DEFAULT_MODES = ("interactive", "editing")

SERENA_FILE_ENCODING = "utf-8"
"""The encoding used for Serena's own files, such as configuration files and memories."""

PROJECT_TEMPLATE_FILE = str(_serena_pkg_path / "resources" / "project.template.yml")
SERENA_CONFIG_TEMPLATE_FILE = str(_serena_pkg_path / "resources" / "serena_config.template.yml")

SERENA_LOG_FORMAT = "%(levelname)-5s %(asctime)-15s [%(threadName)s] %(name)s:%(funcName)s:%(lineno)d - %(message)s"
