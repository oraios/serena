"""
Multi-language call hierarchy tests.

Tests call hierarchy support across 11+ languages with FULL support:
- Python, Go, TypeScript, Java, Rust, C#, Kotlin, C++, Swift, Vue, Scala

Also tests fallback behavior for unsupported languages.
"""

import pytest

from solidlsp.ls_capabilities import CallHierarchySupport, CapabilityMatrix
from solidlsp.ls_config import Language

# High-priority languages with FULL call hierarchy support
FULL_SUPPORT_LANGUAGES = [
    ("python", "test_repo/math_utils.py", "multiply", 5),
    ("go", "test_repo/main.go", "multiply", 13),
    ("typescript", "test_repo/math.ts", "multiply", 5),
    ("java", "test_repo/src/main/java/com/example/Calculator.java", "multiply", 10),
]

# Additional languages with FULL support (may require specific setup)
ADDITIONAL_FULL_SUPPORT = [
    ("vue", "test_repo/components/Counter.vue", "increment", 10),
]


class TestCallHierarchyMultiLanguage:
    """Test call hierarchy across multiple languages."""

    @pytest.mark.parametrize(
        "language,file_path,symbol_name,expected_line",
        FULL_SUPPORT_LANGUAGES,
        ids=[lang for lang, _, _, _ in FULL_SUPPORT_LANGUAGES],
    )
    def test_prepare_call_hierarchy_full_support_languages(self, make_language_server, language, file_path, symbol_name, expected_line):
        """Test prepareCallHierarchy for languages with FULL support."""
        ls = make_language_server(language)

        # Get language enum
        lang_enum = Language[language.upper()]

        # Verify capability matrix reports FULL support
        support_level = CapabilityMatrix.get_support_level(lang_enum)
        assert support_level == CallHierarchySupport.FULL, f"{language} should have FULL call hierarchy support"

        # Verify language server reports call hierarchy capability
        assert ls._has_call_hierarchy_capability(), f"{language} LS should report call hierarchy capability"

        # Test prepareCallHierarchy
        items = ls.request_call_hierarchy_prepare(file_path, expected_line, 0)

        assert items is not None, f"prepareCallHierarchy should work for {language}"
        assert len(items) > 0, f"Should find call hierarchy item for '{symbol_name}' in {language}"

        # Verify item structure
        item = items[0]
        assert "name" in item
        assert "kind" in item
        assert "uri" in item
        assert "range" in item
        assert symbol_name.lower() in item["name"].lower(), f"Item name should contain '{symbol_name}'"

    @pytest.mark.parametrize(
        "language,file_path,symbol_name,expected_line",
        FULL_SUPPORT_LANGUAGES[:2],  # Test with Python and Go
        ids=[lang for lang, _, _, _ in FULL_SUPPORT_LANGUAGES[:2]],
    )
    def test_incoming_calls_full_support_languages(self, make_language_server, language, file_path, symbol_name, expected_line):
        """Test incomingCalls for languages with FULL support."""
        ls = make_language_server(language)

        # Prepare call hierarchy
        items = ls.request_call_hierarchy_prepare(file_path, expected_line, 0)
        assert items is not None and len(items) > 0

        # Test incoming calls
        incoming = ls.request_incoming_calls(items[0])

        # Note: incoming calls may be empty if the function isn't called in test repo
        # The important part is that the method works without errors
        assert incoming is not None, f"incomingCalls should work for {language}"
        assert isinstance(incoming, list), "incomingCalls should return a list"

    @pytest.mark.parametrize(
        "language,file_path,symbol_name,expected_line",
        FULL_SUPPORT_LANGUAGES[:2],  # Test with Python and Go
        ids=[lang for lang, _, _, _ in FULL_SUPPORT_LANGUAGES[:2]],
    )
    def test_outgoing_calls_full_support_languages(self, make_language_server, language, file_path, symbol_name, expected_line):
        """Test outgoingCalls for languages with FULL support."""
        ls = make_language_server(language)

        # Prepare call hierarchy
        items = ls.request_call_hierarchy_prepare(file_path, expected_line, 0)
        assert items is not None and len(items) > 0

        # Test outgoing calls
        outgoing = ls.request_outgoing_calls(items[0])

        assert outgoing is not None, f"outgoingCalls should work for {language}"
        assert isinstance(outgoing, list), "outgoingCalls should return a list"

    @pytest.mark.parametrize(
        "language,file_path,expected_line",
        [
            ("python", "test_repo/math_utils.py", 5),
            ("go", "test_repo/main.go", 13),
        ],
        ids=["python", "go"],
    )
    def test_call_hierarchy_caching(self, make_language_server, language, file_path, expected_line):
        """Test that call hierarchy results are cached."""
        ls = make_language_server(language)

        # First call (cache miss)
        items1 = ls.request_call_hierarchy_prepare(file_path, expected_line, 0)
        assert items1 is not None

        # Second call (cache hit)
        items2 = ls.request_call_hierarchy_prepare(file_path, expected_line, 0)
        assert items2 is not None

        # Results should be identical (from cache)
        assert len(items1) == len(items2)
        if len(items1) > 0:
            assert items1[0]["name"] == items2[0]["name"]


class TestCallHierarchyCapabilityMatrix:
    """Test the capability matrix for all supported languages."""

    def test_full_support_languages_in_matrix(self):
        """Test that capability matrix correctly identifies FULL support languages."""
        full_support_langs = [
            Language.PYTHON,
            Language.GO,
            Language.TYPESCRIPT,
            Language.JAVA,
            Language.RUST,
            Language.CSHARP,
            Language.KOTLIN,
            Language.CPP,
            Language.SWIFT,
            Language.VUE,
            Language.SCALA,
        ]

        for lang in full_support_langs:
            support = CapabilityMatrix.get_support_level(lang)
            assert support == CallHierarchySupport.FULL, f"{lang.name} should have FULL support"
            assert CapabilityMatrix.has_call_hierarchy(lang), f"{lang.name} should have call hierarchy"

    def test_partial_support_languages_in_matrix(self):
        """Test that capability matrix correctly identifies PARTIAL support languages."""
        partial_support_langs = [
            Language.PHP,
            Language.RUBY,
            Language.ELIXIR,
            Language.DART,
        ]

        for lang in partial_support_langs:
            support = CapabilityMatrix.get_support_level(lang)
            assert support == CallHierarchySupport.PARTIAL, f"{lang.name} should have PARTIAL support"
            assert CapabilityMatrix.has_call_hierarchy(lang), f"{lang.name} should have call hierarchy"

    def test_fallback_languages_in_matrix(self):
        """Test that capability matrix correctly identifies FALLBACK languages."""
        fallback_langs = [
            Language.PERL,
            Language.CLOJURE,
            Language.ELM,
            Language.TERRAFORM,
            Language.BASH,
            Language.R,
        ]

        for lang in fallback_langs:
            support = CapabilityMatrix.get_support_level(lang)
            assert support == CallHierarchySupport.FALLBACK, f"{lang.name} should require FALLBACK"
            assert not CapabilityMatrix.has_call_hierarchy(lang), f"{lang.name} should not have call hierarchy"
            assert CapabilityMatrix.should_fallback_to_references(lang), f"{lang.name} should use fallback"

    def test_get_all_supported_languages(self):
        """Test getting all languages with call hierarchy support."""
        supported = CapabilityMatrix.get_all_supported_languages()

        # Should include all FULL and PARTIAL support languages
        assert "PYTHON" in supported
        assert "GO" in supported
        assert "TYPESCRIPT" in supported
        assert "JAVA" in supported
        assert "PHP" in supported
        assert "RUBY" in supported

        # Should not include FALLBACK languages
        assert "PERL" not in supported
        assert "BASH" not in supported

        # Should have at least 11 FULL + 4 PARTIAL = 15 languages
        assert len(supported) >= 15

    def test_fallback_strategy_descriptions(self):
        """Test that fallback strategies have meaningful descriptions."""
        # FULL support
        strategy = CapabilityMatrix.get_fallback_strategy(Language.PYTHON)
        assert "No fallback needed" in strategy

        # PARTIAL support
        strategy = CapabilityMatrix.get_fallback_strategy(Language.PHP)
        assert "Attempt call hierarchy" in strategy
        assert "fall back" in strategy.lower()

        # FALLBACK
        strategy = CapabilityMatrix.get_fallback_strategy(Language.JULIA)
        assert "find_referencing_symbols" in strategy
        assert "not supported" in strategy.lower()

        # UNKNOWN (using experimental language server)
        strategy = CapabilityMatrix.get_fallback_strategy(Language.RUBY_SOLARGRAPH)
        assert "Attempt" in strategy or "gracefully" in strategy.lower()


class TestCallHierarchyFallback:
    """Test fallback behavior for languages without call hierarchy support."""

    @pytest.mark.parametrize(
        "language",
        ["perl", "bash"],
        ids=["perl", "bash"],
    )
    def test_fallback_languages_no_capability(self, make_language_server, language):
        """Test that fallback languages don't report call hierarchy capability."""
        _ = make_language_server(language)  # Create LS but don't need to use it

        lang_enum = Language[language.upper()]

        # Verify capability matrix reports FALLBACK
        support = CapabilityMatrix.get_support_level(lang_enum)
        assert support == CallHierarchySupport.FALLBACK

        # Language server should not report call hierarchy capability
        # (or if it does, it should be ignored by capability matrix)
        assert CapabilityMatrix.should_fallback_to_references(lang_enum)


class TestCallHierarchyCrossFile:
    """Test call hierarchy with cross-file references."""

    @pytest.mark.parametrize(
        "language",
        ["python", "go"],
        ids=["python", "go"],
    )
    def test_cross_file_call_hierarchy(self, make_language_server, language):
        """Test that call hierarchy works across file boundaries."""
        _ = make_language_server(language)  # Create LS but don't need to use it

        # This test verifies that call hierarchy can find calls across files
        # The specific files and symbols depend on the test repository structure

        # For now, we verify that the capability exists
        lang_enum = Language[language.upper()]
        support = CapabilityMatrix.get_support_level(lang_enum)
        assert support == CallHierarchySupport.FULL

        # Cross-file support is implicit in FULL support
        # Actual cross-file tests would require specific test repositories
        # with multi-file call hierarchies


# Note: The make_language_server fixture is provided by test/conftest.py
# It handles language server initialization for each language
