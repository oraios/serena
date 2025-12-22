
# Connecting Serena MCP Server to ChatGPT via MCPO & Cloudflare Tunnel

This guide explains how to expose a **locally running Serena MCP server** (powered by MCPO) to the internet using **Cloudflare Tunnel**, and how to connect it to **ChatGPT as a Custom GPT with tool access**.

Once configured, ChatGPT becomes a powerful **coding agent** with direct access to your codebase, shell, and file system — so **read the security notes carefully**.

---
## Prerequisites

Make sure you have [uv](https://docs.astral.sh/uv/getting-started/installation/) 
and [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) installed.

## 1. Start the Serena MCP Server via MCPO

Run the following command to launch Serena as http server (assuming port 8000):

```bash
uvx mcpo --port 8000 --api-key <YOUR_SECRET_KEY> -- \
  uvx --from git+https://github.com/oraios/serena \
  serena start-mcp-server --context chatgpt --project $(pwd)
```

- `--api-key` is required to secure the server.
- `--project` should point to the root of your codebase.

You can also use other options, and you don't have to pass `--project` if you want to work on multiple projects
or want to activate it later. See 

```shell
uvx --from git+https://github.com/oraios/serena serena start-mcp-server --help
```

---

## 2. Expose the Server Using Cloudflare Tunnel

Run:

```bash
cloudflared tunnel --url http://localhost:8000
```

This will give you a **public HTTPS URL** like:

```
https://serena-agent-tunnel.trycloudflare.com
```

Your server is now securely exposed to the internet.

---

## 3. Connect It to ChatGPT (Custom GPT)

### Steps:

1. Go to [ChatGPT → Explore GPTs → Create](https://chat.openai.com/gpts/editor)
2. During setup, click **“Add APIs”**
3. Set up **API Key authentication** with the auth type as **Bearer** and enter the api key you used to start the MCPO server.
4. In the **Schema** section, click on **import from URL** and paste `<cloudflared_url>/openapi.json` with the URL you got from the previous step.
5. Add the following line to the top of the imported JSON schema:
    ```
     "servers": ["url": "<cloudflared_url>"],
    ```
   **Important**: don't include a trailing slash at the end of the URL!

ChatGPT will read the schema and create functions automatically.

---

## Security Warning — Read Carefully

Depending on your configuration and enabled tools, Serena's MCP server may:
- Execute **arbitrary shell commands**
- Read, write, and modify **files in your codebase**

This gives ChatGPT the same powers as a remote developer on your machine.

### ⚠️ Key Rules:
- **NEVER expose your API key**
- **Only expose this server when needed**, and monitor its use.

In your project’s `.serena/project.yml` or global config, you can disable tools like:

```yaml
excluded_tools:
  - execute_shell_command
  - ...
read_only: true
```

This is strongly recommended if you want a read-only or safer agent.


---

## Final Thoughts

With this setup, ChatGPT becomes a coding assistant **running on your local code** — able to index, search, edit, and even run shell commands depending on your configuration.

Use responsibly, and keep security in mind.
