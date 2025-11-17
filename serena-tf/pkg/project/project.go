package project

import (
	"fmt"
	"path/filepath"
	"strings"

	"github.com/TahirRiaz/serena-tf/pkg/cache"
	"github.com/TahirRiaz/serena-tf/pkg/editor"
	"github.com/TahirRiaz/serena-tf/pkg/lsp"
	"github.com/TahirRiaz/serena-tf/pkg/memory"
	"github.com/TahirRiaz/serena-tf/pkg/util"
	"github.com/go-git/go-git/v5/plumbing/format/gitignore"
)

// Project represents a Terraform project
type Project struct {
	root            string
	config          *Config
	terraformLS     *lsp.TerraformLS
	symbolRetriever *lsp.SymbolRetriever
	symbolCache     *cache.SymbolCache
	memoryManager   *memory.Manager
	codeEditor      *editor.CodeEditor
	gitignore       gitignore.Matcher
}

// NewProject creates a new project
func NewProject(rootPath string) (*Project, error) {
	// Validate root path
	absRoot, err := filepath.Abs(rootPath)
	if err != nil {
		return nil, fmt.Errorf("failed to resolve project root: %w", err)
	}

	if !util.IsDirectory(absRoot) {
		return nil, fmt.Errorf("project root is not a directory: %s", absRoot)
	}

	// Load project config
	config, err := LoadConfig(absRoot)
	if err != nil {
		// Create default config if not found
		config = NewDefaultConfig()
	}

	// Initialize Terraform LS
	terraformLS, err := lsp.NewTerraformLS(absRoot)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize Terraform LS: %w", err)
	}

	if err := terraformLS.Start(); err != nil {
		return nil, fmt.Errorf("failed to start Terraform LS: %w", err)
	}

	// Initialize symbol cache
	symbolCache, err := cache.NewSymbolCache(absRoot)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize symbol cache: %w", err)
	}

	// Initialize symbol retriever
	symbolRetriever := lsp.NewSymbolRetriever(terraformLS, absRoot, symbolCache)

	// Initialize code editor
	codeEditor := editor.NewCodeEditor(absRoot, symbolRetriever, terraformLS)

	// Initialize memory manager
	memoryManager, err := memory.NewManager(absRoot)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize memory manager: %w", err)
	}

	// Load gitignore
	gitignoreMatcher, err := util.LoadGitignore(absRoot)
	if err != nil {
		// Use empty matcher if gitignore not found
		gitignoreMatcher = gitignore.NewMatcher([]gitignore.Pattern{})
	}

	return &Project{
		root:            absRoot,
		config:          config,
		terraformLS:     terraformLS,
		symbolRetriever: symbolRetriever,
		symbolCache:     symbolCache,
		memoryManager:   memoryManager,
		codeEditor:      codeEditor,
		gitignore:       gitignoreMatcher,
	}, nil
}

// GetRoot returns the project root
func (p *Project) GetRoot() string {
	return p.root
}

// GetConfig returns the project configuration
func (p *Project) GetConfig() *Config {
	return p.config
}

// GetTerraformLS returns the Terraform language server
func (p *Project) GetTerraformLS() *lsp.TerraformLS {
	return p.terraformLS
}

// GetSymbolRetriever returns the symbol retriever
func (p *Project) GetSymbolRetriever() *lsp.SymbolRetriever {
	return p.symbolRetriever
}

// GetMemoryManager returns the memory manager
func (p *Project) GetMemoryManager() *memory.Manager {
	return p.memoryManager
}

// GetCodeEditor returns the code editor
func (p *Project) GetCodeEditor() *editor.CodeEditor {
	return p.codeEditor
}

// ReadFile reads a file from the project
func (p *Project) ReadFile(relativePath string) (string, error) {
	fullPath := filepath.Join(p.root, relativePath)
	return util.ReadFile(fullPath)
}

// WriteFile writes a file to the project
func (p *Project) WriteFile(relativePath string, content string) error {
	fullPath := filepath.Join(p.root, relativePath)
	return util.WriteFile(fullPath, content)
}

// ValidatePath validates a path within the project
func (p *Project) ValidatePath(relativePath string, requireNotIgnored bool) error {
	fullPath := filepath.Join(p.root, relativePath)

	// Check if path is within project root
	if !filepath.HasPrefix(fullPath, p.root) {
		return fmt.Errorf("path is outside project root: %s", relativePath)
	}

	// Check if path exists
	if !util.FileExists(fullPath) {
		return fmt.Errorf("path does not exist: %s", relativePath)
	}

	// Check if ignored
	if requireNotIgnored && p.IsIgnoredPath(fullPath) {
		return fmt.Errorf("path is ignored: %s", relativePath)
	}

	return nil
}

// IsIgnoredPath checks if a path should be ignored
func (p *Project) IsIgnoredPath(path string) bool {
	// Check Terraform-specific ignores
	if p.terraformLS.IsIgnoredPath(path) {
		return true
	}

	// Check gitignore
	relPath, err := filepath.Rel(p.root, path)
	if err != nil {
		return false
	}

	// Split path into components for gitignore matching
	isDir := util.IsDirectory(path)
	return p.gitignore.Match(strings.Split(relPath, string(filepath.Separator)), isDir)
}

// PathExists checks if a path exists
func (p *Project) PathExists(relativePath string) bool {
	fullPath := filepath.Join(p.root, relativePath)
	return util.FileExists(fullPath)
}

// Close closes the project and cleans up resources
func (p *Project) Close() error {
	if p.terraformLS != nil {
		return p.terraformLS.Close()
	}
	return nil
}
