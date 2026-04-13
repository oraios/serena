# Serena Cloud Sync — Feature Plan

> **Status:** DESIGN — approved by Buddy design-review on 2026-04-13. Not yet implemented.
> **Experimental flag required in MVP.** No automatic background sync in MVP.

## 1. Problem

Serena stores project memories (`.serena/memories/**.md`) and configuration
(`~/.serena/serena_config.yml`, per-project `project.yml`, global contexts/modes)
on a single machine. A developer working on multiple machines cannot share these
without an ad-hoc rsync or Git repo. Existing similar tools in this ecosystem:

- `qdrant-mcp-pp` ships a tar.gz R2 push/pull (snapshot-based, last-writer wins).
- Pointerpro's `memory-sync.php` syncs `.agent/` and `.serena/memories/` per-file
  via pure-PHP sigv4 against R2 (`pp-file-memory/` prefix, skip-existing).

We want the same capability first-class inside Serena — **provider-agnostic**,
**additive**, **UI-exposed**, and **byte-safe**.

## 2. Requirements (from user brief)

1. Upload all Serena **memories and configuration** to the cloud.
2. Be **provider-agnostic**: Cloudflare R2 (we have creds), Amazon S3, Azure
   Blob Storage — pluggable.
3. Implement the **Dependency Inversion Principle** (SOLID) and the **Strategy
   pattern** for providers.
4. Expose the sync function in the Serena **dashboard UI**, including a form to
   input credentials.
5. **Bidirectional additive reconciliation**: push only what cloud lacks, pull
   only what local lacks.
6. **Byte-level integrity** on compare (no lost memory/config).
7. Credentials stored **via env**, in the safest reasonable way.

## 3. Non-goals (MVP)

- **No delete propagation.** Removing a file locally does not delete it remotely
  and vice versa. Additive union only.
- **No rename detection.** A rename = one `LOCAL_ONLY` (new path) + one
  `REMOTE_ONLY` (old path). Both get synced, user cleans up on one side.
- **No automatic / background scheduler.** User-triggered only (CLI or
  dashboard button).
- **No client-side encryption** beyond provider defaults. Object bodies rely on
  provider TLS + SSE-S3 / SSE-Blob at rest. (Deferred to Phase 3.)
- **No full mirror / two-way merge.** Divergent content is preserved, not
  merged.

Users must understand that Serena Cloud Sync is a **safe union**, not a
Dropbox-style mirror. This is called out on the dashboard and in `--help`.

## 4. Architecture

### 4.1 Module layout

Additive under `src/serena/cloud_sync/`. No churn in existing modules beyond
one import in `dashboard.py` to register the Flask blueprint.

```
src/serena/cloud_sync/
├── __init__.py
├── provider.py              # CloudStorageProvider ABC  (DIP seam)
├── providers/
│   ├── __init__.py
│   ├── base_s3.py           # Shared S3-compatible impl via boto3
│   ├── r2.py                # R2 = base_s3 + Cloudflare endpoint override
│   ├── s3.py                # Amazon S3 = base_s3 + AWS default endpoint
│   └── azure.py             # Azure Blob via azure-storage-blob (Phase 2)
├── factory.py               # build_provider(settings) -> CloudStorageProvider
├── settings.py              # Pydantic model for provider config
├── credentials.py           # dotenv-based read/write ~/.serena/cloud-sync.env
├── inventory.py             # LocalInventory walks scope dirs -> ObjectMeta map
├── scope.py                 # IncludePaths / ExcludePatterns (pathspec)
├── diff.py                  # Reconciler: union + conflict classifier
├── sync.py                  # CloudSyncService (accepts provider via ctor)
├── hash_util.py             # chunked sha256 + optional byte-compare
├── dashboard_routes.py      # Flask blueprint
└── exceptions.py
```

Dashboard assets:
```
src/serena/resources/dashboard/cloud-sync.html     # settings panel
src/serena/resources/dashboard/cloud-sync.js       # loaded from dashboard.js
```

### 4.2 Dependency inversion

```python
# provider.py
class CloudStorageProvider(ABC):
    @abstractmethod
    def list_objects(self, prefix: str) -> Iterator["RemoteObjectMeta"]: ...
    @abstractmethod
    def head_object(self, key: str) -> Optional["RemoteObjectMeta"]: ...
    @abstractmethod
    def get_object(self, key: str) -> bytes: ...
    @abstractmethod
    def put_object(self, key: str, data: bytes, sha256_hex: str,
                   content_type: str = "application/octet-stream") -> None: ...
    @abstractmethod
    def put_object_if_absent(self, key: str, data: bytes,
                             sha256_hex: str) -> bool: ...   # additive primitive
    @abstractmethod
    def delete_object(self, key: str) -> None: ...            # guarded, never called by default push/pull

    # Capability flags for future-proofing (Buddy amendment)
    supports_multipart: bool = False
    supports_conditional_put: bool = True
    supports_object_metadata: bool = True
    supports_server_side_copy: bool = False
```

```python
# sync.py
class CloudSyncService:
    def __init__(self,
                 provider: CloudStorageProvider,
                 inventory: LocalInventory,
                 scope: ScopeFilter,
                 log: logging.Logger):
        ...
    def push(self, *, dry_run: bool, force: bool) -> SyncReport: ...
    def pull(self, *, dry_run: bool, force: bool) -> SyncReport: ...
    def status(self) -> StatusReport: ...
```

`CloudSyncService` and `diff.py` have **zero** imports from `boto3` or
`azure.storage.blob`. All SDK usage is isolated in `providers/*`. Tests inject a
`FakeCloudProvider` (in-memory dict) to exercise every branch of diff and sync
without network.

### 4.3 Strategy pattern

Each concrete provider implements `CloudStorageProvider`:

- `providers/base_s3.py` — boto3-based implementation of all primitives.
  Uses `If-None-Match: "*"` on PutObject for the `put_object_if_absent`
  primitive. Stores custom metadata under `x-amz-meta-serena-sync-sha256`
  and `x-amz-meta-serena-sync-size`.
- `providers/r2.py` — thin subclass of `BaseS3Provider`; overrides
  `endpoint_url` to `https://<account_id>.r2.cloudflarestorage.com`, disables
  checksum algorithms that R2 doesn't support, uses `auto` region.
- `providers/s3.py` — thin subclass of `BaseS3Provider`; no endpoint override,
  uses configured AWS region.
- `providers/azure.py` — `azure-storage-blob` based. `put_object_if_absent`
  uses `If-None-Match: *`. Custom metadata via the `metadata={}` kwarg on
  `upload_blob`. (Phase 2.)

A `factory.build_provider(settings)` returns the correct concrete instance
based on `settings.provider_type` ∈ {`r2`, `s3`, `azure`}.

### 4.4 Remote key layout

```
<bucket>/<root_prefix>/global/<relpath>
<bucket>/<root_prefix>/projects/<project_slug>/<relpath>
```

- `root_prefix` defaults to `serena-sync/` (configurable).
- `project_slug` = deterministic slug of project absolute path
  (`sha256(abs_path)[:12]` + `-` + basename). Collision-resistant, stable
  across machines, hides local home dir in the key space.
- Paths inside the remote key are POSIX (`/`), UTF-8 NFC normalized.

### 4.5 Data model

#### LocalInventory entry
```
path:              POSIX relpath under scope root, UTF-8 NFC
size:              int (bytes)
sha256:            hex string (chunked 1 MiB reads)
mtime_ns:          int (nanoseconds since epoch, for diagnostics only)
scope_origin:      "global" | f"project:{slug}"
```

#### RemoteObjectMeta
```
key:               POSIX remote key
size:              int
sha256:            Optional[str]  (None if remote metadata missing)
etag:              str            (provider-specific, diagnostic)
version_id:        Optional[str]  (if provider exposes it)
last_modified:     datetime
metadata_present:  bool           (True only if our x-*-meta-serena-sync-sha256 is present)
```

Inventory records are provider-neutral — the struct is identical across R2, S3,
and Azure. The `providers/` layer translates its SDK response into
`RemoteObjectMeta`.

## 5. Diff & reconciliation algorithm

Byte-equivalent via SHA-256 (cryptographic collision resistance ≈ byte compare
for our purposes), with an opt-in paranoid byte-by-byte verifier.

```
LOCAL_MAP  = inventory.build_local()       # {key: LocalMeta}
REMOTE_MAP = inventory.build_remote()      # {key: RemoteMeta}

classify(k):
    l = LOCAL_MAP.get(k)
    r = REMOTE_MAP.get(k)
    if l and not r:     return UPLOAD
    if r and not l:     return DOWNLOAD
    if not l and not r: return SKIP           # impossible
    # both exist
    if r.sha256 is None:
        r.sha256 = stream_hash(provider, k)   # fallback for legacy objects
    if l.sha256 == r.sha256 and l.size == r.size:
        if opts.byte_compare:                 # paranoid opt-in
            if not stream_byte_compare(provider, k, local_path(k)):
                return CONFLICT               # sha collision or corruption
        return SKIP
    return CONFLICT
```

### Actions

| Class | Push mode | Pull mode |
|---|---|---|
| `UPLOAD` | `put_object_if_absent(k, ...)` — if 412 returned, demote to CONFLICT | (no-op) |
| `DOWNLOAD` | (no-op) | atomic write via tmp+fsync+rename; chmod user-owned |
| `CONFLICT` | Log + report. Do **not** overwrite remote. Require `--force-push`. | Log + save remote as `<path>.cloud-<iso8601>` sibling. Leave local intact. Require `--force-pull` to overwrite. |
| `SKIP` | No-op | No-op |

### Dry-run-first UX contract (Buddy amendment)

Both `push` and `pull` always produce a **classified plan** before any I/O
mutation. The dashboard surfaces this same plan — "3 uploads, 1 download, 0
conflicts" — and the user confirms before execution. `--dry-run` on CLI shows
the plan and exits.

## 6. Scope

### INCLUDE (default)

```
~/.serena/serena_config.yml
~/.serena/contexts/**/*.yml
~/.serena/modes/**/*.yml
~/.serena/memories/**/*              # global memories (if used)

<project>/.serena/project.yml
<project>/.serena/memories/**/*.md
<project>/.serena/memories/**/*.json # rare, but include anything under memories/
```

### EXCLUDE (always, not overridable)

```
~/.serena/logs/**                    # noisy, privacy
~/.serena/cache/**                   # derivable
<project>/.serena/ls-cache/**        # LS symbol cache, derivable
**/*.env                             # defensive: never sync credential files
**/*.secret
**/*.key                             # private keys
**/*Zone.Identifier                  # Windows sidecar
symlinks                             # never follow
files > 5 MiB                        # hard cap (likely not a memory file)
```

### OPT-IN (warned)

```
<project>/.serena/project.local.yml  # may contain machine-specific values
```
Dashboard shows a prominent warning when `project.local.yml` is in scope,
because it can hold paths / credentials specific to one machine.

## 7. Security model

### 7.1 Credential storage

Single file: `~/.serena/cloud-sync.env` (chmod `600`, owner-only).

- Written **atomically**: write tmp file → `fsync` → `rename` → `chmod 600`.
- On startup, read with `python-dotenv`. If file perms are wider than `600`,
  log a loud warning and refuse to start sync until user runs
  `serena cloud-sync fix-perms`.
- On overwrite, backup existing file to `cloud-sync.env.bak` (also `600`).
- Git-check at configure time: if `~/.serena/` is inside a git repo and the
  env file is tracked, refuse and print remediation.

### 7.2 Env schema (provider-prefixed, one shared file)

```
# Active provider (r2 | s3 | azure)
CLOUD_SYNC_PROVIDER=r2

# Common
CLOUD_SYNC_BUCKET=serena-sync
CLOUD_SYNC_ROOT_PREFIX=serena-sync/

# R2
R2_ACCOUNT_ID=63cc5315...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_ENDPOINT_URL=https://63cc5315....r2.cloudflarestorage.com   # derived by default

# S3
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=eu-west-1

# Azure
AZURE_STORAGE_ACCOUNT=...
AZURE_STORAGE_ACCOUNT_KEY=...
AZURE_CONTAINER=serena-sync
```

Why one file with prefixes (Buddy-approved):
- Operationally simple: one file to back up / copy / rotate.
- Clear which provider is "active" via `CLOUD_SYNC_PROVIDER`.
- Unused provider's keys can remain in the file (stale but inert).
- Avoids proliferation of `cloud-sync-r2.env`, `cloud-sync-s3.env`, etc.

### 7.3 Dashboard secret handling

- `GET /api/cloud-sync/config` returns all fields **masked** (e.g. `****abcd`
  — last 4 chars only). Never returns full secrets.
- `POST /api/cloud-sync/config` accepts partial updates. If a field value is
  `"****"`, it's treated as "unchanged" and NOT overwritten.
- No secret values pass through browser `fetch` response bodies after save.
- Sync-layer `logging.Filter` redacts `AWS_SECRET_ACCESS_KEY`,
  `R2_SECRET_ACCESS_KEY`, `AZURE_STORAGE_ACCOUNT_KEY`, and any value matching
  a high-entropy base64-like pattern in log records.
- Tracebacks from boto3 / azure-storage-blob are caught at the sync-layer
  boundary and reformatted without credential material.

### 7.4 Process isolation

SDK clients constructed with explicit kwargs from the `Settings` pydantic
model. Never `os.environ` side-channel so a stale shell env cannot override.

## 8. Dashboard UX

New navigation item **Cloud Sync** in `index.html`. Page is loaded from
`cloud-sync.html` + `cloud-sync.js`. Layout:

```
┌── Cloud Sync ────────────────────────────────────────────────┐
│                                                              │
│  Provider: [ R2 ▾ ]                                          │
│                                                              │
│  Credentials                                                 │
│    Account ID     [ 63cc5315...                        ]     │
│    Access Key ID  [ ****abcd                           ]     │
│    Secret         [ ****                               ]     │
│    Bucket         [ serena-sync                        ]     │
│    Root prefix    [ serena-sync/                       ]     │
│                                                              │
│  [ Test connection ]   [ Save ]                              │
│                                                              │
│  Actions                                                     │
│    [ Dry-run Push ]  [ Dry-run Pull ]                        │
│    [ Push ]          [ Pull ]       [ Full Sync ]            │
│                                                              │
│  Status                                                      │
│    Local inventory:   52 files  (2.1 MB)                     │
│    Remote inventory:  48 files  (1.9 MB)                     │
│    Last push:         2026-04-13T14:22Z  OK  (4 uploaded)    │
│    Last pull:         2026-04-13T12:01Z  OK  (0 downloaded)  │
│                                                              │
│  Dry-run plan (click an action above)                        │
│    UPLOAD   3                                                │
│    DOWNLOAD 1                                                │
│    CONFLICT 0                                                │
│    SKIP     48                                               │
│                                                              │
│  [ Warning: project.local.yml is included.                   │
│    It may contain machine-specific values. Uncheck to omit. ]│
└──────────────────────────────────────────────────────────────┘
```

- Experimental badge top-right.
- Every destructive action ("Push", "Pull", "Full Sync") **requires a
  dry-run preview** to be rendered within the last 60 seconds (UI enforces).
- Action buttons disable while a sync is running; a live progress area streams
  log lines via Server-Sent Events.

## 9. CLI surface

```
serena cloud-sync configure                 # interactive credential prompt
serena cloud-sync test                      # PUT/HEAD/GET/DELETE probe
serena cloud-sync status                    # inventory counts + last sync markers
serena cloud-sync push [--dry-run] [--force-push] [--byte-compare]
serena cloud-sync pull [--dry-run] [--force-pull] [--byte-compare]
serena cloud-sync fix-perms                 # chmod 600 env file
serena cloud-sync --provider r2|s3|azure    # override active provider for this run
```

- `configure` prompts only for the selected provider's fields; unchanged
  values keep previous (masked input "****" means leave as-is).
- `test` writes a probe object at `<root_prefix>.self-test/<ts>-<host>`,
  HEADs it, GETs it back, compares sha256, then DELETEs it. Only endpoint
  that invokes `delete_object`.

## 10. Dependencies

Add to `pyproject.toml`:

```
"boto3==1.40.x",                 # R2 + S3 (Cloudflare R2 is S3-compatible via endpoint_url)
"azure-storage-blob==12.25.x",   # Phase 2 provider (can be lazy-loaded)
```

Existing deps that cover the rest:
- `flask` — dashboard blueprint
- `python-dotenv` / `dotenv` — env read/write
- `pydantic` — `Settings` typed model
- `cryptography` — reserved for Phase 3 envelope encryption
- `pathspec` — scope include/exclude matching
- `filelock` — local lock on push
- `urllib3` — already TLS-verified

Azure SDK is **lazy-imported** — not required for R2/S3 users in MVP.

## 11. Testing strategy

Clear seam between unit and integration:

### Unit (fast, offline, no SDK calls)
- `tests/cloud_sync/test_scope.py` — include/exclude matrix, symlink reject,
  size cap, Zone.Identifier reject.
- `tests/cloud_sync/test_inventory.py` — sha256 chunked hashing, UTF-8 NFC
  normalization, path-traversal hardening.
- `tests/cloud_sync/test_diff.py` — classify every branch with a
  `FakeCloudProvider` (in-memory dict). Includes CONFLICT detection, sha256
  fallback path, paranoid byte-compare.
- `tests/cloud_sync/test_credentials.py` — atomic write, chmod 600, masked
  read, perms warning, env-file-in-git-repo refusal.
- `tests/cloud_sync/test_sync.py` — `CloudSyncService` push/pull with
  FakeCloudProvider; dry-run plan matches execution.

### Integration (LocalStack for S3-compatible, Azurite for Azure)
- `tests/cloud_sync/integration/test_s3_provider.py` — full round-trip
  against LocalStack S3.
- `tests/cloud_sync/integration/test_r2_provider.py` — round-trip against
  LocalStack S3 configured with R2-shaped endpoint override (R2 specifics
  validated manually against a real R2 token, gated by env var).
- Azure deferred to Phase 2 (Azurite emulator).

### Contract tests
Parametrized test that runs the `put_object_if_absent` semantics against
every available provider and asserts: first PUT succeeds, second PUT with
different body returns `ProviderConflictError` (mapped from 412).

## 12. Phased rollout

### Phase 1 (MVP)
- `CloudStorageProvider` ABC + `base_s3`, `r2`, `s3` providers.
- `CloudSyncService`, `LocalInventory`, `ScopeFilter`, `CredentialsStore`.
- CLI: `configure`, `test`, `status`, `push`, `pull`, `fix-perms`.
- Dashboard: config form, test button, status cards, dry-run + push + pull
  actions.
- Unit tests + LocalStack integration test.
- Experimental flag in dashboard + `--experimental` CLI gate until 1 release
  cycle of field testing.

### Phase 2
- `providers/azure.py` with `azure-storage-blob`.
- Paranoid `--byte-compare` mode.
- Log redactor filter (belt-and-suspenders; basic redaction already in P1).
- Conflict UI: render `.cloud-<ts>` sibling as a diff against local in the
  dashboard.
- Azurite-backed contract + integration tests.

### Phase 3
- Client-side envelope encryption (age via `pyrage` or AES-GCM via
  `cryptography` with a keyring-backed master key).
- Background scheduler (cron-like, opt-in).
- Multi-bucket federation (sync across 2+ clouds for redundancy).
- Rename detection via content-hash lookup.

## 13. Safety / UX commitments

- **Dry-run-first** always.
- **Never silently overwrite divergent content.** `.cloud-<ts>` sibling on
  pull conflicts; refuse push on conflicts without `--force-push`.
- **Mask all secret reads** over HTTP.
- **chmod 600** on credential file, with loud warning if permissions drift.
- **Experimental badge** until field-tested.
- **Additive only.** Documented in dashboard, `--help`, and this doc.
- **`.env`, `.secret`, `.key`** files are never uploaded — hard rule in
  `scope.py` that cannot be overridden by config.

## 14. Known MVP limitations (explicit)

| Area | Limitation | Mitigation / Phase |
|---|---|---|
| Deletes | Not propagated | User deletes on both sides manually; future tombstone design |
| Renames | Not detected (double-counts) | User cleans up the side with the old name |
| Large files | 5 MiB cap | Intended: memory/config files are tiny. Raise cap via Phase 2 if needed |
| Full two-way merge | Not supported | Additive only; CONFLICT preserves both versions |
| At-rest encryption | Provider-default SSE | Client-side envelope encryption in Phase 3 |
| Background sync | User-triggered only | Scheduler in Phase 3 |
| Azure | Deferred | Phase 2 |

## 15. References / prior art

- **Pointerpro `memory-sync.php`** (qdrant memory id `2f431691`) — the
  reference semantics: per-file additive, HEAD-then-PUT-if-404, atomic writes,
  path-traversal hardening, `self-test` probe pattern. This plan is a
  Python-native port into Serena with a proper DIP seam + strategy pattern for
  the three target providers.
- **qdrant-mcp-pp R2 sync** (qdrant memory id `401c13c4`) — snapshot-based R2
  transport; architecturally different (tar.gz snapshots, last-writer wins).
  Not a model for this feature because we explicitly want additive union.
- **Cloudflare R2 S3 compatibility**: R2 supports most S3 APIs via
  `endpoint_url` override in boto3. Known incompatibilities (checksum
  algorithms, specific ACLs) are handled in `providers/r2.py`.

## 16. Acceptance criteria

- [ ] `serena cloud-sync configure` writes `~/.serena/cloud-sync.env` with
      mode `0600`; re-reading returns masked values.
- [ ] `serena cloud-sync test` against R2 (using provided creds) round-trips
      a probe object and cleans it up.
- [ ] `serena cloud-sync push --dry-run` on a populated test project prints a
      classified plan without mutating remote state.
- [ ] `serena cloud-sync push` uploads exactly the files in `UPLOAD` class;
      remote `x-amz-meta-serena-sync-sha256` present on every uploaded
      object.
- [ ] `serena cloud-sync pull` into a freshly-deleted local Serena tree
      restores byte-identical files (sha256 verified).
- [ ] Induced conflict (different body for same key on two machines) is
      classified `CONFLICT`; neither side is overwritten; `.cloud-<ts>`
      sibling appears on pull.
- [ ] Dashboard **Cloud Sync** panel renders; config save writes env atomically;
      masked secrets never leave the server; live action streams progress.
- [ ] Unit test suite: FakeCloudProvider tests for diff / scope / credentials
      all green; LocalStack integration test green.
- [ ] No new import of `boto3` or `azure.storage.blob` outside `providers/`.

## 17. Remote inventory consistency (MVP contract)

For the diff algorithm to be stable across providers, implementation honors
one source-of-truth model:

- **Object key presence** via `ListObjectsV2` (S3/R2) / `list_blobs` (Azure)
  is authoritative for "does this object exist".
- **sha256** comes first from `serena-sync-sha256` in custom metadata (set by
  every upload this tool performs). If absent (legacy / alien object), fall
  back to a streaming hash during diff. Stream-hash results are cached in a
  local `~/.serena/cloud-sync.inventory-cache.json` keyed on
  `(key, etag, last_modified)` so subsequent runs don't re-stream.
- **ETag** is diagnostic only; not a correctness signal. R2 and S3 compute
  ETag differently for multipart uploads; we do not rely on it.
- **version_id** captured when the provider exposes it (S3 with versioning
  enabled) and recorded in `RemoteObjectMeta`, but MVP does not branch on
  version_id. Future phase may use it for time-travel pull.
- **last_modified** captured for reporting, not for diff.
- When a provider returns no object-metadata in listing, the inventory builder
  HEADs each candidate before diff (bounded concurrency). This makes first-run
  inventory slower but correct.

## 18. Failure & idempotency contract

Uploads and downloads are always **interruption-safe** and **idempotent**:

### Upload
- `put_object_if_absent` uses `If-None-Match: "*"`. Server accepts or rejects
  atomically; partial objects don't leak (providers commit only on body-end).
- Multipart is disabled in MVP (5 MiB cap covers all memory/config files).
- On `ProviderConflictError` (412): re-classify the key as CONFLICT, record
  the remote meta, continue the batch.
- On network error: retry with exponential backoff (boto3 default 5 retries;
  Azure explicit retry policy). If all retries fail, that single key is
  reported `FAILED` in the sync report, sync continues for other keys.

### Download
- Write to `<target>.cloud-sync.tmp.<pid>.<rand>` in the same dir, `fsync`,
  `rename` → atomic publication. Temp files cleaned in a `finally`.
- If download is interrupted mid-body, no partial file becomes visible
  because the rename is the commit.
- `.cloud-<ts>` conflict siblings use the same atomic write pattern.

### Retry boundaries
- All provider methods idempotent by construction (`put_if_absent`, GET,
  HEAD, LIST). Retrying a failed op never mutates state beyond what was
  intended.
- Local inventory caching is atomic via tmp+rename; a torn cache file is
  detected on next run (bad JSON) and rebuilt.

### Interrupted sync
- The sync report is written as it progresses to
  `~/.serena/cloud-sync.progress.json`. A Ctrl-C between file k and k+1
  leaves a consistent state on disk: what was done is committed; what
  wasn't done is simply not done.

## 19. Open questions

1. **Should Phase 1 include `azurite`-based integration tests for Azure even
   though the Azure adapter itself ships in Phase 2?** Trade-off: extra CI
   time vs. lower Phase-2 risk.
2. **Should `configure` accept an S3-compatible custom endpoint for
   self-hosted MinIO / Ceph RGW?** Trivial to support (already a field in
   R2), but expands MVP test surface.
3. **Should we publish the Serena cloud-sync wire format (object key layout,
   metadata keys) as a stable contract so third-party tools can interop?**
   Recommendation: mark unstable in MVP, stabilize after Phase 2 feedback.
