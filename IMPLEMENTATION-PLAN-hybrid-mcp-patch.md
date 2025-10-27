# Implementation Plan: Hybrid MCP Patch Approach

**Date**: 2025-10-08  
**Goal**: Enable Augment and other MCP clients to reliably initialize Serena sessions every time without failure, surviving restarts, cache invalidation, and environment changes.

## Architecture Decision

**Recommendation**: Option C - Hybrid Approach

**Rationale**:
- Addresses root problem: patch persistence, not full SDK vendoring
- Minimal complexity: only vendor what needs to be patched
- Maintainability: easier to sync with upstream SDK updates
- Debuggability: simpler to troubleshoot than import hooks
- Best practices: aligns with Python packaging standards

## Problem Statement

**Current Issue**: Augment MCP client caches session IDs across server restarts. When Serena restarts, cached session IDs become invalid, causing 400 Bad Request errors.

**Root Cause**: MCP SDK's `streamable_http_manager.py` rejects invalid session IDs with 400 error instead of creating new sessions.

**Previous Approach**: Attempted to vendor entire MCP SDK (81 files, 1.3MB) to apply patch. This introduced complexity with import hooks and circular imports.

**New Approach**: Vendor ONLY the patched file, keep external MCP SDK dependency.

## Architecture Decision

### Option C: Hybrid Approach (APPROVED)

**Strategy**:
1. Keep `mcp==1.12.3` as external dependency
2. Vendor ONLY `streamable_http_manager.py` to `src/serena/patches/mcp/`
3. Use minimal import hook to redirect ONLY `mcp.server.streamable_http_manager` → `serena.patches.mcp.streamable_http_manager`
4. All other mcp imports use external package
5. Patch survives cache invalidation because it's in source tree

**Benefits**:
- ✅ Minimal changes (1 file instead of 81)
- ✅ Easier to maintain and sync with upstream
- ✅ Simpler to debug
- ✅ Follows Python packaging best practices
- ✅ Patch persists through cache invalidation

**Trade-offs**:
- ⚠️ Still requires import hook (but much simpler)
- ⚠️ Must keep patch in sync with SDK version
- ⚠️ External dependency on mcp==1.12.3

## Implementation Phases

### Phase 1: Rollback Full Vendoring ✅ IN PROGRESS

**Objective**: Remove full vendoring attempt and restore external MCP SDK dependency

**Tasks**:
1. ✅ Remove `src/serena/vendor/mcp/` directory (81 files)
2. ✅ Remove `src/serena/vendor/__init__.py` (import hook infrastructure)
3. ✅ Restore `mcp==1.12.3` to pyproject.toml dependencies
4. ✅ Revert import changes:
   - `src/serena/mcp.py`: `serena.vendor.mcp.*` → `mcp.*`
   - `src/serena/tools/tools_base.py`: `serena.vendor.mcp.*` → `mcp.*`
   - `test/serena/test_mcp.py`: `serena.vendor.mcp.*` → `mcp.*`
5. ✅ Revert version bump: `0.1.5` → `0.1.4`
6. ✅ Remove VENDOR-NOTES.md (will be replaced with PATCH-NOTES.md)
7. ✅ Clear uv cache to remove vendored builds
8. ✅ Run tests to verify rollback successful

**Success Criteria**:
- All 48 MCP tests passing
- All 35 polyglot tests passing
- External `mcp==1.12.3` installed and working
- No vendored mcp code in source tree

**Commit Message**:
```
refactor: Rollback full MCP SDK vendoring, prepare for hybrid patch approach

WHY:
- Hybrid approach is more maintainable than full vendoring
- Full vendoring (81 files) introduced unnecessary complexity
- Root problem is patch persistence, not SDK packaging
- Import hook issues with circular imports

EXPECTED:
- External mcp==1.12.3 dependency restored
- All vendored mcp code removed
- Clean slate for minimal patch implementation
- All tests passing with external SDK

CHANGES:
- Removed src/serena/vendor/mcp/ (81 files)
- Removed src/serena/vendor/__init__.py
- Restored mcp==1.12.3 to pyproject.toml
- Reverted imports: serena.vendor.mcp.* → mcp.*
- Reverted version: 0.1.5 → 0.1.4
- Removed VENDOR-NOTES.md

REFS: #hybrid-mcp-patch
See: IMPLEMENTATION-PLAN-hybrid-mcp-patch.md
```

### Phase 2: Create Minimal Patch System

**Objective**: Implement single-file patch with minimal import hook

**Tasks**:
1. Create directory structure:
   ```
   src/serena/patches/
   src/serena/patches/__init__.py
   src/serena/patches/mcp/
   src/serena/patches/mcp/__init__.py
   src/serena/patches/mcp/server/
   src/serena/patches/mcp/server/__init__.py
   src/serena/patches/mcp/server/streamable_http_manager.py
   ```

2. Copy `streamable_http_manager.py` from external mcp package:
   ```bash
   cp .venv/lib/python3.11/site-packages/mcp/server/streamable_http_manager.py \
      src/serena/patches/mcp/server/streamable_http_manager.py
   ```

3. Apply session handling patch to copied file (lines 265-317):
   - Invalid session IDs → create new sessions (not 400 errors)
   - Add SERENA PATCH comment markers
   - Add version compatibility check

4. Create minimal import hook in `src/serena/patches/__init__.py`:
   ```python
   import sys
   import importlib
   
   class _PatchImportHook:
       """Redirect mcp.server.streamable_http_manager to patched version"""
       
       def find_module(self, fullname, path=None):
           if fullname == "mcp.server.streamable_http_manager":
               return self
           return None
       
       def load_module(self, fullname):
           if fullname in sys.modules:
               return sys.modules[fullname]
           
           # Load patched version
           patched = importlib.import_module("serena.patches.mcp.server.streamable_http_manager")
           sys.modules[fullname] = patched
           return patched
   
   # Install hook
   if not any(isinstance(h, _PatchImportHook) for h in sys.meta_path):
       sys.meta_path.insert(0, _PatchImportHook())
   ```

5. Import patches in `src/serena/__init__.py`:
   ```python
   import serena.patches  # Install import hooks
   ```

6. Add version compatibility check in patched file:
   ```python
   # SERENA PATCH: Version compatibility check
   import mcp
   EXPECTED_MCP_VERSION = "1.12.3"
   if hasattr(mcp, '__version__') and mcp.__version__ != EXPECTED_MCP_VERSION:
       import warnings
       warnings.warn(f"Patched streamable_http_manager expects mcp=={EXPECTED_MCP_VERSION}, found {mcp.__version__}")
   ```

**Success Criteria**:
- Import hook redirects only `mcp.server.streamable_http_manager`
- All other mcp imports use external package
- Version compatibility check warns on mismatch
- All tests passing

**Commit Message**:
```
feat(patches): Implement minimal MCP patch system for session handling

WHY:
- Augment caches session IDs across restarts
- Invalid session IDs should create new sessions, not return 400 errors
- Patch must survive cache invalidation

EXPECTED:
- Single-file patch in src/serena/patches/mcp/server/streamable_http_manager.py
- Minimal import hook redirects only patched module
- Version compatibility check warns on SDK mismatch
- All tests passing

CHANGES:
- Created src/serena/patches/ directory structure
- Copied and patched streamable_http_manager.py
- Created minimal import hook in patches/__init__.py
- Added version compatibility check
- Imported patches in serena/__init__.py

REFS: #hybrid-mcp-patch
See: IMPLEMENTATION-PLAN-hybrid-mcp-patch.md
```

### Phase 3: Testing & Validation

**Objective**: Comprehensive testing across all deployment methods

**Test Scenarios**:

1. **Session Invalidation Tests** (NEW):
   ```python
   def test_invalid_session_creates_new():
       """Test that invalid session ID creates new session instead of 400 error"""
       # Send request with invalid session ID
       # Verify 200 OK response
       # Verify new session ID in response header
   
   def test_expired_session_graceful_recovery():
       """Test that expired session is handled gracefully"""
       # Create session, restart server, use old session ID
       # Verify new session created
   
   def test_cache_invalidation_survival():
       """Test that patch survives uv cache clean"""
       # Run server, clean cache, restart server
       # Verify patch still applied
   ```

2. **Deployment Method Tests**:
   - ✅ `uv run serena start-mcp-server` (local development)
   - ✅ `uvx --from . serena start-mcp-server` (isolated environment)
   - ✅ plist-managed server (production-like)

3. **Regression Tests**:
   - ✅ All 48 MCP tests passing
   - ✅ All 35 polyglot tests passing
   - ✅ stdio transport works
   - ✅ SSE transport works
   - ✅ streamable-http transport works

4. **Integration Tests**:
   - ✅ Augment MCP client connects successfully
   - ✅ Invalid session ID handled gracefully
   - ✅ Server restart doesn't break clients

**Success Criteria**:
- All new session invalidation tests passing
- All existing tests passing
- Patch works in all deployment methods
- Augment can connect reliably

**Commit Message**:
```
test(patches): Add comprehensive session invalidation tests

WHY:
- Ensure patch handles all session invalidation scenarios
- Verify robustness across deployment methods
- Prevent regressions

EXPECTED:
- Session invalidation tests passing
- All deployment methods tested
- Augment integration verified

CHANGES:
- Added test_invalid_session_creates_new
- Added test_expired_session_graceful_recovery
- Added test_cache_invalidation_survival
- Tested uvx, uv run, plist deployments

REFS: #hybrid-mcp-patch
See: IMPLEMENTATION-PLAN-hybrid-mcp-patch.md
```

### Phase 4: Documentation

**Objective**: Comprehensive documentation for maintenance and troubleshooting

**Documents to Create/Update**:

1. **PATCH-NOTES.md** (NEW):
   - Why patch is needed
   - What was changed (exact diff from upstream)
   - How to update patch when SDK updates
   - Version compatibility matrix
   - Troubleshooting guide

2. **IMPLEMENTATION-PLAN-hybrid-mcp-patch.md** (THIS FILE):
   - Keep as historical record
   - Mark phases as complete

3. **README.md** (UPDATE):
   - Add section on MCP session handling
   - Document patch system

4. **pyproject.toml** (UPDATE):
   - Add comment explaining mcp dependency and patch

**Telemetry/Monitoring** (OPTIONAL):
- Add logging for session recreation events
- Track invalid session ID frequency
- Monitor patch effectiveness

**Success Criteria**:
- Clear documentation for future maintainers
- Patch update procedure documented
- Troubleshooting guide available

**Commit Message**:
```
docs(patches): Document MCP patch system and maintenance procedures

WHY:
- Future maintainers need clear guidance
- Patch update procedure must be documented
- Troubleshooting guide prevents issues

EXPECTED:
- PATCH-NOTES.md with complete patch documentation
- README.md updated with patch system info
- Clear maintenance procedures

CHANGES:
- Created PATCH-NOTES.md
- Updated README.md
- Added comments to pyproject.toml
- Documented troubleshooting steps

REFS: #hybrid-mcp-patch
See: IMPLEMENTATION-PLAN-hybrid-mcp-patch.md
```

## Success Metrics

**Primary Goal**: Augment and other MCP clients can reliably initialize Serena sessions every time without failure.

**Measurable Outcomes**:
- ✅ 0% session initialization failures with Augment
- ✅ Invalid session IDs create new sessions (not 400 errors)
- ✅ Patch survives `uv cache clean`
- ✅ Patch survives server restarts
- ✅ All 48+ MCP tests passing
- ✅ All 35+ polyglot tests passing

**Maintenance Metrics**:
- ⏱️ Time to update patch when SDK updates: <30 minutes
- 📝 Documentation completeness: 100%
- 🐛 Debugging complexity: Low (single file, clear logs)

## Rollback Procedure

If hybrid approach fails:

1. Remove `src/serena/patches/` directory
2. Remove import hook from `src/serena/__init__.py`
3. Revert to external `mcp==1.12.3` without patches
4. Document failure mode and lessons learned
5. Escalate to user for alternative approach

## References

- MCP SDK: https://github.com/modelcontextprotocol/python-sdk
- Original Issue: Augment session caching across restarts
