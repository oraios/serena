package tools

import (
	"context"
	"fmt"
)

// InitialInstructionsTool provides system prompt and manual
type InitialInstructionsTool struct {
	*BaseTool
}

func NewInitialInstructionsTool() *InitialInstructionsTool {
	return &InitialInstructionsTool{
		BaseTool: NewBaseTool(
			"initial_instructions",
			"Provides system prompt and manual for the agent",
			false,
			nil,
		),
	}
}

func (t *InitialInstructionsTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	instructions := `# Serena-TF: Terraform Language Server Agent

## Overview
You are Serena-TF, an AI assistant specialized in Terraform infrastructure as code.
You have access to comprehensive tools for working with Terraform projects through
the Terraform Language Server.

## Available Tool Categories

### File Operations
- **read_file**: Read files with line range support
- **create_text_file**: Create or overwrite files
- **list_dir**: List directory contents (recursive option)
- **find_file**: Find files by glob patterns
- **search_for_pattern**: Regex search across files with context
- **replace_regex**: Regex-based file editing

### Symbol Operations (LSP-powered)
- **get_symbols_overview**: Get top-level symbols in a file
- **find_symbol**: Advanced symbol search with name path patterns
- **find_referencing_symbols**: Find all references to a symbol

### Symbol Editing Operations
- **replace_symbol_body**: Replace entire symbol definition
- **insert_after_symbol**: Insert content after a symbol
- **insert_before_symbol**: Insert content before a symbol
- **rename_symbol**: LSP-powered symbol renaming across project

### Line Editing Operations (Optional tools)
- **delete_lines**: Delete a range of lines
- **replace_lines**: Replace a range of lines
- **insert_at_line**: Insert content at a specific line

### Memory Operations
- **write_memory**: Save project knowledge for future sessions
- **read_memory**: Retrieve saved knowledge
- **list_memories**: List all memories
- **delete_memory**: Remove a memory
- **edit_memory**: Edit memory with regex

### Command Operations
- **execute_shell_command**: Run shell commands (terraform plan/apply/validate, etc.)

### Configuration
- **get_current_config**: Show current configuration and active project

## Best Practices

1. **Use Symbolic Tools First**: When working with code, prefer symbol-based operations
   (find_symbol, get_symbols_overview) over plain file reading. They provide structured
   information about resources, modules, variables, and outputs.

2. **Memory System**: Use memories to store important project information:
   - Deployment procedures
   - Environment configurations
   - Known issues and solutions
   - Team conventions
   This knowledge persists across sessions!

3. **Terraform-Specific Operations**:
   - Use execute_shell_command for terraform CLI operations
   - Understand Terraform symbol hierarchy (resources, modules, variables, outputs, locals, data)
   - Pay attention to resource dependencies

4. **Precise Editing**:
   - Use replace_symbol_body for complete resource/module changes
   - Use insert_after_symbol to add new resources
   - Use rename_symbol for safe refactoring across files

5. **Search Strategy**:
   - Use find_symbol with name patterns (e.g., "aws_" for AWS resources)
   - Use substring_matching for exploratory searches
   - Restrict search with relative_path when you know the location

## Example Workflows

### Exploring a New Project
1. list_dir with recursive=true to understand structure
2. get_symbols_overview on main.tf to see primary resources
3. find_symbol to locate specific resources or modules
4. write_memory to store important findings

### Modifying Infrastructure
1. find_symbol to locate the target resource
2. get_symbols_overview to understand context
3. replace_symbol_body or insert_after_symbol to make changes
4. execute_shell_command to run terraform plan

### Refactoring
1. find_symbol to locate all instances
2. rename_symbol for safe renaming across project
3. find_referencing_symbols to verify changes
4. execute_shell_command to validate with terraform

## Terraform Symbol Kinds
- **Resource** (kind: 5): Infrastructure resources (aws_instance, etc.)
- **Module** (kind: 2): Module calls
- **Variable** (kind: 13): Input variables
- **Output** (kind: 13): Output values
- **Local** (kind: 13): Local values
- **Data** (kind: 5): Data sources

Remember: Always verify changes with terraform plan before applying!
`

	return instructions, nil
}

func (t *InitialInstructionsTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type:       "object",
		Properties: map[string]PropertySchema{},
		Required:   []string{},
	}
}

// CheckOnboardingPerformedTool checks if project onboarding was done
type CheckOnboardingPerformedTool struct {
	*BaseTool
}

func NewCheckOnboardingPerformedTool() *CheckOnboardingPerformedTool {
	return &CheckOnboardingPerformedTool{
		BaseTool: NewBaseTool(
			"check_onboarding_performed",
			"Checks if project onboarding has been performed",
			true,
			[]ToolMarker{ToolMarkerOptional{}},
		),
	}
}

func (t *CheckOnboardingPerformedTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	project := t.GetProject()
	if project == nil {
		return "", fmt.Errorf("no active project")
	}

	memoryMgr := t.GetAgent().GetMemoryManager()
	if memoryMgr == nil {
		return "false", nil
	}

	// Check if onboarding memory exists
	_, err := memoryMgr.LoadMemory("onboarding")
	if err != nil {
		return "false", nil
	}

	return "true", nil
}

func (t *CheckOnboardingPerformedTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type:       "object",
		Properties: map[string]PropertySchema{},
		Required:   []string{},
	}
}

// OnboardingTool performs project onboarding
type OnboardingTool struct {
	*BaseTool
}

func NewOnboardingTool() *OnboardingTool {
	return &OnboardingTool{
		BaseTool: NewBaseTool(
			"onboarding",
			"Performs initial project onboarding and analysis",
			true,
			[]ToolMarker{ToolMarkerOptional{}},
		),
	}
}

func (t *OnboardingTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	instructions := `# Project Onboarding Instructions

Perform the following steps to understand this Terraform project:

1. **Explore Directory Structure**:
   - Use list_dir with recursive=true on "." to see the project layout
   - Identify main configuration files (main.tf, variables.tf, outputs.tf)
   - Look for modules directory
   - Check for environment-specific directories

2. **Analyze Main Configuration**:
   - Use get_symbols_overview on main.tf to see primary resources
   - Identify the cloud provider(s) being used
   - Note resource types and names

3. **Understand Variables**:
   - Use get_symbols_overview on variables.tf to see input parameters
   - Note required vs optional variables
   - Identify default values

4. **Check Outputs**:
   - Use get_symbols_overview on outputs.tf to see exported values
   - Understand what information is exposed

5. **Examine Modules** (if present):
   - Use find_symbol to locate module calls
   - Explore module source directories
   - Understand module purposes

6. **Check Terraform Configuration**:
   - Look for terraform.tf or versions.tf for provider constraints
   - Note required Terraform version
   - Check backend configuration

7. **Identify Key Resources**:
   - Use find_symbol with substring matching to find resource patterns
   - Group resources by type (networking, compute, storage, etc.)
   - Note resource dependencies

8. **Store Findings**:
   - Use write_memory to save "project_structure" memory
   - Store key resources in "key_resources" memory
   - Document deployment approach in "deployment_notes" memory

After onboarding, create an "onboarding" memory to mark completion.
`

	return instructions, nil
}

func (t *OnboardingTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type:       "object",
		Properties: map[string]PropertySchema{},
		Required:   []string{},
	}
}
