from solidlsp.ls_config import FilenameMatcher, LanguageServerId


class TestFilenameMatcherCaseSensitivity:
    """Regression tests for FilenameMatcher case-sensitivity handling.

    ``is_relevant_filename`` and ``string_contains_relevant_filename`` must apply the same
    case-folding rule: fold to lower case only when ``case_sensitive=False``. A previously inverted
    check in ``string_contains_relevant_filename`` folded the input when ``case_sensitive=True``
    (and left it unfolded when ``case_sensitive=False``), so both modes could mismatch.
    """

    def test_case_insensitive_matches_uppercase_input(self) -> None:
        matcher = FilenameMatcher(".py", ".pyi", case_sensitive=False)
        # Uppercase / mixed-case input must match a lower-case extension when case-insensitive.
        assert matcher.is_relevant_filename("FOO.PY")
        assert matcher.is_relevant_filename("Foo.PyI")
        assert matcher.string_contains_relevant_filename("opened FOO.PY for editing")
        assert matcher.string_contains_relevant_filename("see Foo.PyI:10")

    def test_case_sensitive_respects_extension_case(self) -> None:
        # R uses case-significant extensions: .R and .r are distinct.
        matcher = FilenameMatcher(".R", case_sensitive=True)
        assert matcher.is_relevant_filename("script.R")
        assert not matcher.is_relevant_filename("script.r")
        # The same must hold for the substring variant (previously inverted).
        assert matcher.string_contains_relevant_filename("edited script.R just now")
        assert not matcher.string_contains_relevant_filename("edited script.r just now")

    def test_two_methods_agree_on_case_folding(self) -> None:
        """The two matcher methods must never disagree on a filename that ends the string."""
        for case_sensitive in (True, False):
            for extensions in ((".py",), (".R", ".Rmd"), (".ts", ".tsx")):
                matcher = FilenameMatcher(*extensions, case_sensitive=case_sensitive)
                for candidate in ("main.py", "Main.PY", "app.R", "app.r", "x.ts", "X.TSX"):
                    assert matcher.is_relevant_filename(candidate) == matcher.string_contains_relevant_filename(candidate), (
                        f"disagreement for {candidate!r} with extensions={extensions} case_sensitive={case_sensitive}"
                    )

    def test_string_contains_requires_complete_extension(self) -> None:
        """A registered extension must be a *complete* extension, not a prefix of a longer word."""
        matcher = FilenameMatcher(".py", case_sensitive=False)
        assert matcher.string_contains_relevant_filename("run main.py now")
        assert matcher.string_contains_relevant_filename("main.py")
        # ".py" embedded in ".python" is not a complete extension occurrence.
        assert not matcher.string_contains_relevant_filename("file.python")


class TestFilenameMatcherExactFilenames:
    """Tests for exact-filename matching (e.g. Bazel's extensionless BUILD/WORKSPACE files),
    which must compare against the path basename rather than doing suffix matching.
    """

    def test_exact_filename_matches_bare_and_pathed(self) -> None:
        matcher = FilenameMatcher(".bzl", filenames=("BUILD", "WORKSPACE"))
        assert matcher.is_relevant_filename("BUILD")
        assert matcher.is_relevant_filename("pkg/BUILD")
        assert matcher.is_relevant_filename("/abs/path/BUILD")
        assert matcher.is_relevant_filename("WORKSPACE")

    def test_exact_filename_rejects_suffix_false_positives(self) -> None:
        matcher = FilenameMatcher(".bzl", filenames=("BUILD", "WORKSPACE"))
        assert not matcher.is_relevant_filename("PREBUILD")
        assert not matcher.is_relevant_filename("a/PREBUILD")
        assert not matcher.is_relevant_filename("BUILDER")
        assert not matcher.is_relevant_filename("foo.BUILD")
        assert not matcher.is_relevant_filename("BUILD.md")

    def test_extensions_still_match_alongside_filenames(self) -> None:
        matcher = FilenameMatcher(".bzl", ".bazel", filenames=("BUILD",))
        assert matcher.is_relevant_filename("defs.bzl")
        assert matcher.is_relevant_filename("src/rules.bzl")
        assert matcher.is_relevant_filename("BUILD.bazel")
        assert matcher.is_relevant_filename("MODULE.bazel")

    def test_case_sensitivity_applies_to_filenames(self) -> None:
        sensitive = FilenameMatcher(filenames=("BUILD",), case_sensitive=True)
        assert sensitive.is_relevant_filename("BUILD")
        assert not sensitive.is_relevant_filename("build")
        insensitive = FilenameMatcher(filenames=("BUILD",), case_sensitive=False)
        assert insensitive.is_relevant_filename("build")
        assert insensitive.is_relevant_filename("Build")

    def test_reset_and_add_extensions_leave_filenames_intact(self) -> None:
        matcher = FilenameMatcher(".bzl", filenames=("BUILD",))
        matcher.add_extensions(".foo")
        assert matcher.is_relevant_filename("BUILD")
        assert matcher.is_relevant_filename("x.foo")
        matcher.reset()
        assert matcher.is_relevant_filename("BUILD")
        assert matcher.is_relevant_filename("defs.bzl")
        assert not matcher.is_relevant_filename("x.foo")

    def test_string_contains_agrees_for_exact_filenames(self) -> None:
        matcher = FilenameMatcher(filenames=("BUILD",))
        for candidate in ("BUILD", "PREBUILD", "foo.BUILD", "BUILDER"):
            assert matcher.is_relevant_filename(candidate) == matcher.string_contains_relevant_filename(candidate), (
                f"disagreement for {candidate!r}"
            )
        assert matcher.string_contains_relevant_filename("see pkg/BUILD:12")
        assert not matcher.string_contains_relevant_filename("the PREBUILD step")

    def test_starlark_language_matcher(self) -> None:
        matcher = LanguageServerId.STARLARK.get_source_fn_matcher()
        for fn in ("BUILD", "WORKSPACE", "BUILD.bazel", "MODULE.bazel", "WORKSPACE.bzlmod", "defs.bzl", "config.star", "pkg/BUILD"):
            assert matcher.is_relevant_filename(fn), fn
        for fn in ("PREBUILD", "README.md", "main.py"):
            assert not matcher.is_relevant_filename(fn), fn
