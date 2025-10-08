# Serena MCP Server - Production Deployment Guide

## Overview

This guide explains how to deploy Serena MCP server to production with the session handling patch that enables graceful recovery from client session ID caching.

**What this solves**: MCP clients (like Augment) cache session IDs across server restarts. Without this patch, clients receive 400 errors after server restart and must be manually restarted. With this patch, clients automatically recover with new sessions.

## Prerequisites

- Python 3.11 or higher
- `uv` package manager installed
- Git repository cloned
- Network access to MCP clients (Augment, Claude Desktop, etc.)

## Deployment Methods

### Method 1: Local Development (Recommended for Testing)

**Use case**: Testing Serena with Augment or other MCP clients on your local machine

**Steps**:

1. **Navigate to Serena directory**:
   ```bash
   cd submodules/serena
   ```

2. **Install dependencies**:
   ```bash
   uv sync
   ```

3. **Verify patch is loaded**:
   ```bash
   uv run python -c "
   import serena
   import mcp.server.streamable_http_manager as manager
   print('✅ Patch loaded from:', manager.__file__)
   print('✅ Expected MCP version:', manager.EXPECTED_MCP_VERSION)
   assert 'serena/patches' in manager.__file__, 'Patch not loaded!'
   "
   ```

   **Expected output**:
   ```
   ✅ Patch loaded from: /path/to/serena/src/serena/patches/mcp/server/streamable_http_manager.py
   ✅ Expected MCP version: 1.12.3
   ```

4. **Start Serena MCP server**:
   ```bash
   uv run serena start-mcp-server \
     --transport streamable-http \
     --port 9121 \
     --project /path/to/your/project
   ```

   **Expected output**:
   ```
   INFO: Serena MCP server starting...
   INFO: Transport: streamable-http
   INFO: Port: 9121
   INFO: Project: /path/to/your/project
   INFO: Server ready
   ```

5. **Configure MCP client** (e.g., Augment):
   
   Add to VS Code `settings.json`:
   ```json
   {
     "mcp.servers": {
       "serena": {
         "command": "uv",
         "args": [
           "run",
           "--directory",
           "/path/to/serena",
           "serena",
           "start-mcp-server",
           "--transport",
           "streamable-http",
           "--port",
           "9121",
           "--project",
           "/path/to/your/project"
         ]
       }
     }
   }
   ```

6. **Test session recovery**:
   - Open Augment and verify Serena tools are available
   - Restart Serena server (Ctrl+C, then restart)
   - **Without patch**: Augment tools disappear, 400 errors in logs
   - **With patch**: Augment tools remain available, warning in logs about invalid session ID

### Method 2: Isolated Environment (uvx)

**Use case**: Running Serena as an isolated tool without polluting global Python environment

**Steps**:

1. **Install Serena with uvx**:
   ```bash
   uvx --from /path/to/serena serena start-mcp-server \
     --transport streamable-http \
     --port 9121 \
     --project /path/to/your/project
   ```

2. **Verify patch is loaded**:
   ```bash
   uvx --from /path/to/serena python -c "
   import serena
   import mcp.server.streamable_http_manager as manager
   assert 'serena/patches' in manager.__file__
   print('✅ Patch loaded successfully')
   "
   ```

3. **Configure MCP client**:
   ```json
   {
     "mcp.servers": {
       "serena": {
         "command": "uvx",
         "args": [
           "--from",
           "/path/to/serena",
           "serena",
           "start-mcp-server",
           "--transport",
           "streamable-http",
           "--port",
           "9121",
           "--project",
           "/path/to/your/project"
         ]
       }
     }
   }
   ```

### Method 3: Background Service (macOS plist)

**Use case**: Running Serena as a persistent background service that starts on login

**Steps**:

1. **Create plist file** (`~/Library/LaunchAgents/com.serena.mcp.plist`):
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
   <dict>
       <key>Label</key>
       <string>com.serena.mcp</string>
       <key>ProgramArguments</key>
       <array>
           <string>/path/to/uv</string>
           <string>run</string>
           <string>--directory</string>
           <string>/path/to/serena</string>
           <string>serena</string>
           <string>start-mcp-server</string>
           <string>--transport</string>
           <string>streamable-http</string>
           <string>--port</string>
           <string>9121</string>
           <string>--project</string>
           <string>/path/to/your/project</string>
       </array>
       <key>RunAtLoad</key>
       <true/>
       <key>KeepAlive</key>
       <true/>
       <key>StandardOutPath</key>
       <string>/tmp/serena-mcp.log</string>
       <key>StandardErrorPath</key>
       <string>/tmp/serena-mcp-error.log</string>
   </dict>
   </plist>
   ```

2. **Load service**:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.serena.mcp.plist
   ```

3. **Verify service is running**:
   ```bash
   launchctl list | grep serena
   tail -f /tmp/serena-mcp.log
   ```

4. **Configure MCP client**:
   ```json
   {
     "mcp.servers": {
       "serena": {
         "url": "http://localhost:9121/sse"
       }
     }
   }
   ```

### Method 4: Docker Container (Production)

**Use case**: Deploying Serena in containerized production environment

**Steps**:

1. **Create Dockerfile** (if not exists):
   ```dockerfile
   FROM python:3.11-slim
   
   WORKDIR /app
   
   # Install uv
   RUN pip install uv
   
   # Copy Serena source
   COPY . /app
   
   # Install dependencies
   RUN uv sync
   
   # Expose MCP port
   EXPOSE 9121
   
   # Start server
   CMD ["uv", "run", "serena", "start-mcp-server", "--transport", "streamable-http", "--port", "9121", "--project", "/workspace"]
   ```

2. **Build image**:
   ```bash
   docker build -t serena-mcp:latest .
   ```

3. **Run container**:
   ```bash
   docker run -d \
     --name serena-mcp \
     -p 9121:9121 \
     -v /path/to/workspace:/workspace \
     serena-mcp:latest
   ```

4. **Verify patch is loaded**:
   ```bash
   docker exec serena-mcp python -c "
   import serena
   import mcp.server.streamable_http_manager as manager
   assert 'serena/patches' in manager.__file__
   print('✅ Patch loaded successfully')
   "
   ```

## Verification Steps

### 1. Verify Patch is Loaded

**Command**:
```bash
uv run python -c "
import serena
import sys
from serena.patches import _PatchImportHook

# Check import hook is installed
hook_found = any(isinstance(h, _PatchImportHook) for h in sys.meta_path)
print(f'Import hook installed: {hook_found}')

# Check patched module is loaded
import mcp.server.streamable_http_manager as manager
is_patched = 'serena/patches' in manager.__file__
print(f'Patched module loaded: {is_patched}')
print(f'Module location: {manager.__file__}')
print(f'Expected MCP version: {manager.EXPECTED_MCP_VERSION}')

assert hook_found, 'Import hook not installed!'
assert is_patched, 'Patched module not loaded!'
print('✅ All checks passed')
"
```

**Expected output**:
```
Import hook installed: True
Patched module loaded: True
Module location: /path/to/serena/src/serena/patches/mcp/server/streamable_http_manager.py
Expected MCP version: 1.12.3
✅ All checks passed
```

### 2. Test Session Recovery

**Scenario**: Simulate client caching session ID across server restart

**Steps**:

1. **Start Serena server**:
   ```bash
   uv run serena start-mcp-server --transport streamable-http --port 9121 --project .
   ```

2. **Connect MCP client** (Augment, Claude Desktop, etc.)

3. **Verify tools are available** in the client

4. **Restart Serena server** (Ctrl+C, then restart)

5. **Check client behavior**:
   - **Without patch**: Tools disappear, client shows errors
   - **With patch**: Tools remain available, seamless recovery

6. **Check server logs**:
   ```bash
   # Look for warning about invalid session ID
   grep "Invalid or expired session ID" /tmp/serena-mcp.log
   ```

   **Expected log entry**:
   ```
   WARNING: Invalid or expired session ID received: abc123def456. Creating new session.
   ```

### 3. Run Test Suite

**Command**:
```bash
uv run pytest test/serena/test_session_invalidation.py -v
```

**Expected output**:
```
======================== 23 passed, 1 warning in 0.20s =========================
```

## Troubleshooting

### Issue: Patch Not Loading

**Symptoms**:
- Tests fail with "Patched module should be loaded from serena/patches"
- Server logs show 400 errors for invalid session IDs

**Diagnosis**:
```bash
uv run python -c "
import mcp.server.streamable_http_manager as manager
print('Module location:', manager.__file__)
print('Is patched:', 'serena/patches' in manager.__file__)
"
```

**Solutions**:
1. **Clear cache**: `uv cache clean && uv sync`
2. **Verify import order**: Ensure `import serena.patches` happens first
3. **Check Python version**: Requires Python 3.11+

### Issue: Version Mismatch Warning

**Symptoms**:
```
RuntimeWarning: Patched streamable_http_manager expects mcp==1.12.3, found mcp==1.13.0
```

**Solutions**:
1. **Downgrade MCP**: `uv pip install mcp==1.12.3`
2. **Update patch**: See PATCH-NOTES.md "Maintenance Guide"

### Issue: Client Still Shows 400 Errors

**Symptoms**:
- Client shows "Bad Request" errors after server restart
- Logs don't show "Invalid or expired session ID" warnings

**Diagnosis**:
1. **Check patch is loaded**: Run verification steps above
2. **Check client configuration**: Ensure client is connecting to correct port
3. **Check logs**: Look for any errors during session creation

**Solutions**:
1. **Restart client**: Sometimes client needs restart to clear cached state
2. **Check network**: Ensure client can reach server on specified port
3. **Review logs**: Look for errors in both client and server logs

## Rollback Procedure

If issues occur after deploying the patch:

1. **Stop Serena server**:
   ```bash
   # For local development
   Ctrl+C
   
   # For plist service
   launchctl unload ~/Library/LaunchAgents/com.serena.mcp.plist
   
   # For Docker
   docker stop serena-mcp
   ```

2. **Revert to previous version**:
   ```bash
   git log --oneline -10  # Find commit before patch
   git checkout <commit-hash>
   uv sync
   ```

3. **Restart server** using same method as before

4. **Verify rollback**:
   ```bash
   uv run python -c "
   import mcp.server.streamable_http_manager as manager
   print('Module location:', manager.__file__)
   # Should NOT contain 'serena/patches'
   "
   ```

## Production Checklist

Before deploying to production:

- [ ] Run full test suite: `uv run pytest -v`
- [ ] Verify patch is loaded in target environment
- [ ] Test session recovery with real MCP client
- [ ] Configure logging to capture session warnings
- [ ] Set up monitoring for 400 errors (should be zero)
- [ ] Document rollback procedure for your environment
- [ ] Test rollback procedure in staging
- [ ] Configure alerts for version mismatch warnings

## References

- **Technical Documentation**: `PATCH-NOTES.md`
- **Implementation Plan**: `IMPLEMENTATION-PLAN-hybrid-mcp-patch.md`
- **Test Suite**: `test/serena/test_session_invalidation.py`
- **MCP Protocol**: https://modelcontextprotocol.io/

