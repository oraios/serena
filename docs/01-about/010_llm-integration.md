# LLM Integration

Murena provides the necessary [tools](035_tools) for coding workflows, but an LLM is required to do the actual work,
orchestrating tool use.

In general, Murena can be integrated with an LLM in several ways:

* by using the **model context protocol (MCP)**.
  Murena provides an MCP server which integrates with
    * Claude Code and Claude Desktop,
    * Terminal-based clients like Codex, Gemini-CLI, Qwen3-Coder, rovodev, OpenHands CLI and others,
    * IDEs like VSCode, Cursor or IntelliJ,
    * Extensions like Cline or Roo Code
    * Local clients like [OpenWebUI](https://docs.openwebui.com/openapi-servers/mcp), [Jan](https://jan.ai/docs/mcp-examples/browser/browserbase#enable-mcp), [Agno](https://docs.agno.com/introduction/playground) and others
* by using [mcpo to connect it to ChatGPT](../03-special-guides/murena_on_chatgpt.md) or other clients that don't support MCP but do support tool calling via OpenAPI.
* by incorporating Murena's tools into an agent framework of your choice, as illustrated [here](../03-special-guides/custom_agent).
  Murena's tool implementation is decoupled from the framework-specific code and can thus easily be adapted to any agent framework.
