import os

import pytest

from multilspy.language_server import SyncLanguageServer
from multilspy.multilspy_config import Language

FILE_MAP = {
    Language.PYTHON: os.path.join("test_repo", "name_collisions.py"),
    Language.GO: "main.go",
    Language.JAVA: os.path.join("src", "main", "java", "test_repo", "Main.java"),
    Language.RUST: os.path.join("src", "main.rs"),
    Language.TYPESCRIPT: "index.ts",
    Language.PHP: "index.php",
}


@pytest.mark.parametrize(
    "language_server,language",
    [
        pytest.param(Language.PYTHON, Language.PYTHON, marks=pytest.mark.python),
        pytest.param(Language.GO, Language.GO, marks=pytest.mark.go),
        pytest.param(Language.JAVA, Language.JAVA, marks=pytest.mark.java),
        pytest.param(Language.RUST, Language.RUST, marks=pytest.mark.rust),
        pytest.param(Language.TYPESCRIPT, Language.TYPESCRIPT, marks=pytest.mark.typescript),
        pytest.param(Language.PHP, Language.PHP, marks=pytest.mark.php),
    ],
    indirect=["language_server"],
)
def test_request_diagnostics(language_server: SyncLanguageServer, language: Language) -> None:
    file_path = FILE_MAP[language]
    diags = language_server.request_diagnostics(file_path)
    assert isinstance(diags, list)
