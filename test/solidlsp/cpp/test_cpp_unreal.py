"""
Unreal Engine 5 fixture tests for the clangd language server.

UE game code is written against a macro-based reflection layer (UCLASS, UFUNCTION,
UPROPERTY, GENERATED_BODY) and engine container types (TArray, TMap). These tests
verify that the clangd backend resolves symbols, references, definitions, and
rename edits in the hand-written sources under Source/, and never in the
UnrealHeaderTool-style generated files under Intermediate/ (which contain the
same identifiers, as real generated reflection code does).

The fixture's stub engine headers mirror UE 5.7's ObjectMacros.h: annotation
macros are empty in real UE compilation too (only UnrealHeaderTool parses them).

The fixture lives in its own repository directory (ue_test_repo) served by
clangd only: ccls 0.20240202, the build shipped by Ubuntu and Homebrew, crashes
intermittently when its session covers the stub engine headers, and clangd is
the supported backend for Unreal Engine projects (see the setup guide).
"""

import os
from collections.abc import Iterator

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils
from test.conftest import find_identifier_position, get_repo_path, start_ls_context
from test.solidlsp.conftest import document_symbol_names, find_document_symbol

UE_REPO_PATH = get_repo_path(Language.CPP).parent / "ue_test_repo"
ABILITY_COMPONENT_H = os.path.join("Source", "TestGame", "AbilityComponent.h")
ABILITY_ACTOR_H = os.path.join("Source", "TestGame", "AbilityActor.h")
ABILITY_ACTOR_CPP = os.path.join("Source", "TestGame", "AbilityActor.cpp")


@pytest.fixture(scope="module")
def language_server() -> Iterator[SolidLanguageServer]:
    """Clangd over ue_test_repo; overrides the shared fixture for this module."""
    with start_ls_context(Language.CPP, repo_path=str(UE_REPO_PATH)) as ls:
        yield ls


@pytest.mark.cpp
class TestClangdUnrealEngine:
    """clangd on Unreal Engine-shaped C++ (reflection macros, engine containers)."""

    def test_symbol_tree_contains_reflected_types(self, language_server: SolidLanguageServer) -> None:
        """UCLASS/USTRUCT-decorated types appear in the full symbol tree."""
        symbols = language_server.request_full_symbol_tree()
        for name in ("UAbilityComponent", "AAbilityActor", "FAbilityInfo"):
            assert SymbolUtils.symbol_tree_contains_name(symbols, name), f"'{name}' not found in symbol tree"

    def test_document_symbols_show_uclass_members(self, language_server: SolidLanguageServer) -> None:
        """UFUNCTION methods and UPROPERTY fields are visible despite the macro layer."""
        names = document_symbol_names(language_server, ABILITY_COMPONENT_H)
        for expected in ("UAbilityComponent", "TriggerAbility", "GetRemainingCooldown", "Abilities", "ActiveCooldowns"):
            assert expected in names, f"Expected '{expected}' in document symbols of AbilityComponent.h, got: {names}"

    def test_references_resolve_to_handwritten_sources(self, language_server: SolidLanguageServer) -> None:
        """References to a UFUNCTION are found across files, and only in Source/, never Intermediate/."""
        # Precondition: the identifier appears verbatim in generated files on disk.
        # A text search would return them; a symbol-level tool must not.
        gen_cpp = UE_REPO_PATH / "Intermediate" / "TestGame" / "UHT" / "AbilityComponent.gen.cpp"
        assert "TriggerAbility" in gen_cpp.read_text(encoding="utf-8"), "fixture broken: honeypot lost its bait"

        trigger = find_document_symbol(language_server, ABILITY_COMPONENT_H, "TriggerAbility")
        sel_start = trigger["selectionRange"]["start"]
        refs = language_server.request_references(ABILITY_COMPONENT_H, sel_start["line"], sel_start["character"])
        ref_files = [ref.get("relativePath", "") for ref in refs]
        assert any("AbilityActor.cpp" in ref_file for ref_file in ref_files), (
            f"Expected cross-file reference in AbilityActor.cpp, got: {ref_files}"
        )
        leaked = [ref_file for ref_file in ref_files if "Intermediate" in ref_file]
        assert not leaked, f"References leaked into generated files: {leaked}"

    def test_definition_resolves_to_source_not_generated(self, language_server: SolidLanguageServer) -> None:
        """Go-to-definition on a UCLASS usage lands in the hand-written header."""
        header_path = UE_REPO_PATH / "Source" / "TestGame" / "AbilityActor.h"
        position = find_identifier_position(header_path, "UAbilityComponent")
        assert position is not None, "UAbilityComponent is not used in AbilityActor.h"
        definitions = language_server.request_definition(ABILITY_ACTOR_H, position[0], position[1])
        def_paths = [d.get("relativePath", "") for d in definitions]
        assert any("AbilityComponent.h" in p for p in def_paths), f"Expected definition in AbilityComponent.h, got: {def_paths}"
        assert all("Intermediate" not in p for p in def_paths), f"Definition resolved into generated files: {def_paths}"

    def test_symbol_locations_are_in_handwritten_sources(self, language_server: SolidLanguageServer) -> None:
        """Each reflected symbol's defining declaration is locatable in Source/.
        Serena's symbol edits (replace_symbol_body, insert_after_symbol) operate at
        these locations, so this is the edit-targeting guarantee. Generated headers
        may legitimately surface same-named forward declarations (real UHT output
        contains them); what matters is that the Source/ declaration is present.
        """
        expected_files = {
            "UAbilityComponent": "AbilityComponent.h",
            "AAbilityActor": "AbilityActor.h",
            "FAbilityInfo": "AbilityTypes.h",
            "TriggerAbility": "AbilityComponent.h",
            "OnAbilityInput": "AbilityActor.h",
        }
        symbols = language_server.request_full_symbol_tree()
        found: dict[str, list[str]] = {name: [] for name in expected_files}

        def _walk(syms):
            for sym in syms:
                name = sym.get("name")
                if name in found:
                    location = sym.get("location") or {}
                    found[name].append(location.get("relativePath", "") or str(location.get("uri", "")))
                _walk(sym.get("children", []) or [])

        _walk(symbols)
        for name, expected_file in expected_files.items():
            source_locations = [p for p in found[name] if "Source" in p and expected_file in p]
            assert source_locations, f"'{name}' has no location in Source/{{...}}/{expected_file}, got: {found[name]}"

    def test_uenum_and_enumerators_visible(self, language_server: SolidLanguageServer) -> None:
        """UENUM-decorated enum and its UMETA-annotated enumerators appear as symbols."""
        ability_types_h = os.path.join("Source", "TestGame", "AbilityTypes.h")
        names = document_symbol_names(language_server, ability_types_h)
        for expected in ("EAbilityState", "Idle", "Active", "Cooldown"):
            assert expected in names, f"Expected '{expected}' in document symbols of AbilityTypes.h, got: {names}"

    def test_macro_generated_delegate_type_resolves_to_source(self, language_server: SolidLanguageServer) -> None:
        """DECLARE_DYNAMIC_MULTICAST_DELEGATE manufactures a class, which must appear
        as a symbol located at the macro expansion site in the hand-written header.
        """
        delegate = find_document_symbol(language_server, ABILITY_COMPONENT_H, "FOnAbilityTriggered")
        location_path = (delegate.get("location") or {}).get("relativePath", "")
        assert location_path, f"FOnAbilityTriggered has no location: {delegate}"
        assert "Intermediate" not in location_path, f"Delegate symbol located in generated files: {location_path}"
        member_names = document_symbol_names(language_server, ABILITY_COMPONENT_H)
        assert "OnAbilityTriggered" in member_names, "BlueprintAssignable delegate property not visible"

    def test_interface_pattern_symbols(self, language_server: SolidLanguageServer) -> None:
        """The UINTERFACE pattern (paired UDamageable/IDamageable classes) yields both
        classes and the interface method; the implementing class shows the override.
        """
        damageable_h = os.path.join("Source", "TestGame", "Damageable.h")
        names = document_symbol_names(language_server, damageable_h)
        for expected in ("UDamageable", "IDamageable", "ReceiveDamage"):
            assert expected in names, f"Expected '{expected}' in document symbols of Damageable.h, got: {names}"

        character_h = os.path.join("Source", "TestGame", "GameCharacter.h")
        character_names = document_symbol_names(language_server, character_h)
        assert "ReceiveDamage" in character_names, "Interface override not visible in implementing class"

    def test_log_category_symbol_in_source(self, language_server: SolidLanguageServer) -> None:
        """DECLARE_LOG_CATEGORY_EXTERN manufactures a category object symbol in hand-written code."""
        log_h = os.path.join("Source", "TestGame", "TestGameLog.h")
        names = document_symbol_names(language_server, log_h)
        assert "LogTestGame" in names, f"Expected log category symbol 'LogTestGame', got: {names}"

    def test_nondynamic_delegate_type_in_source(self, language_server: SolidLanguageServer) -> None:
        """DECLARE_MULTICAST_DELEGATE (non-dynamic family) also manufactures a type in Source/."""
        delegate = find_document_symbol(language_server, ABILITY_COMPONENT_H, "FOnCooldownExpired")
        location_path = (delegate.get("location") or {}).get("relativePath", "")
        assert location_path, f"FOnCooldownExpired has no location: {delegate}"
        assert "Intermediate" not in location_path, f"Delegate symbol located in generated files: {location_path}"

    def test_character_members_with_ue_types_visible(self, language_server: SolidLanguageServer) -> None:
        """Members typed with FVector/TObjectPtr/TWeakObjectPtr/TSoftObjectPtr and a
        UPARAM(ref) UFUNCTION are all visible in the symbol tree.
        """
        character_h = os.path.join("Source", "TestGame", "GameCharacter.h")
        names = document_symbol_names(language_server, character_h)
        for expected in ("AGameCharacter", "SpawnOffset", "Abilities", "CurrentTarget", "FallbackLoadout", "Heal"):
            assert expected in names, f"Expected '{expected}' in document symbols of GameCharacter.h, got: {names}"

    def test_rename_edit_targets_only_source_files(self, language_server: SolidLanguageServer) -> None:
        """A rename WorkspaceEdit for a UFUNCTION touches only hand-written files (edit is not applied)."""
        trigger = find_document_symbol(language_server, ABILITY_COMPONENT_H, "TriggerAbility")
        sel_start = trigger["selectionRange"]["start"]
        edit = language_server.request_rename_symbol_edit(ABILITY_COMPONENT_H, sel_start["line"], sel_start["character"], "ActivateAbility")
        assert edit is not None, "clangd should support rename"

        touched: list[str] = []
        for uri in edit.get("changes") or {}:
            touched.append(uri)
        for doc_change in edit.get("documentChanges") or []:
            text_doc = doc_change.get("textDocument") or {}
            if text_doc.get("uri"):
                touched.append(text_doc["uri"])

        assert any("AbilityComponent.h" in uri for uri in touched), f"Rename does not edit the declaring header, touched: {touched}"
        leaked = [uri for uri in touched if "Intermediate" in uri]
        assert not leaked, f"Rename would edit generated files: {leaked}"
