# Agents Development Guide

This guide outlines best practices for AI agents contributing to the Serena codebase. Serena is a powerful coding agent toolkit that provides IDE-like semantic code analysis and editing capabilities across many programming languages.

## Core Development Principles

### 1. Real-World Testing - Minimize Mocking Philosophy

Serena **strongly prefers real integration testing** over mocking, especially for core language server functionality. However, mocks are used strategically for specific scenarios.

**When to Use Real Integration:**
- Language server interactions (symbol retrieval, code editing, LSP communication)
- File system operations and repository structures
- Cross-language feature testing
- End-to-end tool workflows

**When Mocks Are Acceptable:**
- External dependencies (network calls, system utilities)
- Environment detection and platform-specific behavior
- Infrastructure setup that doesn't affect core functionality
- Test utilities and file readers for isolated unit tests

**Test Infrastructure:**
- Each test spins up a **real language server** for the target language
- Tests use **real repository structures** from `test/resources/repos/`
- Files are copied to temporary directories for isolated testing
- Language servers are properly started, used, and cleaned up

### 2. Testing New Features

When implementing a new feature, follow the established `EditingTest` pattern:

1. **Create Test Infrastructure**: Extend `EditingTest` base class with feature-specific parameters
2. **Use Real Test Repositories**: Add test files to appropriate language directories in `test/resources/repos/`
3. **Snapshot-Based Testing**: Use pytest snapshots to validate complex text transformations
4. **Cross-Language Testing**: Use parameterized tests with language-specific markers

### 3. Language Server Integration

Serena's power comes from deep language server integration:

- **Proper Lifecycle Management**: Use context managers for setup/teardown
- **Symbol-Level Operations**: Always work at the symbol level, not text level
- **Semantic Understanding**: Leverage LSP capabilities over string manipulation

### 4. Code Architecture Patterns

- **Abstract Base Classes**: Use ABCs to define clear interfaces
- **Language-Agnostic Design**: Build features that work across languages through LSP
- **Tool Pattern**: Follow established tool pattern for new capabilities with proper error handling

### 5. Testing Best Practices

- **Comprehensive Edge Cases**: Test various symbol patterns and failure modes
- **Multi-Language Support**: Test features across supported languages with appropriate markers
- **Snapshot Testing**: Use snapshots for complex output validation with sanity checks
- **Resource Management**: Always clean up language servers and temporary files

### 6. Error Handling and Performance

- **Graceful Degradation**: Provide fallbacks when language server operations fail
- **Resource Cleanup**: Handle Windows file locking and proper cleanup
- **Efficient Operations**: Cache when possible, use targeted searches, implement depth limits

## Contributing Guidelines

### Before Implementing a New Feature:
1. Study existing similar features in the codebase
2. Design language-agnostic interfaces
3. Plan comprehensive test coverage
4. Consider multi-language support from the start

### Code Review Checklist:
- [ ] Core functionality uses real language servers, not mocks
- [ ] Mocks are only used for external dependencies or infrastructure
- [ ] Tests cover multiple languages where applicable
- [ ] Proper error handling and cleanup
- [ ] Follows established architectural patterns
- [ ] Snapshot tests validate actual behavior
