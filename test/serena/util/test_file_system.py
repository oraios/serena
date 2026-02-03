import os
import shutil
import tempfile
from pathlib import Path

# Assuming the gitignore parser code is in a module named 'gitignore_parser'
from serena.util.file_system import GitignoreParser, GitignoreSpec


class TestGitignoreParser:
    """Test class for GitignoreParser functionality."""

    def setup_method(self):
        """Set up test environment before each test method."""
        # Create a temporary directory for testing
        self.test_dir = tempfile.mkdtemp()
        self.repo_path = Path(self.test_dir)

        # Create test repository structure
        self._create_repo_structure()

    def teardown_method(self):
        """Clean up test environment after each test method."""
        # Remove the temporary directory
        shutil.rmtree(self.test_dir)

    def _create_repo_structure(self):
        """
        Create a test repository structure with multiple gitignore files.

        Structure:
        repo/
        ├── .gitignore
        ├── file1.txt
        ├── test.log
        ├── src/
        │   ├── .gitignore
        │   ├── main.py
        │   ├── test.log
        │   ├── build/
        │   │   └── output.o
        │   └── lib/
        │       ├── .gitignore
        │       └── cache.tmp
        └── docs/
            ├── .gitignore
            ├── api.md
            └── temp/
                └── draft.md
        """
        # Create directories
        (self.repo_path / "src").mkdir()
        (self.repo_path / "src" / "build").mkdir()
        (self.repo_path / "src" / "lib").mkdir()
        (self.repo_path / "docs").mkdir()
        (self.repo_path / "docs" / "temp").mkdir()

        # Create files
        (self.repo_path / "file1.txt").touch()
        (self.repo_path / "test.log").touch()
        (self.repo_path / "src" / "main.py").touch()
        (self.repo_path / "src" / "test.log").touch()
        (self.repo_path / "src" / "build" / "output.o").touch()
        (self.repo_path / "src" / "lib" / "cache.tmp").touch()
        (self.repo_path / "docs" / "api.md").touch()
        (self.repo_path / "docs" / "temp" / "draft.md").touch()

        # Create root .gitignore
        root_gitignore = self.repo_path / ".gitignore"
        root_gitignore.write_text(
            """# Root gitignore
*.log
/build/
"""
        )

        # Create src/.gitignore
        src_gitignore = self.repo_path / "src" / ".gitignore"
        src_gitignore.write_text(
            """# Source gitignore
*.o
build/
!important.log
"""
        )

        # Create src/lib/.gitignore (deeply nested)
        src_lib_gitignore = self.repo_path / "src" / "lib" / ".gitignore"
        src_lib_gitignore.write_text(
            """# Library gitignore
*.tmp
*.cache
"""
        )

        # Create docs/.gitignore
        docs_gitignore = self.repo_path / "docs" / ".gitignore"
        docs_gitignore.write_text(
            """# Docs gitignore
temp/
*.tmp
"""
        )

    def test_initialization(self):
        """Test GitignoreParser initialization."""
        parser = GitignoreParser(str(self.repo_path))

        assert parser.repo_root == str(self.repo_path.absolute())
        assert len(parser.get_ignore_specs()) == 4

    def test_find_gitignore_files(self):
        """Test finding all gitignore files in repository, including deeply nested ones."""
        parser = GitignoreParser(str(self.repo_path))

        # Get file paths from specs
        gitignore_files = [spec.file_path for spec in parser.get_ignore_specs()]

        # Convert to relative paths for easier testing
        rel_paths = [os.path.relpath(f, self.repo_path) for f in gitignore_files]
        rel_paths.sort()

        assert len(rel_paths) == 4
        assert ".gitignore" in rel_paths
        assert os.path.join("src", ".gitignore") in rel_paths
        assert os.path.join("src", "lib", ".gitignore") in rel_paths  # Deeply nested
        assert os.path.join("docs", ".gitignore") in rel_paths

    def test_parse_patterns_root_directory(self):
        """Test parsing gitignore patterns in root directory."""
        # Create a simple test case with only root gitignore
        test_dir = self.repo_path / "test_root"
        test_dir.mkdir()

        gitignore = test_dir / ".gitignore"
        gitignore.write_text(
            """*.log
build/
/temp.txt
"""
        )

        parser = GitignoreParser(str(test_dir))
        specs = parser.get_ignore_specs()

        assert len(specs) == 1
        patterns = specs[0].patterns

        assert "*.log" in patterns
        assert "build/" in patterns
        assert "/temp.txt" in patterns

    def test_parse_patterns_subdirectory(self):
        """Test parsing gitignore patterns in subdirectory."""
        # Create a test case with subdirectory gitignore
        test_dir = self.repo_path / "test_sub"
        test_dir.mkdir()
        subdir = test_dir / "src"
        subdir.mkdir()

        gitignore = subdir / ".gitignore"
        gitignore.write_text(
            """*.o
/build/
test.log
"""
        )

        parser = GitignoreParser(str(test_dir))
        specs = parser.get_ignore_specs()

        assert len(specs) == 1
        patterns = specs[0].patterns

        # Non-anchored pattern should get ** prefix
        assert "src/**/*.o" in patterns
        # Anchored pattern should not get ** prefix
        assert "src/build/" in patterns
        # Non-anchored pattern without slash
        assert "src/**/test.log" in patterns

    def test_should_ignore_root_patterns(self):
        """Test ignoring files based on root .gitignore."""
        parser = GitignoreParser(str(self.repo_path))

        # Files that should be ignored
        assert parser.should_ignore("test.log")
        assert parser.should_ignore(str(self.repo_path / "test.log"))

        # Files that should NOT be ignored
        assert not parser.should_ignore("file1.txt")
        assert not parser.should_ignore("src/main.py")

    def test_should_ignore_subdirectory_patterns(self):
        """Test ignoring files based on subdirectory .gitignore files."""
        parser = GitignoreParser(str(self.repo_path))

        # .o files in src should be ignored
        assert parser.should_ignore("src/build/output.o")

        # build/ directory in src should be ignored
        assert parser.should_ignore("src/build/")

        # temp/ directory in docs should be ignored
        assert parser.should_ignore("docs/temp/draft.md")

        # But temp/ outside docs should not be ignored by docs/.gitignore
        assert not parser.should_ignore("temp/file.txt")

        # Test deeply nested .gitignore in src/lib/
        # .tmp files in src/lib should be ignored
        assert parser.should_ignore("src/lib/cache.tmp")

        # .cache files in src/lib should also be ignored
        assert parser.should_ignore("src/lib/data.cache")

        # But .tmp files outside src/lib should not be ignored by src/lib/.gitignore
        assert not parser.should_ignore("src/other.tmp")

    def test_anchored_vs_non_anchored_patterns(self):
        """Test the difference between anchored and non-anchored patterns."""
        # Create new test structure
        test_dir = self.repo_path / "test_anchored"
        test_dir.mkdir()
        (test_dir / "src").mkdir()
        (test_dir / "src" / "subdir").mkdir()
        (test_dir / "src" / "subdir" / "deep").mkdir()

        # Create src/.gitignore with both anchored and non-anchored patterns
        gitignore = test_dir / "src" / ".gitignore"
        gitignore.write_text(
            """/temp.txt
data.json
"""
        )

        # Create test files
        (test_dir / "src" / "temp.txt").touch()
        (test_dir / "src" / "data.json").touch()
        (test_dir / "src" / "subdir" / "temp.txt").touch()
        (test_dir / "src" / "subdir" / "data.json").touch()
        (test_dir / "src" / "subdir" / "deep" / "data.json").touch()

        parser = GitignoreParser(str(test_dir))

        # Anchored pattern /temp.txt should only match in src/
        assert parser.should_ignore("src/temp.txt")
        assert not parser.should_ignore("src/subdir/temp.txt")

        # Non-anchored pattern data.json should match anywhere under src/
        assert parser.should_ignore("src/data.json")
        assert parser.should_ignore("src/subdir/data.json")
        assert parser.should_ignore("src/subdir/deep/data.json")

    def test_root_anchored_patterns(self):
        """Test anchored patterns in root .gitignore only match root-level files."""
        # Create new test structure for root anchored patterns
        test_dir = self.repo_path / "test_root_anchored"
        test_dir.mkdir()
        (test_dir / "src").mkdir()
        (test_dir / "docs").mkdir()
        (test_dir / "src" / "nested").mkdir()

        # Create root .gitignore with anchored patterns
        gitignore = test_dir / ".gitignore"
        gitignore.write_text(
            """/config.json
/temp.log
/build
*.pyc
"""
        )

        # Create test files at root level
        (test_dir / "config.json").touch()
        (test_dir / "temp.log").touch()
        (test_dir / "build").mkdir()
        (test_dir / "file.pyc").touch()

        # Create same-named files in subdirectories
        (test_dir / "src" / "config.json").touch()
        (test_dir / "src" / "temp.log").touch()
        (test_dir / "src" / "build").mkdir()
        (test_dir / "src" / "file.pyc").touch()
        (test_dir / "docs" / "config.json").touch()
        (test_dir / "docs" / "temp.log").touch()
        (test_dir / "src" / "nested" / "config.json").touch()
        (test_dir / "src" / "nested" / "temp.log").touch()
        (test_dir / "src" / "nested" / "build").mkdir()

        parser = GitignoreParser(str(test_dir))

        # Anchored patterns should only match root-level files
        assert parser.should_ignore("config.json")
        assert not parser.should_ignore("src/config.json")
        assert not parser.should_ignore("docs/config.json")
        assert not parser.should_ignore("src/nested/config.json")

        assert parser.should_ignore("temp.log")
        assert not parser.should_ignore("src/temp.log")
        assert not parser.should_ignore("docs/temp.log")
        assert not parser.should_ignore("src/nested/temp.log")

        assert parser.should_ignore("build")
        assert not parser.should_ignore("src/build")
        assert not parser.should_ignore("src/nested/build")

        # Non-anchored patterns should match everywhere
        assert parser.should_ignore("file.pyc")
        assert parser.should_ignore("src/file.pyc")

    def test_mixed_anchored_and_non_anchored_root_patterns(self):
        """Test mix of anchored and non-anchored patterns in root .gitignore."""
        test_dir = self.repo_path / "test_mixed_patterns"
        test_dir.mkdir()
        (test_dir / "app").mkdir()
        (test_dir / "tests").mkdir()
        (test_dir / "app" / "modules").mkdir()

        # Create root .gitignore with mixed patterns
        gitignore = test_dir / ".gitignore"
        gitignore.write_text(
            """/secrets.env
/dist/
node_modules/
*.tmp
/app/local.config
debug.log
"""
        )

        # Create test files and directories
        (test_dir / "secrets.env").touch()
        (test_dir / "dist").mkdir()
        (test_dir / "node_modules").mkdir()
        (test_dir / "file.tmp").touch()
        (test_dir / "app" / "local.config").touch()
        (test_dir / "debug.log").touch()

        # Create same files in subdirectories
        (test_dir / "app" / "secrets.env").touch()
        (test_dir / "app" / "dist").mkdir()
        (test_dir / "app" / "node_modules").mkdir()
        (test_dir / "app" / "file.tmp").touch()
        (test_dir / "app" / "debug.log").touch()
        (test_dir / "tests" / "secrets.env").touch()
        (test_dir / "tests" / "node_modules").mkdir()
        (test_dir / "tests" / "debug.log").touch()
        (test_dir / "app" / "modules" / "local.config").touch()

        parser = GitignoreParser(str(test_dir))

        # Anchored patterns should only match at root
        assert parser.should_ignore("secrets.env")
        assert not parser.should_ignore("app/secrets.env")
        assert not parser.should_ignore("tests/secrets.env")

        assert parser.should_ignore("dist")
        assert not parser.should_ignore("app/dist")

        assert parser.should_ignore("app/local.config")
        assert not parser.should_ignore("app/modules/local.config")

        # Non-anchored patterns should match everywhere
        assert parser.should_ignore("node_modules")
        assert parser.should_ignore("app/node_modules")
        assert parser.should_ignore("tests/node_modules")

        assert parser.should_ignore("file.tmp")
        assert parser.should_ignore("app/file.tmp")

        assert parser.should_ignore("debug.log")
        assert parser.should_ignore("app/debug.log")
        assert parser.should_ignore("tests/debug.log")

    def test_negation_patterns(self):
        """Test negation patterns are parsed correctly."""
        test_dir = self.repo_path / "test_negation"
        test_dir.mkdir()

        gitignore = test_dir / ".gitignore"
        gitignore.write_text(
            """*.log
!important.log
!src/keep.log
"""
        )

        parser = GitignoreParser(str(test_dir))
        specs = parser.get_ignore_specs()

        assert len(specs) == 1
        patterns = specs[0].patterns

        assert "*.log" in patterns
        assert "!important.log" in patterns
        assert "!src/keep.log" in patterns

    def test_comments_and_empty_lines(self):
        """Test that comments and empty lines are ignored."""
        test_dir = self.repo_path / "test_comments"
        test_dir.mkdir()

        gitignore = test_dir / ".gitignore"
        gitignore.write_text(
            """# This is a comment
*.log

# Another comment
  # Indented comment

build/
"""
        )

        parser = GitignoreParser(str(test_dir))
        specs = parser.get_ignore_specs()

        assert len(specs) == 1
        patterns = specs[0].patterns

        assert len(patterns) == 2
        assert "*.log" in patterns
        assert "build/" in patterns

    def test_escaped_characters(self):
        """Test escaped special characters."""
        test_dir = self.repo_path / "test_escaped"
        test_dir.mkdir()

        gitignore = test_dir / ".gitignore"
        gitignore.write_text(
            """\\#not-a-comment.txt
\\!not-negation.txt
"""
        )

        parser = GitignoreParser(str(test_dir))
        specs = parser.get_ignore_specs()

        assert len(specs) == 1
        patterns = specs[0].patterns

        assert "#not-a-comment.txt" in patterns
        assert "!not-negation.txt" in patterns

    def test_escaped_negation_patterns(self):
        test_dir = self.repo_path / "test_escaped_negation"
        test_dir.mkdir()

        gitignore = test_dir / ".gitignore"
        gitignore.write_text(
            """*.log
\\!not-negation.log
!actual-negation.log
"""
        )

        parser = GitignoreParser(str(test_dir))
        specs = parser.get_ignore_specs()

        assert len(specs) == 1
        patterns = specs[0].patterns

        # Key assertions: escaped exclamation becomes literal, real negation preserved
        assert "!not-negation.log" in patterns  # escaped -> literal
        assert "!actual-negation.log" in patterns  # real negation preserved

        # Test the actual behavioral difference between escaped and real negation:
        # *.log pattern should ignore test.log
        assert parser.should_ignore("test.log")

        # Escaped negation file should still be ignored by *.log pattern
        assert parser.should_ignore("!not-negation.log")

        # Actual negation should override the *.log pattern
        assert not parser.should_ignore("actual-negation.log")

    def test_glob_patterns(self):
        """Test various glob patterns work correctly."""
        test_dir = self.repo_path / "test_glob"
        test_dir.mkdir()

        gitignore = test_dir / ".gitignore"
        gitignore.write_text(
            """*.pyc
**/*.tmp
src/*.o
!src/important.o
[Tt]est*
"""
        )

        # Create test files
        (test_dir / "src").mkdir()
        (test_dir / "src" / "nested").mkdir()
        (test_dir / "file.pyc").touch()
        (test_dir / "src" / "file.pyc").touch()
        (test_dir / "file.tmp").touch()
        (test_dir / "src" / "nested" / "file.tmp").touch()
        (test_dir / "src" / "file.o").touch()
        (test_dir / "src" / "important.o").touch()
        (test_dir / "Test.txt").touch()
        (test_dir / "test.log").touch()

        parser = GitignoreParser(str(test_dir))

        # *.pyc should match everywhere
        assert parser.should_ignore("file.pyc")
        assert parser.should_ignore("src/file.pyc")

        # **/*.tmp should match all .tmp files
        assert parser.should_ignore("file.tmp")
        assert parser.should_ignore("src/nested/file.tmp")

        # src/*.o should only match .o files directly in src/
        assert parser.should_ignore("src/file.o")

        # Character class patterns
        assert parser.should_ignore("Test.txt")
        assert parser.should_ignore("test.log")

    def test_empty_gitignore(self):
        """Test handling of empty gitignore files."""
        test_dir = self.repo_path / "test_empty"
        test_dir.mkdir()

        gitignore = test_dir / ".gitignore"
        gitignore.write_text("")

        parser = GitignoreParser(str(test_dir))

        # Should not crash and should return empty list
        assert len(parser.get_ignore_specs()) == 0

    def test_malformed_gitignore(self):
        """Test handling of malformed gitignore content."""
        test_dir = self.repo_path / "test_malformed"
        test_dir.mkdir()

        gitignore = test_dir / ".gitignore"
        gitignore.write_text(
            """# Only comments and empty lines
    
# More comments
    
    """
        )

        parser = GitignoreParser(str(test_dir))

        # Should handle gracefully
        assert len(parser.get_ignore_specs()) == 0

    def test_reload(self):
        """Test reloading gitignore files."""
        test_dir = self.repo_path / "test_reload"
        test_dir.mkdir()

        # Create initial gitignore
        gitignore = test_dir / ".gitignore"
        gitignore.write_text("*.log")

        parser = GitignoreParser(str(test_dir))
        assert len(parser.get_ignore_specs()) == 1
        assert parser.should_ignore("test.log")

        # Modify gitignore
        gitignore.write_text("*.tmp")

        # Without reload, should still use old patterns
        assert parser.should_ignore("test.log")
        assert not parser.should_ignore("test.tmp")

        # After reload, should use new patterns
        parser.reload()
        assert not parser.should_ignore("test.log")
        assert parser.should_ignore("test.tmp")

    def test_gitignore_spec_matches(self):
        """Test GitignoreSpec.matches method."""
        spec = GitignoreSpec("/path/to/.gitignore", ["*.log", "build/", "!important.log"])

        assert spec.matches("test.log")
        assert spec.matches("build/output.o")
        assert spec.matches("src/test.log")

        # Note: Negation patterns in pathspec work differently than in git
        # This is a limitation of the pathspec library

    def test_subdirectory_gitignore_pattern_scoping(self):
        """Test that subdirectory .gitignore patterns are scoped correctly."""
        # Create test structure: foo/ with subdirectory bar/
        test_dir = self.repo_path / "test_subdir_scoping"
        test_dir.mkdir()
        (test_dir / "foo").mkdir()
        (test_dir / "foo" / "bar").mkdir()

        # Create files in various locations
        (test_dir / "foo.txt").touch()  # root level
        (test_dir / "foo" / "foo.txt").touch()  # in foo/
        (test_dir / "foo" / "bar" / "foo.txt").touch()  # in foo/bar/

        # Test case 1: foo.txt in foo/.gitignore should only ignore in foo/ subtree
        gitignore = test_dir / "foo" / ".gitignore"
        gitignore.write_text("foo.txt\n")

        parser = GitignoreParser(str(test_dir))

        # foo.txt at root should NOT be ignored by foo/.gitignore
        assert not parser.should_ignore("foo.txt"), "Root foo.txt should not be ignored by foo/.gitignore"

        # foo.txt in foo/ should be ignored
        assert parser.should_ignore("foo/foo.txt"), "foo/foo.txt should be ignored"

        # foo.txt in foo/bar/ should be ignored (within foo/ subtree)
        assert parser.should_ignore("foo/bar/foo.txt"), "foo/bar/foo.txt should be ignored"

    def test_anchored_pattern_in_subdirectory(self):
        """Test that anchored patterns in subdirectory only match immediate children."""
        test_dir = self.repo_path / "test_anchored_subdir"
        test_dir.mkdir()
        (test_dir / "foo").mkdir()
        (test_dir / "foo" / "bar").mkdir()

        # Create files
        (test_dir / "foo.txt").touch()  # root level
        (test_dir / "foo" / "foo.txt").touch()  # in foo/
        (test_dir / "foo" / "bar" / "foo.txt").touch()  # in foo/bar/

        # Test case 2: /foo.txt in foo/.gitignore should only match foo/foo.txt
        gitignore = test_dir / "foo" / ".gitignore"
        gitignore.write_text("/foo.txt\n")

        parser = GitignoreParser(str(test_dir))

        # foo.txt at root should NOT be ignored
        assert not parser.should_ignore("foo.txt"), "Root foo.txt should not be ignored"

        # foo.txt directly in foo/ should be ignored
        assert parser.should_ignore("foo/foo.txt"), "foo/foo.txt should be ignored by /foo.txt pattern"

        # foo.txt in foo/bar/ should NOT be ignored (anchored pattern only matches immediate children)
        assert not parser.should_ignore("foo/bar/foo.txt"), "foo/bar/foo.txt should NOT be ignored by /foo.txt pattern"

    def test_double_star_pattern_scoping(self):
        """Test that **/pattern in subdirectory only applies within that subtree."""
        test_dir = self.repo_path / "test_doublestar_scope"
        test_dir.mkdir()
        (test_dir / "foo").mkdir()
        (test_dir / "foo" / "bar").mkdir()
        (test_dir / "other").mkdir()

        # Create files
        (test_dir / "foo.txt").touch()  # root level
        (test_dir / "foo" / "foo.txt").touch()  # in foo/
        (test_dir / "foo" / "bar" / "foo.txt").touch()  # in foo/bar/
        (test_dir / "other" / "foo.txt").touch()  # in other/

        # Test case 3: **/foo.txt in foo/.gitignore should only ignore within foo/ subtree
        gitignore = test_dir / "foo" / ".gitignore"
        gitignore.write_text("**/foo.txt\n")

        parser = GitignoreParser(str(test_dir))

        # foo.txt at root should NOT be ignored
        assert not parser.should_ignore("foo.txt"), "Root foo.txt should not be ignored by foo/.gitignore"

        # foo.txt in foo/ should be ignored
        assert parser.should_ignore("foo/foo.txt"), "foo/foo.txt should be ignored"

        # foo.txt in foo/bar/ should be ignored (within foo/ subtree)
        assert parser.should_ignore("foo/bar/foo.txt"), "foo/bar/foo.txt should be ignored"

        # foo.txt in other/ should NOT be ignored (outside foo/ subtree)
        assert not parser.should_ignore("other/foo.txt"), "other/foo.txt should NOT be ignored by foo/.gitignore"

    def test_anchored_double_star_pattern(self):
        """Test that /**/pattern in subdirectory works correctly."""
        test_dir = self.repo_path / "test_anchored_doublestar"
        test_dir.mkdir()
        (test_dir / "foo").mkdir()
        (test_dir / "foo" / "bar").mkdir()
        (test_dir / "other").mkdir()

        # Create files
        (test_dir / "foo.txt").touch()  # root level
        (test_dir / "foo" / "foo.txt").touch()  # in foo/
        (test_dir / "foo" / "bar" / "foo.txt").touch()  # in foo/bar/
        (test_dir / "other" / "foo.txt").touch()  # in other/

        # Test case 4: /**/foo.txt in foo/.gitignore should correctly ignore only within foo/ subtree
        gitignore = test_dir / "foo" / ".gitignore"
        gitignore.write_text("/**/foo.txt\n")

        parser = GitignoreParser(str(test_dir))

        # foo.txt at root should NOT be ignored
        assert not parser.should_ignore("foo.txt"), "Root foo.txt should not be ignored"

        # foo.txt in foo/ should be ignored
        assert parser.should_ignore("foo/foo.txt"), "foo/foo.txt should be ignored"

        # foo.txt in foo/bar/ should be ignored (within foo/ subtree)
        assert parser.should_ignore("foo/bar/foo.txt"), "foo/bar/foo.txt should be ignored"

        # foo.txt in other/ should NOT be ignored (outside foo/ subtree)
        assert not parser.should_ignore("other/foo.txt"), "other/foo.txt should NOT be ignored by foo/.gitignore"


import subprocess


class TestGitWorktree:
    """Test class for Git worktree functionality."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.repo_path = Path(self.test_dir) / "main_repo"
        self.repo_path.mkdir()

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    def _run_git(self, args, cwd=None):
        """Helper to run git commands."""
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd or self.repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Git command failed: {result.stderr}")
        return result

    def _init_repo(self):
        """Initialize a git repository with a commit."""
        self._run_git(["init"])
        self._run_git(["config", "user.name", "Test User"])
        self._run_git(["config", "user.email", "test@example.com"])
        (self.repo_path / "test.txt").write_text("initial content")
        self._run_git(["add", "test.txt"])
        self._run_git(["commit", "-m", "Initial commit"])

    def test_is_git_worktree_main_repo(self):
        """Test that main repo is not detected as a worktree."""
        self._init_repo()
        from serena.util.file_system import is_git_worktree

        assert not is_git_worktree(self.repo_path)

    def test_is_git_worktree_worktree(self):
        """Test that worktree is correctly detected."""
        self._init_repo()
        from serena.util.file_system import is_git_worktree

        # Create a branch for the worktree
        self._run_git(["branch", "test-branch"])

        # Create a worktree
        worktree_path = Path(self.test_dir) / "worktree1"
        self._run_git(["worktree", "add", str(worktree_path), "test-branch"])

        assert is_git_worktree(worktree_path)
        assert not is_git_worktree(self.repo_path)

    def test_find_git_main_repo_path_from_worktree(self):
        """Test finding main repo path from a worktree."""
        self._init_repo()
        from serena.util.file_system import find_git_main_repo_path

        # Create a branch for the worktree
        self._run_git(["branch", "test-branch"])

        # Create a worktree
        worktree_path = Path(self.test_dir) / "worktree1"
        self._run_git(["worktree", "add", str(worktree_path), "test-branch"])

        # From worktree, should find main repo
        main_repo = find_git_main_repo_path(worktree_path)
        assert main_repo is not None
        assert main_repo.resolve() == self.repo_path.resolve()

        # From main repo, should return None (not a worktree)
        main_repo_from_main = find_git_main_repo_path(self.repo_path)
        assert main_repo_from_main is None

    def test_get_git_state(self):
        """Test getting git state information."""
        self._init_repo()
        from serena.util.file_system import get_git_state

        state = get_git_state(self.repo_path)

        assert state is not None
        assert state.branch == "main" or state.branch == "master"  # Git default varies
        assert len(state.commit) == 40  # Full commit hash
        assert state.is_worktree is False
        assert state.worktree_path is None

    def test_get_git_state_from_worktree(self):
        """Test getting git state from a worktree."""
        self._init_repo()
        from serena.util.file_system import get_git_state

        # Create a branch for the worktree
        self._run_git(["branch", "feature-branch"])

        # Create a worktree
        worktree_path = Path(self.test_dir) / "worktree1"
        self._run_git(["worktree", "add", str(worktree_path), "feature-branch"])

        state = get_git_state(worktree_path)

        assert state is not None
        assert state.branch == "feature-branch"
        assert state.is_worktree is True
        assert state.worktree_path is not None
        assert state.worktree_path == str(self.repo_path.resolve())

    def test_get_git_common_dir(self):
        """Test getting the common git directory."""
        self._init_repo()
        from serena.util.file_system import get_git_common_dir

        # Main repo common dir is .git
        common_dir = get_git_common_dir(self.repo_path)
        assert common_dir is not None
        assert common_dir.name == ".git"

    def test_get_git_common_dir_from_worktree(self):
        """Test getting common git directory from worktree."""
        self._init_repo()
        from serena.util.file_system import get_git_common_dir

        # Create a worktree
        self._run_git(["branch", "test-branch"])
        worktree_path = Path(self.test_dir) / "worktree1"
        self._run_git(["worktree", "add", str(worktree_path), "test-branch"])

        # From worktree, common dir should still be main repo's .git
        common_dir = get_git_common_dir(worktree_path)
        assert common_dir is not None
        # Should point to main repo's .git
        assert self.repo_path.resolve() in common_dir.parents or common_dir == self.repo_path / ".git"

    def test_git_state_equality(self):
        """Test GitState equality and hashing."""
        from serena.util.file_system import GitState

        state1 = GitState(branch="main", commit="abc123", worktree_path=None, is_worktree=False)
        state2 = GitState(branch="main", commit="abc123", worktree_path=None, is_worktree=False)
        state3 = GitState(branch="main", commit="def456", worktree_path=None, is_worktree=False)

        assert state1 == state2
        assert state1 != state3
        assert hash(state1) == hash(state2)

        # Can be used in sets
        state_set = {state1, state2, state3}
        assert len(state_set) == 2  # state1 and state2 are duplicates
