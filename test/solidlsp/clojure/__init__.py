from pathlib import Path

from solidlsp.language_servers.clojure_lsp import verify_clojure_cli


def _test_clojure_cli() -> bool:
    try:
        verify_clojure_cli()
        return False
    except (FileNotFoundError, RuntimeError):
        return True


CLI_FAIL = _test_clojure_cli()
TEST_APP_PATH = Path("src") / "test_app"
CORE_PATH = str(TEST_APP_PATH / "core.clj")
UTILS_PATH = str(TEST_APP_PATH / "utils.clj")
