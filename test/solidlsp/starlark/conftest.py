"""Starlark-specific fixtures.

GitHub-hosted runners ship bazelisk as `bazel`. starpls probes `bazel info` at startup;
with bazelisk and no pinned version that downloads a full Bazel release and boots a JVM
server (~60-90s stall before the first request is served) -- pure flake risk with zero
test value: everything exercised here (main-workspace label resolution, symbols,
references, diagnostics) works without bazel. We point starpls at a nonexistent bazel
binary so the probe fails instantly and deterministically on every machine.
"""

from collections.abc import Iterator

import pytest

from solidlsp import SolidLanguageServer
from test.conftest import LanguageParamRequest, start_ls_context

_BAZEL_DISABLED_SENTINEL = "serena-starlark-tests-no-bazel"


@pytest.fixture(scope="module")
def language_server(request: LanguageParamRequest) -> Iterator[SolidLanguageServer]:
    if not hasattr(request, "param"):
        raise ValueError("Language parameter must be provided via pytest.mark.parametrize")
    ls_id = request.param
    with start_ls_context(ls_id, ls_specific_settings={ls_id: {"bazel_path": _BAZEL_DISABLED_SENTINEL}}) as ls:
        yield ls
