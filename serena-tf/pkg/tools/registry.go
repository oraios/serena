package tools

import (
	"fmt"
	"sync"
)

// Registry manages all available tools
type Registry struct {
	tools map[string]Tool
	mutex sync.RWMutex
}

// NewRegistry creates a new tool registry
func NewRegistry() *Registry {
	return &Registry{
		tools: make(map[string]Tool),
	}
}

// Register registers a tool
func (r *Registry) Register(tool Tool) error {
	r.mutex.Lock()
	defer r.mutex.Unlock()

	name := tool.Name()
	if _, exists := r.tools[name]; exists {
		return fmt.Errorf("tool %s is already registered", name)
	}

	r.tools[name] = tool
	return nil
}

// Get retrieves a tool by name
func (r *Registry) Get(name string) (Tool, error) {
	r.mutex.RLock()
	defer r.mutex.RUnlock()

	tool, exists := r.tools[name]
	if !exists {
		return nil, fmt.Errorf("tool %s not found", name)
	}

	return tool, nil
}

// GetAll returns all registered tools
func (r *Registry) GetAll() []Tool {
	r.mutex.RLock()
	defer r.mutex.RUnlock()

	tools := make([]Tool, 0, len(r.tools))
	for _, tool := range r.tools {
		tools = append(tools, tool)
	}

	return tools
}

// GetNames returns all tool names
func (r *Registry) GetNames() []string {
	r.mutex.RLock()
	defer r.mutex.RUnlock()

	names := make([]string, 0, len(r.tools))
	for name := range r.tools {
		names = append(names, name)
	}

	return names
}

// GetDefaultEnabled returns tools that are enabled by default (not optional)
func (r *Registry) GetDefaultEnabled() []Tool {
	r.mutex.RLock()
	defer r.mutex.RUnlock()

	var tools []Tool
	for _, tool := range r.tools {
		isOptional := false
		for _, marker := range tool.Markers() {
			if marker.MarkerName() == "optional" {
				isOptional = true
				break
			}
		}

		if !isOptional {
			tools = append(tools, tool)
		}
	}

	return tools
}

// FilterByMarker returns tools with a specific marker
func (r *Registry) FilterByMarker(markerName string) []Tool {
	r.mutex.RLock()
	defer r.mutex.RUnlock()

	var tools []Tool
	for _, tool := range r.tools {
		for _, marker := range tool.Markers() {
			if marker.MarkerName() == markerName {
				tools = append(tools, tool)
				break
			}
		}
	}

	return tools
}

// FilterByNames returns tools with specific names
func (r *Registry) FilterByNames(names []string) []Tool {
	r.mutex.RLock()
	defer r.mutex.RUnlock()

	var tools []Tool
	nameSet := make(map[string]bool)
	for _, name := range names {
		nameSet[name] = true
	}

	for _, tool := range r.tools {
		if nameSet[tool.Name()] {
			tools = append(tools, tool)
		}
	}

	return tools
}

// ExcludeByNames returns tools excluding specific names
func (r *Registry) ExcludeByNames(excludeNames []string) []Tool {
	r.mutex.RLock()
	defer r.mutex.RUnlock()

	excludeSet := make(map[string]bool)
	for _, name := range excludeNames {
		excludeSet[name] = true
	}

	var tools []Tool
	for _, tool := range r.tools {
		if !excludeSet[tool.Name()] {
			tools = append(tools, tool)
		}
	}

	return tools
}

// SetAgentForAll sets the agent for all tools
func (r *Registry) SetAgentForAll(agent ToolAgent) {
	r.mutex.RLock()
	defer r.mutex.RUnlock()

	for _, tool := range r.tools {
		tool.SetAgent(agent)
	}
}

// Clear clears all tools
func (r *Registry) Clear() {
	r.mutex.Lock()
	defer r.mutex.Unlock()

	r.tools = make(map[string]Tool)
}

// Count returns the number of registered tools
func (r *Registry) Count() int {
	r.mutex.RLock()
	defer r.mutex.RUnlock()

	return len(r.tools)
}
