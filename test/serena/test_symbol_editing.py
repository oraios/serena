import logging
import os
import shutil
import sys
import tempfile
import time
from abc import abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal, NamedTuple

import pytest

from serena.code_editor import CodeEditor, LanguageServerCodeEditor
from solidlsp.ls_config import Language
from src.serena.symbol import LanguageServerSymbolRetriever
from test.conftest import create_ls, get_repo_path

pytestmark = pytest.mark.snapshot

log = logging.getLogger(__name__)


class LineChange(NamedTuple):
    """Represents a change to a specific line or range of lines."""

    operation: Literal["insert", "delete", "replace"]
    original_start: int
    original_end: int
    modified_start: int
    modified_end: int
    original_lines: list[str]
    modified_lines: list[str]


@dataclass
class CodeDiff:
    """
    Represents the difference between original and modified code.
    Provides object-oriented access to diff information including line numbers.
    """

    relative_path: str
    original_content: str
    modified_content: str
    _line_changes: list[LineChange] = field(init=False)

    def __post_init__(self) -> None:
        """Compute the diff using difflib's SequenceMatcher."""
        original_lines = self.original_content.splitlines(keepends=True)
        modified_lines = self.modified_content.splitlines(keepends=True)

        matcher = SequenceMatcher(None, original_lines, modified_lines)
        self._line_changes = []

        for tag, orig_start, orig_end, mod_start, mod_end in matcher.get_opcodes():
            if tag == "equal":
                continue
            if tag == "insert":
                self._line_changes.append(
                    LineChange(
                        operation="insert",
                        original_start=orig_start,
                        original_end=orig_start,
                        modified_start=mod_start,
                        modified_end=mod_end,
                        original_lines=[],
                        modified_lines=modified_lines[mod_start:mod_end],
                    )
                )
            elif tag == "delete":
                self._line_changes.append(
                    LineChange(
                        operation="delete",
                        original_start=orig_start,
                        original_end=orig_end,
                        modified_start=mod_start,
                        modified_end=mod_start,
                        original_lines=original_lines[orig_start:orig_end],
                        modified_lines=[],
                    )
                )
            elif tag == "replace":
                self._line_changes.append(
                    LineChange(
                        operation="replace",
                        original_start=orig_start,
                        original_end=orig_end,
                        modified_start=mod_start,
                        modified_end=mod_end,
                        original_lines=original_lines[orig_start:orig_end],
                        modified_lines=modified_lines[mod_start:mod_end],
                    )
                )

    @property
    def line_changes(self) -> list[LineChange]:
        """Get all line changes in the diff."""
        return self._line_changes

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return len(self._line_changes) > 0

    @property
    def added_lines(self) -> list[tuple[int, str]]:
        """Get all added lines with their line numbers (0-based) in the modified file."""
        result = []
        for change in self._line_changes:
            if change.operation in ("insert", "replace"):
                for i, line in enumerate(change.modified_lines):
                    result.append((change.modified_start + i, line))
        return result

    @property
    def deleted_lines(self) -> list[tuple[int, str]]:
        """Get all deleted lines with their line numbers (0-based) in the original file."""
        result = []
        for change in self._line_changes:
            if change.operation in ("delete", "replace"):
                for i, line in enumerate(change.original_lines):
                    result.append((change.original_start + i, line))
        return result

    @property
    def modified_line_numbers(self) -> list[int]:
        """Get all line numbers (0-based) that were modified in the modified file."""
        line_nums: set[int] = set()
        for change in self._line_changes:
            if change.operation in ("insert", "replace"):
                line_nums.update(range(change.modified_start, change.modified_end))
        return sorted(line_nums)

    @property
    def affected_original_line_numbers(self) -> list[int]:
        """Get all line numbers (0-based) that were affected in the original file."""
        line_nums: set[int] = set()
        for change in self._line_changes:
            if change.operation in ("delete", "replace"):
                line_nums.update(range(change.original_start, change.original_end))
        return sorted(line_nums)

    def get_unified_diff(self, context_lines: int = 3) -> str:
        """Get the unified diff as a string."""
        import difflib

        original_lines = self.original_content.splitlines(keepends=True)
        modified_lines = self.modified_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines, modified_lines, fromfile=f"a/{self.relative_path}", tofile=f"b/{self.relative_path}", n=context_lines
        )
        return "".join(diff)

    def get_context_diff(self, context_lines: int = 3) -> str:
        """Get the context diff as a string."""
        import difflib

        original_lines = self.original_content.splitlines(keepends=True)
        modified_lines = self.modified_content.splitlines(keepends=True)

        diff = difflib.context_diff(
            original_lines, modified_lines, fromfile=f"a/{self.relative_path}", tofile=f"b/{self.relative_path}", n=context_lines
        )
        return "".join(diff)


class EditingTest:
    def __init__(self, language: Language, rel_path: str):
        """
        :param language: the language
        :param rel_path: the relative path of the edited file
        """
        self.rel_path = rel_path
        self.language = language
        self.original_repo_path = get_repo_path(language)
        self.repo_path: Path | None = None

    @contextmanager
    def _setup(self) -> Iterator[LanguageServerSymbolRetriever]:
        """Context manager for setup/teardown with a temporary directory, providing the symbol manager."""
        temp_dir = Path(tempfile.mkdtemp())
        self.repo_path = temp_dir / self.original_repo_path.name
        language_server = None  # Initialize language_server
        try:
            print(f"Copying repo from {self.original_repo_path} to {self.repo_path}")
            shutil.copytree(self.original_repo_path, self.repo_path)
            # prevent deadlock on Windows due to file locks caused by antivirus or some other external software
            # wait for a long time here
            if os.name == "nt":
                time.sleep(0.1)
            log.info(f"Creating language server for {self.language} {self.rel_path}")
            language_server = create_ls(self.language, str(self.repo_path))
            log.info(f"Starting language server for {self.language} {self.rel_path}")
            language_server.start()
            log.info(f"Language server started for {self.language} {self.rel_path}")
            yield LanguageServerSymbolRetriever(lang_server=language_server)
        finally:
            if language_server is not None and language_server.is_running():
                log.info(f"Stopping language server for {self.language} {self.rel_path}")
                language_server.stop()
                # attempt at trigger of garbage collection
                language_server = None
                log.info(f"Language server stopped for {self.language} {self.rel_path}")

            # prevent deadlock on Windows due to lingering file locks
            if os.name == "nt":
                time.sleep(0.1)
            log.info(f"Removing temp directory {temp_dir}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            log.info(f"Temp directory {temp_dir} removed")

    def _read_file(self, rel_path: str) -> str:
        """Read the content of a file in the test repository."""
        assert self.repo_path is not None
        file_path = self.repo_path / rel_path
        with open(file_path, encoding="utf-8") as f:
            return f.read()

    def run_test(self, content_after_ground_truth: str) -> None:
        with self._setup() as symbol_retriever:
            content_before = self._read_file(self.rel_path)
            code_editor = LanguageServerCodeEditor(symbol_retriever)
            self._apply_edit(code_editor)
            content_after = self._read_file(self.rel_path)
            code_diff = CodeDiff(self.rel_path, original_content=content_before, modified_content=content_after)
            self._test_diff(code_diff, content_after_ground_truth)

    @abstractmethod
    def _apply_edit(self, code_editor: CodeEditor) -> None:
        pass

    def _test_diff(self, code_diff: CodeDiff, snapshot: str) -> None:
        assert code_diff.modified_content == snapshot


# Python test file path
PYTHON_TEST_REL_FILE_PATH = os.path.join("test_repo", "variables.py")

# TypeScript test file path
TYPESCRIPT_TEST_FILE = "index.ts"


class DeleteSymbolTest(EditingTest):
    def __init__(self, language: Language, rel_path: str, deleted_symbol: str):
        super().__init__(language, rel_path)
        self.deleted_symbol = deleted_symbol
        self.rel_path = rel_path

    def _apply_edit(self, code_editor: CodeEditor) -> None:
        code_editor.delete_symbol(self.deleted_symbol, self.rel_path)


@pytest.mark.parametrize(
    "test_case",
    [
        pytest.param(
            DeleteSymbolTest(
                Language.PYTHON,
                PYTHON_TEST_REL_FILE_PATH,
                "VariableContainer",
            ),
            marks=pytest.mark.python,
        ),
        pytest.param(
            DeleteSymbolTest(
                Language.TYPESCRIPT,
                TYPESCRIPT_TEST_FILE,
                "DemoClass",
            ),
            marks=pytest.mark.typescript,
        ),
    ],
)
def test_delete_symbol(test_case, snapshot):
    test_case.run_test(content_after_ground_truth=snapshot)


NEW_PYTHON_FUNCTION = """def new_inserted_function():
    print("This is a new function inserted before another.")"""

NEW_PYTHON_CLASS_WITH_LEADING_NEWLINES = """

class NewInsertedClass:
    pass
"""

NEW_PYTHON_CLASS_WITH_TRAILING_NEWLINES = """class NewInsertedClass:
    pass


"""

NEW_TYPESCRIPT_FUNCTION = """function newInsertedFunction(): void {
    console.log("This is a new function inserted before another.");
}"""


NEW_PYTHON_VARIABLE = 'new_module_var = "Inserted after typed_module_var"'

NEW_TYPESCRIPT_FUNCTION_AFTER = """function newFunctionAfterClass(): void {
    console.log("This function is after DemoClass.");
}"""


class InsertInRelToSymbolTest(EditingTest):
    def __init__(
        self, language: Language, rel_path: str, symbol_name: str, new_content: str, mode: Literal["before", "after"] | None = None
    ):
        super().__init__(language, rel_path)
        self.symbol_name = symbol_name
        self.new_content = new_content
        self.mode: Literal["before", "after"] | None = mode

    def set_mode(self, mode: Literal["before", "after"]):
        self.mode = mode

    def _apply_edit(self, code_editor: CodeEditor) -> None:
        assert self.mode is not None
        if self.mode == "before":
            code_editor.insert_before_symbol(self.symbol_name, self.rel_path, self.new_content)
        elif self.mode == "after":
            code_editor.insert_after_symbol(self.symbol_name, self.rel_path, self.new_content)


@pytest.mark.parametrize("mode", ["before", "after"])
@pytest.mark.parametrize(
    "test_case",
    [
        pytest.param(
            InsertInRelToSymbolTest(
                Language.PYTHON,
                PYTHON_TEST_REL_FILE_PATH,
                "typed_module_var",
                NEW_PYTHON_VARIABLE,
            ),
            marks=pytest.mark.python,
        ),
        pytest.param(
            InsertInRelToSymbolTest(
                Language.PYTHON,
                PYTHON_TEST_REL_FILE_PATH,
                "use_module_variables",
                NEW_PYTHON_FUNCTION,
            ),
            marks=pytest.mark.python,
        ),
        pytest.param(
            InsertInRelToSymbolTest(
                Language.TYPESCRIPT,
                TYPESCRIPT_TEST_FILE,
                "DemoClass",
                NEW_TYPESCRIPT_FUNCTION_AFTER,
            ),
            marks=pytest.mark.typescript,
        ),
        pytest.param(
            InsertInRelToSymbolTest(
                Language.TYPESCRIPT,
                TYPESCRIPT_TEST_FILE,
                "helperFunction",
                NEW_TYPESCRIPT_FUNCTION,
            ),
            marks=pytest.mark.typescript,
        ),
    ],
)
def test_insert_in_rel_to_symbol(test_case: InsertInRelToSymbolTest, mode: Literal["before", "after"], snapshot):
    test_case.set_mode(mode)
    test_case.run_test(content_after_ground_truth=snapshot)


@pytest.mark.python
def test_insert_python_class_before(snapshot):
    InsertInRelToSymbolTest(
        Language.PYTHON,
        PYTHON_TEST_REL_FILE_PATH,
        "VariableDataclass",
        NEW_PYTHON_CLASS_WITH_TRAILING_NEWLINES,
        mode="before",
    ).run_test(snapshot)


@pytest.mark.python
def test_insert_python_class_after(snapshot):
    InsertInRelToSymbolTest(
        Language.PYTHON,
        PYTHON_TEST_REL_FILE_PATH,
        "VariableDataclass",
        NEW_PYTHON_CLASS_WITH_LEADING_NEWLINES,
        mode="after",
    ).run_test(snapshot)


PYTHON_REPLACED_BODY = """def modify_instance_var(self):
        # This body has been replaced
        self.instance_var = "Replaced!"
        self.reassignable_instance_var = 999
"""

TYPESCRIPT_REPLACED_BODY = """function printValue() {
        // This body has been replaced
        console.warn("New value: " + this.value);
    }
"""


class ReplaceBodyTest(EditingTest):
    def __init__(self, language: Language, rel_path: str, symbol_name: str, new_body: str):
        super().__init__(language, rel_path)
        self.symbol_name = symbol_name
        self.new_body = new_body

    def _apply_edit(self, code_editor: CodeEditor) -> None:
        code_editor.replace_body(self.symbol_name, self.rel_path, self.new_body)


@pytest.mark.parametrize(
    "test_case",
    [
        pytest.param(
            ReplaceBodyTest(
                Language.PYTHON,
                PYTHON_TEST_REL_FILE_PATH,
                "VariableContainer/modify_instance_var",
                PYTHON_REPLACED_BODY,
            ),
            marks=pytest.mark.python,
        ),
        pytest.param(
            ReplaceBodyTest(
                Language.TYPESCRIPT,
                TYPESCRIPT_TEST_FILE,
                "DemoClass/printValue",
                TYPESCRIPT_REPLACED_BODY,
            ),
            marks=pytest.mark.typescript,
        ),
    ],
)
def test_replace_body(test_case: ReplaceBodyTest, snapshot):
    test_case.run_test(content_after_ground_truth=snapshot)


NIX_ATTR_REPLACEMENT = """c = 3;"""


class NixAttrReplacementTest(EditingTest):
    """Test for replacing individual attributes in Nix that should NOT result in double semicolons."""

    def __init__(self, language: Language, rel_path: str, symbol_name: str, new_body: str):
        super().__init__(language, rel_path)
        self.symbol_name = symbol_name
        self.new_body = new_body

    def _apply_edit(self, code_editor: CodeEditor) -> None:
        code_editor.replace_body(self.symbol_name, self.rel_path, self.new_body)


@pytest.mark.nix
@pytest.mark.skipif(sys.platform == "win32", reason="nixd language server doesn't run on Windows")
def test_nix_symbol_replacement_no_double_semicolon(snapshot):
    """
    Test that replacing a Nix attribute does not result in double semicolons.

    This test exercises the bug where:
    - Original: users.users.example = { isSystemUser = true; group = "example"; description = "Example service user"; };
    - Replacement: c = 3;
    - Bug result would be: c = 3;; (double semicolon)
    - Correct result should be: c = 3; (single semicolon)

    The replacement body includes a semicolon, but the language server's range extension
    logic should prevent double semicolons.
    """
    test_case = NixAttrReplacementTest(
        Language.NIX,
        "default.nix",
        "testUser",  # Simple attrset with multiple key-value pairs
        NIX_ATTR_REPLACEMENT,
    )
    test_case.run_test(content_after_ground_truth=snapshot)
