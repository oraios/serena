package tools

import (
	"context"
	"fmt"
)

// ReplaceSymbolBodyTool replaces the full definition of a symbol
type ReplaceSymbolBodyTool struct {
	*BaseTool
}

func NewReplaceSymbolBodyTool() *ReplaceSymbolBodyTool {
	return &ReplaceSymbolBodyTool{
		BaseTool: NewBaseTool(
			"replace_symbol_body",
			"Replaces the full definition of a symbol",
			true,
			[]ToolMarker{ToolMarkerSymbolicEdit{}},
		),
	}
}

func (t *ReplaceSymbolBodyTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	var p struct {
		NamePath     string `json:"name_path"`
		RelativePath string `json:"relative_path"`
		Body         string `json:"body"`
	}

	if err := ParseParams(params, &p); err != nil {
		return "", err
	}

	project := t.GetProject()
	if project == nil {
		return "", fmt.Errorf("no active project")
	}

	// Get code editor through interface
	codeEditor := t.getCodeEditor()
	if codeEditor == nil {
		return "", fmt.Errorf("code editor not available")
	}

	if err := codeEditor.ReplaceSymbolBody(p.NamePath, p.RelativePath, p.Body); err != nil {
		return "", err
	}

	return SuccessResult, nil
}

func (t *ReplaceSymbolBodyTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type: "object",
		Properties: map[string]PropertySchema{
			"name_path": {
				Type:        "string",
				Description: "The name path of the symbol to replace (e.g., 'resource/aws_instance')",
			},
			"relative_path": {
				Type:        "string",
				Description: "The relative path to the file containing the symbol",
			},
			"body": {
				Type:        "string",
				Description: "The new body for the symbol (including signature/definition)",
			},
		},
		Required: []string{"name_path", "relative_path", "body"},
	}
}

// InsertAfterSymbolTool inserts content after a symbol
type InsertAfterSymbolTool struct {
	*BaseTool
}

func NewInsertAfterSymbolTool() *InsertAfterSymbolTool {
	return &InsertAfterSymbolTool{
		BaseTool: NewBaseTool(
			"insert_after_symbol",
			"Inserts content after the end of a symbol definition",
			true,
			[]ToolMarker{ToolMarkerSymbolicEdit{}},
		),
	}
}

func (t *InsertAfterSymbolTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	var p struct {
		NamePath     string `json:"name_path"`
		RelativePath string `json:"relative_path"`
		Body         string `json:"body"`
	}

	if err := ParseParams(params, &p); err != nil {
		return "", err
	}

	project := t.GetProject()
	if project == nil {
		return "", fmt.Errorf("no active project")
	}

	codeEditor := t.getCodeEditor()
	if codeEditor == nil {
		return "", fmt.Errorf("code editor not available")
	}

	if err := codeEditor.InsertAfterSymbol(p.NamePath, p.RelativePath, p.Body); err != nil {
		return "", err
	}

	return SuccessResult, nil
}

func (t *InsertAfterSymbolTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type: "object",
		Properties: map[string]PropertySchema{
			"name_path": {
				Type:        "string",
				Description: "The name path of the symbol after which to insert content",
			},
			"relative_path": {
				Type:        "string",
				Description: "The relative path to the file containing the symbol",
			},
			"body": {
				Type:        "string",
				Description: "The content to insert after the symbol",
			},
		},
		Required: []string{"name_path", "relative_path", "body"},
	}
}

// InsertBeforeSymbolTool inserts content before a symbol
type InsertBeforeSymbolTool struct {
	*BaseTool
}

func NewInsertBeforeSymbolTool() *InsertBeforeSymbolTool {
	return &InsertBeforeSymbolTool{
		BaseTool: NewBaseTool(
			"insert_before_symbol",
			"Inserts content before the beginning of a symbol definition",
			true,
			[]ToolMarker{ToolMarkerSymbolicEdit{}},
		),
	}
}

func (t *InsertBeforeSymbolTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	var p struct {
		NamePath     string `json:"name_path"`
		RelativePath string `json:"relative_path"`
		Body         string `json:"body"`
	}

	if err := ParseParams(params, &p); err != nil {
		return "", err
	}

	project := t.GetProject()
	if project == nil {
		return "", fmt.Errorf("no active project")
	}

	codeEditor := t.getCodeEditor()
	if codeEditor == nil {
		return "", fmt.Errorf("code editor not available")
	}

	if err := codeEditor.InsertBeforeSymbol(p.NamePath, p.RelativePath, p.Body); err != nil {
		return "", err
	}

	return SuccessResult, nil
}

func (t *InsertBeforeSymbolTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type: "object",
		Properties: map[string]PropertySchema{
			"name_path": {
				Type:        "string",
				Description: "The name path of the symbol before which to insert content",
			},
			"relative_path": {
				Type:        "string",
				Description: "The relative path to the file containing the symbol",
			},
			"body": {
				Type:        "string",
				Description: "The content to insert before the symbol",
			},
		},
		Required: []string{"name_path", "relative_path", "body"},
	}
}

// RenameSymbolTool renames a symbol using LSP
type RenameSymbolTool struct {
	*BaseTool
}

func NewRenameSymbolTool() *RenameSymbolTool {
	return &RenameSymbolTool{
		BaseTool: NewBaseTool(
			"rename_symbol",
			"Renames a symbol throughout the codebase using LSP refactoring",
			true,
			[]ToolMarker{ToolMarkerSymbolicEdit{}},
		),
	}
}

func (t *RenameSymbolTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	var p struct {
		NamePath     string `json:"name_path"`
		RelativePath string `json:"relative_path"`
		NewName      string `json:"new_name"`
	}

	if err := ParseParams(params, &p); err != nil {
		return "", err
	}

	project := t.GetProject()
	if project == nil {
		return "", fmt.Errorf("no active project")
	}

	codeEditor := t.getCodeEditor()
	if codeEditor == nil {
		return "", fmt.Errorf("code editor not available")
	}

	result, err := codeEditor.RenameSymbol(p.NamePath, p.RelativePath, p.NewName)
	if err != nil {
		return "", err
	}

	return result, nil
}

func (t *RenameSymbolTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type: "object",
		Properties: map[string]PropertySchema{
			"name_path": {
				Type:        "string",
				Description: "The name path of the symbol to rename",
			},
			"relative_path": {
				Type:        "string",
				Description: "The relative path to the file containing the symbol",
			},
			"new_name": {
				Type:        "string",
				Description: "The new name for the symbol",
			},
		},
		Required: []string{"name_path", "relative_path", "new_name"},
	}
}

// RestartLanguageServerTool restarts the Terraform language server
type RestartLanguageServerTool struct {
	*BaseTool
}

func NewRestartLanguageServerTool() *RestartLanguageServerTool {
	return &RestartLanguageServerTool{
		BaseTool: NewBaseTool(
			"restart_language_server",
			"Restarts the Terraform language server (use only when it hangs)",
			true,
			[]ToolMarker{ToolMarkerOptional{}},
		),
	}
}

func (t *RestartLanguageServerTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	// This would need agent-level support to restart the LS
	// For now, return a message
	return "Language server restart requested. Please restart the MCP server to reinitialize the language server.", nil
}

func (t *RestartLanguageServerTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type:       "object",
		Properties: map[string]PropertySchema{},
		Required:   []string{},
	}
}

// Helper to get code editor from project through interface
type codeEditorProvider interface {
	GetCodeEditor() codeEditor
}

type codeEditor interface {
	ReplaceSymbolBody(namePath, relativePath, body string) error
	InsertAfterSymbol(namePath, relativePath, content string) error
	InsertBeforeSymbol(namePath, relativePath, content string) error
	RenameSymbol(namePath, relativePath, newName string) (string, error)
}

func (t *ReplaceSymbolBodyTool) getCodeEditor() codeEditor {
	if provider, ok := t.GetProject().(codeEditorProvider); ok {
		return provider.GetCodeEditor()
	}
	return nil
}

func (t *InsertAfterSymbolTool) getCodeEditor() codeEditor {
	if provider, ok := t.GetProject().(codeEditorProvider); ok {
		return provider.GetCodeEditor()
	}
	return nil
}

func (t *InsertBeforeSymbolTool) getCodeEditor() codeEditor {
	if provider, ok := t.GetProject().(codeEditorProvider); ok {
		return provider.GetCodeEditor()
	}
	return nil
}

func (t *RenameSymbolTool) getCodeEditor() codeEditor {
	if provider, ok := t.GetProject().(codeEditorProvider); ok {
		return provider.GetCodeEditor()
	}
	return nil
}
