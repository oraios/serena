# Serena OpenAI plugin

Publisher: [Oraios AI](https://oraios-ai.de), legally **Jain & Panchenko IT-Berater Partnerschaft**.
Repository: <https://github.com/oraios/serena>.

## Build

With Python 3.13, run from the repository root:

```sh
python openai-plugin/build_archive.py
```

The output is `openai-plugin/dist/serena-0.1.0.zip`, with one top-level `serena/`
directory. The version comes from `plugin.json`. Output archives are ignored by Git.
The script also works from another working directory when invoked by its full path.

Edit `plugin.json` and `mcp.json` here. The builder generates the Codex compatibility
files from these manifests and packages the icons and license texts. It validates
the package and verifies the archived contents using only the Python standard library.
License files are read directly from the repository's root `LICENSE` and `LICENSES/`
at build time. Icons are read from `src/serena/resources/dashboard/` using the
filenames referenced in the manifest, and placed under `assets/` inside the ZIP.

## Launcher

Running the plugin requires `uv`. The configured local stdio command is:

```sh
uvx -p 3.13 serena-agent@latest start-mcp-server --context codex --project-from-cwd
```

The build script creates the ZIP; submission and publication are separate steps.
