# SPDX-License-Identifier: MIT
"""Observable Vue reference behavior with controlled language-service responses."""

from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any
from unittest.mock import Mock

import pathspec
import pytest

from solidlsp.language_servers.vue_language_server import VueLanguageServer, VueTypeScriptServer
from solidlsp.ls_config import LanguageServerId
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_process import LanguageServerTerminatedException
from solidlsp.ls_utils import PathUtils


@dataclass
class ReferenceService:
    server: VueLanguageServer
    transport: Mock
    root: Path


@pytest.fixture
def service(tmp_path: Path) -> ReferenceService:
    server = object.__new__(VueLanguageServer)
    server.repository_root_path = str(tmp_path)
    server.ls_id = LanguageServerId.VUE
    server._ignore_spec = pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, ["ignored/**"])
    companion = Mock(spec=VueTypeScriptServer)
    companion.handler = Mock()
    companion.open_file.side_effect = lambda path: nullcontext()
    server._ts_server = companion
    server._ls_operational_ready_event = Event()
    server._ls_operational_ready_event.set()
    transport = companion.handler.send
    transport.references.return_value = []
    return ReferenceService(server, transport, tmp_path)


def response(refs: list[dict]) -> dict:
    return {"type": "response", "command": "fileReferences", "success": True, "body": {"refs": refs, "symbolName": "Child.vue"}}


def reference(path: Path) -> dict:
    return {"file": str(path), "start": {"line": 2, "offset": 20}, "end": {"line": 2, "offset": 31}}


def test_successful_empty_lookup_is_empty(service: ReferenceService) -> None:
    service.transport.execute_command.return_value = response([])
    assert service.server.request_references("Child.vue", 0, 1) == []


@pytest.mark.parametrize(("line", "column"), [(-1, 0), (0, -1)])
def test_invalid_symbol_position_does_not_produce_component_references(service: ReferenceService, line: int, column: int) -> None:
    service.transport.execute_command.return_value = response([reference(service.root / "Parent.vue")])
    assert service.server.request_references("Child.vue", line, column) == []


@pytest.mark.parametrize(
    "result",
    [
        None,
        {},
        {"success": False, "message": "project unavailable"},
        {"success": True, "body": None},
        {"success": True, "body": {}},
        {"success": True, "body": {"refs": None}},
        response([{}]),
        response([{"file": "relative.vue"}]),
    ],
)
def test_failed_or_invalid_lookup_is_not_empty(service: ReferenceService, result: Any) -> None:
    service.transport.execute_command.return_value = result
    with pytest.raises(SolidLSPException, match=r"fileReferences.*Child.vue"):
        service.server.request_references("Child.vue", 0, 1)


def test_transport_failure_keeps_error_context(service: ReferenceService) -> None:
    failure = SolidLSPException("TypeScript connection closed")
    service.transport.execute_command.side_effect = failure
    with pytest.raises(SolidLSPException, match=r"fileReferences.*Child.vue.*TypeScript connection closed") as exc:
        service.server.request_references("Child.vue", 0, 1)
    assert exc.value.cause is failure


def test_terminated_service_remains_identifiable(service: ReferenceService) -> None:
    termination = LanguageServerTerminatedException("connection closed", LanguageServerId.TYPESCRIPT)
    service.transport.execute_command.side_effect = SolidLSPException("request failed", cause=termination)
    with pytest.raises(SolidLSPException, match=r"fileReferences.*Child.vue") as exc:
        service.server.request_file_references("Child.vue")
    assert exc.value.is_language_server_terminated()
    assert exc.value.get_affected_language() == LanguageServerId.TYPESCRIPT


@pytest.mark.parametrize("position", [None, {}, {"line": 0, "offset": 1}, {"line": 1, "offset": -1}, {"line": True, "offset": 1}])
def test_invalid_reference_position_is_not_empty(service: ReferenceService, position: Any) -> None:
    item = reference(service.root / "Parent.vue")
    item["start"] = position
    service.transport.execute_command.return_value = response([item])
    with pytest.raises(SolidLSPException, match="Invalid fileReferences position"):
        service.server.request_references("Child.vue", 0, 1)


def test_reversed_reference_range_is_not_empty(service: ReferenceService) -> None:
    item = reference(service.root / "Parent.vue")
    item["end"] = {"line": 1, "offset": 1}
    service.transport.execute_command.return_value = response([item])
    with pytest.raises(SolidLSPException, match="Reversed fileReferences range"):
        service.server.request_references("Child.vue", 0, 1)


def test_missing_companion_is_not_empty(service: ReferenceService) -> None:
    service.server._ts_server = None
    with pytest.raises(SolidLSPException, match=r"fileReferences.*Child.vue.*not available"):
        service.server.request_file_references("Child.vue")


def test_merge_filters_ignored_and_external_locations_and_deduplicates(service: ReferenceService) -> None:
    parent = service.root / "Parent.vue"
    ignored = service.root / "ignored" / "Generated.vue"
    ignored.parent.mkdir()
    ignored.touch()
    symbol_ref = {
        "uri": PathUtils.path_to_uri(str(parent)),
        "range": {"start": {"line": 1, "character": 19}, "end": {"line": 1, "character": 30}},
    }
    service.transport.references.return_value = [symbol_ref]
    service.transport.execute_command.return_value = response(
        [reference(parent), reference(parent), reference(ignored), reference(service.root.parent / "External.vue")]
    )

    references = service.server.request_references("Child.vue", 0, 1)

    assert references == [{**symbol_ref, "absolutePath": str(parent), "relativePath": "Parent.vue"}]


def test_utf16_offsets_and_encoded_paths_are_preserved(service: ReferenceService) -> None:
    parent = service.root / "使用 方.vue"
    source = "/* 😀 */ import Child from './Child.vue'"
    start = len(source[: source.index("./Child.vue")].encode("utf-16-le")) // 2
    item = reference(parent)
    item["start"] = {"line": 2, "offset": start + 1}
    item["end"] = {"line": 2, "offset": start + 12}
    service.transport.execute_command.return_value = response([item])

    references = service.server.request_references("Child.vue", 0, 1)

    assert len(references) == 1
    ref = references[0]
    assert Path(PathUtils.uri_to_path(ref["uri"])) == parent
    assert Path(ref["absolutePath"]) == parent
    assert ref["relativePath"] == parent.name
    assert ref["range"] == {"start": {"line": 1, "character": start}, "end": {"line": 1, "character": start + 11}}
