package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"

	"github.com/TahirRiaz/serena-tf/pkg/agent"
	"github.com/TahirRiaz/serena-tf/pkg/mcp"
	"github.com/spf13/cobra"
)

var (
	projectPath string
	contextName string
	modeNames   string
	configDir   string
)

func main() {
	var rootCmd = &cobra.Command{
		Use:   "serena-tf",
		Short: "Serena-TF: Terraform Language Server MCP Server",
		Long: `Serena-TF is a comprehensive Terraform coding assistant that exposes
Terraform Language Server capabilities via the Model Context Protocol (MCP).

It provides symbol-based navigation, editing, memory management, and more
specifically optimized for Terraform infrastructure as code.`,
		Run: runMCPServer,
	}

	// Get default config directory
	homeDir, err := os.UserHomeDir()
	if err != nil {
		log.Fatal(err)
	}
	defaultConfigDir := filepath.Join(homeDir, ".serena-tf")

	// Check if configs directory exists in current directory (for embedded configs)
	if _, err := os.Stat("configs"); err == nil {
		wd, _ := os.Getwd()
		defaultConfigDir = filepath.Join(wd, "configs")
	}

	rootCmd.Flags().StringVarP(&projectPath, "project", "p", ".", "Path to the Terraform project")
	rootCmd.Flags().StringVarP(&contextName, "context", "c", "agent", "Context name (agent, ide-assistant, desktop-app)")
	rootCmd.Flags().StringVarP(&modeNames, "modes", "m", "interactive", "Comma-separated mode names (planning, editing, interactive, one-shot)")
	rootCmd.Flags().StringVarP(&configDir, "config-dir", "d", defaultConfigDir, "Configuration directory")

	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func runMCPServer(cmd *cobra.Command, args []string) {
	// Parse mode names
	modes := strings.Split(modeNames, ",")
	for i, mode := range modes {
		modes[i] = strings.TrimSpace(mode)
	}

	// Create agent
	log.Printf("Initializing Serena-TF agent...")
	log.Printf("Project path: %s", projectPath)
	log.Printf("Context: %s", contextName)
	log.Printf("Modes: %v", modes)
	log.Printf("Config directory: %s", configDir)

	ag, err := agent.NewAgent(projectPath, contextName, modes, configDir)
	if err != nil {
		log.Fatalf("Failed to create agent: %v", err)
	}
	defer ag.Close()

	log.Printf("Agent initialized successfully")
	log.Printf("Active tools: %d", len(ag.GetTools()))

	// Create MCP server
	server := mcp.NewServer(ag)

	// Start server
	log.Println("Starting MCP server...")
	ctx := context.Background()
	if err := server.Start(ctx); err != nil {
		log.Fatalf("MCP server error: %v", err)
	}
}
