# Lean 4 Support in Serena

Serena provides comprehensive support for Lean 4, the functional programming language and theorem prover. This guide covers installation, features, and usage tips for working with Lean 4 projects in Serena.

## Table of Contents

- [Installation](#installation)
- [Features](#features)
- [Project Types](#project-types)
- [Dependencies and Mathlib](#dependencies-and-mathlib)
- [Usage Examples](#usage-examples)
- [Troubleshooting](#troubleshooting)
- [Performance Notes](#performance-notes)

## Installation

### Prerequisites

1. **Install Lean 4 via elan** (the Lean version manager):
   ```bash
   curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh
   source ~/.profile  # or restart your terminal
   ```

2. **Verify installation**:
   ```bash
   lean --version  # Should show Lean 4.x.x
   elan --version  # Should show elan version
   ```

3. **Install Serena** following the [main README](README.md#installation)

### Supported Environments

- ✅ **Linux** - Full support
- ✅ **macOS** - Full support  
- ✅ **Windows** - Full support via WSL or native
- ✅ **GitHub Codespaces** - Works out of the box
- ✅ **Docker** - Supported in containerized environments

## Features

Serena's Lean 4 support provides all the essential IDE-like capabilities:

### 🔍 **Symbol Navigation**
- **Go to Definition**: Navigate to function, theorem, or structure definitions
- **Find References**: Locate all usages of symbols across your project
- **Document Symbols**: Browse all definitions in a file
- **Cross-file Navigation**: Works across Lake project modules

### 📝 **Code Intelligence**
- **Hover Information**: View type signatures and documentation
- **Symbol Completion**: Auto-complete for functions, theorems, and variables
- **Error Detection**: Real-time syntax and type error reporting
- **Import Resolution**: Automatic handling of `import` statements

### 🏗️ **Project Support**
- **Lake Projects**: Full support for Lean 4's build system
- **Dependency Management**: Automatic mathlib and dependency handling
- **Multi-file Projects**: Works with complex project structures
- **Single Files**: Also supports standalone `.lean` files

## Project Types

### Lake Projects (Recommended)

Lake is Lean 4's official build system. Create a new Lake project:

```bash
lake new MyProject
cd MyProject
```

**Directory structure:**
```
MyProject/
├── lakefile.lean      # Project configuration
├── lean-toolchain     # Lean version specification
├── MyProject/
│   └── Basic.lean     # Your Lean code
└── MyProject.lean     # Main module file
```

**Sample `lakefile.lean`:**
```lean
import Lake
open Lake DSL

package myProject

@[default_target]
lean_lib MyProject where
  srcDir := "."
```

### With Mathlib Dependencies

To use mathlib (Lean's mathematical library):

```bash
lake new MyMathProject math
cd MyMathProject
```

This creates a project with mathlib automatically configured in `lakefile.lean`:

```lean
import Lake
open Lake DSL

package myMathProject

require mathlib from git
  "https://github.com/leanprover-community/mathlib4.git"

@[default_target]
lean_lib MyMathProject where
  srcDir := "."
```

### Single Files

For simple exploration, you can work with individual `.lean` files:

```lean
-- hello.lean
def greet (name : String) : String :=
  s!"Hello, {name}!"

#eval greet "Lean 4"
```

## Dependencies and Mathlib

### Automatic Dependency Handling

Serena automatically detects and handles Lean 4 dependencies:

1. **Detection**: Scans `lakefile.lean` for `require` statements
2. **Background Downloads**: Downloads dependencies without blocking the LSP
3. **Progress Tracking**: Provides status updates on download progress
4. **Smart Caching**: Reuses previously downloaded dependencies

### Mathlib Support

Mathlib is Lean's extensive mathematical library. Serena provides special handling:

- **Large Downloads**: Mathlib can be 100MB+, downloads run in background
- **Build Time**: Initial compilation can take 30+ minutes
- **Fallback Mode**: Uses `lean --server` initially, upgrades to `lake serve` when ready
- **Dependency Status**: Check download progress via Serena's tools

### Example Mathlib Project

```lean
-- lakefile.lean
import Lake
open Lake DSL

package mathExample

require mathlib from git
  "https://github.com/leanprover-community/mathlib4.git"

@[default_target]
lean_lib MathExample
```

```lean
-- MathExample/Basic.lean
import Mathlib.Data.Nat.Basic
import Mathlib.Tactic

theorem add_comm_example (a b : ℕ) : a + b = b + a := by
  exact Nat.add_comm a b

-- Using mathlib tactics
theorem simple_proof (n : ℕ) : n + 0 = n := by simp
```

## Usage Examples

### Working with Structures

```lean
-- Define a structure
structure Point where
  x : Float
  y : Float

-- Serena can navigate to this definition from any usage
def origin : Point := ⟨0.0, 0.0⟩

-- Find all references to Point
def distance (p1 p2 : Point) : Float :=
  Float.sqrt ((p1.x - p2.x)^2 + (p1.y - p2.y)^2)
```

### Theorem Development

```lean
-- Serena provides symbol navigation for theorems
theorem my_theorem (n : ℕ) : n + 0 = n := by
  -- Use hover to see intermediate proof states
  induction n with
  | zero => rfl
  | succ n ih => simp [Nat.add_succ, ih]

-- Reference the theorem elsewhere
example (m : ℕ) : m + 0 = m := my_theorem m
```

### Cross-file Organization

```lean
-- MyProject/Definitions.lean
def factorial : ℕ → ℕ
| 0 => 1
| n + 1 => (n + 1) * factorial n

-- MyProject/Theorems.lean  
import MyProject.Definitions

theorem factorial_pos (n : ℕ) : 0 < factorial n := by
  induction n with
  | zero => simp [factorial]
  | succ n ih => simp [factorial, Nat.mul_pos, ih]
```

## Troubleshooting

### Common Issues

#### LSP Server Not Starting
```
Error: Language server terminated immediately
```
**Solution**: Verify Lean 4 installation:
```bash
which lean
lean --version
```

#### Dependencies Not Found
```
Error: unknown package 'mathlib'
```
**Solution**: 
1. Check `lakefile.lean` syntax
2. Run `lake update` manually
3. Ensure internet connectivity for downloads

#### Slow Performance
```
LSP requests timing out
```
**Solutions**:
- Wait for initial dependency downloads to complete
- Use `lake build` to pre-compile dependencies
- Check system resources (mathlib compilation is intensive)

#### Cross-file References Not Working
```
References only found within same file
```
**Solutions**:
- Open all relevant files in your editor
- Wait for LSP indexing to complete (~30 seconds)
- Verify import statements are correct

### Performance Optimization

#### For Large Projects
1. **Pre-build dependencies**:
   ```bash
   lake build
   ```

2. **Use dependency status checks**:
   ```lean
   -- Check if dependencies are ready
   #check DependencyStatus
   ```

3. **Optimize Lake configuration**:
   ```lean
   -- In lakefile.lean, specify exact dependency versions
   require mathlib from git
     "https://github.com/leanprover-community/mathlib4.git" @ "v4.8.0"
   ```

#### Memory Usage
- Lean 4 LSP can use significant RAM (1-4GB for mathlib projects)
- Close unused files to reduce memory pressure
- Consider using lighter alternatives for learning/exploration

### Debugging LSP Issues

Enable verbose logging:
```bash
# Set environment variable
export LEAN_LSP_DEBUG=1

# Run Serena with debug output
uv run serena start-mcp-server --log-level debug
```

Check LSP communication in Serena's web dashboard (usually http://localhost:3001).

## Performance Notes

### Startup Times
- **Simple projects**: ~2-5 seconds
- **Projects with dependencies**: ~10-30 seconds  
- **Mathlib projects**: ~30 seconds - 5 minutes (first time)

### Resource Usage
- **Memory**: 200MB - 4GB depending on project size
- **CPU**: High during initial compilation, moderate during development
- **Disk**: Mathlib cache can be 500MB+

### Optimization Tips
1. **Use specific Lean versions** in `lean-toolchain`
2. **Pre-download dependencies** with `lake update`
3. **Build incrementally** rather than full rebuilds
4. **Close unused projects** to free resources

---

## Getting Help

- **Lean 4 Documentation**: https://lean-lang.org/lean4/doc/
- **Mathlib Documentation**: https://leanprover-community.github.io/mathlib4_docs/
- **Lake Build System**: https://github.com/leanprover/lake
- **Serena Issues**: [GitHub Issues](https://github.com/oraios/serena/issues)

For Lean 4-specific questions, the [Lean Zulip Chat](https://leanprover.zulipchat.com/) is an excellent resource.