# MCP Session Handling Patch - Technical Documentation

## Problem Statement

### The Issue

MCP (Model Context Protocol) clients like Augment cache session IDs across server restarts. When a Serena MCP server restarts:

1. **Client behavior**: Augment retains the cached session ID from the previous server instance
2. **Server behavior**: The new server instance doesn't recognize the old session ID
3. **Original SDK behavior**: Returns `400 Bad Request: No valid session ID provided`
4. **Result**: MCP tools become unavailable until the client is manually restarted

This creates a poor user experience where Serena tools disappear from Augment after every server restart, requiring manual intervention to restore functionality.

### Root Cause

The upstream `mcp-python-sdk` (v1.12.3) in `streamable_http_manager.py` treats invalid session IDs as errors:

```python
# Original code (lines 290-296)
else:
    # Invalid session ID
    response = Response(
        "Bad Request: No valid session ID provided",
        status_code=HTTPStatus.BAD_REQUEST,
    )
    await response(scope, receive, send)
```

This is technically correct but not resilient to the common scenario of clients caching session IDs across server restarts.

## Solution Overview

### Hybrid Patch Approach

We implement a **minimal hybrid patch system** that:

1. **Keeps external dependency**: `mcp==1.12.3` remains as an external package
2. **Patches single file**: Only `streamable_http_manager.py` is vendored to `src/serena/patches/`
3. **Uses import hook**: PEP 451 import hook redirects imports to the patched version
4. **Survives cache invalidation**: Patch is in source tree, not in pip/uv cache

**Why hybrid approach?**
- **Minimal maintenance**: Only 1 file to update vs 81 files in full vendoring
- **Cache resilient**: Patch survives `uv cache clean` and environment rebuilds
- **Selective patching**: Other MCP modules use upstream package normally
- **Easy updates**: Clear diff makes it easy to reapply patch to new SDK versions

### The Patch

**Location**: `src/serena/patches/mcp/server/streamable_http_manager.py` (lines 290-338)

**Change**: Replace 400 error response with graceful new session creation

**Before** (upstream SDK):
```python
else:
    # Invalid session ID
    response = Response(
        "Bad Request: No valid session ID provided",
        status_code=HTTPStatus.BAD_REQUEST,
    )
    await response(scope, receive, send)
```

**After** (patched):
```python
else:
    # SERENA PATCH: Invalid/expired session ID - create new session instead of 400 error
    # This handles cases where clients cache session IDs across server restarts
    logger.warning(
        "Invalid or expired session ID received: %s. Creating new session.",
        request_mcp_session_id,
        extra={"invalid_session_id": request_mcp_session_id, "action": "create_new_session"},
    )

    # Create new session (duplicate of "if request_mcp_session_id is None" logic above)
    logger.debug("Creating new transport for invalid session ID")
    async with self._session_creation_lock:
        new_session_id = uuid4().hex
        http_transport = StreamableHTTPServerTransport(
            mcp_session_id=new_session_id,
            is_json_response_enabled=self.json_response,
            event_store=self.event_store,
            security_settings=self.security_settings,
        )
        self._server_instances[new_session_id] = http_transport

        async def run_server(*, task_status: TaskStatus[None] = anyio.TASK_STATUS_IGNORED) -> None:
            """Run the MCP server for this session."""
            try:
                task_status.started()
                await self._server_factory(http_transport)
            except Exception as e:
                if not http_transport.is_terminated:
                    logger.error(
                        f"Session {http_transport.mcp_session_id} crashed: {e}",
                        exc_info=True,
                    )
            finally:
                if (
                    http_transport.mcp_session_id
                    and http_transport.mcp_session_id in self._server_instances
                    and not http_transport.is_terminated
                ):
                    logger.info("Cleaning up crashed session " f"{http_transport.mcp_session_id} from " "active instances.")
                    del self._server_instances[http_transport.mcp_session_id]

        assert self._task_group is not None
        await self._task_group.start(run_server)
        await http_transport.handle_request(scope, receive, send)
```

**Behavior**: When an invalid session ID is received, log a warning and create a new session instead of returning an error. The client receives a valid response with a new session ID and can continue working.

## Version Compatibility

### Supported Versions

- **Current**: `mcp==1.12.3` ✅ Fully tested and supported
- **Future versions**: Patch may need updates (see Maintenance Guide below)

### Version Check

The patched file includes a version compatibility check:

```python
EXPECTED_MCP_VERSION = "1.12.3"
try:
    import mcp
    if hasattr(mcp, "__version__") and mcp.__version__ != EXPECTED_MCP_VERSION:
        warnings.warn(
            f"Patched streamable_http_manager expects mcp=={EXPECTED_MCP_VERSION}, "
            f"found mcp=={mcp.__version__}. Patch may not work correctly.",
            RuntimeWarning,
            stacklevel=2,
        )
except ImportError:
    pass
```

**What this means**: If you upgrade the MCP SDK, you'll see a warning at import time. Review the patch and update if needed.

## Maintenance Guide

### When to Update the Patch

Update the patch when:
1. **MCP SDK releases new version** with changes to `streamable_http_manager.py`
2. **Session handling logic changes** in upstream SDK
3. **Security vulnerabilities** are fixed in upstream SDK

### How to Update the Patch

**Step 1: Check upstream changes**
```bash
# Compare current patch with new SDK version
diff src/serena/patches/mcp/server/streamable_http_manager.py \
     .venv/lib/python3.11/site-packages/mcp/server/streamable_http_manager.py
```

**Step 2: Copy new upstream file**
```bash
# Backup current patch
cp src/serena/patches/mcp/server/streamable_http_manager.py \
   src/serena/patches/mcp/server/streamable_http_manager.py.backup

# Copy new upstream version
cp .venv/lib/python3.11/site-packages/mcp/server/streamable_http_manager.py \
   src/serena/patches/mcp/server/streamable_http_manager.py
```

**Step 3: Reapply patch**

Find the section that handles invalid session IDs (search for "Invalid session ID" or similar error message) and replace the error response with the new session creation logic shown above.

**Step 4: Update version check**
```python
EXPECTED_MCP_VERSION = "1.13.0"  # Update to new version
```

**Step 5: Test**
```bash
# Run all tests
uv run pytest test/serena/test_mcp.py test/serena/test_session_invalidation.py -v

# Test with real MCP client (Augment)
# 1. Start Serena server
# 2. Connect from Augment
# 3. Restart Serena server
# 4. Verify Augment tools still work (no 400 errors)
```

**Step 6: Update documentation**
- Update this file with new version number
- Update IMPLEMENTATION-PLAN-hybrid-mcp-patch.md if approach changed
- Commit with detailed message explaining changes

## Troubleshooting

### Patch Not Loading

**Symptom**: Tests fail with "Patched module should be loaded from serena/patches"

**Diagnosis**:
```python
import mcp.server.streamable_http_manager as manager
print(manager.__file__)  # Should contain "serena/patches"
```

**Solutions**:
1. **Import hook not installed**: Check that `import serena.patches` happens before any MCP imports
2. **Cache issue**: Run `uv cache clean` and rebuild environment
3. **Wrong Python environment**: Verify you're using the correct virtual environment

### Version Mismatch Warning

**Symptom**: `RuntimeWarning: Patched streamable_http_manager expects mcp==1.12.3, found mcp==1.13.0`

**Diagnosis**: MCP SDK was upgraded but patch wasn't updated

**Solutions**:
1. **Downgrade SDK**: `uv pip install mcp==1.12.3` (temporary fix)
2. **Update patch**: Follow "How to Update the Patch" guide above (permanent fix)

### Session Creation Fails

**Symptom**: Logs show "Failed to create new session for invalid session ID"

**Diagnosis**: Patch logic may be incompatible with new SDK version

**Solutions**:
1. **Check SDK changes**: Review upstream changes to session creation logic
2. **Update patch**: Reapply patch to match new SDK structure
3. **Rollback**: Temporarily revert to known-good SDK version

### Import Hook Conflicts

**Symptom**: Other packages fail to import or behave unexpectedly

**Diagnosis**: Import hook may be interfering with other imports

**Solutions**:
1. **Check hook selectivity**: Verify hook only intercepts `mcp.server.streamable_http_manager`
2. **Review sys.meta_path**: Ensure hook is first and not duplicated
3. **Test isolation**: Run tests with `-v` to see import order

## Implementation Details

### Import Hook (PEP 451)

**File**: `src/serena/patches/__init__.py`

The import hook uses modern Python import protocol (PEP 451):

```python
class _PatchImportHook(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path, target=None):
        if fullname == "mcp.server.streamable_http_manager":
            return importlib.util.spec_from_loader(
                fullname,
                _PatchLoader(),
                origin="serena.patches.mcp.server.streamable_http_manager"
            )
        return None
```

**Installation**: Hook is installed in `src/serena/__init__.py`:
```python
import serena.patches  # Installs import hook before any MCP imports
```

### Testing

**Test suite**: `test/serena/test_session_invalidation.py` (23 tests)

**Coverage**:
- ✅ Patch loading from source tree
- ✅ Import hook installation and selectivity
- ✅ Version compatibility check
- ✅ Patch survives reimport
- ✅ Other MCP modules not affected
- ✅ Cache invalidation survival
- ✅ Documentation completeness

**Run tests**:
```bash
uv run pytest test/serena/test_session_invalidation.py -v
```

## References

- **Implementation Plan**: `IMPLEMENTATION-PLAN-hybrid-mcp-patch.md`
- **Deployment Guide**: `DEPLOYMENT-GUIDE.md`
- **AI Panel Critique**: Git commits 92b418d, 7dda9a5
- **Upstream SDK**: https://github.com/modelcontextprotocol/python-sdk
- **PEP 451**: https://peps.python.org/pep-0451/ (Import System)

