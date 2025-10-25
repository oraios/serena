# TDD GREEN Phase Implementation Progress

**Branch**: `feature/polyglot-support`
**Date**: 2025-10-25
**Session**: AI Panel Iterative Code Critique + TDD Implementation

---

## RED Phase Status: ✅ COMPLETE

### Tests Written (6 tests):
1. ✅ `test_concurrent_reset_lsp_manager_is_thread_safe` - **FAILING** (race condition confirmed)
2. ✅ `test_get_language_server_during_reset_is_safe` - **PENDING**
3. ✅ `test_rollback_validates_old_manager_is_functional` - **PENDING**
4. ✅ `test_rollback_handles_old_manager_already_shut_down` - **PENDING**
5. ✅ `test_language_server_property_emits_deprecation_warning` - **PENDING**
6. ✅ `test_language_server_deprecation_message_includes_migration_path` - **PENDING**

### Test Failure Evidence:
```
AssertionError: Expected 'shutdown_all_sync' to have been called once. Called 2 times.
Calls: [call(), call()].
```

**Root Cause**: Two concurrent threads both shut down the same manager due to lack of synchronization.

**Logs Proof**:
```
INFO serena.agent:agent.py:630 Stopping existing LSPManager...
INFO serena.agent:agent.py:630 Stopping existing LSPManager...  # DUPLICATE - RACE CONDITION
```

---

## GREEN Phase Implementation Plan

### Fix 1: Thread-Safe Manager Replacement (P1 - CRITICAL)
**File**: `src/serena/agent.py`
**Location**: `SerenaAgent.__init__()` and `reset_lsp_manager()`

**Changes**:
1. Add `threading.RLock()` to `__init__`
2. Wrap entire `reset_lsp_manager()` in lock
3. Use atomic swap pattern

### Fix 2: Improved Rollback Validation (P1 - CRITICAL)
**File**: `src/serena/agent.py`
**Location**: `reset_lsp_manager()` exception handler

**Changes**:
1. Validate `old_manager.get_all_working_language_servers()`
2. Only restore if functional
3. Set to None if non-functional

### Fix 3: Deprecation Warnings (P1 - CRITICAL)
**File**: `src/serena/agent.py`
**Location**: `language_server` property

**Changes**:
1. Add `warnings.warn()` with DeprecationWarning
2. Include migration path in message

---

## Implementation Order

1. ✅ Install test dependencies
2. ⏳ Implement Fix 1 (thread-safety)
3. ⏳ Run tests - verify thread-safety tests pass
4. ⏳ Implement Fix 2 (rollback validation)
5. ⏳ Run tests - verify rollback tests pass
6. ⏳ Implement Fix 3 (deprecation)
7. ⏳ Run tests - verify deprecation tests pass
8. ⏳ Run ALL tests - verify no regressions
9. ⏳ Commit with evidence

---

## Evidence Format (AGENTS.md)

When committing, include:
```
[TEST:test_agent_polyglot::TestAgentThreadSafety::test_concurrent_reset_lsp_manager_is_thread_safe=PASS]
[TEST:test_agent_polyglot::TestAgentRollbackValidation::test_rollback_validates_old_manager_is_functional=PASS]
[TEST:test_agent_polyglot::TestAgentBackwardCompatibilityDeprecation::test_language_server_property_emits_deprecation_warning=PASS]
[COMMIT:<hash>]
```

---

## Current Status

**RED Phase**: ✅ Complete - Tests failing as expected
**GREEN Phase**: ⏳ In Progress - Starting implementation
**REFACTOR Phase**: ⏳ Pending - After tests pass
**AI Panel Review**: ⏳ Pending - After refactor
