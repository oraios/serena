import sys
import inspect
from typing import get_type_hints
sys.path.insert(0, 'src')

from serena.tools.workflow_tools import AskUserTool

# Check the signature
sig = inspect.signature(AskUserTool.apply)
print("AskUserTool.apply signature (raw):")
for name, param in sig.parameters.items():
    print(f"  {name}: annotation={param.annotation}, default={param.default}")

print("\nAskUserTool.apply type hints (resolved):")
try:
    hints = get_type_hints(AskUserTool.apply)
    for name, hint in hints.items():
        print(f"  {name}: {hint}")
except Exception as e:
    print(f"  Error: {e}")

