# Available Language Servers

Serena supports multiple programming languages through language servers. The language servers currently available in the project are:

## Directly Supported (Out of the Box)
- **Python**: Using Pyright Language Server (previously used Jedi)
- **Java**: Using Eclipse JDTLS (Note: startup is slow, especially initial startup)
- **TypeScript/JavaScript**: Using TypeScript Language Server

## Indirectly Supported (May Require Manual Setup)
- **Ruby**: Using Solargraph
- **Go**: Using Gopls
- **C#**: Using OmniSharp
- **Rust**: Using Rust-Analyzer

These language servers utilize the Language Server Protocol (LSP) to provide semantic code analysis capabilities. The system can be extended to support additional languages by providing adapters for new language server implementations.