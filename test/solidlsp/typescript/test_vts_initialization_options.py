"""
Unit tests for the ``VtsLanguageServer`` configuration pass-through:
``ls_specific_settings["typescript_vts"]["initialization_options"]`` is forwarded
to vtsls through three LSP channels:

* the ``initialize`` request (``initializationOptions`` field),
* the ``workspace/didChangeConfiguration`` notification (sent after initialize),
* and the ``workspace/configuration`` pull (answered per requested section).

These tests construct a minimally initialised ``VtsLanguageServer`` instance via
``object.__new__`` so that no runtime dependencies (``node``, ``npm``, network)
are required.
"""

import pytest

from solidlsp.language_servers.vts_language_server import VtsLanguageServer
from solidlsp.settings import SolidLSPSettings


def _make_server(custom_settings: dict[str, object]) -> VtsLanguageServer:
    """Create a VtsLanguageServer instance bypassing __init__ (and thus the vtsls install).

    Only the ``_custom_settings`` attribute is initialised — the tested methods touch
    nothing else on the instance. Adding new method coverage may require setting more
    attributes here.
    """
    server = object.__new__(VtsLanguageServer)
    server._custom_settings = SolidLSPSettings.CustomLSSettings(custom_settings)  # type: ignore[attr-defined]
    return server


@pytest.mark.typescript
class TestVtsInitializationOptions:
    repo_path = "/tmp/some-repo"

    def test_no_initialization_options_omits_field(self) -> None:
        server = _make_server({})
        params = server._get_initialize_params(self.repo_path)
        assert "initializationOptions" not in params

    def test_dict_initialization_options_forwarded_verbatim(self) -> None:
        opts = {
            "typescript": {"tsdk": "project/.yarn/sdks/typescript/lib"},
            "vtsls": {"autoUseWorkspaceTsdk": True},
        }
        server = _make_server({"initialization_options": opts})
        params = server._get_initialize_params(self.repo_path)
        assert params["initializationOptions"] == opts

    def test_empty_dict_initialization_options_omits_field(self) -> None:
        """Empty dict carries no settings, so it is not forwarded — same as unset."""
        server = _make_server({"initialization_options": {}})
        params = server._get_initialize_params(self.repo_path)
        assert "initializationOptions" not in params

    def test_non_dict_initialization_options_raises(self) -> None:
        for bad in ["a string", ["a", "list"], 42]:
            server = _make_server({"initialization_options": bad})
            with pytest.raises(ValueError, match="initialization_options must be a dict"):
                server._get_initialize_params(self.repo_path)

    def test_validated_accessor_returns_empty_dict_when_unset(self) -> None:
        """The accessor contract: missing key → ``{}`` (treated as 'no settings')."""
        server = _make_server({})
        assert server._initialization_options == {}

    def test_validated_accessor_returns_empty_dict_when_empty(self) -> None:
        """The accessor contract: explicit empty dict stays empty (omitted by both callers)."""
        server = _make_server({"initialization_options": {}})
        assert server._initialization_options == {}

    def test_validated_accessor_raises_on_non_dict(self) -> None:
        """The accessor contract: non-dict raises ValueError (covers both call sites)."""
        for bad in ["a string", ["a", "list"], 42]:
            server = _make_server({"initialization_options": bad})
            with pytest.raises(ValueError, match="initialization_options must be a dict"):
                server._initialization_options  # noqa: B018  # property access triggers validation

    def test_other_base_params_unchanged(self) -> None:
        """Sanity: adding initialization_options does not disturb the base initialize payload."""
        server = _make_server({"initialization_options": {"foo": "bar"}})
        params = server._get_initialize_params(self.repo_path)
        assert params["rootPath"] == self.repo_path
        root_uri = params["rootUri"]
        assert root_uri is not None and root_uri.startswith("file://")
        workspace_folders = params["workspaceFolders"]
        assert workspace_folders is not None and workspace_folders[0]["name"] == "some-repo"
        assert "capabilities" in params


@pytest.mark.typescript
class TestVtsSettingsSectionLookup:
    """
    Exercise the section extraction used to answer ``workspace/configuration``
    pull requests from vtsls (e.g. ``{"section": "typescript"}``).
    """

    SETTINGS = {
        "typescript": {"tsdk": "project/.yarn/sdks/typescript/lib"},
        "vtsls": {"autoUseWorkspaceTsdk": True},
        "javascript": {},
    }

    def test_top_level_section_returns_subdict(self) -> None:
        assert VtsLanguageServer._extract_section_value(self.SETTINGS, "typescript") == {"tsdk": "project/.yarn/sdks/typescript/lib"}

    def test_dotted_path_descends(self) -> None:
        assert VtsLanguageServer._extract_section_value(self.SETTINGS, "typescript.tsdk") == "project/.yarn/sdks/typescript/lib"

    def test_empty_section_returns_full_dict(self) -> None:
        assert VtsLanguageServer._extract_section_value(self.SETTINGS, "") == self.SETTINGS

    def test_missing_section_returns_empty_dict(self) -> None:
        assert VtsLanguageServer._extract_section_value(self.SETTINGS, "ruby") == {}

    def test_missing_leaf_returns_empty_dict(self) -> None:
        assert VtsLanguageServer._extract_section_value(self.SETTINGS, "typescript.missing") == {}

    def test_empty_user_settings_always_empty(self) -> None:
        assert VtsLanguageServer._extract_section_value({}, "typescript") == {}
        assert VtsLanguageServer._extract_section_value({}, "") == {}
