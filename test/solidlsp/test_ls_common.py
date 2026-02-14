import os
import platform
import time

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.conftest import is_ci


class TestLanguageServerCommonFunctionality:
    """Test common functionality of SolidLanguageServer base implementation (not language-specific behaviour)."""

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_open_file_cache_invalidate(self, language_server: SolidLanguageServer) -> None:
        """
        Tests that the file buffer cache is invalidated when the file is changed on disk.
        """
        file_path = os.path.join(language_server.repository_root_path, "test_open_file.py")
        test_string1 = "# foo"
        test_string2 = "# bar"

        with open(file_path, "w") as f:
            f.write(test_string1)

        try:
            with language_server.open_file(file_path) as fb:
                assert fb.contents == test_string1

                # apply external change to file
                with open(file_path, "w") as f:
                    f.write(test_string2)

                # ensure that mtime is updated for Windows CI (odd FS behaviour, updates lazily)
                if is_ci and platform.system() == "Windows":
                    now = time.time()
                    os.utime(file_path, (now, now))
                    time.sleep(5)

                # check that the file buffer has been invalidated and reloaded
                assert fb.contents == test_string2

        finally:
            os.remove(file_path)
