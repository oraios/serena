import pytest

from serena.jetbrains.jetbrains_types import SymbolDTO, SymbolDTOKey
from serena.symbol import LanguageServerSymbol, LanguageServerSymbolRetriever, NamePathComponent, NamePathMatcher
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


class TestSymbolNameMatching:
    def _create_assertion_error_message(
        self,
        name_path_pattern: str,
        name_path_components: list[NamePathComponent],
        is_substring_match: bool,
        expected_result: bool,
        actual_result: bool,
    ) -> str:
        """Helper to create a detailed error message for assertions."""
        qnp_repr = "/".join(map(str, name_path_components))

        return (
            f"Pattern '{name_path_pattern}' (substring: {is_substring_match}) vs "
            f"Name path components {name_path_components} (as '{qnp_repr}'). "
            f"Expected: {expected_result}, Got: {actual_result}"
        )

    @pytest.mark.parametrize(
        "name_path_pattern, symbol_name_path_parts, is_substring_match, expected",
        [
            # Exact matches, anywhere in the name (is_substring_match=False)
            pytest.param("foo", ["foo"], False, True, id="'foo' matches 'foo' exactly (simple)"),
            pytest.param("foo/", ["foo"], False, True, id="'foo/' matches 'foo' exactly (simple)"),
            pytest.param("foo", ["bar", "foo"], False, True, id="'foo' matches ['bar', 'foo'] exactly (simple, last element)"),
            pytest.param("foo", ["foobar"], False, False, id="'foo' does not match 'foobar' exactly (simple)"),
            pytest.param(
                "foo", ["bar", "foobar"], False, False, id="'foo' does not match ['bar', 'foobar'] exactly (simple, last element)"
            ),
            pytest.param(
                "foo", ["path", "to", "foo"], False, True, id="'foo' matches ['path', 'to', 'foo'] exactly (simple, last element)"
            ),
            # Exact matches, absolute patterns (is_substring_match=False)
            pytest.param("/foo", ["foo"], False, True, id="'/foo' matches ['foo'] exactly (absolute simple)"),
            pytest.param("/foo", ["foo", "bar"], False, False, id="'/foo' does not match ['foo', 'bar'] (absolute simple, len mismatch)"),
            pytest.param("/foo", ["bar"], False, False, id="'/foo' does not match ['bar'] (absolute simple, name mismatch)"),
            pytest.param(
                "/foo", ["bar", "foo"], False, False, id="'/foo' does not match ['bar', 'foo'] (absolute simple, position mismatch)"
            ),
            # Substring matches, anywhere in the name (is_substring_match=True)
            pytest.param("foo", ["foobar"], True, True, id="'foo' matches 'foobar' as substring (simple)"),
            pytest.param("foo", ["bar", "foobar"], True, True, id="'foo' matches ['bar', 'foobar'] as substring (simple, last element)"),
            pytest.param(
                "foo", ["barfoo"], True, True, id="'foo' matches 'barfoo' as substring (simple)"
            ),  # This was potentially ambiguous before
            pytest.param("foo", ["baz"], True, False, id="'foo' does not match 'baz' as substring (simple)"),
            pytest.param("foo", ["bar", "baz"], True, False, id="'foo' does not match ['bar', 'baz'] as substring (simple, last element)"),
            pytest.param("foo", ["my_foobar_func"], True, True, id="'foo' matches 'my_foobar_func' as substring (simple)"),
            pytest.param(
                "foo",
                ["ClassA", "my_foobar_method"],
                True,
                True,
                id="'foo' matches ['ClassA', 'my_foobar_method'] as substring (simple, last element)",
            ),
            pytest.param("foo", ["my_bar_func"], True, False, id="'foo' does not match 'my_bar_func' as substring (simple)"),
            # Substring matches, absolute patterns (is_substring_match=True)
            pytest.param("/foo", ["foobar"], True, True, id="'/foo' matches ['foobar'] as substring (absolute simple)"),
            pytest.param("/foo/", ["foobar"], True, True, id="'/foo/' matches ['foobar'] as substring (absolute simple, last element)"),
            pytest.param("/foo", ["barfoobaz"], True, True, id="'/foo' matches ['barfoobaz'] as substring (absolute simple)"),
            pytest.param(
                "/foo", ["foo", "bar"], True, False, id="'/foo' does not match ['foo', 'bar'] as substring (absolute simple, len mismatch)"
            ),
            pytest.param("/foo", ["bar"], True, False, id="'/foo' does not match ['bar'] (absolute simple, no substr)"),
            pytest.param(
                "/foo", ["bar", "foo"], True, False, id="'/foo' does not match ['bar', 'foo'] (absolute simple, position mismatch)"
            ),
            pytest.param(
                "/foo/", ["bar", "foo"], True, False, id="'/foo/' does not match ['bar', 'foo'] (absolute simple, position mismatch)"
            ),
        ],
    )
    def test_match_simple_name(self, name_path_pattern, symbol_name_path_parts, is_substring_match, expected):
        """Tests matching for simple names (no '/' in pattern)."""
        symbol_name_path_components = [NamePathComponent(part) for part in symbol_name_path_parts]
        result = NamePathMatcher(name_path_pattern, is_substring_match).matches_reversed_components(reversed(symbol_name_path_components))
        error_msg = self._create_assertion_error_message(name_path_pattern, symbol_name_path_parts, is_substring_match, expected, result)
        assert result == expected, error_msg

    @pytest.mark.parametrize(
        "name_path_pattern, symbol_name_path_parts, is_substring_match, expected",
        [
            # --- Relative patterns (suffix matching) ---
            # Exact matches, relative patterns (is_substring_match=False)
            pytest.param("bar/foo", ["bar", "foo"], False, True, id="R: 'bar/foo' matches ['bar', 'foo'] exactly"),
            pytest.param("bar/foo", ["mod", "bar", "foo"], False, True, id="R: 'bar/foo' matches ['mod', 'bar', 'foo'] exactly (suffix)"),
            pytest.param(
                "bar/foo", ["bar", "foo", "baz"], False, False, id="R: 'bar/foo' does not match ['bar', 'foo', 'baz'] (pattern shorter)"
            ),
            pytest.param("bar/foo", ["bar"], False, False, id="R: 'bar/foo' does not match ['bar'] (pattern longer)"),
            pytest.param("bar/foo", ["baz", "foo"], False, False, id="R: 'bar/foo' does not match ['baz', 'foo'] (first part mismatch)"),
            pytest.param("bar/foo", ["bar", "baz"], False, False, id="R: 'bar/foo' does not match ['bar', 'baz'] (last part mismatch)"),
            pytest.param("bar/foo", ["foo"], False, False, id="R: 'bar/foo' does not match ['foo'] (pattern longer)"),
            pytest.param(
                "bar/foo", ["other", "foo"], False, False, id="R: 'bar/foo' does not match ['other', 'foo'] (first part mismatch)"
            ),
            pytest.param(
                "bar/foo", ["bar", "otherfoo"], False, False, id="R: 'bar/foo' does not match ['bar', 'otherfoo'] (last part mismatch)"
            ),
            # Substring matches, relative patterns (is_substring_match=True)
            pytest.param("bar/foo", ["bar", "foobar"], True, True, id="R: 'bar/foo' matches ['bar', 'foobar'] as substring"),
            pytest.param(
                "bar/foo", ["mod", "bar", "foobar"], True, True, id="R: 'bar/foo' matches ['mod', 'bar', 'foobar'] as substring (suffix)"
            ),
            pytest.param("bar/foo", ["bar", "bazfoo"], True, True, id="R: 'bar/foo' matches ['bar', 'bazfoo'] as substring"),
            pytest.param("bar/fo", ["bar", "foo"], True, True, id="R: 'bar/fo' matches ['bar', 'foo'] as substring"),  # codespell:ignore
            pytest.param("bar/foo", ["bar", "baz"], True, False, id="R: 'bar/foo' does not match ['bar', 'baz'] (last no substr)"),
            pytest.param(
                "bar/foo", ["baz", "foobar"], True, False, id="R: 'bar/foo' does not match ['baz', 'foobar'] (first part mismatch)"
            ),
            pytest.param(
                "bar/foo", ["bar", "my_foobar_method"], True, True, id="R: 'bar/foo' matches ['bar', 'my_foobar_method'] as substring"
            ),
            pytest.param(
                "bar/foo",
                ["mod", "bar", "my_foobar_method"],
                True,
                True,
                id="R: 'bar/foo' matches ['mod', 'bar', 'my_foobar_method'] as substring (suffix)",
            ),
            pytest.param(
                "bar/foo",
                ["bar", "another_method"],
                True,
                False,
                id="R: 'bar/foo' does not match ['bar', 'another_method'] (last no substr)",
            ),
            pytest.param(
                "bar/foo",
                ["other", "my_foobar_method"],
                True,
                False,
                id="R: 'bar/foo' does not match ['other', 'my_foobar_method'] (first part mismatch)",
            ),
            pytest.param("bar/f", ["bar", "foo"], True, True, id="R: 'bar/f' matches ['bar', 'foo'] as substring"),
            # Exact matches, absolute patterns (is_substring_match=False)
            pytest.param("/bar/foo", ["bar", "foo"], False, True, id="A: '/bar/foo' matches ['bar', 'foo'] exactly"),
            pytest.param(
                "/bar/foo", ["bar", "foo", "baz"], False, False, id="A: '/bar/foo' does not match ['bar', 'foo', 'baz'] (pattern shorter)"
            ),
            pytest.param("/bar/foo", ["bar"], False, False, id="A: '/bar/foo' does not match ['bar'] (pattern longer)"),
            pytest.param("/bar/foo", ["baz", "foo"], False, False, id="A: '/bar/foo' does not match ['baz', 'foo'] (first part mismatch)"),
            pytest.param(
                "/bar/foo",
                ["baz", "bar", "foo"],
                False,
                False,
                id="A: '/bar/foo' does not match ['baz', 'bar', 'foo'] (only suffix match for abs pattern)",
            ),
            pytest.param("/bar/foo", ["bar", "baz"], False, False, id="A: '/bar/foo' does not match ['bar', 'baz'] (last part mismatch)"),
            # Substring matches (is_substring_match=True)
            pytest.param("/bar/foo", ["bar", "foobar"], True, True, id="A: '/bar/foo' matches ['bar', 'foobar'] as substring"),
            pytest.param("/bar/foo", ["bar", "bazfoo"], True, True, id="A: '/bar/foo' matches ['bar', 'bazfoo'] as substring"),
            pytest.param("/bar/fo", ["bar", "foo"], True, True, id="A: '/bar/fo' matches ['bar', 'foo'] as substring"),  # codespell:ignore
            pytest.param("/bar/foo", ["bar", "baz"], True, False, id="A: '/bar/foo' does not match ['bar', 'baz'] (last no substr)"),
            pytest.param(
                "/bar/foo", ["baz", "foobar"], True, False, id="A: '/bar/foo' does not match ['baz', 'foobar'] (first part mismatch)"
            ),
        ],
    )
    def test_match_name_path_pattern_path_len_2(self, name_path_pattern, symbol_name_path_parts, is_substring_match, expected):
        """Tests matching for qualified names (e.g. 'module/class/func')."""
        symbol_name_path_components = [NamePathComponent(part) for part in symbol_name_path_parts]
        result = NamePathMatcher(name_path_pattern, is_substring_match).matches_reversed_components(reversed(symbol_name_path_components))
        error_msg = self._create_assertion_error_message(name_path_pattern, symbol_name_path_parts, is_substring_match, expected, result)
        assert result == expected, error_msg

    @pytest.mark.parametrize(
        "name_path_pattern, symbol_name_path_components, expected",
        [
            pytest.param(
                "bar/foo",
                [NamePathComponent("bar"), NamePathComponent("foo", 0)],
                True,
                id="R: 'bar/foo' matches ['bar', 'foo'] with overload_index=0",
            ),
            pytest.param(
                "bar/foo",
                [NamePathComponent("bar"), NamePathComponent("foo", 1)],
                True,
                id="R: 'bar/foo' matches ['bar', 'foo'] with overload_index=1",
            ),
            pytest.param(
                "bar/foo[0]",
                [NamePathComponent("bar"), NamePathComponent("foo", 0)],
                True,
                id="R: 'bar/foo[0]' matches ['bar', 'foo'] with overload_index=0",
            ),
            pytest.param(
                "bar/foo[1]",
                [NamePathComponent("bar"), NamePathComponent("foo", 0)],
                False,
                id="R: 'bar/foo[1]' does not match ['bar', 'foo'] with overload_index=0",
            ),
            pytest.param(
                "bar/foo", [NamePathComponent("bar", 0), NamePathComponent("foo")], True, id="R: 'bar/foo' matches ['bar[0]', 'foo']"
            ),
            pytest.param(
                "bar/foo", [NamePathComponent("bar", 0), NamePathComponent("foo", 1)], True, id="R: 'bar/foo' matches ['bar[0]', 'foo[1]']"
            ),
            pytest.param(
                "bar[0]/foo", [NamePathComponent("bar", 0), NamePathComponent("foo")], True, id="R: 'bar[0]/foo' matches ['bar[0]', 'foo']"
            ),
            pytest.param(
                "bar[0]/foo[1]",
                [NamePathComponent("bar", 0), NamePathComponent("foo", 1)],
                True,
                id="R: 'bar[0]/foo[1]' matches ['bar[0]', 'foo[1]']",
            ),
            pytest.param(
                "bar[0]/foo[1]",
                [NamePathComponent("bar", 1), NamePathComponent("foo", 0)],
                False,
                id="R: 'bar[0]/foo[1]' does not match ['bar[1]', 'foo[0]']",
            ),
        ],
    )
    def test_match_name_path_pattern_with_overload_idx(self, name_path_pattern, symbol_name_path_components, expected):
        """Tests matching for qualified names (e.g. 'module/class/func')."""
        matcher = NamePathMatcher(name_path_pattern, False)
        result = matcher.matches_reversed_components(reversed(symbol_name_path_components))
        error_msg = self._create_assertion_error_message(name_path_pattern, symbol_name_path_components, False, expected, result)
        assert result == expected, error_msg


@pytest.mark.python
class TestLanguageServerSymbolRetriever:
    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_request_info(self, language_server: SolidLanguageServer):
        symbol_retriever = LanguageServerSymbolRetriever(language_server)
        create_user_method_symbol = symbol_retriever.find("UserService/create_user", within_relative_path="test_repo/services.py")[0]
        create_user_method_symbol_info = symbol_retriever.request_info_for_symbol(create_user_method_symbol)
        assert "Create a new user and store it" in create_user_method_symbol_info


class TestSymbolDictTypes:
    @staticmethod
    def check_key_type(dict_type: type, key_type: type):
        """
        :param dict_type: a TypedDict type
        :param key_type: the corresponding key type (Literal[...]) that the dict should have for keys
        """
        dict_type_keys = dict_type.__annotations__.keys()
        assert len(dict_type_keys) == len(
            key_type.__args__
        ), f"Expected {len(key_type.__args__)} keys in {dict_type}, but got {len(dict_type_keys)}"
        for expected_key in key_type.__args__:
            assert expected_key in dict_type_keys, f"Expected key '{expected_key}' not found in {dict_type}"

    def test_ls_symbol_dict_type(self):
        self.check_key_type(LanguageServerSymbol.OutputDict, LanguageServerSymbol.OutputDictKey)

    def test_jb_symbol_dict_type(self):
        self.check_key_type(SymbolDTO, SymbolDTOKey)
