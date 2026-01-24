# Custom Agents with Murena

As a reference implementation, we provide an integration with the [Agno](https://docs.agno.com/introduction/playground) agent framework.
Agno is a model-agnostic agent framework that allows you to turn Murena into an agent 
(independent of the MCP technology) with a large number of underlying LLMs. While Agno has recently
added support for MCP servers out of the box, our Agno integration predates this and is a good illustration of how
easy it is to integrate Murena into an arbitrary agent framework.

Here's how it works:

1. Download the agent-ui code with npx
   ```shell
   npx create-agent-ui@latest
   ```
   or, alternatively, clone it manually:
   ```shell
   git clone https://github.com/agno-agi/agent-ui.git
   cd agent-ui 
   pnpm install 
   pnpm dev
   ```

2. Install murena with the optional requirements:
   ```shell
   # You can also only select agno,google or agno,anthropic instead of all-extras
   uv pip install --all-extras -r pyproject.toml -e .
   ```
   
3. Copy `.env.example` to `.env` and fill in the API keys for the provider(s) you
   intend to use.

4. Start the agno agent app with
   ```shell
   uv run python scripts/agno_agent.py
   ```
   By default, the script uses Claude as the model, but you can choose any model
   supported by Agno (which is essentially any existing model).

5. In a new terminal, start the agno UI with
   ```shell
   cd agent-ui 
   pnpm dev
   ```
   Connect the UI to the agent you started above and start chatting. You will have
   the same tools as in the MCP server version.


Here is a short demo of Murena performing a small analysis task with the newest Gemini model:

https://github.com/user-attachments/assets/ccfcb968-277d-4ca9-af7f-b84578858c62


⚠️ IMPORTANT: In contrast to the MCP server approach, tool execution in the Agno UI does
not ask for the user's permission. The shell tool is particularly critical, as it can perform arbitrary code execution. 
While we have never encountered any issues with
this in our testing with Claude, allowing this may not be entirely safe. 
You may choose to disable certain tools for your setup in your Murena project's
configuration file (`.yml`).


## Other Agent Frameworks

It should be straightforward to incorporate Murena into any
agent framework (like [pydantic-ai](https://ai.pydantic.dev/), [langgraph](https://langchain-ai.github.io/langgraph/tutorials/introduction/) or others).
Typically, you need only to write an adapter for Murena's tools to the tool representation in the framework of your choice, 
as was done by us for Agno with `MurenaAgnoToolkit` (see `/src/murena/agno.py`).

