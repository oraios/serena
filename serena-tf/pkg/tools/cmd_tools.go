package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"path/filepath"
)

// ExecuteShellCommandTool executes shell commands
type ExecuteShellCommandTool struct {
	*BaseTool
}

func NewExecuteShellCommandTool() *ExecuteShellCommandTool {
	return &ExecuteShellCommandTool{
		BaseTool: NewBaseTool(
			"execute_shell_command",
			"Executes a shell command in the project directory",
			true,
			[]ToolMarker{ToolMarkerCanEdit{}},
		),
	}
}

func (t *ExecuteShellCommandTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	var p struct {
		Command        string `json:"command"`
		Cwd            string `json:"cwd"`
		CaptureStderr  bool   `json:"capture_stderr"`
		MaxAnswerChars int    `json:"max_answer_chars"`
	}
	p.CaptureStderr = true
	p.MaxAnswerChars = -1

	if err := ParseParams(params, &p); err != nil {
		return "", err
	}

	project := t.GetProject()
	if project == nil {
		return "", fmt.Errorf("no active project")
	}

	// Determine working directory
	workDir := project.GetRoot()
	if p.Cwd != "" {
		if filepath.IsAbs(p.Cwd) {
			workDir = p.Cwd
		} else {
			workDir = filepath.Join(project.GetRoot(), p.Cwd)
		}
	}

	// Execute command
	cmd := exec.CommandContext(ctx, "sh", "-c", p.Command)
	cmd.Dir = workDir

	output, err := cmd.CombinedOutput()

	result := map[string]interface{}{
		"stdout": string(output),
		"stderr": "",
	}

	if err != nil {
		result["error"] = err.Error()
		result["exit_code"] = cmd.ProcessState.ExitCode()
	} else {
		result["exit_code"] = 0
	}

	jsonResult, _ := json.Marshal(result)
	return t.LimitLength(string(jsonResult), p.MaxAnswerChars), nil
}

func (t *ExecuteShellCommandTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type: "object",
		Properties: map[string]PropertySchema{
			"command": {
				Type:        "string",
				Description: "The shell command to execute",
			},
			"cwd": {
				Type:        "string",
				Description: "Working directory (relative or absolute, defaults to project root)",
				Default:     "",
			},
			"capture_stderr": {
				Type:        "boolean",
				Description: "Whether to capture stderr output",
				Default:     true,
			},
			"max_answer_chars": {
				Type:        "integer",
				Description: "Maximum characters to return",
				Default:     -1,
			},
		},
		Required: []string{"command"},
	}
}
