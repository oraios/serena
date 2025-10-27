# Polyglot Test Repository

This test repository demonstrates Serena's polyglot support by implementing the same Calculator interface in four languages:

- **Python** (`python/calculator.py`): Object-oriented Calculator class
- **Rust** (`rust/src/lib.rs`): Struct-based Calculator with methods
- **Haskell** (`haskell/src/Calculator.hs`): Functional Calculator data type
- **TypeScript** (`typescript/calculator.ts`): Class-based Calculator

Each implementation provides:
- Basic arithmetic operations (add, subtract, multiply, divide)
- State management (value field)
- Helper functions (double, square)

This repository is used by integration tests in `test/solidlsp/polyglot/` to verify:
- Multi-language LSP routing
- Symbol operations across languages
- Graceful LSP failure handling
