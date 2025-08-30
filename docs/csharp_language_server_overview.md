# C# Language Server (Roslyn) – Overview & Configuration

Unified reference for Serena's C# language server integration: features, lifecycle, performance/readiness behavior, security hardening, and environment variables.

---
## Table of Contents

1. Goals & Design Pillars
2. Startup & Lifecycle
3. Readiness Model
4. Deterministic Environment & Runtime Management
5. Secure Artifact Acquisition
6. Logging & Diagnostics
7. Feature Toggles / Environment Variables
8. Razor Capability Detection
9. Initialization Options Injection (Maintainer Gate)
10. Protocol Tracing
11. Common Scenarios Cheat‑Sheet
12. Testing Coverage Summary

---

## 1. Goals & Design Pillars

- Deterministic: Managed, pinned Roslyn + .NET SDK in a Serena cache (ignoring host system dotnet for execution).
- Secure: Bounded retry and path‑safe extraction.
- Observable: Structured logging, optional protocol trace.
- Fast & Reliable: Readiness relies on progress quiescence + probe.
- Minimal Surface: Only curated environment variables passed to the server unless explicitly overridden.

## 2. Startup & Lifecycle

1. Ensure / reuse managed .NET 9 SDK (never executing arbitrary system dotnet).
2. Download Roslyn language server NuGet (pinned version or override via `CSHARP_LS_VERSION`).
3. Optionally synthesize a minimal `runtimeconfig.json` if the package omits one (`CSHARP_LS_GENERATE_RUNTIME_CONFIG`).
4. Launch `dotnet <LanguageServer.dll> --stdio` with filtered environment.
5. Track initialization completion & readiness event.
6. Serve LSP; on shutdown set `is_shutdown=True`.

## 3. Readiness Model

The server becomes "ready" when either:

- Quiet period: No active progress operations for a configured span AND probing succeeds, or
- Probe success first (workspace_symbol lightweight request), or
- Fallback timer elapses.
A minimal pre-ready delay (default ~1s) can be tuned / disabled via `CSHARP_LS_MIN_READY_DELAY`.
Legacy heartbeat has been removed to reduce threads and failure modes.


## 4. Deterministic Environment & Runtime Management

- Only a small allowlist of env keys forwarded: `DOTNET_*`, `CSHARP_LS_*`, plus `DOTNET_ROOT` & `PATH` (rewritten to start with managed dotnet).
- Set `CSHARP_LS_ALLOW_FULL_ENV=1` to bypass filtering (discouraged; breaks determinism).
- Optional debug dumps: `CSHARP_LS_DEBUG_ENV=1`.
- System dotnet only logged for diagnostics, never used.

## 5. Secure Artifact Acquisition

Implemented in `solidlsp.util.secure_downloads`:

- `download_with_retries` (exponential backoff)
- Safe extraction (zip/tar) with path traversal prevention

## 6. Logging & Diagnostics

- Server internal log level via `CSHARP_LS_LOG_LEVEL` (default `Information`).
  
- Additional runtime introspection: `CSHARP_LS_DEBUG_RUNTIME=1` (framework detection, sample DLL listing, probe paths).

## 7. Feature Toggles / Environment Variables (Summary)

| Variable | Purpose | Default |
|----------|---------|---------|
| `CSHARP_LS_VERSION` | Override Roslyn LS NuGet version | Pinned internal value |
| `CSHARP_LS_LOG_LEVEL` | Roslyn logging verbosity | Information |
| `CSHARP_LS_DISABLE_RAZOR` | Force disable Razor | Auto heuristic |
| `CSHARP_LS_FORCE_ENABLE_RAZOR` | Force enable Razor | Auto heuristic |
| `CSHARP_LS_INIT_OPTIONS` | Shallow JSON merge into init options (needs enable) | Off |
| `CSHARP_LS_ENABLE_INIT_OPTIONS` | Gate allowing merge | Off |
| `CSHARP_LS_MIN_READY_DELAY` | One-time initial delay seconds | ~1.0 |
| `CSHARP_LS_PROTOCOL_TRACE` | Enable NDJSON protocol trace (1/filename) | Off |

| `CSHARP_LS_DISABLE_SOLUTION_NOTIFICATIONS` | Skip custom solution/project notifications | Off |
| `CSHARP_LS_GENERATE_RUNTIME_CONFIG` | Synthesize minimal runtimeconfig if missing | On (1) |
| `CSHARP_LS_GENERATE_RUNTIME_CONFIG_DRY_RUN` | Log would-be runtimeconfig only | Off |
| `CSHARP_LS_DEBUG_RUNTIME` | Extra runtime / framework diagnostics | Off |
| `CSHARP_LS_DEBUG_ENV` | Dump filtered env passed to server | Off |
| `CSHARP_LS_ALLOW_FULL_ENV` | Bypass env filtering (non-deterministic) | Off |
| `DOTNET_ROOT` / `DOTNET_ROLL_FORWARD` | Manual override for runtime | Managed internally |

## 8. Razor Capability Detection

Heuristic breadth-first scan disables Razor if no `*.razor` or `*.cshtml` present. Override via disable/force env vars (precedence: disable > force_enable > auto). Disabling sets `{"razor":{"disabled":true}}` entries in init options.

## 9. Initialization Options Injection (Maintainer Gate)

`CSHARP_LS_ENABLE_INIT_OPTIONS=1` + `CSHARP_LS_INIT_OPTIONS='{"..."}'` allows a shallow top-level merge. Entire top-level keys are replaced (NOT deep merged). Include all nested keys you wish preserved.
Improper JSON or missing gate -> ignored with log.

## 10. Protocol Tracing

`CSHARP_LS_PROTOCOL_TRACE=1` => `logs/protocol.ndjson` inside the server log directory. Setting a custom filename uses that path (relative -> inside logs). Contains one JSON object per line (direction, method, id, timestamp).


## 11. Common Scenarios Cheat‑Sheet

| Scenario | Suggested Settings |
|----------|--------------------|
| Fast non-Razor repo indexing | (leave Razor vars unset) + default readiness |
| Forcing Razor in sparse checkout | `CSHARP_LS_FORCE_ENABLE_RAZOR=1` |
| Quiet logs in noisy workspace | (no special flag; review log level) |
| Experimental Roslyn build | `CSHARP_LS_VERSION=<new-version>` |
| Debug startup environment | `CSHARP_LS_DEBUG_ENV=1` + maybe `CSHARP_LS_DEBUG_RUNTIME=1` |
| Investigate protocol issues | `CSHARP_LS_PROTOCOL_TRACE=1` |
| Remove initial latency | `CSHARP_LS_MIN_READY_DELAY=0` (may risk flakier early requests) |
| Experimental Roslyn build | `CSHARP_LS_VERSION=<new-version>` (optionally hash pin) |


## 12. Testing Coverage Summary

Automated tests cover:

- Environment filtering & path validation.
- Readiness structures presence.
-- Secure download and extraction.
- Path / runtime validation error paths.
- (Legacy heartbeat removed; no thread liveness tests remain.)

Additions encouraged:

- Readiness timing integration tests (probe vs quiet period).
- Retry behavior for cross-file references.

---
