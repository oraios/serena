# Workflow Intelligence Developer Guide

This guide explains how to extend the Murena workflow intelligence system with custom hooks, composite tools, and workflows.

## Table of Contents

1. [Hook System API](#hook-system-api)
2. [Creating Composite Tools](#creating-composite-tools)
3. [Workflow Composition](#workflow-composition)
4. [Pattern Detection](#pattern-detection)

---

## Hook System API

### Overview

The hook system allows you to register callbacks that execute at specific points in the Murena agent lifecycle.

### Available Events

```python
from murena.hooks import HookEvent

HookEvent.TOOL_BEFORE_EXECUTE  # Before any tool executes
HookEvent.TOOL_AFTER_EXECUTE   # After any tool completes
HookEvent.TOOL_REGISTERED      # When a tool is registered
HookEvent.PROJECT_ACTIVATED    # When a project becomes active
HookEvent.MODE_CHANGED         # When operational mode changes
```

### Registering a Hook

```python
from murena.hooks import get_global_registry, HookContext

def my_hook(context: HookContext) -> None:
    """Hook callback function."""
    print(f"Tool executed: {context.data.get('tool_name')}")
    # Access agent: context.agent
    # Access event-specific data: context.data
    # Modify data for next hooks: context.data['key'] = 'value'

# Register the hook
registry = get_global_registry()
hook = registry.register(
    event=HookEvent.TOOL_AFTER_EXECUTE,
    callback=my_hook,
    priority=100,  # Lower numbers execute first
    name="my_custom_hook"
)
```

### Hook Context

The `HookContext` object passed to callbacks contains:

```python
@dataclass
class HookContext:
    event: HookEvent           # The event that triggered this hook
    data: Dict[str, Any]       # Event-specific data
    agent: MurenaAgent         # Reference to the agent
    metadata: Dict[str, Any]   # Additional metadata
```

### Event-Specific Data

**TOOL_BEFORE_EXECUTE:**
```python
{
    "tool_name": str,           # Name of the tool
    "tool_instance": Tool,      # The tool instance
    "kwargs": dict,             # Tool parameters (can be modified!)
}
```

**TOOL_AFTER_EXECUTE:**
```python
{
    "tool_name": str,
    "tool_instance": Tool,
    "kwargs": dict,
    "result": str,              # Tool result
    "success": bool,            # Whether execution succeeded
    "error": Exception | None,  # Exception if failed
}
```

**PROJECT_ACTIVATED:**
```python
{
    "project": Project,
    "project_name": str,
    "project_root": str,
}
```

**MODE_CHANGED:**
```python
{
    "old_modes": List[str],
    "new_modes": List[str],
    "modes": List[MurenaAgentMode],
}
```

### Modifying Tool Parameters

Hooks on `TOOL_BEFORE_EXECUTE` can modify parameters:

```python
def auto_optimize(context: HookContext) -> HookContext:
    """Automatically enable compact format for large operations."""
    if context.data["tool_name"] == "get_symbols_overview":
        context.data["kwargs"]["compact_format"] = True
    return context

registry.register(HookEvent.TOOL_BEFORE_EXECUTE, auto_optimize)
```

### Global Hooks

Global hooks run on **all** events:

```python
def log_all_events(context: HookContext) -> None:
    """Log every event."""
    print(f"Event: {context.event.value}")

registry.register_global(log_all_events)
```

### Error Handling

Exceptions in hooks are caught and logged but don't interrupt execution:

```python
def risky_hook(context: HookContext) -> None:
    if context.data.get("critical"):
        raise ValueError("Critical error!")
    # Execution continues even if this raises

registry.register(HookEvent.TOOL_AFTER_EXECUTE, risky_hook)
```

### Hook Management

```python
# Disable a hook temporarily
registry.disable_hook(hook)

# Re-enable it
registry.enable_hook(hook)

# Unregister completely
registry.unregister(hook)

# Clear all hooks for an event
registry.clear(HookEvent.TOOL_BEFORE_EXECUTE)

# Clear all hooks
registry.clear()
```

---

## Creating Composite Tools

### Overview

Composite tools combine multiple atomic operations into cohesive workflows with automatic result chaining and error handling.

### Basic Structure

```python
from murena.tools.composite.base import CompositeTool, CompositeStep, CompositeResult

class MyCompositeTool(CompositeTool):
    @staticmethod
    def get_name_from_cls() -> str:
        return "my_composite_tool"

    @staticmethod
    def get_apply_docstring_from_cls() -> str:
        return """Description of what this composite tool does.

        Args:
            param1: Description
            param2: Description

        Returns:
            Formatted result

        Example:
            my_composite_tool(param1="value")
        """

    def get_steps(self, **kwargs) -> List[CompositeStep]:
        """Define the workflow steps."""
        return [
            CompositeStep(
                tool_name="first_tool",
                params={"arg": kwargs.get("param1")},
                result_key="step1"
            ),
            CompositeStep(
                tool_name="second_tool",
                params={"input": "${step1}"},  # Reference previous result
                result_key="step2"
            ),
        ]

    def format_result(self, composite_result: CompositeResult) -> str:
        """Format the final result for the user."""
        step1_result = composite_result.results.get("step1")
        step2_result = composite_result.results.get("step2")

        return f"# Results\n\nStep 1: {step1_result}\n\nStep 2: {step2_result}"
```

### Parameter Interpolation

Use `${result_key}` syntax to reference previous results:

```python
CompositeStep(
    tool_name="find_referencing_symbols",
    params={
        "name_path": "${symbol_name}",      # From previous step
        "relative_path": "${file_path}",    # From previous step
        "context_mode": "line_only"         # Static value
    },
    result_key="references"
)
```

### Conditional Steps

Add conditions to execute steps only when criteria are met:

```python
CompositeStep(
    tool_name="analyze_test_failure",
    params={"test_result": "${test_results}"},
    result_key="failure_analysis",
    condition=lambda ctx: ctx.get("tests_failed", 0) > 0
)
```

### Error Handling

Provide custom error handlers for specific steps:

```python
def handle_search_error(error: Exception, context: Dict[str, Any]) -> str:
    """Handle errors when search fails."""
    return f"Search failed: {error}. Using fallback pattern."

CompositeStep(
    tool_name="search_for_pattern",
    params={"pattern": "${search_term}"},
    result_key="search_results",
    error_handler=handle_search_error
)
```

### Token Optimization

Composite tools automatically save tokens by:
- Batching operations (fewer round-trips)
- Avoiding redundant reads
- Chaining results efficiently

**Example savings:**
```python
# Manual approach: 5 tool calls, 50,000 tokens
find_symbol(...)
find_referencing_symbols(...)
rename_symbol(...)
find_tests_for_symbol(...)
run_tests(...)

# Composite approach: 1 tool call, 5,000 tokens (90% savings)
refactor_symbol(symbol_name="...", operation="rename", new_name="...")
```

### Registration

Composite tools must be registered like regular tools:

```python
# In src/murena/tools/__init__.py
from murena.tools.composite.my_tool import MyCompositeTool

# Tool will be auto-discovered by ToolRegistry
```

---

## Workflow Composition

### Overview

Workflows can call other workflows and include reusable fragments, enabling complex automations.

### Calling Workflows

```yaml
# parent-workflow.yml
name: parent-workflow
description: Calls nested workflows
steps:
  - tool: find_symbol
    args:
      name_path_pattern: ${symbol_name}

  - call_workflow: test-validation  # Call nested workflow
    args:
      symbol_name: ${symbol_name}
      relative_path: ${relative_path}
```

### Workflow Fragments

Create reusable fragments in `workflows/fragments/`:

```yaml
# workflows/fragments/test-validation.yml
name: test-validation
description: Reusable test validation fragment
steps:
  - tool: find_tests_for_symbol
    args:
      symbol_name: ${symbol_name}
      relative_path: ${relative_path}

  - tool: run_tests

  - condition: ${test_results.failed} > 0
    tool: analyze_test_failure
    args:
      test_result: ${test_results}
```

Include in workflows:

```yaml
steps:
  - tool: refactor_symbol
    args: {symbol: ${symbol}}

  - include_fragment: test-validation  # Include fragment steps
```

### Composer API

```python
from murena.workflows.composition import WorkflowComposer

composer = WorkflowComposer(
    workflow_dirs=["~/.murena/workflows", ".murena/workflows"]
)

# Load a workflow
workflow = composer.load_workflow("my-workflow")

# Load a fragment
fragment = composer.load_fragment("test-validation")

# Compose (resolve call_workflow and include_fragment directives)
composed = composer.compose_workflow(workflow)
```

### Creating Example Workflows

```python
from murena.workflows.composition import create_example_workflows

# Creates example workflows and fragments in ~/.murena/workflows/
create_example_workflows()
```

---

## Pattern Detection

### Overview

The pattern detector analyzes conversation logs to identify repetitive tool sequences and suggest workflow creation.

### Recording Tool Calls

```python
from murena.discovery.pattern_detector import PatternDetector

detector = PatternDetector(
    min_occurrences=3,      # Minimum times pattern must occur
    min_sequence_length=2   # Minimum length of sequences
)

# Record tool calls during session
detector.add_tool_call("find_symbol", {"name": "MyClass"})
detector.add_tool_call("find_referencing_symbols", {"name": "MyClass"})

# Mark end of session
detector.end_session()
```

### Detecting Patterns

```python
# After multiple sessions
patterns = detector.detect_patterns()

for pattern in patterns:
    print(f"Pattern: {pattern.tool_sequence}")
    print(f"Occurrences: {pattern.occurrences}")
    print(f"Suggested workflow: {pattern.suggested_workflow_name}")
```

### Pattern Object

```python
@dataclass
class DetectedPattern:
    pattern_id: str                      # Unique identifier
    tool_sequence: List[str]             # Sequence of tools
    occurrences: int                     # How many times it occurred
    confidence: float                    # Confidence score (0.0-1.0)
    suggested_workflow_name: str         # Suggested name
    example_params: Dict[str, Any]       # Example parameters
```

### Integration with Hooks

```python
from murena.hooks import get_global_registry, HookEvent
from murena.discovery.pattern_detector import PatternDetector

detector = PatternDetector()

def track_tool_usage(context: HookContext) -> None:
    """Record tool usage for pattern detection."""
    detector.add_tool_call(
        tool_name=context.data["tool_name"],
        params=context.data["kwargs"]
    )

registry = get_global_registry()
registry.register(HookEvent.TOOL_AFTER_EXECUTE, track_tool_usage)

# End session periodically
def on_project_activated(context: HookContext) -> None:
    detector.end_session()  # New session for new project

registry.register(HookEvent.PROJECT_ACTIVATED, on_project_activated)
```

---

## Best Practices

### Hook System
- ✅ Keep hooks lightweight (avoid expensive operations)
- ✅ Use priority ordering for dependent hooks
- ✅ Handle errors gracefully (don't interrupt execution)
- ✅ Document hook side effects clearly

### Composite Tools
- ✅ Design for common workflows (80/20 rule)
- ✅ Provide clear documentation with examples
- ✅ Include error handlers for unreliable steps
- ✅ Measure and report token savings

### Workflows
- ✅ Create fragments for reusable patterns
- ✅ Use meaningful parameter names
- ✅ Document expected inputs/outputs
- ✅ Test workflows before deployment

### Pattern Detection
- ✅ Set appropriate thresholds (avoid noise)
- ✅ Review suggested workflows before creation
- ✅ Clear patterns periodically to avoid stale data
- ✅ Combine with user feedback for refinement

---

## Examples

See the following files for complete examples:
- `src/murena/tools/composite/navigation.py` - Navigation composite tools
- `src/murena/tools/composite/refactoring.py` - Refactoring composite tools
- `~/.murena/workflows/` - Example workflows
- `test/murena/test_hooks.py` - Hook system tests
- `test/murena/test_composite_tools.py` - Composite tool tests
