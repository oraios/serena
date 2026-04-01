import sys
from types import SimpleNamespace

import serena.dashboard as dashboard_module
from serena.dashboard import SerenaDashboardAPI, SerenaDashboardViewer
from solidlsp.ls_config import Language


class _DummyMemoryLogHandler:
    def get_log_messages(self, from_idx: int = 0):  # pragma: no cover - simple stub
        return SimpleNamespace(messages=[], max_idx=-1)

    def clear_log_messages(self) -> None:  # pragma: no cover - simple stub
        pass


class _DummyAgent:
    def __init__(self, project: SimpleNamespace | None) -> None:
        self._project = project

    def execute_task(self, func, *, logged: bool | None = None, name: str | None = None):
        del logged, name
        return func()

    def get_active_project(self):
        return self._project


def _make_dashboard(project_languages: list[Language] | None) -> SerenaDashboardAPI:
    project = None
    if project_languages is not None:
        project = SimpleNamespace(project_config=SimpleNamespace(languages=project_languages))
    agent = _DummyAgent(project)
    return SerenaDashboardAPI(
        memory_log_handler=_DummyMemoryLogHandler(),
        tool_names=[],
        agent=agent,
        shutdown_callback=None,
        tool_usage_stats=None,
    )


def test_available_languages_include_experimental_when_no_active_project():
    dashboard = _make_dashboard(project_languages=None)
    response = dashboard._get_available_languages()
    expected = sorted(lang.value for lang in Language.iter_all(include_experimental=True))
    assert response.languages == expected


def test_available_languages_exclude_project_languages():
    dashboard = _make_dashboard(project_languages=[Language.PYTHON, Language.MARKDOWN])
    response = dashboard._get_available_languages()
    available = set(response.languages)
    assert Language.PYTHON.value not in available
    assert Language.MARKDOWN.value not in available
    # ensure experimental languages remain available for selection
    assert Language.ANSIBLE.value in available


def test_dashboard_viewer_initializes_macos_delegate_slot():
    viewer = SerenaDashboardViewer("http://localhost:24282/dashboard/index.html")
    assert viewer._app_delegate is None
    assert viewer._window_hidden_to_tray is False
    assert viewer._suppress_next_activate_reopen is False


def test_dashboard_viewer_initializes_hidden_state_for_minimized_start():
    viewer = SerenaDashboardViewer("http://localhost:24282/dashboard/index.html", start_minimized=True)
    assert viewer._window_hidden_to_tray is True
    assert viewer._suppress_next_activate_reopen is True


def test_dashboard_viewer_show_and_hide_helpers_update_state():
    viewer = SerenaDashboardViewer("http://localhost:24282/dashboard/index.html", start_minimized=True)

    class _FakeWindow:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def show(self) -> None:
            self.calls.append("show")

        def restore(self) -> None:
            self.calls.append("restore")

        def hide(self) -> None:
            self.calls.append("hide")

    viewer.window = _FakeWindow()

    viewer._show_window()
    assert viewer.window.calls == ["show", "restore"]
    assert viewer._window_hidden_to_tray is False
    assert viewer._suppress_next_activate_reopen is False

    viewer._hide_window()
    assert viewer.window.calls == ["show", "restore", "hide"]
    assert viewer._window_hidden_to_tray is True


def test_dashboard_viewer_installs_macos_dock_handler_after_pywebview_start(monkeypatch):
    order: list[str] = []

    class _ClosingEvent:
        def __iadd__(self, _handler):
            order.append("bind-closing")
            return self

    class _FakeWindow:
        def __init__(self) -> None:
            self.events = SimpleNamespace(closing=_ClosingEvent())

        def minimize(self) -> None:
            order.append("minimize")

        def show(self) -> None:
            order.append("show")

        def restore(self) -> None:
            order.append("restore")

    fake_window = _FakeWindow()

    def fake_create_window(*args, **kwargs):
        order.append("create-window")
        return fake_window

    def fake_start(callback, **kwargs):
        del kwargs
        order.append("start")
        callback()

    class _FakeAppHelperModule:
        @staticmethod
        def callAfter(func, *args, **kwargs):
            del args, kwargs
            order.append("schedule-dock-handler")
            func()

    monkeypatch.setattr(dashboard_module.sys, "platform", "darwin")
    monkeypatch.setattr(dashboard_module.webview, "create_window", fake_create_window)
    monkeypatch.setattr(dashboard_module.webview, "start", fake_start)
    monkeypatch.setitem(sys.modules, "PyObjCTools.AppHelper", _FakeAppHelperModule)

    viewer = SerenaDashboardViewer("http://localhost:24282/dashboard/index.html")
    monkeypatch.setattr(viewer, "_start_tray", lambda: order.append("start-tray"))
    monkeypatch.setattr(viewer, "_setup_macos_dock_handler", lambda: order.append("setup-dock-handler"))

    viewer.run()

    assert order == [
        "create-window",
        "bind-closing",
        "start-tray",
        "start",
        "schedule-dock-handler",
        "setup-dock-handler",
        "show",
        "restore",
    ]
