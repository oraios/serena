package tools

import (
	"context"
	"encoding/json"
	"fmt"
)

// Tool represents a tool interface
type Tool interface {
	// Name returns the tool name
	Name() string

	// Description returns the tool description
	Description() string

	// Apply executes the tool with given parameters
	Apply(ctx context.Context, params map[string]interface{}) (string, error)

	// Schema returns the tool's parameter schema
	Schema() *ToolSchema

	// RequiresProject returns true if the tool requires an active project
	RequiresProject() bool

	// Markers returns the tool markers
	Markers() []ToolMarker

	// SetAgent sets the agent for the tool
	SetAgent(agent ToolAgent)
}

// ToolAgent provides access to agent functionality for tools
type ToolAgent interface {
	GetProject() Project
	GetSymbolRetriever() SymbolRetriever
	GetMemoryManager() MemoryManager
	GetTool(name string) Tool
}

// Project interface for project operations
type Project interface {
	GetRoot() string
	ReadFile(relativePath string) (string, error)
	WriteFile(relativePath string, content string) error
	ValidatePath(relativePath string, requireNotIgnored bool) error
	IsIgnoredPath(path string) bool
	PathExists(relativePath string) bool
}

// SymbolRetriever interface for symbol operations
type SymbolRetriever interface {
	GetDocumentSymbols(relativePath string) (interface{}, error)
	FindSymbolsByName(namePath string, withinPath string, substringMatching bool, includeKinds, excludeKinds []int) (interface{}, error)
	FindReferences(namePath string, relativePath string) (interface{}, error)
}

// MemoryManager interface for memory operations
type MemoryManager interface {
	SaveMemory(name string, content string) error
	LoadMemory(name string) (string, error)
	ListMemories() ([]string, error)
	DeleteMemory(name string) error
}

// ToolSchema represents a tool's parameter schema
type ToolSchema struct {
	Type       string                    `json:"type"`
	Properties map[string]PropertySchema `json:"properties"`
	Required   []string                  `json:"required,omitempty"`
}

// PropertySchema represents a property schema
type PropertySchema struct {
	Type        string      `json:"type"`
	Description string      `json:"description,omitempty"`
	Default     interface{} `json:"default,omitempty"`
	Items       *PropertySchema `json:"items,omitempty"`
	Enum        []interface{} `json:"enum,omitempty"`
}

// ToolMarker represents a tool marker interface
type ToolMarker interface {
	MarkerName() string
}

// ToolMarkerCanEdit marks tools that can edit files
type ToolMarkerCanEdit struct{}

func (t ToolMarkerCanEdit) MarkerName() string {
	return "can_edit"
}

// ToolMarkerSymbolicEdit marks tools that perform symbolic edits
type ToolMarkerSymbolicEdit struct{}

func (t ToolMarkerSymbolicEdit) MarkerName() string {
	return "symbolic_edit"
}

// ToolMarkerSymbolicRead marks tools that perform symbolic reads
type ToolMarkerSymbolicRead struct{}

func (t ToolMarkerSymbolicRead) MarkerName() string {
	return "symbolic_read"
}

// ToolMarkerOptional marks optional tools (disabled by default)
type ToolMarkerOptional struct{}

func (t ToolMarkerOptional) MarkerName() string {
	return "optional"
}

// BaseTool provides common functionality for tools
type BaseTool struct {
	name             string
	description      string
	requiresProject  bool
	markers          []ToolMarker
	agent            ToolAgent
	maxAnswerChars   int
	defaultMaxChars  int
}

// NewBaseTool creates a new base tool
func NewBaseTool(name, description string, requiresProject bool, markers []ToolMarker) *BaseTool {
	return &BaseTool{
		name:            name,
		description:     description,
		requiresProject: requiresProject,
		markers:         markers,
		defaultMaxChars: 100000, // Default limit
	}
}

// Name returns the tool name
func (bt *BaseTool) Name() string {
	return bt.name
}

// Description returns the tool description
func (bt *BaseTool) Description() string {
	return bt.description
}

// RequiresProject returns true if tool requires a project
func (bt *BaseTool) RequiresProject() bool {
	return bt.requiresProject
}

// Markers returns the tool markers
func (bt *BaseTool) Markers() []ToolMarker {
	return bt.markers
}

// SetAgent sets the agent
func (bt *BaseTool) SetAgent(agent ToolAgent) {
	bt.agent = agent
}

// GetAgent returns the agent
func (bt *BaseTool) GetAgent() ToolAgent {
	return bt.agent
}

// GetProject returns the project
func (bt *BaseTool) GetProject() Project {
	if bt.agent == nil {
		return nil
	}
	return bt.agent.GetProject()
}

// LimitLength limits the length of output
func (bt *BaseTool) LimitLength(content string, maxChars int) string {
	if maxChars == -1 {
		maxChars = bt.defaultMaxChars
	}

	if len(content) <= maxChars {
		return content
	}

	return fmt.Sprintf("[Content truncated: %d characters, limit is %d]", len(content), maxChars)
}

// ParseParams parses parameters from map into a struct
func ParseParams(params map[string]interface{}, target interface{}) error {
	// Convert to JSON and back
	data, err := json.Marshal(params)
	if err != nil {
		return fmt.Errorf("failed to marshal params: %w", err)
	}

	if err := json.Unmarshal(data, target); err != nil {
		return fmt.Errorf("failed to unmarshal params: %w", err)
	}

	return nil
}

// SuccessResult is a constant for success messages
const SuccessResult = "Operation completed successfully"
