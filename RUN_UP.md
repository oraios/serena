# Run_up.md  
Complete workflow to clone, run, and contribute to **Serena** with Claude Code (Aug 2025 CLI).

---

## 1 · Fresh clone & remote setup
```bash
# (Optional) remove any existing local copy
rm -rf ~/dev/serena

# Clone YOUR fork
git clone https://github.com/liebertar/serena.git ~/dev/serena
cd ~/dev/serena

# Link the original repo for future sync
git remote add upstream https://github.com/oraios/serena.git
git remote -v          # verify origin + upstream
```

---

## 2 · Keep your fork current
```bash
git checkout main
git fetch upstream
git merge upstream/main        # or: git rebase upstream/main
git push origin main
```

---

## 3 · Launch Serena locally (detached, no dashboard)
```bash
uv run serena start-mcp-server \
  --context ide-assistant \
  --mode no-onboarding &
```
*Add `--enable-web-dashboard` if you prefer the browser log UI.*

---

## 4 · Register Serena in Claude Code

### 4‑1 Clean any old MCP entry
```bash
claude mcp remove serena || true
```

### 4‑2 Local stdio registration (recommended)
```bash
claude mcp add serena -- \
  uv run --directory "$HOME/dev/serena" serena start-mcp-server \
  --context ide-assistant --mode no-onboarding
```

### 4‑3 Remote SSE registration (silent background)
```bash
# Start Serena as a remote SSE server
uv run serena start-mcp-server --transport sse --port 9121 \
  --context ide-assistant --mode no-onboarding &

# Add the endpoint to Claude Code (user‑wide)
claude mcp remove serena || true
claude mcp add --transport sse --scope user serena http://localhost:9121/sse
```
*Swap `--transport sse`→`http` if you change the server transport.*

---

## 5 · Daily contributor loop
```bash
# 1) Sync fork
git checkout main
git fetch upstream
git merge upstream/main          # or: git rebase upstream/main
git push origin main

# 2) Create a work branch
git checkout -b feat/<my-change>

# 3) Hack, test, commit
git commit -am "feat: <describe change>"

# 4) Push & open PR
git push origin feat/<my-change>
gh pr create -B main -H feat/<my-change> --fill
```

---

### Quick tips
* **Logs:** bring the background job to foreground with `fg` or view with `jobs -l`.
* **Port clash:** add `--port 9222` (server) and update the URL in `claude mcp add`.
* **Dashboard:** globally enable/disable by editing `~/.serena/serena_config.yml` (`web_dashboard: true|false`).
