from pathlib import Path

from platformdirs import user_data_path

_appname = "serena"
_author = "oraios"

_repo_root_path = Path(__file__).parent.parent.parent.resolve()
_serena_pkg_path = Path(__file__).parent.resolve()
_serena_data_path = user_data_path(appname=_appname, appauthor=_author)

REPO_ROOT = str(_repo_root_path)
SERENA_DATA_DIR = str(_serena_data_path)
PROMPT_TEMPLATES_DIR = str(_serena_data_path / "config" / "prompt_templates")
CONTEXT_YAMLS_DIR = str(_serena_data_path / "config" / "contexts")
MODE_YAMLS_DIR = str(_serena_data_path / "config" / "modes")
SERENA_DASHBOARD_DIR = str(_serena_pkg_path / "resources" / "dashboard")
SERENA_ICON_DIR = str(_serena_pkg_path / "resources" / "icons")

SERENA_MANAGED_DIR_NAME = ".serena"

DEFAULT_CONTEXT = "desktop-app"
DEFAULT_MODES = ("interactive", "editing")

PROJECT_TEMPLATE_FILE = str(_serena_pkg_path / "resources" / "project.template.yml")
SERENA_CONFIG_TEMPLATE_FILE = str(_serena_pkg_path / "resources" / "serena_config.template.yml")

SERENA_CONFIG_FILE = str(_serena_data_path / "serena_config.yml")
