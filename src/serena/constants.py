from pathlib import Path

_repo_root_path = Path(__file__).parent.parent.parent.resolve()
_serena_pkg_path = Path(__file__).parent.resolve()

SERENA_MANAGED_DIR_NAME = ".serena"

# TODO: Path-related constants should be moved to SerenaPaths; don't add further constants here.
REPO_ROOT = str(_repo_root_path)
PROMPT_TEMPLATES_DIR_INTERNAL = str(_serena_pkg_path / "resources" / "config" / "prompt_templates")
SERENAS_OWN_CONTEXT_YAMLS_DIR = str(_serena_pkg_path / "resources" / "config" / "contexts")
"""The contexts that are shipped with the Serena package, i.e. the default contexts."""
SERENAS_OWN_MODE_YAMLS_DIR = str(_serena_pkg_path / "resources" / "config" / "modes")
"""The modes that are shipped with the Serena package, i.e. the default modes."""
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
