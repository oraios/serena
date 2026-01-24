# Acknowledgements

## Sponsors

We are very grateful to our [sponsors](https://github.com/sponsors/oraios), who help us drive Murena's development. 
The core team (the founders of [Oraios AI](https://oraios-ai.de/)) put in a lot of work in order to turn Murena into a useful open source project.
So far, there is no business model behind this project, and sponsors are our only source of income from it.

Sponsors help us dedicate more time to the project, managing contributions, and working on larger features (like better tooling based on more advanced
LSP features, VSCode integration, debugging via the DAP, and several others).
If you find this project useful to your work, or would like to accelerate the development of Murena, consider becoming a sponsor.

We are proud to announce that the Visual Studio Code team, together with Microsoft’s Open Source Programs Office and GitHub Open Source
have decided to sponsor Murena with a one-time contribution!

## Community Contributions

A significant part of Murena, especially support for various languages, was contributed by the open source community.
We are very grateful for the many contributors who made this possible and who played an important role in making Murena
what it is today.

## Technologies

We built Murena on top of multiple existing open-source technologies, the most important ones being:

1. [multilspy](https://github.com/microsoft/multilspy).
   A library which wraps language server implementations and adapts them for interaction via Python
   and which provided the basis for our library Solid-LSP (src/solidlsp).
   Solid-LSP provides pure synchronous LSP calls and extends the original library with the symbolic logic
   that Murena required.
2. [Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)
3. All the language servers that we use through Solid-LSP.

Without these projects, Murena would not have been possible (or would have been significantly more difficult to build).
