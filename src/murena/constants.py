from pathlib import Path

_repo_root_path = Path(__file__).parent.parent.parent.resolve()
_serena_pkg_path = Path(__file__).parent.resolve()

MURENA_MANAGED_DIR_NAME = ".murena"

# TODO: Path-related constants should be moved to MurenaPaths; don't add further constants here.
REPO_ROOT = str(_repo_root_path)
PROMPT_TEMPLATES_DIR_INTERNAL = str(_serena_pkg_path / "resources" / "config" / "prompt_templates")
MURENAS_OWN_CONTEXT_YAMLS_DIR = str(_serena_pkg_path / "resources" / "config" / "contexts")
"""The contexts that are shipped with the Serena package, i.e. the default contexts."""
MURENAS_OWN_MODE_YAMLS_DIR = str(_serena_pkg_path / "resources" / "config" / "modes")
"""The modes that are shipped with the Serena package, i.e. the default modes."""
INTERNAL_MODE_YAMLS_DIR = str(_serena_pkg_path / "resources" / "config" / "internal_modes")
"""Internal modes, never overridden by user modes."""
MURENA_DASHBOARD_DIR = str(_serena_pkg_path / "resources" / "dashboard")
MURENA_ICON_DIR = str(_serena_pkg_path / "resources" / "icons")

DEFAULT_SOURCE_FILE_ENCODING = "utf-8"
"""The default encoding assumed for project source files."""
DEFAULT_CONTEXT = "desktop-app"
DEFAULT_MODES = ("interactive", "editing")

MURENA_FILE_ENCODING = "utf-8"
"""The encoding used for Serena's own files, such as configuration files and memories."""

PROJECT_TEMPLATE_FILE = str(_serena_pkg_path / "resources" / "project.template.yml")
MURENA_CONFIG_TEMPLATE_FILE = str(_serena_pkg_path / "resources" / "murena_config.template.yml")

MURENA_LOG_FORMAT = "%(levelname)-5s %(asctime)-15s [%(threadName)s] %(name)s:%(funcName)s:%(lineno)d - %(message)s"
