# About Serena

* Serena is a powerful **coding agent toolkit** capable of turning an LLM into a fully-featured agent that works
  **directly on your codebase**.
  Unlike most other tools, it is not tied to an LLM, framework or an interface, making it easy to use it in a variety of ways.
* Serena provides essential **semantic code retrieval and editing tools** that are akin to an IDE's capabilities,
  extracting code entities at the symbol level and exploiting relational structure.
  When combined with an existing coding agent, these tools greatly enhance (token) efficiency.
* Serena is **free & open-source**, enhancing the capabilities of LLMs you already have access to free of charge.

Therefore, you can think of Serena as providing IDE-like tools to your LLM/coding agent.
With it, the agent no longer needs to read entire files, perform grep-like searches or string replacements to find and
edit the right code.
Instead, it can use code-centred tools like `find_symbol`, `find_referencing_symbols` and `insert_after_symbol`.
