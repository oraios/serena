from pathlib import Path

from solidlsp.language_servers.ruby_lsp import RubyLsp
from solidlsp.ls_config import Language
from solidlsp.settings import SolidLSPSettings


def _build_ruby_lsp(settings: SolidLSPSettings) -> RubyLsp:
    language_server = RubyLsp.__new__(RubyLsp)
    language_server._solidlsp_settings = settings
    language_server.repository_root_path = ""
    return language_server


def test_ruby_lsp_excludes_vendor_by_default(tmp_path: Path) -> None:
    language_server = _build_ruby_lsp(SolidLSPSettings())

    patterns = language_server._get_ruby_exclude_patterns(str(tmp_path))

    assert "**/vendor/**" in patterns


def test_ruby_lsp_can_keep_vendor_engines_indexed(tmp_path: Path) -> None:
    (tmp_path / "vendor" / "engines").mkdir(parents=True)
    (tmp_path / "vendor" / "bundle").mkdir(parents=True)
    (tmp_path / "vendor" / "cache").mkdir(parents=True)
    (tmp_path / "vendor" / "engines" / "blog" / "vendor" / "bundle").mkdir(parents=True)

    settings = SolidLSPSettings(ls_specific_settings={Language.RUBY: {"vendor_include_paths": ["vendor/engines"]}})
    language_server = _build_ruby_lsp(settings)

    patterns = language_server._get_ruby_exclude_patterns(str(tmp_path))

    assert "**/vendor/**" not in patterns
    assert "vendor/bundle/**" in patterns
    assert "vendor/cache/**" in patterns
    assert "vendor/engines/**" not in patterns
    assert "vendor/engines/**/vendor/**" in patterns


def test_ruby_lsp_ignores_non_allowlisted_vendor_paths(tmp_path: Path) -> None:
    bundle_file = tmp_path / "vendor" / "bundle" / "tool.rb"
    bundle_file.parent.mkdir(parents=True)
    bundle_file.write_text("class Tool; end\n")

    nested_vendor_file = tmp_path / "vendor" / "engines" / "blog" / "vendor" / "cache" / "tool.rb"
    nested_vendor_file.parent.mkdir(parents=True)
    nested_vendor_file.write_text("class Tool; end\n")

    settings = SolidLSPSettings(ls_specific_settings={Language.RUBY: {"vendor_include_paths": ["vendor/engines"]}})
    language_server = _build_ruby_lsp(settings)
    language_server.repository_root_path = str(tmp_path)

    assert language_server.is_ignored_path("vendor/bundle/tool.rb")
    assert language_server.is_ignored_path("vendor/engines/blog/vendor/cache/tool.rb")


def test_ruby_lsp_keeps_allowlisted_vendor_engines_paths(tmp_path: Path) -> None:
    engine_file = tmp_path / "vendor" / "engines" / "blog" / "app" / "models" / "post.rb"
    engine_file.parent.mkdir(parents=True)
    engine_file.write_text("class Post; end\n")

    settings = SolidLSPSettings(ls_specific_settings={Language.RUBY: {"vendor_include_paths": ["vendor/engines"]}})
    language_server = _build_ruby_lsp(settings)
    language_server.repository_root_path = str(tmp_path)

    assert not language_server.is_ignored_path("vendor/engines/blog/app/models/post.rb", ignore_unsupported_files=False)
