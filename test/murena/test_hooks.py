"""
Unit tests for the hook system.
"""

import pytest

from murena.hooks import HookContext, HookEvent, HookRegistry, get_global_registry, set_global_registry


class TestHookRegistry:
    """Test the HookRegistry class."""

    @pytest.fixture
    def registry(self):
        """Create a fresh registry for each test."""
        reg = HookRegistry()
        return reg

    def test_register_hook(self, registry):
        """Test registering a hook."""
        called = []

        def callback(context: HookContext) -> None:
            called.append(context.event)

        hook = registry.register(HookEvent.TOOL_BEFORE_EXECUTE, callback, name="test_hook")

        assert hook.name == "test_hook"
        assert hook.enabled is True
        assert hook.priority == 100

    def test_trigger_hook(self, registry):
        """Test triggering a hook."""
        called = []

        def callback(context: HookContext) -> None:
            called.append(context.data.get("test_data"))

        registry.register(HookEvent.TOOL_BEFORE_EXECUTE, callback)

        registry.trigger(HookEvent.TOOL_BEFORE_EXECUTE, agent=None, data={"test_data": "hello"})

        assert called == ["hello"]

    def test_hook_priority(self, registry):
        """Test that hooks execute in priority order."""
        order = []

        def callback1(context: HookContext) -> None:
            order.append(1)

        def callback2(context: HookContext) -> None:
            order.append(2)

        def callback3(context: HookContext) -> None:
            order.append(3)

        # Register in reverse order with priorities
        registry.register(HookEvent.TOOL_BEFORE_EXECUTE, callback3, priority=30)
        registry.register(HookEvent.TOOL_BEFORE_EXECUTE, callback1, priority=10)
        registry.register(HookEvent.TOOL_BEFORE_EXECUTE, callback2, priority=20)

        registry.trigger(HookEvent.TOOL_BEFORE_EXECUTE, agent=None, data={})

        assert order == [1, 2, 3]

    def test_hook_context_modification(self, registry):
        """Test that hooks can modify context."""

        def callback(context: HookContext) -> HookContext:
            context.data["modified"] = True
            return context

        registry.register(HookEvent.TOOL_BEFORE_EXECUTE, callback)

        context = registry.trigger(HookEvent.TOOL_BEFORE_EXECUTE, agent=None, data={})

        assert context.data.get("modified") is True

    def test_disable_hook(self, registry):
        """Test disabling a hook."""
        called = []

        def callback(context: HookContext) -> None:
            called.append("called")

        hook = registry.register(HookEvent.TOOL_BEFORE_EXECUTE, callback)
        registry.disable_hook(hook)

        registry.trigger(HookEvent.TOOL_BEFORE_EXECUTE, agent=None, data={})

        assert called == []

    def test_global_hooks(self, registry):
        """Test global hooks that run on all events."""
        called = []

        def callback(context: HookContext) -> None:
            called.append(context.event)

        registry.register_global(callback)

        registry.trigger(HookEvent.TOOL_BEFORE_EXECUTE, agent=None, data={})
        registry.trigger(HookEvent.TOOL_AFTER_EXECUTE, agent=None, data={})

        assert len(called) == 2
        assert HookEvent.TOOL_BEFORE_EXECUTE in called
        assert HookEvent.TOOL_AFTER_EXECUTE in called

    def test_error_in_hook_doesnt_break_execution(self, registry):
        """Test that errors in hooks don't interrupt execution."""
        called = []

        def error_callback(context: HookContext) -> None:
            raise ValueError("Test error")

        def success_callback(context: HookContext) -> None:
            called.append("success")

        registry.register(HookEvent.TOOL_BEFORE_EXECUTE, error_callback, priority=10)
        registry.register(HookEvent.TOOL_BEFORE_EXECUTE, success_callback, priority=20)

        # Should not raise, but log error
        registry.trigger(HookEvent.TOOL_BEFORE_EXECUTE, agent=None, data={})

        assert called == ["success"]

    def test_unregister_hook(self, registry):
        """Test unregistering a hook."""

        def callback(context: HookContext) -> None:
            pass

        hook = registry.register(HookEvent.TOOL_BEFORE_EXECUTE, callback)
        assert len(registry.get_hooks(HookEvent.TOOL_BEFORE_EXECUTE)) == 1

        result = registry.unregister(hook)
        assert result is True
        assert len(registry.get_hooks(HookEvent.TOOL_BEFORE_EXECUTE)) == 0

    def test_global_registry(self):
        """Test global registry singleton pattern."""
        # Reset global registry
        set_global_registry(None)

        registry1 = get_global_registry()
        registry2 = get_global_registry()

        assert registry1 is registry2

        # Test custom registry
        custom = HookRegistry()
        set_global_registry(custom)

        assert get_global_registry() is custom

        # Reset
        set_global_registry(None)
