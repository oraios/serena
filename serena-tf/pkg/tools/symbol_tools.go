package tools

import (
	"context"
	"encoding/json"
	"fmt"
)

// GetSymbolsOverviewTool gets top-level symbols in a file
type GetSymbolsOverviewTool struct {
	*BaseTool
}

func NewGetSymbolsOverviewTool() *GetSymbolsOverviewTool {
	return &GetSymbolsOverviewTool{
		BaseTool: NewBaseTool(
			"get_symbols_overview",
			"Gets an overview of top-level symbols in a file",
			true,
			[]ToolMarker{ToolMarkerSymbolicRead{}},
		),
	}
}

func (t *GetSymbolsOverviewTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	var p struct {
		RelativePath   string `json:"relative_path"`
		MaxAnswerChars int    `json:"max_answer_chars"`
	}
	p.MaxAnswerChars = -1

	if err := ParseParams(params, &p); err != nil {
		return "", err
	}

	symbolRetriever := t.GetAgent().GetSymbolRetriever()
	if symbolRetriever == nil {
		return "", fmt.Errorf("symbol retriever not available")
	}

	symbols, err := symbolRetriever.GetDocumentSymbols(p.RelativePath)
	if err != nil {
		return "", err
	}

	result, _ := json.Marshal(symbols)
	return t.LimitLength(string(result), p.MaxAnswerChars), nil
}

func (t *GetSymbolsOverviewTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type: "object",
		Properties: map[string]PropertySchema{
			"relative_path": {
				Type:        "string",
				Description: "The relative path to the file",
			},
			"max_answer_chars": {
				Type:        "integer",
				Description: "Maximum characters to return",
				Default:     -1,
			},
		},
		Required: []string{"relative_path"},
	}
}

// FindSymbolTool finds symbols by name pattern
type FindSymbolTool struct {
	*BaseTool
}

func NewFindSymbolTool() *FindSymbolTool {
	return &FindSymbolTool{
		BaseTool: NewBaseTool(
			"find_symbol",
			"Performs a search for symbols with/containing a given name pattern",
			true,
			[]ToolMarker{ToolMarkerSymbolicRead{}},
		),
	}
}

func (t *FindSymbolTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	var p struct {
		NamePath          string `json:"name_path"`
		RelativePath      string `json:"relative_path"`
		SubstringMatching bool   `json:"substring_matching"`
		IncludeKinds      []int  `json:"include_kinds"`
		ExcludeKinds      []int  `json:"exclude_kinds"`
		MaxAnswerChars    int    `json:"max_answer_chars"`
	}
	p.MaxAnswerChars = -1

	if err := ParseParams(params, &p); err != nil {
		return "", err
	}

	symbolRetriever := t.GetAgent().GetSymbolRetriever()
	if symbolRetriever == nil {
		return "", fmt.Errorf("symbol retriever not available")
	}

	symbols, err := symbolRetriever.FindSymbolsByName(
		p.NamePath,
		p.RelativePath,
		p.SubstringMatching,
		p.IncludeKinds,
		p.ExcludeKinds,
	)

	if err != nil {
		return "", err
	}

	result, _ := json.Marshal(symbols)
	return t.LimitLength(string(result), p.MaxAnswerChars), nil
}

func (t *FindSymbolTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type: "object",
		Properties: map[string]PropertySchema{
			"name_path": {
				Type:        "string",
				Description: "The name path pattern to search for (e.g., 'resource', '/module/resource')",
			},
			"relative_path": {
				Type:        "string",
				Description: "Optional. Restrict search to this file or directory",
				Default:     "",
			},
			"substring_matching": {
				Type:        "boolean",
				Description: "If true, use substring matching for the last segment",
				Default:     false,
			},
			"include_kinds": {
				Type:        "array",
				Description: "Optional. List of symbol kind integers to include",
				Items:       &PropertySchema{Type: "integer"},
			},
			"exclude_kinds": {
				Type:        "array",
				Description: "Optional. List of symbol kind integers to exclude",
				Items:       &PropertySchema{Type: "integer"},
			},
			"max_answer_chars": {
				Type:        "integer",
				Description: "Maximum characters to return",
				Default:     -1,
			},
		},
		Required: []string{"name_path"},
	}
}

// FindReferencingSymbolsTool finds symbols that reference a given symbol
type FindReferencingSymbolsTool struct {
	*BaseTool
}

func NewFindReferencingSymbolsTool() *FindReferencingSymbolsTool {
	return &FindReferencingSymbolsTool{
		BaseTool: NewBaseTool(
			"find_referencing_symbols",
			"Finds symbols that reference a given symbol",
			true,
			[]ToolMarker{ToolMarkerSymbolicRead{}},
		),
	}
}

func (t *FindReferencingSymbolsTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	var p struct {
		NamePath       string `json:"name_path"`
		RelativePath   string `json:"relative_path"`
		MaxAnswerChars int    `json:"max_answer_chars"`
	}
	p.MaxAnswerChars = -1

	if err := ParseParams(params, &p); err != nil {
		return "", err
	}

	symbolRetriever := t.GetAgent().GetSymbolRetriever()
	if symbolRetriever == nil {
		return "", fmt.Errorf("symbol retriever not available")
	}

	references, err := symbolRetriever.FindReferences(p.NamePath, p.RelativePath)
	if err != nil {
		return "", err
	}

	result, _ := json.Marshal(references)
	return t.LimitLength(string(result), p.MaxAnswerChars), nil
}

func (t *FindReferencingSymbolsTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type: "object",
		Properties: map[string]PropertySchema{
			"name_path": {
				Type:        "string",
				Description: "The name path of the symbol to find references for",
			},
			"relative_path": {
				Type:        "string",
				Description: "The relative path to the file containing the symbol",
			},
			"max_answer_chars": {
				Type:        "integer",
				Description: "Maximum characters to return",
				Default:     -1,
			},
		},
		Required: []string{"name_path", "relative_path"},
	}
}
