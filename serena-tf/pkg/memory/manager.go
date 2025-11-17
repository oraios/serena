package memory

import (
	"fmt"
	"io/ioutil"
	"os"
	"path/filepath"
	"strings"
)

// Manager manages project memories
type Manager struct {
	memoryDir string
}

// NewManager creates a new memory manager
func NewManager(projectRoot string) (*Manager, error) {
	memoryDir := filepath.Join(projectRoot, ".serena-tf", "memories")

	if err := os.MkdirAll(memoryDir, 0755); err != nil {
		return nil, fmt.Errorf("failed to create memory directory: %w", err)
	}

	return &Manager{
		memoryDir: memoryDir,
	}, nil
}

// GetMemoryFilePath returns the file path for a memory
func (m *Manager) GetMemoryFilePath(name string) string {
	// Strip .md extension if present
	name = strings.TrimSuffix(name, ".md")
	return filepath.Join(m.memoryDir, name+".md")
}

// SaveMemory saves a memory
func (m *Manager) SaveMemory(name string, content string) error {
	path := m.GetMemoryFilePath(name)

	if err := ioutil.WriteFile(path, []byte(content), 0644); err != nil {
		return fmt.Errorf("failed to write memory: %w", err)
	}

	return nil
}

// LoadMemory loads a memory
func (m *Manager) LoadMemory(name string) (string, error) {
	path := m.GetMemoryFilePath(name)

	if _, err := os.Stat(path); os.IsNotExist(err) {
		return "", fmt.Errorf("memory file %s not found", name)
	}

	content, err := ioutil.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("failed to read memory: %w", err)
	}

	return string(content), nil
}

// ListMemories lists all memories
func (m *Manager) ListMemories() ([]string, error) {
	files, err := ioutil.ReadDir(m.memoryDir)
	if err != nil {
		return nil, fmt.Errorf("failed to read memory directory: %w", err)
	}

	var memories []string
	for _, file := range files {
		if !file.IsDir() && strings.HasSuffix(file.Name(), ".md") {
			name := strings.TrimSuffix(file.Name(), ".md")
			memories = append(memories, name)
		}
	}

	return memories, nil
}

// DeleteMemory deletes a memory
func (m *Manager) DeleteMemory(name string) error {
	path := m.GetMemoryFilePath(name)

	if err := os.Remove(path); err != nil {
		return fmt.Errorf("failed to delete memory: %w", err)
	}

	return nil
}

// MemoryExists checks if a memory exists
func (m *Manager) MemoryExists(name string) bool {
	path := m.GetMemoryFilePath(name)
	_, err := os.Stat(path)
	return err == nil
}
