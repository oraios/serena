"""
Basic integration tests for the Angular language server.

The Angular LS understands Angular template syntax (*ngIf, [prop], (event),
{{ interpolation }}, @if/@for blocks) and provides type-aware navigation
between templates and component classes.

Workspace: a minimal standalone-component Angular app with a service that the
component injects, plus a template (.html) that interpolates component methods.
"""

import os
import re
from pathlib import Path

import pytest

from serena.util.text_utils import find_text_coordinates
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.solidlsp.conftest import read_repo_file, request_all_symbols


@pytest.mark.angular
class TestAngularLanguageServerBasics:
    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.ANGULAR], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_component_class_symbols(self, language_server: SolidLanguageServer) -> None:
        """The Angular LS exposes the component class methods/fields via tsserver."""
        all_symbols, _ = language_server.request_document_symbols("src/app/app.component.ts").get_all_symbols_and_roots()
        names = [s["name"] for s in all_symbols]
        for expected in ("AppComponent", "title", "userName", "items", "greeting", "setName"):
            assert expected in names, f"Expected '{expected}' in component symbols: {names}"

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_service_class_symbols(self, language_server: SolidLanguageServer) -> None:
        all_symbols, _ = language_server.request_document_symbols("src/app/greeting.service.ts").get_all_symbols_and_roots()
        names = [s["name"] for s in all_symbols]
        for expected in ("GreetingService", "greet", "defaultName"):
            assert expected in names, f"Expected '{expected}' in service symbols: {names}"

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_full_symbol_tree_includes_all_files(self, language_server: SolidLanguageServer) -> None:
        all_symbols = request_all_symbols(language_server)
        relative_paths = {s.get("location", {}).get("relativePath") for s in all_symbols}
        # The HTML companion is unconditionally started, so .html documentSymbol
        # contributes structural element entries to the workspace tree alongside
        # the two TS files.
        # relativePath uses OS-native separators (Path.relative_to), so build expectations the same way.
        for f in (
            os.path.join("src", "app", "app.component.ts"),
            os.path.join("src", "app", "greeting.service.ts"),
            os.path.join("src", "app", "app.component.html"),
        ):
            assert f in relative_paths, f"Expected {f} to appear in symbol tree, got {relative_paths}"

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_template_definition_to_component_method(self, language_server: SolidLanguageServer) -> None:
        """Resolve `greeting()` interpolation in the template to its component method.

        Cursor lands inside the ``greeting`` identifier on the ``{{ greeting() }}``
        line of ``app.component.html``.
        """
        path = "src/app/app.component.html"
        needle = "greeting()"
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        line, col = coords.line, coords.col
        # +1 puts the cursor inside the identifier rather than on its leading boundary.
        definitions = language_server.request_definition(path, line, col + 1)
        assert definitions, f"Expected non-empty cross-file definition for template->component method, got {definitions}"
        target_uris = [d["uri"] for d in definitions]
        assert any(uri.endswith("app.component.ts") for uri in target_uris), (
            f"Expected definition to resolve into app.component.ts, got URIs: {target_uris}"
        )

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_plain_html_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """DocumentSymbol on plain index.html should come back from the HTML companion.

        ngserver returns -32601 for documentSymbol on every .html file (plain or
        Angular template). The AngularLanguageServer routes .html documentSymbol
        to a tertiary vscode-html-language-server companion so users get a
        structural element outline instead of an empty list.
        """
        all_symbols, _ = language_server.request_document_symbols("src/index.html").get_all_symbols_and_roots()
        names = [s["name"] for s in all_symbols]
        # index.html contains <html>, <head>, <meta>, <title>, <body>, <app-root>
        for expected in ("html", "head", "body", "app-root"):
            assert expected in names, f"Expected '{expected}' in plain-HTML symbol list, got: {names}"

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_template_html_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """DocumentSymbol on an Angular template must return the HTML element tree.

        Angular template syntax (``@if``/``@for``/``{{ }}``) is ignored by the
        vscode-html-language-server parser but the surrounding element structure
        (``<section>``, ``<h1>``, ``<p>``, ``<input>``, ``<ul>``, ``<app-item-card>``)
        is still reported, which is the intended outline.
        """
        all_symbols, _ = language_server.request_document_symbols("src/app/app.component.html").get_all_symbols_and_roots()
        names = [s["name"] for s in all_symbols]
        for expected in ("section", "h1", "p", "input", "ul", "app-item-card"):
            assert expected in names, f"Expected '{expected}' in template HTML symbol list, got: {names}"

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_ts_method_references_include_template_usage(self, language_server: SolidLanguageServer) -> None:
        """References on a .ts component method must include its template callers.

        ``setName`` is defined in app.component.ts and bound in the template via
        ``(input)="setName(...)"``. On real Angular projects the typescript-language-server
        alone misses the template callers, so the Angular LS routes .ts references
        through ngserver which aggregates both .ts and .html usages.
        """
        src_path = "src/app/app.component.ts"
        # Probe at the declaration site of setName, not a usage; the regex anchors on the
        # parameter list signature so we always land on the method header even if calls move.
        coords = find_text_coordinates(read_repo_file(language_server, src_path), r"(setName)\(name:")
        assert coords is not None, "Could not locate setName declaration in app.component.ts"
        # +1 puts the cursor inside the identifier rather than on its leading boundary.
        refs = language_server.request_references(src_path, coords.line, coords.col + 1)
        ref_paths = {r.get("relativePath", "") for r in refs}
        assert any(p.endswith("app.component.html") for p in ref_paths), (
            f"Expected references for setName to include its template callsite in app.component.html, got: {ref_paths}"
        )


@pytest.mark.angular
class TestAngularHover:
    """Hover routing — .ts goes to the companion tsserver, .html goes to ngserver."""

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_hover_on_ts_method(self, language_server: SolidLanguageServer) -> None:
        """Hover on a .ts method declaration is routed through the companion TS server
        and must yield a non-empty MarkupContent describing the method signature.
        """
        path = "src/app/app.component.ts"
        needle = "setName("
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        line, col = coords.line, coords.col
        # Cursor inside the identifier (one past the leading 's') so the LSP
        # treats the position as the symbol rather than a token boundary.
        hover = language_server.request_hover(path, line, col + 1)
        assert hover is not None, f"Expected hover info for setName in {path}, got None"
        contents = hover.get("contents")
        assert contents, f"Expected non-empty hover contents, got: {hover}"
        text = contents["value"] if isinstance(contents, dict) else str(contents)
        assert "setName" in text, f"Expected setName in hover text, got: {text}"

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_hover_on_template_method_call(self, language_server: SolidLanguageServer) -> None:
        """Hover on a method call inside an Angular template ({{ greeting() }}) goes
        through ngserver and must yield Angular-aware type info.
        """
        path = "src/app/app.component.html"
        needle = "greeting()"
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        line, col = coords.line, coords.col
        # Cursor inside the identifier (one past the leading 'g').
        hover = language_server.request_hover(path, line, col + 1)
        assert hover is not None, f"Expected hover info for greeting() in {path}, got None"
        contents = hover.get("contents")
        assert contents, f"Expected non-empty hover contents, got: {hover}"


@pytest.mark.angular
class TestAngularDefinitionRouting:
    """Cross-file definition for the binding flavours not covered by basic tests."""

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_definition_from_property_binding(self, language_server: SolidLanguageServer) -> None:
        """Property binding ``[value]="userName()"`` must resolve to the component's
        ``userName`` signal field declaration in app.component.ts.
        """
        path = "src/app/app.component.html"
        needle = '[value]="userName()"'
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        line, col = coords.line, coords.col
        # Cursor on the 'u' of userName inside the binding expression
        col = col + len('[value]="')
        definitions = language_server.request_definition(path, line, col)
        assert definitions, f"Expected non-empty definition for userName binding, got {definitions}"
        target_uris = [d["uri"] for d in definitions]
        assert any(uri.endswith("app.component.ts") for uri in target_uris), (
            f"Expected definition to resolve into app.component.ts, got URIs: {target_uris}"
        )

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_definition_from_event_binding(self, language_server: SolidLanguageServer) -> None:
        """Event binding ``(input)="setName(...)"`` must resolve to the component's
        ``setName`` method declaration in app.component.ts.
        """
        path = "src/app/app.component.html"
        needle = '(input)="setName('
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        line, col = coords.line, coords.col
        col = col + len('(input)="')  # cursor on 's' of setName
        definitions = language_server.request_definition(path, line, col)
        assert definitions, f"Expected non-empty definition for setName binding, got {definitions}"
        target_uris = [d["uri"] for d in definitions]
        assert any(uri.endswith("app.component.ts") for uri in target_uris), (
            f"Expected definition to resolve into app.component.ts, got URIs: {target_uris}"
        )

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_definition_service_import_in_component(self, language_server: SolidLanguageServer) -> None:
        """The ``GreetingService`` symbol used in the constructor parameter list
        of AppComponent must resolve to greeting.service.ts via the companion TS server.
        """
        path = "src/app/app.component.ts"
        # Probe at the constructor signature, not the import line, to make sure
        # we exercise the type-resolution path rather than the module-resolution path.
        needle = "private readonly greetings: GreetingService"
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        line, col = coords.line, coords.col
        col = col + len("private readonly greetings: ")  # cursor on 'G' of GreetingService
        definitions = language_server.request_definition(path, line, col)
        assert definitions, f"Expected definition for GreetingService, got {definitions}"
        target_uris = [d["uri"] for d in definitions]
        assert any(uri.endswith("greeting.service.ts") for uri in target_uris), (
            f"Expected definition to resolve into greeting.service.ts, got URIs: {target_uris}"
        )

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_definition_from_child_component_selector(self, language_server: SolidLanguageServer) -> None:
        """The ``<app-item-card>`` element in the parent template must resolve to the
        ItemCardComponent class declaration in item-card.component.ts.

        This is an Angular-specific feature: the @angular/language-service tsserver
        plugin makes the selector string a navigable type-reference back to its
        component class.
        """
        path = "src/app/app.component.html"
        needle = "app-item-card"
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        line, col = coords.line, coords.col
        col = col + 1  # cursor inside 'app-item-card'
        definitions = language_server.request_definition(path, line, col)
        assert definitions, f"Expected definition for <app-item-card>, got {definitions}"
        target_uris = [d["uri"] for d in definitions]
        assert any(uri.endswith("item-card.component.ts") for uri in target_uris), (
            f"Expected definition to resolve into item-card.component.ts, got URIs: {target_uris}"
        )


@pytest.mark.angular
class TestAngularRename:
    """Rename routing returns a WorkspaceEdit without applying it (safe for fixtures)."""

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_rename_method_returns_edits_for_ts_and_template(self, language_server: SolidLanguageServer) -> None:
        """Renaming the ``setName`` method from its .ts declaration must return a
        WorkspaceEdit that touches both app.component.ts (declaration + any TS calls)
        and app.component.html (the ``(input)="setName(...)"`` binding).
        """
        path = "src/app/app.component.ts"
        # Anchor on the declaration site (signature with the parameter list), not a usage.
        coords = find_text_coordinates(read_repo_file(language_server, path), r"(setName)\(name:")
        assert coords is not None, "Could not locate setName declaration in app.component.ts"
        # +1 puts the cursor inside the identifier rather than on its leading boundary.
        edit = language_server.request_rename_symbol_edit(path, coords.line, coords.col + 1, "updateName")
        assert edit is not None, "Expected WorkspaceEdit, got None"
        changes = edit.get("changes") or {}
        # Some servers return ``documentChanges`` instead of (or in addition to) ``changes``.
        document_changes = edit.get("documentChanges") or []
        all_uris: set[str] = set(changes.keys())
        for dc in document_changes:
            uri = (dc.get("textDocument") or {}).get("uri") or dc.get("uri")
            if uri:
                all_uris.add(uri)
        assert any(uri.endswith("app.component.ts") for uri in all_uris), f"Expected rename edits in app.component.ts, got URIs: {all_uris}"
        assert any(uri.endswith("app.component.html") for uri in all_uris), (
            f"Expected rename edits in app.component.html (template binding), got URIs: {all_uris}"
        )


@pytest.mark.angular
class TestAngularSymbolStructure:
    """Hierarchical symbol structure — class symbols must contain method/field children."""

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_component_class_has_methods_and_fields_as_children(self, language_server: SolidLanguageServer) -> None:
        """``request_document_symbols`` should return AppComponent as a class symbol
        whose children include its methods (``greeting``, ``setName``) and signal
        fields (``title``, ``userName``, ``items``). Flat-name checks pass even when
        the hierarchy is broken; this test asserts the parent-child relationship.
        """
        all_symbols, root_symbols = language_server.request_document_symbols("src/app/app.component.ts").get_all_symbols_and_roots()

        component = next((s for s in all_symbols if s.get("name") == "AppComponent"), None)
        assert component is not None, "AppComponent class symbol not found"

        children = component.get("children") or []
        child_names = {c.get("name") for c in children}
        for expected in ("greeting", "setName", "title", "userName", "items"):
            assert expected in child_names, f"Expected '{expected}' as child of AppComponent, got: {child_names}"

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_pipe_class_in_symbol_tree(self, language_server: SolidLanguageServer) -> None:
        """A custom pipe (``ExclaimPipe``) declared in exclaim.pipe.ts must appear in
        the workspace symbol tree alongside the components and the service.
        """
        all_symbols = request_all_symbols(language_server)
        names = {s.get("name") for s in all_symbols}
        for expected in ("ExclaimPipe", "ItemCardComponent", "AppComponent", "GreetingService"):
            assert expected in names, f"Expected '{expected}' in full symbol tree, got: {sorted(names)}"


@pytest.mark.angular
class TestAngularImplementations:
    """``textDocument/implementation`` is routed through tsserver via the Angular plugin."""

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_find_implementations_of_interface_method(self, language_server: SolidLanguageServer) -> None:
        """``Greeter.greet`` is implemented by ``GreetingService``; ``request_implementation``
        invoked at the interface declaration must point at the service.

        Routed through the Angular LS' companion typescript-language-server (with the
        @angular/language-service plugin loaded as a tsserver plugin) — bare ngserver
        does not own ``textDocument/implementation``.
        """
        path = "src/app/greeter.interface.ts"
        needle = "greet("
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        line, col = coords.line, coords.col
        # Cursor inside the identifier (one past 'g').
        implementations = language_server.request_implementation(path, line, col + 1)
        assert implementations, f"Expected at least one implementation of Greeter.greet, got {implementations}"
        target_uris = [impl["uri"] for impl in implementations]
        assert any(uri.endswith("greeting.service.ts") for uri in target_uris), (
            f"Expected implementation to resolve into greeting.service.ts, got URIs: {target_uris}"
        )
