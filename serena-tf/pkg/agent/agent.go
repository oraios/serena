package agent

import (
	"fmt"

	"github.com/TahirRiaz/serena-tf/pkg/config"
	"github.com/TahirRiaz/serena-tf/pkg/lsp"
	"github.com/TahirRiaz/serena-tf/pkg/memory"
	"github.com/TahirRiaz/serena-tf/pkg/project"
	"github.com/TahirRiaz/serena-tf/pkg/tools"
)

// Agent represents the Serena-TF agent
type Agent struct {
	project    *project.Project
	registry   *tools.Registry
	config     *config.Configuration
	activeTools []tools.Tool
}

// NewAgent creates a new agent
func NewAgent(projectPath string, contextName string, modeNames []string, configDir string) (*Agent, error) {
	// Create project
	proj, err := project.NewProject(projectPath)
	if err != nil {
		return nil, fmt.Errorf("failed to create project: %w", err)
	}

	// Create tool registry
	registry := tools.NewRegistry()

	// Register all tools
	if err := registerAllTools(registry); err != nil {
		return nil, fmt.Errorf("failed to register tools: %w", err)
	}

	// Create configuration
	cfg := config.NewConfiguration()

	// Load context if specified
	if contextName != "" {
		context, err := config.LoadContext(contextName, configDir)
		if err != nil {
			return nil, fmt.Errorf("failed to load context %s: %w", contextName, err)
		}
		cfg.AddContext(context)
	}

	// Load modes if specified
	for _, modeName := range modeNames {
		mode, err := config.LoadMode(modeName, configDir)
		if err != nil {
			return nil, fmt.Errorf("failed to load mode %s: %w", modeName, err)
		}
		cfg.AddMode(mode)
	}

	agent := &Agent{
		project:  proj,
		registry: registry,
		config:   cfg,
	}

	// Set agent for all tools
	registry.SetAgentForAll(agent)

	// Filter active tools based on configuration
	agent.activeTools = agent.getActiveTools()

	return agent, nil
}

// registerAllTools registers all available tools
func registerAllTools(registry *tools.Registry) error {
	toolsToRegister := []tools.Tool{
		// File tools
		tools.NewReadFileTool(),
		tools.NewCreateTextFileTool(),
		tools.NewListDirTool(),
		tools.NewFindFileTool(),
		tools.NewSearchForPatternTool(),
		tools.NewReplaceRegexTool(),

		// Symbol tools (read-only)
		tools.NewGetSymbolsOverviewTool(),
		tools.NewFindSymbolTool(),
		tools.NewFindReferencingSymbolsTool(),

		// Symbol editing tools
		tools.NewReplaceSymbolBodyTool(),
		tools.NewInsertAfterSymbolTool(),
		tools.NewInsertBeforeSymbolTool(),
		tools.NewRenameSymbolTool(),
		tools.NewRestartLanguageServerTool(),

		// Line editing tools (optional)
		tools.NewDeleteLinesTool(),
		tools.NewReplaceLinesTool(),
		tools.NewInsertAtLineTool(),

		// Memory tools
		tools.NewWriteMemoryTool(),
		tools.NewReadMemoryTool(),
		tools.NewListMemoriesTool(),
		tools.NewDeleteMemoryTool(),
		tools.NewEditMemoryTool(),

		// Config tools
		tools.NewGetCurrentConfigTool(),

		// Command tools
		tools.NewExecuteShellCommandTool(),

		// Workflow tools
		tools.NewInitialInstructionsTool(),
		tools.NewCheckOnboardingPerformedTool(),
		tools.NewOnboardingTool(),
	}

	for _, tool := range toolsToRegister {
		if err := registry.Register(tool); err != nil {
			return err
		}
	}

	return nil
}

// getActiveTools returns the active tools based on configuration
func (a *Agent) getActiveTools() []tools.Tool {
	allTools := a.registry.GetDefaultEnabled()

	var activeTools []tools.Tool
	for _, tool := range allTools {
		if !a.config.IsToolExcluded(tool.Name()) {
			activeTools = append(activeTools, tool)
		}
	}

	return activeTools
}

// GetProject returns the project
func (a *Agent) GetProject() tools.Project {
	return a.project
}

// GetSymbolRetriever returns the symbol retriever
func (a *Agent) GetSymbolRetriever() tools.SymbolRetriever {
	return &symbolRetrieverAdapter{a.project.GetSymbolRetriever()}
}

// GetMemoryManager returns the memory manager
func (a *Agent) GetMemoryManager() tools.MemoryManager {
	return &memoryManagerAdapter{a.project.GetMemoryManager()}
}

// GetTool returns a tool by name
func (a *Agent) GetTool(name string) tools.Tool {
	tool, _ := a.registry.Get(name)
	return tool
}

// GetTools returns all active tools
func (a *Agent) GetTools() []tools.Tool {
	return a.activeTools
}

// GetSystemPrompt returns the system prompt
func (a *Agent) GetSystemPrompt() string {
	basePrompt := `You are Serena-TF, an AI assistant specialized in Terraform infrastructure as code.

You have access to a comprehensive set of tools for working with Terraform projects:
- File operations (read, create, list, search, edit)
- Symbol-based navigation and editing (find resources, modules, variables, outputs)
- Memory system for preserving knowledge across sessions
- Shell command execution for running Terraform CLI commands

Use symbolic tools when possible for precise code understanding and modification.
The project uses Terraform Language Server for accurate symbol information.
`

	return basePrompt + "\n" + a.config.GetSystemPrompt()
}

// Close closes the agent and cleans up resources
func (a *Agent) Close() error {
	if a.project != nil {
		return a.project.Close()
	}
	return nil
}

// symbolRetrieverAdapter adapts lsp.SymbolRetriever to tools.SymbolRetriever
type symbolRetrieverAdapter struct {
	retriever *lsp.SymbolRetriever
}

func (sra *symbolRetrieverAdapter) GetDocumentSymbols(relativePath string) (interface{}, error) {
	return sra.retriever.GetDocumentSymbols(relativePath)
}

func (sra *symbolRetrieverAdapter) FindSymbolsByName(namePath string, withinPath string, substringMatching bool, includeKinds, excludeKinds []int) (interface{}, error) {
	var includeSymbolKinds []lsp.SymbolKind
	for _, k := range includeKinds {
		includeSymbolKinds = append(includeSymbolKinds, lsp.SymbolKind(k))
	}

	var excludeSymbolKinds []lsp.SymbolKind
	for _, k := range excludeKinds {
		excludeSymbolKinds = append(excludeSymbolKinds, lsp.SymbolKind(k))
	}

	return sra.retriever.FindSymbolsByName(namePath, withinPath, substringMatching, includeSymbolKinds, excludeSymbolKinds)
}

func (sra *symbolRetrieverAdapter) FindReferences(namePath string, relativePath string) (interface{}, error) {
	// This would need to be implemented in the LSP symbol retriever
	// For now, return not implemented
	return nil, fmt.Errorf("find references not yet implemented")
}

// memoryManagerAdapter adapts memory.Manager to tools.MemoryManager
type memoryManagerAdapter struct {
	manager *memory.Manager
}

func (mma *memoryManagerAdapter) SaveMemory(name string, content string) error {
	return mma.manager.SaveMemory(name, content)
}

func (mma *memoryManagerAdapter) LoadMemory(name string) (string, error) {
	return mma.manager.LoadMemory(name)
}

func (mma *memoryManagerAdapter) ListMemories() ([]string, error) {
	return mma.manager.ListMemories()
}

func (mma *memoryManagerAdapter) DeleteMemory(name string) error {
	return mma.manager.DeleteMemory(name)
}
