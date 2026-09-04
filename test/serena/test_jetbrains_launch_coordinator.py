import threading
import time
from unittest import mock

from filelock import FileLock

from serena.jetbrains import jetbrains_plugin_client, launch_coordinator


def _make_project(root: str = "/tmp/project", name: str = "project") -> mock.Mock:
    project = mock.Mock()
    project.project_root = root
    project.project_name = name
    return project


def _fake_process(returncode: int = 0) -> mock.Mock:
    process = mock.Mock()
    process.communicate.return_value = (b"", b"")
    process.returncode = returncode
    return process


class TestFindPluginServer:
    def test_returns_client_when_found(self) -> None:
        project = _make_project()
        client = mock.Mock()
        with mock.patch.object(jetbrains_plugin_client.JetBrainsPluginClient, "from_project", return_value=client) as from_project:
            result = launch_coordinator.find_plugin_server(project)
        assert result is client
        from_project.assert_called_once_with(project, log_warning=False)

    def test_returns_none_when_not_found(self) -> None:
        project = _make_project()
        with mock.patch.object(
            jetbrains_plugin_client.JetBrainsPluginClient, "from_project", side_effect=jetbrains_plugin_client.ServerNotFoundError("nope")
        ):
            assert launch_coordinator.find_plugin_server(project) is None


class TestLaunchAndWaitForPluginServer:
    def test_skips_launch_when_a_server_is_already_reachable(self, tmp_path) -> None:
        project = _make_project()
        client = mock.Mock()
        with (
            mock.patch.object(jetbrains_plugin_client.JetBrainsPluginClient, "from_project", return_value=client),
            mock.patch.object(launch_coordinator, "_lock_path_for_launch_command", return_value=tmp_path / "lock"),
            mock.patch("serena.jetbrains.launch_coordinator.subprocess.Popen") as popen,
        ):
            launch_coordinator.launch_and_wait_for_plugin_server(project, "pycharm")
        popen.assert_not_called()

    def test_launches_once_and_polls_until_the_server_is_reachable(self, tmp_path) -> None:
        project = _make_project()
        client = mock.Mock()
        calls = {"n": 0}

        def from_project(_project: object, log_warning: bool = True) -> object:
            calls["n"] += 1
            if calls["n"] <= 3:
                raise jetbrains_plugin_client.ServerNotFoundError("not yet")
            return client

        with (
            mock.patch.object(jetbrains_plugin_client.JetBrainsPluginClient, "from_project", side_effect=from_project),
            mock.patch.object(launch_coordinator, "_lock_path_for_launch_command", return_value=tmp_path / "lock"),
            mock.patch("serena.jetbrains.launch_coordinator.subprocess.Popen", return_value=_fake_process()) as popen,
            mock.patch("serena.jetbrains.launch_coordinator.time.sleep") as sleep,
        ):
            launch_coordinator.launch_and_wait_for_plugin_server(
                project, "pycharm", plugin_server_wait_timeout=5.0, plugin_server_poll_interval=0.01
            )
        popen.assert_called_once()
        # 1 check right after acquiring the lock (raises) + 3 polls (2 raise, the 3rd succeeds)
        assert calls["n"] == 4
        assert sleep.call_count == 2

    def test_gives_up_after_the_wait_timeout_without_raising(self, tmp_path) -> None:
        project = _make_project()
        with (
            mock.patch.object(
                jetbrains_plugin_client.JetBrainsPluginClient,
                "from_project",
                side_effect=jetbrains_plugin_client.ServerNotFoundError("never"),
            ),
            mock.patch.object(launch_coordinator, "_lock_path_for_launch_command", return_value=tmp_path / "lock"),
            mock.patch("serena.jetbrains.launch_coordinator.subprocess.Popen", return_value=_fake_process()) as popen,
        ):
            # real, tiny timeout/interval: exercises the deadline branch itself, not a mocked clock
            launch_coordinator.launch_and_wait_for_plugin_server(
                project, "pycharm", plugin_server_wait_timeout=0.05, plugin_server_poll_interval=0.01
            )
        popen.assert_called_once()

    def test_launch_command_failure_is_logged_and_does_not_poll(self, tmp_path) -> None:
        project = _make_project()
        with (
            mock.patch.object(
                jetbrains_plugin_client.JetBrainsPluginClient,
                "from_project",
                side_effect=jetbrains_plugin_client.ServerNotFoundError("not yet"),
            ) as from_project,
            mock.patch.object(launch_coordinator, "_lock_path_for_launch_command", return_value=tmp_path / "lock"),
            mock.patch("serena.jetbrains.launch_coordinator.subprocess.Popen", return_value=_fake_process(returncode=1)),
        ):
            launch_coordinator.launch_and_wait_for_plugin_server(project, "pycharm")
        # exactly one check (inside the lock, before launching); a failed launch must not enter the poll loop
        assert from_project.call_count == 1

    def test_lock_acquire_timeout_gives_up_without_launching(self, tmp_path) -> None:
        lock_path = tmp_path / "lock"
        project = _make_project()
        holder = FileLock(str(lock_path))
        holder.acquire()
        try:
            with (
                mock.patch.object(launch_coordinator, "_lock_path_for_launch_command", return_value=lock_path),
                mock.patch("serena.jetbrains.launch_coordinator.subprocess.Popen") as popen,
            ):
                launch_coordinator.launch_and_wait_for_plugin_server(project, "pycharm", lock_acquire_timeout=0.2)
        finally:
            holder.release()
        popen.assert_not_called()

    def test_concurrent_sessions_serialize_and_launch_only_once(self, tmp_path) -> None:
        lock_path = tmp_path / "lock"
        ide_started = threading.Event()
        popen_calls: list[str] = []
        popen_calls_lock = threading.Lock()

        def fake_popen(cmd: str, **_kwargs: object) -> mock.Mock:
            with popen_calls_lock:
                popen_calls.append(cmd)
            time.sleep(0.05)  # simulate the IDE taking a moment to start
            ide_started.set()
            return _fake_process()

        def from_project(_project: object, log_warning: bool = True) -> object:
            if ide_started.is_set():
                return mock.Mock()
            raise jetbrains_plugin_client.ServerNotFoundError("not yet")

        with (
            mock.patch.object(jetbrains_plugin_client.JetBrainsPluginClient, "from_project", side_effect=from_project),
            mock.patch.object(launch_coordinator, "_lock_path_for_launch_command", return_value=lock_path),
            mock.patch("serena.jetbrains.launch_coordinator.subprocess.Popen", side_effect=fake_popen),
        ):
            threads = [
                threading.Thread(
                    target=launch_coordinator.launch_and_wait_for_plugin_server,
                    args=(_make_project(root=f"/tmp/{i}", name=str(i)), "pycharm"),
                    kwargs={"plugin_server_wait_timeout": 5.0, "plugin_server_poll_interval": 0.01},
                )
                for i in range(2)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)
                assert not t.is_alive()

        assert popen_calls == ["pycharm /tmp/0"] or popen_calls == ["pycharm /tmp/1"]
