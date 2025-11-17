package tools

import (
	"context"
	"fmt"
)

// DeleteLinesTool deletes a range of lines
type DeleteLinesTool struct {
	*BaseTool
}

func NewDeleteLinesTool() *DeleteLinesTool {
	return &DeleteLinesTool{
		BaseTool: NewBaseTool(
			"delete_lines",
			"Deletes a range of lines within a file",
			true,
			[]ToolMarker{ToolMarkerCanEdit{}, ToolMarkerOptional{}},
		),
	}
}

func (t *DeleteLinesTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	var p struct {
		RelativePath string `json:"relative_path"`
		StartLine    int    `json:"start_line"`
		EndLine      int    `json:"end_line"`
	}

	if err := ParseParams(params, &p); err != nil {
		return "", err
	}

	project := t.GetProject()
	if project == nil {
		return "", fmt.Errorf("no active project")
	}

	if err := project.ValidatePath(p.RelativePath, true); err != nil {
		return "", err
	}

	codeEditor := t.getCodeEditor()
	if codeEditor == nil {
		return "", fmt.Errorf("code editor not available")
	}

	if err := codeEditor.DeleteLines(p.RelativePath, p.StartLine, p.EndLine); err != nil {
		return "", err
	}

	return SuccessResult, nil
}

func (t *DeleteLinesTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type: "object",
		Properties: map[string]PropertySchema{
			"relative_path": {
				Type:        "string",
				Description: "The relative path to the file",
			},
			"start_line": {
				Type:        "integer",
				Description: "The 0-based index of the first line to delete",
			},
			"end_line": {
				Type:        "integer",
				Description: "The 0-based index of the last line to delete (inclusive)",
			},
		},
		Required: []string{"relative_path", "start_line", "end_line"},
	}
}

// ReplaceLinesTool replaces a range of lines
type ReplaceLinesTool struct {
	*BaseTool
}

func NewReplaceLinesTool() *ReplaceLinesTool {
	return &ReplaceLinesTool{
		BaseTool: NewBaseTool(
			"replace_lines",
			"Replaces a range of lines within a file with new content",
			true,
			[]ToolMarker{ToolMarkerCanEdit{}, ToolMarkerOptional{}},
		),
	}
}

func (t *ReplaceLinesTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	var p struct {
		RelativePath string `json:"relative_path"`
		StartLine    int    `json:"start_line"`
		EndLine      int    `json:"end_line"`
		Content      string `json:"content"`
	}

	if err := ParseParams(params, &p); err != nil {
		return "", err
	}

	project := t.GetProject()
	if project == nil {
		return "", fmt.Errorf("no active project")
	}

	if err := project.ValidatePath(p.RelativePath, true); err != nil {
		return "", err
	}

	codeEditor := t.getCodeEditor()
	if codeEditor == nil {
		return "", fmt.Errorf("code editor not available")
	}

	if err := codeEditor.ReplaceLines(p.RelativePath, p.StartLine, p.EndLine, p.Content); err != nil {
		return "", err
	}

	return SuccessResult, nil
}

func (t *ReplaceLinesTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type: "object",
		Properties: map[string]PropertySchema{
			"relative_path": {
				Type:        "string",
				Description: "The relative path to the file",
			},
			"start_line": {
				Type:        "integer",
				Description: "The 0-based index of the first line to replace",
			},
			"end_line": {
				Type:        "integer",
				Description: "The 0-based index of the last line to replace (inclusive)",
			},
			"content": {
				Type:        "string",
				Description: "The new content to replace the lines with",
			},
		},
		Required: []string{"relative_path", "start_line", "end_line", "content"},
	}
}

// InsertAtLineTool inserts content at a specific line
type InsertAtLineTool struct {
	*BaseTool
}

func NewInsertAtLineTool() *InsertAtLineTool {
	return &InsertAtLineTool{
		BaseTool: NewBaseTool(
			"insert_at_line",
			"Inserts content at a specific line in a file",
			true,
			[]ToolMarker{ToolMarkerCanEdit{}, ToolMarkerOptional{}},
		),
	}
}

func (t *InsertAtLineTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	var p struct {
		RelativePath string `json:"relative_path"`
		Line         int    `json:"line"`
		Content      string `json:"content"`
	}

	if err := ParseParams(params, &p); err != nil {
		return "", err
	}

	project := t.GetProject()
	if project == nil {
		return "", fmt.Errorf("no active project")
	}

	if err := project.ValidatePath(p.RelativePath, true); err != nil {
		return "", err
	}

	codeEditor := t.getCodeEditor()
	if codeEditor == nil {
		return "", fmt.Errorf("code editor not available")
	}

	if err := codeEditor.InsertAtLine(p.RelativePath, p.Line, p.Content); err != nil {
		return "", err
	}

	return SuccessResult, nil
}

func (t *InsertAtLineTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type: "object",
		Properties: map[string]PropertySchema{
			"relative_path": {
				Type:        "string",
				Description: "The relative path to the file",
			},
			"line": {
				Type:        "integer",
				Description: "The 0-based index of the line at which to insert content",
			},
			"content": {
				Type:        "string",
				Description: "The content to insert",
			},
		},
		Required: []string{"relative_path", "line", "content"},
	}
}

// Helper interface to access code editor
type lineEditorProvider interface {
	GetCodeEditor() lineEditor
}

type lineEditor interface {
	DeleteLines(relativePath string, startLine, endLine int) error
	ReplaceLines(relativePath string, startLine, endLine int, content string) error
	InsertAtLine(relativePath string, line int, content string) error
}

func (t *DeleteLinesTool) getCodeEditor() lineEditor {
	if provider, ok := t.GetProject().(lineEditorProvider); ok {
		return provider.GetCodeEditor()
	}
	return nil
}

func (t *ReplaceLinesTool) getCodeEditor() lineEditor {
	if provider, ok := t.GetProject().(lineEditorProvider); ok {
		return provider.GetCodeEditor()
	}
	return nil
}

func (t *InsertAtLineTool) getCodeEditor() lineEditor {
	if provider, ok := t.GetProject().(lineEditorProvider); ok {
		return provider.GetCodeEditor()
	}
	return nil
}
