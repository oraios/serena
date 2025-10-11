#!/usr/bin/env python3
"""Test script to verify AskUserTool registration with FastMCP"""

import sys
import logging
sys.path.insert(0, 'src')

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

# Test 1: Check if Context can be imported and tool has correct annotation
print("=" * 60)
print("Test 1: Checking Context import and tool annotation")
print("=" * 60)

try:
    from fastmcp import Context
    print(f"✓ Context imported successfully: {Context}")
except Exception as e:
    print(f"✗ Failed to import Context: {e}")
    sys.exit(1)

try:
    from serena.tools.workflow_tools import AskUserTool
    import inspect

    sig = inspect.signature(AskUserTool.apply)
    print(f"\n✓ AskUserTool imported successfully")
    print(f"  Parameters: {list(sig.parameters.keys())}")

    ctx_param = sig.parameters.get('ctx')
    if ctx_param:
        print(f"  ctx parameter annotation: {ctx_param.annotation}")
        print(f"  ctx parameter default: {ctx_param.default}")

        # Check if annotation matches Context
        from typing import get_type_hints, Union, get_origin, get_args
        try:
            hints = get_type_hints(AskUserTool.apply)
            ctx_hint = hints.get('ctx')
            print(f"  ctx resolved type hint: {ctx_hint}")

            # Check if it's a Union with Context
            if get_origin(ctx_hint) is Union:
                args = get_args(ctx_hint)
                print(f"  Union args: {args}")
                if Context in args:
                    print(f"  ✓ Context found in type hint!")
                else:
                    print(f"  ✗ Context NOT found in type hint")
            elif ctx_hint is Context:
                print(f"  ✓ Type hint is exactly Context!")
            else:
                print(f"  ✗ Type hint does not match Context")
        except Exception as e:
            print(f"  ✗ Error resolving type hints: {e}")
    else:
        print(f"  ✗ No ctx parameter found!")

except Exception as e:
    print(f"✗ Failed to import AskUserTool: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("Test 2: Check if FastMCP can detect Context in wrapper")
print("=" * 60)

# Simulate what happens in register_mcp_tool
try:
    from serena.agent import SerenaAgent
    from serena.config.context_mode import SerenaAgentContext

    # Create a minimal agent instance
    context = SerenaAgentContext.load("default")
    agent = SerenaAgent(context=context)

    # Get the AskUserTool instance
    ask_user_tool = agent.get_tool(AskUserTool)
    print(f"\n✓ Got AskUserTool instance from agent")

    # Check the bound method
    apply_method = ask_user_tool.apply
    print(f"  Bound method: {apply_method}")

    # Check class method
    class_method = AskUserTool.apply
    class_sig = inspect.signature(class_method)
    print(f"  Class method parameters: {list(class_sig.parameters.keys())}")

    # Try to get type hints the same way the registration code does
    from typing import get_type_hints
    try:
        type_hints = get_type_hints(class_method)
        print(f"  Type hints from class method: {type_hints}")

        # Check if Context is in the hints
        ctx_hint = type_hints.get('ctx')
        if ctx_hint:
            print(f"  ✓ ctx type hint found: {ctx_hint}")
            from typing import get_origin, get_args
            if get_origin(ctx_hint) is Union:
                args = get_args(ctx_hint)
                if Context in args:
                    print(f"  ✓ Context IS in the Union!")
                else:
                    print(f"  ✗ Context NOT in the Union: {args}")
        else:
            print(f"  ✗ No ctx in type hints")
    except Exception as e:
        print(f"  ✗ Error getting type hints: {e}")
        import traceback
        traceback.print_exc()

except Exception as e:
    print(f"✗ Failed to create agent or get tool: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("All tests completed!")
print("=" * 60)

