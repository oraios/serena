"""
Hook system for event-driven callbacks in Murena.

This module provides a flexible hook system that allows plugins and extensions
to register callbacks that are triggered on various events throughout the
Murena agent lifecycle.

Events:
    - tool.before_execute: Triggered before a tool is executed
    - tool.after_execute: Triggered after a tool completes execution
    - tool.registered: Triggered when a tool is registered in the agent
    - project.activated: Triggered when a project becomes active
    - mode.changed: Triggered when operational mode changes
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Protocol

log = logging.getLogger(__name__)


class HookEvent(str, Enum):
    """Events that can trigger hooks."""

    TOOL_BEFORE_EXECUTE = "tool.before_execute"
    TOOL_AFTER_EXECUTE = "tool.after_execute"
    TOOL_REGISTERED = "tool.registered"
    PROJECT_ACTIVATED = "project.activated"
    MODE_CHANGED = "mode.changed"


@dataclass
class HookContext:
    """Context information passed to hook callbacks.

    Attributes:
        event: The event that triggered the hook
        data: Event-specific data (structure varies by event type)
        agent: Reference to the MurenaAgent instance
        metadata: Additional metadata for the hook execution

    """

    event: HookEvent
    data: dict[str, Any]
    agent: Any  # MurenaAgent - using Any to avoid circular import
    metadata: dict[str, Any] = field(default_factory=dict)


class HookCallback(Protocol):
    """Protocol for hook callback functions.

    Callbacks should accept a HookContext and return None or a modified context.
    Exceptions raised in callbacks are caught and logged but do not interrupt execution.
    """

    def __call__(self, context: HookContext) -> Optional[HookContext]:
        """Execute the hook callback.

        Args:
            context: The hook context containing event information

        Returns:
            Optional modified context (can modify data for next hooks in chain)

        """
        ...


@dataclass
class Hook:
    """A registered hook with metadata.

    Attributes:
        callback: The function to call when the hook is triggered
        priority: Execution priority (lower numbers execute first)
        name: Human-readable name for the hook
        enabled: Whether this hook is currently active

    """

    callback: HookCallback
    priority: int = 100
    name: str = ""
    enabled: bool = True

    def __post_init__(self):
        if not self.name:
            self.name = getattr(self.callback, "__name__", str(self.callback))


class HookRegistry:
    """Central registry for managing hooks.

    The hook registry maintains a collection of hooks organized by event type.
    It handles registration, unregistration, and triggering of hooks.

    Thread-safety: This class is not thread-safe. Hook registration should
    typically happen during agent initialization.
    """

    def __init__(self):
        """Initialize an empty hook registry."""
        self._hooks: dict[HookEvent, list[Hook]] = {event: [] for event in HookEvent}
        self._global_hooks: list[Hook] = []  # Hooks that run on all events

    def register(
        self,
        event: HookEvent,
        callback: HookCallback,
        priority: int = 100,
        name: str = "",
        enabled: bool = True,
    ) -> Hook:
        """Register a hook for a specific event.

        Args:
            event: The event to listen for
            callback: Function to call when event occurs
            priority: Execution order (lower = earlier, default 100)
            name: Optional name for the hook (defaults to callback name)
            enabled: Whether the hook starts enabled (default True)

        Returns:
            The registered Hook object

        Example:
            >>> def my_callback(ctx: HookContext) -> None:
            ...     print(f"Tool {ctx.data['tool_name']} executed")
            >>> hook = registry.register(
            ...     HookEvent.TOOL_AFTER_EXECUTE,
            ...     my_callback,
            ...     priority=50,
            ...     name="log_tool_execution"
            ... )

        """
        hook = Hook(callback=callback, priority=priority, name=name, enabled=enabled)
        self._hooks[event].append(hook)
        self._hooks[event].sort(key=lambda h: h.priority)
        log.debug(f"Registered hook '{hook.name}' for event {event.value} (priority={priority})")
        return hook

    def register_global(
        self,
        callback: HookCallback,
        priority: int = 100,
        name: str = "",
        enabled: bool = True,
    ) -> Hook:
        """Register a hook that runs on ALL events.

        Args:
            callback: Function to call on any event
            priority: Execution order (lower = earlier, default 100)
            name: Optional name for the hook
            enabled: Whether the hook starts enabled

        Returns:
            The registered Hook object

        """
        hook = Hook(callback=callback, priority=priority, name=name, enabled=enabled)
        self._global_hooks.append(hook)
        self._global_hooks.sort(key=lambda h: h.priority)
        log.debug(f"Registered global hook '{hook.name}' (priority={priority})")
        return hook

    def unregister(self, hook: Hook) -> bool:
        """Unregister a hook.

        Args:
            hook: The hook object to remove

        Returns:
            True if the hook was found and removed, False otherwise

        """
        for event_hooks in self._hooks.values():
            if hook in event_hooks:
                event_hooks.remove(hook)
                log.debug(f"Unregistered hook '{hook.name}'")
                return True

        if hook in self._global_hooks:
            self._global_hooks.remove(hook)
            log.debug(f"Unregistered global hook '{hook.name}'")
            return True

        return False

    def trigger(self, event: HookEvent, agent: Any, data: Optional[dict[str, Any]] = None) -> HookContext:
        """Trigger all hooks for a specific event.

        Hooks are executed in priority order (lowest first). If a hook modifies
        the context, the modified version is passed to subsequent hooks.

        Exceptions in hooks are caught and logged but do not interrupt execution.

        Args:
            event: The event being triggered
            agent: The MurenaAgent instance
            data: Event-specific data to pass to hooks

        Returns:
            The final hook context after all hooks have executed

        Example:
            >>> context = registry.trigger(
            ...     HookEvent.TOOL_BEFORE_EXECUTE,
            ...     agent=my_agent,
            ...     data={"tool_name": "find_symbol", "kwargs": {...}}
            ... )

        """
        context = HookContext(event=event, agent=agent, data=data or {})

        # Combine event-specific and global hooks
        all_hooks = list(self._global_hooks) + list(self._hooks[event])
        all_hooks.sort(key=lambda h: h.priority)

        # Execute hooks in priority order
        for hook in all_hooks:
            if not hook.enabled:
                continue

            try:
                result = hook.callback(context)
                if result is not None:
                    context = result  # Allow hooks to modify context
            except Exception as e:
                log.error(f"Error in hook '{hook.name}' for event {event.value}: {e}", exc_info=True)
                # Continue executing other hooks despite error

        return context

    def get_hooks(self, event: HookEvent) -> list[Hook]:
        """Get all registered hooks for an event.

        Args:
            event: The event to query

        Returns:
            List of hooks registered for this event (sorted by priority)

        """
        return list(self._hooks[event])

    def get_global_hooks(self) -> list[Hook]:
        """Get all global hooks.

        Returns:
            List of global hooks (sorted by priority)

        """
        return list(self._global_hooks)

    def disable_hook(self, hook: Hook) -> None:
        """Temporarily disable a hook without unregistering it.

        Args:
            hook: The hook to disable

        """
        hook.enabled = False
        log.debug(f"Disabled hook '{hook.name}'")

    def enable_hook(self, hook: Hook) -> None:
        """Re-enable a previously disabled hook.

        Args:
            hook: The hook to enable

        """
        hook.enabled = True
        log.debug(f"Enabled hook '{hook.name}'")

    def clear(self, event: Optional[HookEvent] = None) -> None:
        """Clear hooks for a specific event or all events.

        Args:
            event: The event to clear hooks for, or None to clear all

        """
        if event is None:
            for event_hooks in self._hooks.values():
                event_hooks.clear()
            self._global_hooks.clear()
            log.debug("Cleared all hooks")
        else:
            self._hooks[event].clear()
            log.debug(f"Cleared hooks for event {event.value}")


# Global registry instance (can be overridden in tests)
_global_registry: Optional[HookRegistry] = None


def get_global_registry() -> HookRegistry:
    """Get the global hook registry instance.

    Creates a new registry if one doesn't exist.

    Returns:
        The global HookRegistry instance

    """
    global _global_registry
    if _global_registry is None:
        _global_registry = HookRegistry()
    return _global_registry


def set_global_registry(registry: Optional[HookRegistry]) -> None:
    """Set the global hook registry instance.

    Primarily used for testing to inject a custom registry.

    Args:
        registry: The registry to use, or None to reset

    """
    global _global_registry
    _global_registry = registry
