"""Regression test for the Nextflow deferred-workspace-scan flush flag.

``_flush_deferred_workspace_scan`` sends two ``completion`` requests purely to force the
server's debounced workspace scan, discarding their results; ``_workspace_scan_flushed``
exists only to skip that work once it is known to have happened. If both requests raise,
nothing was actually flushed and the flag must stay clear so the next call retries,
without spawning a real language server process.
"""

from solidlsp.language_servers.nextflow_language_server import NextflowLanguageServer


class _FakeCompletionSender:
    def __init__(self, *, always_raise: bool = False) -> None:
        self.calls = 0
        self._always_raise = always_raise

    def completion(self, params: dict) -> None:
        self.calls += 1
        if self._always_raise:
            raise TimeoutError("no response from the Nextflow language server")


class _FakeServer:
    def __init__(self, sender: _FakeCompletionSender) -> None:
        self.send = sender


def _bare_nextflow_ls(sender: _FakeCompletionSender, repo_path: str) -> NextflowLanguageServer:
    """Create an instance without running __init__ (no JVM, no process), setting only the
    state the flush machinery touches; same technique as test_typescript_timeout_policy.py.
    """
    ls = object.__new__(NextflowLanguageServer)
    ls.repository_root_path = repo_path
    ls._workspace_scan_flushed = False
    ls.server = _FakeServer(sender)
    return ls


def test_flag_stays_clear_when_both_completion_calls_fail(tmp_path) -> None:
    sender = _FakeCompletionSender(always_raise=True)
    ls = _bare_nextflow_ls(sender, str(tmp_path))

    ls._flush_deferred_workspace_scan("main.nf")

    assert sender.calls == 2
    assert ls._workspace_scan_flushed is False

    # a later call must retry, not silently skip forever
    ls._flush_deferred_workspace_scan("main.nf")
    assert sender.calls == 4


def test_flag_is_set_when_a_completion_call_succeeds(tmp_path) -> None:
    sender = _FakeCompletionSender(always_raise=False)
    ls = _bare_nextflow_ls(sender, str(tmp_path))

    ls._flush_deferred_workspace_scan("main.nf")

    assert sender.calls == 2
    assert ls._workspace_scan_flushed is True

    # once flushed, a later call is a no-op
    ls._flush_deferred_workspace_scan("main.nf")
    assert sender.calls == 2
