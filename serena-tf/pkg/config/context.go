package config

import (
	"io/ioutil"
	"path/filepath"

	"gopkg.in/yaml.v3"
)

// Context represents a context configuration
type Context struct {
	Description string            `yaml:"description"`
	Prompt      string            `yaml:"prompt"`
	ExcludedTools []string        `yaml:"excluded_tools"`
	ToolDescriptionOverrides map[string]string `yaml:"tool_description_overrides"`
}

// LoadContext loads a context from a YAML file
func LoadContext(name string, configDir string) (*Context, error) {
	path := filepath.Join(configDir, "contexts", name+".yml")

	data, err := ioutil.ReadFile(path)
	if err != nil {
		return nil, err
	}

	var context Context
	if err := yaml.Unmarshal(data, &context); err != nil {
		return nil, err
	}

	return &context, nil
}

// Mode represents a mode configuration
type Mode struct {
	Description string   `yaml:"description"`
	Prompt      string   `yaml:"prompt"`
	ExcludedTools []string `yaml:"excluded_tools"`
}

// LoadMode loads a mode from a YAML file
func LoadMode(name string, configDir string) (*Mode, error) {
	path := filepath.Join(configDir, "modes", name+".yml")

	data, err := ioutil.ReadFile(path)
	if err != nil {
		return nil, err
	}

	var mode Mode
	if err := yaml.Unmarshal(data, &mode); err != nil {
		return nil, err
	}

	return &mode, nil
}

// Configuration represents the full configuration
type Configuration struct {
	Context       *Context
	Modes         []*Mode
	ExcludedTools map[string]bool
	SystemPrompt  string
}

// NewConfiguration creates a new configuration
func NewConfiguration() *Configuration {
	return &Configuration{
		ExcludedTools: make(map[string]bool),
	}
}

// AddContext adds a context to the configuration
func (c *Configuration) AddContext(context *Context) {
	c.Context = context

	for _, tool := range context.ExcludedTools {
		c.ExcludedTools[tool] = true
	}

	c.buildSystemPrompt()
}

// AddMode adds a mode to the configuration
func (c *Configuration) AddMode(mode *Mode) {
	c.Modes = append(c.Modes, mode)

	for _, tool := range mode.ExcludedTools {
		c.ExcludedTools[tool] = true
	}

	c.buildSystemPrompt()
}

// buildSystemPrompt builds the combined system prompt
func (c *Configuration) buildSystemPrompt() {
	var prompt string

	// Add context prompt
	if c.Context != nil && c.Context.Prompt != "" {
		prompt += c.Context.Prompt + "\n\n"
	}

	// Add mode prompts
	for _, mode := range c.Modes {
		if mode.Prompt != "" {
			prompt += mode.Prompt + "\n\n"
		}
	}

	c.SystemPrompt = prompt
}

// IsToolExcluded checks if a tool is excluded
func (c *Configuration) IsToolExcluded(toolName string) bool {
	return c.ExcludedTools[toolName]
}

// GetSystemPrompt returns the system prompt
func (c *Configuration) GetSystemPrompt() string {
	return c.SystemPrompt
}
