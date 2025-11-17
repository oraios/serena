package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"path/filepath"

	"github.com/TahirRiaz/serena-tf/pkg/util"
)

// WriteMemoryTool writes a memory
type WriteMemoryTool struct {
	*BaseTool
}

func NewWriteMemoryTool() *WriteMemoryTool {
	return &WriteMemoryTool{
		BaseTool: NewBaseTool(
			"write_memory",
			"Writes a named memory to the project-specific memory store",
			true,
			nil,
		),
	}
}

func (t *WriteMemoryTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	var p struct {
		MemoryFileName string `json:"memory_file_name"`
		Content        string `json:"content"`
		MaxAnswerChars int    `json:"max_answer_chars"`
	}
	p.MaxAnswerChars = -1

	if err := ParseParams(params, &p); err != nil {
		return "", err
	}

	if p.MaxAnswerChars == -1 {
		p.MaxAnswerChars = 100000
	}

	if len(p.Content) > p.MaxAnswerChars {
		return "", fmt.Errorf("content is too long (%d characters, max %d)", len(p.Content), p.MaxAnswerChars)
	}

	memoryMgr := t.GetAgent().GetMemoryManager()
	if memoryMgr == nil {
		return "", fmt.Errorf("memory manager not available")
	}

	if err := memoryMgr.SaveMemory(p.MemoryFileName, p.Content); err != nil {
		return "", err
	}

	return fmt.Sprintf("Memory %s written successfully", p.MemoryFileName), nil
}

func (t *WriteMemoryTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type: "object",
		Properties: map[string]PropertySchema{
			"memory_file_name": {
				Type:        "string",
				Description: "The name of the memory file (meaningful name in markdown format)",
			},
			"content": {
				Type:        "string",
				Description: "The content to store in the memory",
			},
			"max_answer_chars": {
				Type:        "integer",
				Description: "Maximum allowed content length",
				Default:     -1,
			},
		},
		Required: []string{"memory_file_name", "content"},
	}
}

// ReadMemoryTool reads a memory
type ReadMemoryTool struct {
	*BaseTool
}

func NewReadMemoryTool() *ReadMemoryTool {
	return &ReadMemoryTool{
		BaseTool: NewBaseTool(
			"read_memory",
			"Reads a memory from the project-specific memory store",
			true,
			nil,
		),
	}
}

func (t *ReadMemoryTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	var p struct {
		MemoryFileName string `json:"memory_file_name"`
	}

	if err := ParseParams(params, &p); err != nil {
		return "", err
	}

	memoryMgr := t.GetAgent().GetMemoryManager()
	if memoryMgr == nil {
		return "", fmt.Errorf("memory manager not available")
	}

	content, err := memoryMgr.LoadMemory(p.MemoryFileName)
	if err != nil {
		return fmt.Sprintf("Memory file %s not found. Consider creating it with write_memory if needed.", p.MemoryFileName), nil
	}

	return content, nil
}

func (t *ReadMemoryTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type: "object",
		Properties: map[string]PropertySchema{
			"memory_file_name": {
				Type:        "string",
				Description: "The name of the memory file to read",
			},
		},
		Required: []string{"memory_file_name"},
	}
}

// ListMemoriesTool lists all memories
type ListMemoriesTool struct {
	*BaseTool
}

func NewListMemoriesTool() *ListMemoriesTool {
	return &ListMemoriesTool{
		BaseTool: NewBaseTool(
			"list_memories",
			"Lists all memories in the project-specific memory store",
			true,
			nil,
		),
	}
}

func (t *ListMemoriesTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	memoryMgr := t.GetAgent().GetMemoryManager()
	if memoryMgr == nil {
		return "", fmt.Errorf("memory manager not available")
	}

	memories, err := memoryMgr.ListMemories()
	if err != nil {
		return "", err
	}

	result, _ := json.Marshal(memories)
	return string(result), nil
}

func (t *ListMemoriesTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type:       "object",
		Properties: map[string]PropertySchema{},
		Required:   []string{},
	}
}

// DeleteMemoryTool deletes a memory
type DeleteMemoryTool struct {
	*BaseTool
}

func NewDeleteMemoryTool() *DeleteMemoryTool {
	return &DeleteMemoryTool{
		BaseTool: NewBaseTool(
			"delete_memory",
			"Deletes a memory from the project-specific memory store",
			true,
			nil,
		),
	}
}

func (t *DeleteMemoryTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	var p struct {
		MemoryFileName string `json:"memory_file_name"`
	}

	if err := ParseParams(params, &p); err != nil {
		return "", err
	}

	memoryMgr := t.GetAgent().GetMemoryManager()
	if memoryMgr == nil {
		return "", fmt.Errorf("memory manager not available")
	}

	if err := memoryMgr.DeleteMemory(p.MemoryFileName); err != nil {
		return "", err
	}

	return fmt.Sprintf("Memory %s deleted successfully", p.MemoryFileName), nil
}

func (t *DeleteMemoryTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type: "object",
		Properties: map[string]PropertySchema{
			"memory_file_name": {
				Type:        "string",
				Description: "The name of the memory file to delete",
			},
		},
		Required: []string{"memory_file_name"},
	}
}

// EditMemoryTool edits a memory using regex
type EditMemoryTool struct {
	*BaseTool
}

func NewEditMemoryTool() *EditMemoryTool {
	return &EditMemoryTool{
		BaseTool: NewBaseTool(
			"edit_memory",
			"Edits a memory using regular expression replacement",
			true,
			nil,
		),
	}
}

func (t *EditMemoryTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	var p struct {
		MemoryFileName string `json:"memory_file_name"`
		Regex          string `json:"regex"`
		Repl           string `json:"repl"`
	}

	if err := ParseParams(params, &p); err != nil {
		return "", err
	}

	memoryMgr := t.GetAgent().GetMemoryManager()
	if memoryMgr == nil {
		return "", fmt.Errorf("memory manager not available")
	}

	// Get memory file path
	project := t.GetProject()
	if project == nil {
		return "", fmt.Errorf("no active project")
	}

	memoryPath := filepath.Join(project.GetRoot(), ".serena-tf", "memories", p.MemoryFileName+".md")

	// Use ReplaceInFile utility
	count, err := util.ReplaceInFile(memoryPath, p.Regex, p.Repl, false)
	if err != nil {
		return "", err
	}

	return fmt.Sprintf("Successfully replaced %d occurrence(s) in memory %s", count, p.MemoryFileName), nil
}

func (t *EditMemoryTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type: "object",
		Properties: map[string]PropertySchema{
			"memory_file_name": {
				Type:        "string",
				Description: "The name of the memory file to edit",
			},
			"regex": {
				Type:        "string",
				Description: "Python-style regular expression to match",
			},
			"repl": {
				Type:        "string",
				Description: "Replacement string (may contain backreferences)",
			},
		},
		Required: []string{"memory_file_name", "regex", "repl"},
	}
}
