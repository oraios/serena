package tools

import (
	"context"
	"encoding/json"
)

// GetCurrentConfigTool gets the current configuration
type GetCurrentConfigTool struct {
	*BaseTool
}

func NewGetCurrentConfigTool() *GetCurrentConfigTool {
	return &GetCurrentConfigTool{
		BaseTool: NewBaseTool(
			"get_current_config",
			"Gets the current configuration and active project information",
			false,
			nil,
		),
	}
}

func (t *GetCurrentConfigTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	project := t.GetProject()

	config := map[string]interface{}{
		"has_active_project": project != nil,
	}

	if project != nil {
		config["project_root"] = project.GetRoot()
	}

	result, _ := json.Marshal(config)
	return string(result), nil
}

func (t *GetCurrentConfigTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type:       "object",
		Properties: map[string]PropertySchema{},
		Required:   []string{},
	}
}
