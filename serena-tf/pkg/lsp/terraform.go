package lsp

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// TerraformLS represents a Terraform language server
type TerraformLS struct {
	client     *Client
	rootPath   string
	installDir string
	downloader *TerraformLSDownloader
}

// NewTerraformLS creates a new Terraform language server
func NewTerraformLS(rootPath string) (*TerraformLS, error) {
	// Get home directory
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return nil, fmt.Errorf("failed to get home directory: %w", err)
	}

	installDir := filepath.Join(homeDir, ".serena-tf", "ls_resources", "TerraformLS")

	downloader := NewTerraformLSDownloader(installDir)

	// Ensure terraform CLI is installed
	if err := CheckTerraformCLI(); err != nil {
		return nil, fmt.Errorf("terraform CLI is required: %w", err)
	}

	// Ensure terraform-ls is installed
	if err := downloader.EnsureInstalled(); err != nil {
		return nil, fmt.Errorf("failed to ensure terraform-ls is installed: %w", err)
	}

	return &TerraformLS{
		rootPath:   rootPath,
		installDir: installDir,
		downloader: downloader,
	}, nil
}

// Start starts the Terraform language server
func (t *TerraformLS) Start() error {
	binaryPath := t.downloader.GetBinaryPath()

	// Convert path to URI
	rootURI := pathToURI(t.rootPath)

	// Create client
	client, err := NewClient(binaryPath, []string{"serve"}, rootURI)
	if err != nil {
		return fmt.Errorf("failed to create LSP client: %w", err)
	}

	// Start the client
	if err := client.Start(); err != nil {
		return fmt.Errorf("failed to start LSP client: %w", err)
	}

	// Initialize
	result, err := client.Initialize()
	if err != nil {
		client.Close()
		return fmt.Errorf("failed to initialize LSP client: %w", err)
	}

	// Verify capabilities
	if result.Capabilities.DocumentSymbolProvider == nil {
		client.Close()
		return fmt.Errorf("terraform-ls does not support document symbols")
	}

	t.client = client

	return nil
}

// GetClient returns the LSP client
func (t *TerraformLS) GetClient() *Client {
	return t.client
}

// Close closes the Terraform language server
func (t *TerraformLS) Close() error {
	if t.client != nil {
		return t.client.Close()
	}
	return nil
}

// IsIgnoredPath checks if a path should be ignored for Terraform
func (t *TerraformLS) IsIgnoredPath(path string) bool {
	// Get the base name
	base := filepath.Base(path)

	// Terraform-specific ignore patterns
	ignoredDirs := []string{
		".terraform",
		"terraform.tfstate.d",
	}

	for _, ignored := range ignoredDirs {
		if base == ignored {
			return true
		}
	}

	// Check if it's a state file or backup
	if strings.HasSuffix(base, ".tfstate") ||
		strings.HasSuffix(base, ".tfstate.backup") ||
		strings.HasPrefix(base, ".terraform.") {
		return true
	}

	return false
}

// IsTerraformFile checks if a file is a Terraform file
func IsTerraformFile(path string) bool {
	ext := filepath.Ext(path)
	return ext == ".tf" || ext == ".tfvars"
}

// pathToURI converts a file path to a URI
func pathToURI(path string) string {
	// Convert to absolute path
	absPath, err := filepath.Abs(path)
	if err != nil {
		absPath = path
	}

	// Convert to URI format
	// On Windows, paths need special handling
	if strings.Contains(absPath, "\\") {
		absPath = strings.ReplaceAll(absPath, "\\", "/")
	}

	if !strings.HasPrefix(absPath, "/") {
		absPath = "/" + absPath
	}

	return "file://" + absPath
}

// uriToPath converts a URI to a file path
func URIToPath(uri string) string {
	path := strings.TrimPrefix(uri, "file://")

	// On Windows, remove leading slash if present
	if len(path) > 2 && path[0] == '/' && path[2] == ':' {
		path = path[1:]
	}

	// Convert back to OS-specific path separators
	return filepath.FromSlash(path)
}
