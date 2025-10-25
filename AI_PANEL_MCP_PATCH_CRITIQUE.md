# AI Panel Critique: MCP StreamableHTTP Session Manager Patch

**File**: `src/serena/patches/mcp/server/streamable_http_manager.py`
**Date**: 2025-10-25
**Conversation ID**: 7162a336-d40d-4454-b7db-85ca02939cd9
**Processing Mode**: PARALLEL (OpenAI + Anthropic)

---

## Summary

The patch fixes a real-world client compatibility issue (Augment caching session IDs across server restarts) by creating a new session for invalid/expired session IDs instead of returning a 400 error. However, it introduces a significant **DRY violation** by duplicating 50+ lines of session creation logic.

**Total Findings**: 9 (OpenAI: 5, Anthropic: 4)
- **HIGH Priority**: 1 (DRY violation - 50+ lines duplicated)
- **MEDIUM Priority**: 5 (assert usage, documentation, error handling)
- **LOW Priority**: 3 (separation of concerns, thread-safety documentation)

---

## OpenAI Analysis (5 findings)

### HIGH Priority (1 issue)

#### 1. DRY Violation - Session Creation Logic Duplicated
**Location**: Lines 243-289 and 299-343
**Issue**: Logic for creating a new session is duplicated for both 'no session ID' and 'invalid session ID' cases.
**Explanation**: This increases maintenance burden and risk of future inconsistencies. If session creation logic needs to change, it must be updated in two places.

**Impact**:
- 50+ lines of code duplicated
- Maintenance risk: changes must be applied twice
- Bug risk: easy to update one branch and forget the other

**Recommendation**: Extract to `_create_and_start_session()` helper method

### MEDIUM Priority (2 issues)

#### 2. Assert in Production Code
**Location**: `assert self._task_group is not None`
**Issue**: Using assert for runtime checks in production is discouraged.
**Explanation**: If the assertion fails, it raises AssertionError, which may not be handled gracefully. Assert can also be disabled with Python's `-O` flag.

**Recommendation**: Replace with explicit error handling:
```python
if self._task_group is None:
    raise RuntimeError("Task group is not initialized. Ensure run() context is active.")
```

#### 3. Patch Rationale Not Documented in Code
**Location**: logger.warning(...) for invalid session ID
**Issue**: No inline comment or docstring explaining rationale for patch.
**Explanation**: Comment says "SERENA PATCH" but doesn't explain **why** (Augment client compatibility). This makes it harder for future maintainers to understand why the behavior differs from upstream.

**Recommendation**: Add detailed comment:
```python
# SERENA PATCH: Invalid/expired session ID - create new session instead of 400 error
#
# WHY: Augment MCP client caches session IDs in client-side storage and reuses them
# across server restarts. The upstream mcp-python-sdk returns 400 for invalid session
# IDs, which breaks Augment's connection flow and requires manual reconnection.
#
# EXPECTED: Transparent reconnection - client gets new session ID and continues working.
# Upstream issue: https://github.com/modelcontextprotocol/python-sdk/issues/XXX
```

### LOW Priority (2 issues)

#### 4. Thread-Safety Documentation
**Location**: `async with self._session_creation_lock`
**Issue**: Async lock usage is correct but not explicitly documented.
**Explanation**: Should document **why** the lock is needed (concurrent session creation protection).

#### 5. Separation of Concerns
**Location**: `_handle_stateful_request`
**Issue**: Session creation logic is embedded in request handler.
**Explanation**: Method is long (127 lines) and harder to test. Extracting session creation to a helper would improve readability.

---

## Anthropic Analysis (4 findings)

### MEDIUM Priority (3 issues)

#### 1. Inconsistent Error Handling Patterns
**Location**: Various exception handlers
**Issue**: Some exceptions are caught and logged, others are allowed to propagate.
**Explanation**: The patch handles session crashes differently in different places. Need consistent error handling strategy.

#### 2. Logging String Concatenation
**Location**: Lines 280, 334 (f-strings split with explicit concatenation)
**Issue**: Inconsistent with structured logging approach.
**Code**:
```python
logger.info("Cleaning up crashed session " f"{http_transport.mcp_session_id} from " "active instances.")
```

**Better**:
```python
logger.info(
    "Cleaning up crashed session %s from active instances",
    http_transport.mcp_session_id,
    extra={"session_id": http_transport.mcp_session_id, "reason": "crash"}
)
```

#### 3. Version Compatibility Warning
**Location**: Module-level version check (lines 32-44)
**Issue**: Warning is good, but doesn't prevent incompatible usage.
**Explanation**: If MCP SDK version changes significantly, patch may silently fail. Should consider raising error instead of warning, or have integration tests.

### LOW Priority (1 issue)

#### 4. Magic Number in Assertion
**Location**: Task group assertions throughout code
**Issue**: Same assertion repeated 3 times across different methods.
**Explanation**: Could extract to a helper property or method to avoid repetition.

---

## Risks

### MEDIUM Severity

1. **Future Maintenance Risk Due to Code Duplication**
   - If session creation logic needs to change, it must be updated in two places
   - High risk of bugs and inconsistencies if one branch is updated and other is forgotten
   - Already seeing small differences (logger messages differ slightly)

2. **Unhandled Assertion Errors in Production**
   - If `self._task_group` is None, code raises AssertionError
   - May not be caught by error handlers
   - Can be disabled with `-O` flag, causing None to propagate

### LOW Severity

3. **Upstream Divergence**
   - This is a complete file patch, not a minimal monkey patch
   - If upstream mcp-python-sdk changes significantly, patch will diverge
   - No automated way to detect upstream changes that should be incorporated

---

## Recommendations

### Priority 1 (HIGH - Must Fix)

#### 1. Extract Session Creation to Helper Method

**Current (duplicated)**:
```python
# Lines 240-289: New session creation
if request_mcp_session_id is None:
    logger.debug("Creating new transport")
    async with self._session_creation_lock:
        new_session_id = uuid4().hex
        # ... 40+ lines of session creation logic ...

# Lines 290-343: Invalid session creation (DUPLICATE!)
else:
    logger.warning("Invalid or expired session ID received...")
    logger.debug("Creating new transport for invalid session ID")
    async with self._session_creation_lock:
        new_session_id = uuid4().hex
        # ... SAME 40+ lines of session creation logic ...
```

**Refactored (DRY)**:
```python
async def _create_and_start_session(
    self,
    scope: Scope,
    receive: Receive,
    send: Send,
    reason: str = "new_session"
) -> None:
    """
    Create new session, start server task, and handle first request.

    Args:
        scope: ASGI scope
        receive: ASGI receive function
        send: ASGI send function
        reason: Reason for session creation (for logging): "new_session" or "invalid_session"
    """
    logger.debug(f"Creating new transport ({reason})")
    async with self._session_creation_lock:
        new_session_id = uuid4().hex
        http_transport = StreamableHTTPServerTransport(
            mcp_session_id=new_session_id,
            is_json_response_enabled=self.json_response,
            event_store=self.event_store,
            security_settings=self.security_settings,
        )

        assert http_transport.mcp_session_id is not None
        self._server_instances[http_transport.mcp_session_id] = http_transport
        logger.info(
            "Created new transport with session ID: %s (reason: %s)",
            new_session_id,
            reason,
            extra={"session_id": new_session_id, "reason": reason}
        )

        async def run_server(*, task_status: TaskStatus[None] = anyio.TASK_STATUS_IGNORED) -> None:
            async with http_transport.connect() as streams:
                read_stream, write_stream = streams
                task_status.started()
                try:
                    await self.app.run(
                        read_stream,
                        write_stream,
                        self.app.create_initialization_options(),
                        stateless=False,
                    )
                except Exception as e:
                    logger.error(
                        "Session %s crashed: %s",
                        http_transport.mcp_session_id,
                        e,
                        exc_info=True,
                        extra={"session_id": http_transport.mcp_session_id, "error": str(e)}
                    )
                finally:
                    if (
                        http_transport.mcp_session_id
                        and http_transport.mcp_session_id in self._server_instances
                        and not http_transport.is_terminated
                    ):
                        logger.info(
                            "Cleaning up crashed session %s from active instances",
                            http_transport.mcp_session_id,
                            extra={"session_id": http_transport.mcp_session_id, "reason": "crash"}
                        )
                        del self._server_instances[http_transport.mcp_session_id]

        if self._task_group is None:
            raise RuntimeError("Task group is not initialized. Ensure run() context is active.")

        await self._task_group.start(run_server)
        await http_transport.handle_request(scope, receive, send)


async def _handle_stateful_request(self, scope: Scope, receive: Receive, send: Send) -> None:
    """..."""
    request = Request(scope, receive)
    request_mcp_session_id = request.headers.get(MCP_SESSION_ID_HEADER)

    # Existing session case
    if request_mcp_session_id is not None and request_mcp_session_id in self._server_instances:
        transport = self._server_instances[request_mcp_session_id]
        logger.debug("Session already exists, handling request directly")
        await transport.handle_request(scope, receive, send)
        return

    if request_mcp_session_id is None:
        # New session case
        await self._create_and_start_session(scope, receive, send, reason="new_session")
    else:
        # SERENA PATCH: Invalid/expired session ID - create new session instead of 400 error
        #
        # WHY: Augment MCP client caches session IDs in client-side storage and reuses them
        # across server restarts. The upstream mcp-python-sdk returns 400 for invalid session
        # IDs, which breaks Augment's connection flow and requires manual reconnection.
        #
        # EXPECTED: Transparent reconnection - client gets new session ID and continues working.
        logger.warning(
            "Invalid or expired session ID received: %s. Creating new session.",
            request_mcp_session_id,
            extra={"invalid_session_id": request_mcp_session_id, "action": "create_new_session"},
        )
        await self._create_and_start_session(scope, receive, send, reason="invalid_session")
```

**Benefits**:
- Eliminates 50+ line duplication
- Single source of truth for session creation
- Easier to test in isolation
- Future changes only need to be made once
- Consistent logging across both paths

### Priority 2 (MEDIUM - Should Fix)

#### 2. Replace Asserts with Explicit Checks

Replace all occurrences of:
```python
assert self._task_group is not None
```

With:
```python
if self._task_group is None:
    raise RuntimeError(
        "Task group is not initialized. "
        "Ensure StreamableHTTPSessionManager.run() context is active."
    )
```

#### 3. Improve Structured Logging

Replace f-string concatenation with % formatting:
```python
# Before:
logger.info("Cleaning up crashed session " f"{http_transport.mcp_session_id} from " "active instances.")

# After:
logger.info(
    "Cleaning up crashed session %s from active instances",
    http_transport.mcp_session_id,
    extra={"session_id": http_transport.mcp_session_id, "reason": "crash"}
)
```

#### 4. Add Integration Test for Patch Behavior

Create test that verifies:
- Invalid session ID creates new session (not 400 error)
- New session ID is returned in response headers
- Client can continue making requests with new session ID

---

## Notes

- **Patch Strategy**: Complete file copy from mcp==1.12.3, not minimal monkey patch
- **Upstream Tracking**: Need mechanism to track upstream changes
- **Client Compatibility**: This patch is specifically for Augment client behavior
- **Alternative Approach**: Could use minimal monkey patch instead of full file copy

---

## Next Steps

1. **Immediate**: Implement P1 fix (extract helper method to eliminate DRY violation)
2. **Soon**: Replace asserts with explicit error handling
3. **Future**: Consider minimal monkey patch approach vs full file copy
4. **Upstream**: Consider submitting PR to mcp-python-sdk to handle invalid sessions gracefully
