# Adding Language Support

Your language belongs here. Serena speaks some sixty languages because people kept walking
exactly this path — and the maintainers' answer to "would you accept mine?" has been a
consistent yes. No issue required, no permission to ask: `CONTRIBUTING.md` names this the
contribution that can go straight to a pull request, and servers that follow the template
routinely merge within hours.

The project's own guide,
[`adding_new_language_support_guide.md`](https://github.com/oraios/serena/blob/main/.serena/memories/adding_new_language_support_guide.md),
is the authority — read it in full before starting. This page is the friendly walk beside
it.

## The shape of the trip

You will make five things. None of them is big, and every one has working examples to learn
from:

1. a language-server class — the only real code,
2. one enum entry to register it,
3. a tiny fixture project,
4. the tests that prove it works,
5. a short paper trail.

## 1. The language-server class

The heart of it. Your class lives under `src/solidlsp/language_servers/` and follows the
`DependencyProvider` pattern: the launch command comes from a dependency provider rather
than being assembled inline. Pass `None` for `process_launch_info` in `super().__init__()`,
implement `_create_dependency_provider()`, and you are most of the way there.

### Pick your base class

Good news: most of the work is already done for you. Four base classes cover the usual
shapes, and your job is mostly picking the right one and filling in a method or two. Take
the most specific one that fits — and read one existing implementation of it first; that
half hour will save you an evening.

| base class | fits when | reference |
|:--|:--|:--|
| `LanguageServerDependencyProviderUvx` | the server is a PyPI package run on demand via `uvx` — no install step to implement; instantiate with package name, pinned version and entrypoint | `PyrightServer` |
| `LanguageServerDependencyProviderBaseCommand` | the common case: the launch command builds from a *base command* the user can override in custom settings | — |
| `LanguageServerDependencyProviderSinglePath` | one core dependency (an executable, a JAR) that is not itself the base command | `TypeScriptLanguageServer`, `Intelephense`, `ClojureLSP`, `ClangdLanguageServer` |
| `LanguageServerDependencyProvider` (root) | multiple dependencies or custom setup; implement `create_launch_command()` directly — no automatic user override support | `EclipseJDTLS`, `CSharpLanguageServer`, `MatlabLanguageServer` |

Two habits the guide asks of you: override `create_launch_command_env` when the launch
needs environment variables, and reach for the `subprocess_run` helper from
`solidlsp.util.subprocess_util` instead of `subprocess.run` — it exists for a reason.

### Downloads: declared, verified, done

If your server needs anything downloaded, `DownloadedDependency`
(`solidlsp.dependency_provider`) does the careful parts — URL, archive type, allowed hosts
and checksum verification, all behind one `download_to()` call. The checksums live in a
URL-keyed database, `src/solidlsp/resources/downloaded_dependency_hashes.json`, so a
tampered download simply refuses to arrive.

Four small rules keep it honest:

- build each dependency in a factory classmethod (`_create_dep_*`) that takes an optional
  version and falls back to a pinned `DEFAULT_*` constant;
- add an `update_dep_hashes()` classmethod that refreshes the database, and hook it into
  `scripts/dev/update_downloaded_dependency_hashes.py`;
- after bumping a pinned version, re-run that script and commit the JSON — a stale database
  means unverified downloads locally and a red CI;
- `verified=False` is only for hashes that cannot be pinned by design.

`EclipseJDTLS.DependencyProvider` is the reference. You will notice a few older servers
hard-coding hashes in constants — that is the legacy shape, and you are building the new
one. Don't copy them.

### Initialization: less than you think

A pleasant surprise: you provide only what is specific to *your* server. Override
`_create_base_initialize_params` and return just the server-specific keys — typically
`capabilities` and `initializationOptions`. The common ones (`processId`, `rootPath`,
`rootUri`, `clientInfo`, `workspaceFolders`) belong to the `InitializeParamsBuilder`, which
sets them centrally — one less thing for you to get wrong, so your override must not touch
them.

Two edge cases, both already solved: a server that wants the folder list *nested inside*
`initializationOptions` (as `EclipseJDTLS` and `KotlinLanguageServer` do) sets it there
explicitly — only the top-level `workspaceFolders` is builder-managed; and if the top-level
key must go entirely, `_create_initialize_params_builder` with
`set_workspace_folders=False` does it.

Some servers like to warm up before they answer. If yours needs to wait for a notification
before it is ready, that logic belongs in `_start_server` — `EclipseJDTLS._start_server`
shows how.

## 2. Registration — one enum, two match arms

Genuinely the easy part: add your language to the `LanguageServerId` enum in
`src/solidlsp/ls_config.py`, teach `get_source_fn_matcher()` which file extensions are
yours, and have `get_ls_class()` import and return your server class. Done.

## 3. The fixture repository

Make a tiny, real project under `test/resources/repos/<language>/test_repo/` — think of it
as the stage your tests will perform on. Give it something worth finding: classes or types
(for symbol lookup), functions with callers (for reference finding), an import or two (for
cross-file operations), and some nesting (for hierarchical symbols).

## 4. Tests — where the review happens

The guide says it plainly: the tests will form the main part of the review, so this is
where care pays off most. Create `test/solidlsp/<language>/test_<language>_basic.py`,
modelled on `test/solidlsp/php/test_php_basic.py`, and cover at least: finding symbols,
within-file references, and cross-file references.

Three rules, all firm, all fair:

1. assert on the actual symbol and reference names — "a list came back" proves nothing;
2. never skip, except on package availability or an unsupported OS;
3. the tests must run in CI — check whether a GitHub action exists for installing your
   toolchain.

Declare your marker under `[tool.pytest.ini_options].markers` in `pyproject.toml`, then run
your suite with `uv run poe test -m <marker>` and watch it go green.

## 5. The paper trail

Four small updates and you are done:

- **README.md** — add your language to the list;
- **`docs/01-about/020_programming-languages.md`** — add it, with any special notes a user
  needs (required installations, compatibility);
- **`src/serena/resources/project.template.yml`** — regenerate the commented list with
  `uv run python scripts/dev/print_language_list.py` and paste it over the old one (strip the
  trailing spaces the script pads with);
- **CHANGELOG.md** — one concise line to mark the occasion.

## CI does the rest

Declare the marker and CI seats your language in one of the batched jobs — `jvm`, `native`,
`other-langs` or `niche`, per the lists in `.github/workflows/pytest.yml`. On machines
without your toolchain the tests skip rather than fail, centrally, via `test/conftest.py`.
Nothing to configure. The wider machinery — and why it is shaped the way it is — lives in
[The CI Matrix](045_ci).

## You would be in good company

Nextflow ([#1815](https://github.com/oraios/serena/pull/1815)), Gleam
([#1765](https://github.com/oraios/serena/pull/1765)), Deno
([#1778](https://github.com/oraios/serena/pull/1778)) and BasedPyright
([#1705](https://github.com/oraios/serena/pull/1705)) all landed exactly this way —
most within hours, with reviews closer to "Thanks, looks good, merging!" than to a
checklist. Gleam took three tries and got there anyway.

Bring your language.
