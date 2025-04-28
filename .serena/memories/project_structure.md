# Project Structure

The Serena codebase is organized as follows:

- **src/serena/**: Main package with core functionality
  - **llm/**: LLM integration
  - **util/**: Utilities
  - Key files: mcp.py, agno.py, agent.py
- **src/multilspy/**: Language server integration
  - **language_servers/**: Implementations for different languages
    - Python (pyright/jedi)
    - Java (Eclipse JDTLS)
    - TypeScript/JavaScript
    - C#, Rust, Go, Ruby, C++
- **test/**: Tests
- **scripts/**: Utility scripts