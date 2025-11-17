package project

import (
	"io/ioutil"
	"os"
	"path/filepath"

	"gopkg.in/yaml.v3"
)

// Config represents project configuration
type Config struct {
	Name        string   `yaml:"name"`
	Encoding    string   `yaml:"encoding"`
	ExcludedTools []string `yaml:"excluded_tools"`
}

// NewDefaultConfig creates a default configuration
func NewDefaultConfig() *Config {
	return &Config{
		Name:        "terraform-project",
		Encoding:    "utf-8",
		ExcludedTools: []string{},
	}
}

// LoadConfig loads project configuration
func LoadConfig(projectRoot string) (*Config, error) {
	configPath := filepath.Join(projectRoot, ".serena-tf", "project.yml")

	// Check if config file exists
	if _, err := os.Stat(configPath); os.IsNotExist(err) {
		return nil, err
	}

	// Read config file
	data, err := ioutil.ReadFile(configPath)
	if err != nil {
		return nil, err
	}

	// Parse YAML
	var config Config
	if err := yaml.Unmarshal(data, &config); err != nil {
		return nil, err
	}

	return &config, nil
}

// Save saves the configuration
func (c *Config) Save(projectRoot string) error {
	configPath := filepath.Join(projectRoot, ".serena-tf", "project.yml")

	// Create directory
	if err := os.MkdirAll(filepath.Dir(configPath), 0755); err != nil {
		return err
	}

	// Marshal to YAML
	data, err := yaml.Marshal(c)
	if err != nil {
		return err
	}

	// Write file
	return ioutil.WriteFile(configPath, data, 0644)
}
