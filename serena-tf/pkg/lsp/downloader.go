package lsp

import (
	"archive/zip"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
)

const (
	terraformLSVersion = "0.33.3"
	downloadBaseURL    = "https://releases.hashicorp.com/terraform-ls"
)

// TerraformLSDownloader handles downloading and managing terraform-ls
type TerraformLSDownloader struct {
	installDir string
}

// NewTerraformLSDownloader creates a new downloader
func NewTerraformLSDownloader(installDir string) *TerraformLSDownloader {
	return &TerraformLSDownloader{
		installDir: installDir,
	}
}

// GetBinaryPath returns the path to terraform-ls binary
func (d *TerraformLSDownloader) GetBinaryPath() string {
	binaryName := "terraform-ls"
	if runtime.GOOS == "windows" {
		binaryName = "terraform-ls.exe"
	}
	return filepath.Join(d.installDir, binaryName)
}

// EnsureInstalled ensures terraform-ls is installed
func (d *TerraformLSDownloader) EnsureInstalled() error {
	binaryPath := d.GetBinaryPath()

	// Check if already installed
	if _, err := os.Stat(binaryPath); err == nil {
		return nil
	}

	// Create install directory
	if err := os.MkdirAll(d.installDir, 0755); err != nil {
		return fmt.Errorf("failed to create install directory: %w", err)
	}

	// Download and install
	return d.download()
}

// download downloads and extracts terraform-ls
func (d *TerraformLSDownloader) download() error {
	// Determine platform and architecture
	platform := runtime.GOOS
	arch := runtime.GOARCH

	// Map Go arch names to HashiCorp naming
	archMap := map[string]string{
		"amd64": "amd64",
		"arm64": "arm64",
		"386":   "386",
	}

	mappedArch, ok := archMap[arch]
	if !ok {
		return fmt.Errorf("unsupported architecture: %s", arch)
	}

	// Construct download URL
	filename := fmt.Sprintf("terraform-ls_%s_%s_%s.zip", terraformLSVersion, platform, mappedArch)
	downloadURL := fmt.Sprintf("%s/%s/%s", downloadBaseURL, terraformLSVersion, filename)

	fmt.Printf("Downloading terraform-ls from %s...\n", downloadURL)

	// Download the file
	resp, err := http.Get(downloadURL)
	if err != nil {
		return fmt.Errorf("failed to download terraform-ls: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("failed to download terraform-ls: HTTP %d", resp.StatusCode)
	}

	// Create temporary file
	tmpFile, err := os.CreateTemp("", "terraform-ls-*.zip")
	if err != nil {
		return fmt.Errorf("failed to create temp file: %w", err)
	}
	defer os.Remove(tmpFile.Name())
	defer tmpFile.Close()

	// Write to temp file
	if _, err := io.Copy(tmpFile, resp.Body); err != nil {
		return fmt.Errorf("failed to write temp file: %w", err)
	}

	// Close before extracting
	tmpFile.Close()

	// Extract the zip file
	if err := d.extractZip(tmpFile.Name(), d.installDir); err != nil {
		return fmt.Errorf("failed to extract terraform-ls: %w", err)
	}

	// Make executable on Unix-like systems
	if runtime.GOOS != "windows" {
		binaryPath := d.GetBinaryPath()
		if err := os.Chmod(binaryPath, 0755); err != nil {
			return fmt.Errorf("failed to make terraform-ls executable: %w", err)
		}
	}

	fmt.Println("terraform-ls installed successfully")

	return nil
}

// extractZip extracts a zip file to a destination directory
func (d *TerraformLSDownloader) extractZip(zipPath, destDir string) error {
	r, err := zip.OpenReader(zipPath)
	if err != nil {
		return err
	}
	defer r.Close()

	for _, f := range r.File {
		targetPath := filepath.Join(destDir, f.Name)

		if f.FileInfo().IsDir() {
			if err := os.MkdirAll(targetPath, f.Mode()); err != nil {
				return err
			}
			continue
		}

		// Create parent directories
		if err := os.MkdirAll(filepath.Dir(targetPath), 0755); err != nil {
			return err
		}

		// Extract file
		outFile, err := os.OpenFile(targetPath, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, f.Mode())
		if err != nil {
			return err
		}

		rc, err := f.Open()
		if err != nil {
			outFile.Close()
			return err
		}

		if _, err := io.Copy(outFile, rc); err != nil {
			rc.Close()
			outFile.Close()
			return err
		}

		rc.Close()
		outFile.Close()
	}

	return nil
}

// CheckTerraformCLI checks if terraform CLI is installed
func CheckTerraformCLI() error {
	_, err := exec.LookPath("terraform")
	if err != nil {
		return fmt.Errorf("terraform CLI not found in PATH: %w", err)
	}
	return nil
}
