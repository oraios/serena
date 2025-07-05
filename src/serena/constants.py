from pathlib import Path

_repo_root_path = Path(__file__).parent.parent.parent.resolve()
_serena_pkg_path = Path(__file__).parent.resolve()

REPO_ROOT = str(_repo_root_path)
PROMPT_TEMPLATES_DIR = str(_serena_pkg_path / "resources" / "config" / "prompt_templates")
CONTEXT_YAMLS_DIR = str(_serena_pkg_path / "resources" / "config" / "contexts")
MODE_YAMLS_DIR = str(_serena_pkg_path / "resources" / "config" / "modes")
INTERNAL_MODE_YAMLS_DIR = str(_serena_pkg_path / "resources" / "config" / "internal_modes")
SERENA_DASHBOARD_DIR = str(_serena_pkg_path / "resources" / "dashboard")
SERENA_ICON_DIR = str(_serena_pkg_path / "resources" / "icons")

SERENA_MANAGED_DIR_NAME = ".serena"

DEFAULT_ENCODING = "utf-8"
DEFAULT_CONTEXT = "desktop-app"
DEFAULT_MODES = ("interactive", "editing")

PROJECT_TEMPLATE_FILE = str(_serena_pkg_path / "resources" / "project.template.yml")
SELENA_CONFIG_TEMPLATE_FILE = str(_serena_pkg_path / "resources" / "serena_config.template.yml")

SERENA_LOG_FORMAT = "%(levelname)-5s %(asctime)-15s [%(threadName)s] %(name)s:%(funcName)s:%(lineno)d - %(message)s"
