# Lean 4 Support PR Todo List

## ✅ COMPLETED ITEMS
- [x] Lean4Server implementation done and working (`src/solidlsp/language_servers/lean4_server.py`)
- [x] Integration with Language enum and factory method complete
- [x] Test suite exists with 8 passing tests (`test/solidlsp/lean4/test_lean4_basic.py`)
- [x] Test repository exists at `test/resources/repos/lean4/`
- [x] Code passes type checking and formatting
- [x] Lean4 pytest marker already added to `pyproject.toml` (line 256)

## 🔧 CODE CLEANUP TASKS

### High Priority
- [ ] **Review and merge lean4_server_improvements.py**
  - File: `/home/ubuntu/serena/src/solidlsp/language_servers/lean4_server_improvements.py`
  - Contains improved .ilean file parser with caching and better error handling
  - Decision needed: merge improvements into main lean4_server.py or keep separate
  - Includes performance decorators and better symbol classification

- [ ] **Remove debug scripts from root directory**
  - [ ] Delete `/home/ubuntu/serena/debug_lean4_final.py`
  - [ ] Delete `/home/ubuntu/serena/debug_lean4_refs.py`
  - [ ] Delete `/home/ubuntu/serena/debug_lean4_refs2.py`
  - [ ] Delete `/home/ubuntu/serena/debug_lean4_refs3.py`
  - [ ] Delete `/home/ubuntu/serena/test_lean4_fix.py`

### Medium Priority
- [ ] **Organize documentation files**
  - [ ] Move or remove `/home/ubuntu/serena/SERENA_CLAUDE_CODE_SETUP_ANALYSIS.md`
  - [ ] Move or remove `/home/ubuntu/serena/SERENA_CLAUDE_CODE_SETUP_ANALYSIS_JA.md`
  - [ ] Move or remove `/home/ubuntu/serena/SERENA_PROJECT_SCOPE_SETUP_JA.md`
  - [ ] Move or remove `/home/ubuntu/serena/how_to_add_mcp.md`
  - [ ] Remove `/home/ubuntu/serena/prompt/` directory if not needed

## 📚 DOCUMENTATION UPDATES

### Required Updates
- [ ] **Update CLAUDE.md with Lean 4 information**
  - Add Lean 4 to the language support list in architecture overview
  - Update development patterns section with Lean 4 example
  - Verify existing LEAN4.md is comprehensive

- [ ] **Update README.md**
  - Add Lean 4 to supported languages list
  - Include any Lean 4-specific setup instructions
  - Update language count if necessary

- [ ] **Review LEAN4.md file**
  - Ensure it contains all necessary setup and usage information
  - Verify it aligns with the implemented features
  - Check for any outdated information

## 🧪 FINAL VERIFICATION TASKS

### Pre-PR Checklist
- [ ] **Run complete test suite**
  ```bash
  uv run poe test
  ```

- [ ] **Run Lean 4-specific tests**
  ```bash
  uv run poe test -m lean4
  ```

- [ ] **Verify formatting and type checking**
  ```bash
  uv run poe format
  uv run poe type-check
  ```

- [ ] **Test end-to-end functionality**
  - [ ] Start MCP server with Lean 4 project
  - [ ] Verify symbol finding works
  - [ ] Test symbol editing operations
  - [ ] Confirm language server starts correctly

## 🎯 PR PREPARATION

### Final Steps
- [ ] **Create clean commit for cleanup**
  - Remove debug scripts
  - Organize documentation files
  - Merge or remove lean4_server_improvements.py

- [ ] **Update commit messages**
  - Ensure commit messages follow repository conventions
  - Squash development commits if needed

- [ ] **Prepare PR description**
  - Summarize Lean 4 implementation
  - List supported features
  - Include testing information
  - Document any limitations or known issues

- [ ] **Create branch for PR**
  ```bash
  git checkout -b feature/lean4-support
  ```

## 📋 IMPLEMENTATION SUMMARY

### What's Included
- Full Lean 4 language server integration
- Support for .lean file symbol extraction
- .ilean file parsing for enhanced symbol information
- Symbol finding, navigation, and editing
- Comprehensive test suite with 8 test cases
- Test repository with realistic Lean 4 project structure

### Key Features
- Automatic Lean 4 language server detection and startup
- Symbol kind inference (theorems, definitions, structures, etc.)
- Hierarchical symbol navigation
- Thread-safe implementation with proper cleanup
- Robust error handling and logging

### Test Coverage
- Basic symbol retrieval
- Symbol finding operations
- Language server lifecycle management
- Error handling scenarios
- Integration with SolidLanguageServer framework

## ⚠️ NOTES

1. **lean4_server_improvements.py** contains significant enhancements but needs decision on integration
2. All pytest markers are correctly configured in pyproject.toml
3. Current implementation passes all existing tests
4. Documentation files may contain sensitive setup information - review before committing
5. Debug scripts should be removed but may contain useful debugging patterns for future reference

## 🏁 COMPLETION CRITERIA

PR is ready when:
- [ ] All cleanup tasks completed
- [ ] Documentation updated
- [ ] All tests passing
- [ ] End-to-end verification successful
- [ ] Code review ready
- [ ] No debug files in root directory
- [ ] Clean git history