package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/TahirRiaz/serena-tf/pkg/util"
)

// ReadFileTool reads a file within the project
type ReadFileTool struct {
	*BaseTool
}

func NewReadFileTool() *ReadFileTool {
	return &ReadFileTool{
		BaseTool: NewBaseTool(
			"read_file",
			"Reads a file within the project directory",
			true,
			nil,
		),
	}
}

func (t *ReadFileTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	var p struct {
		RelativePath  string `json:"relative_path"`
		StartLine     int    `json:"start_line"`
		EndLine       int    `json:"end_line"`
		MaxAnswerChars int   `json:"max_answer_chars"`
	}
	p.MaxAnswerChars = -1
	p.EndLine = -1

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

	content, err := project.ReadFile(p.RelativePath)
	if err != nil {
		return "", err
	}

	lines := strings.Split(content, "\n")
	if p.EndLine == -1 {
		lines = lines[p.StartLine:]
	} else {
		lines = lines[p.StartLine : p.EndLine+1]
	}

	result := strings.Join(lines, "\n")
	return t.LimitLength(result, p.MaxAnswerChars), nil
}

func (t *ReadFileTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type: "object",
		Properties: map[string]PropertySchema{
			"relative_path": {
				Type:        "string",
				Description: "The relative path to the file to read",
			},
			"start_line": {
				Type:        "integer",
				Description: "The 0-based index of the first line to retrieve",
				Default:     0,
			},
			"end_line": {
				Type:        "integer",
				Description: "The 0-based index of the last line to retrieve (inclusive). If -1, read until end",
				Default:     -1,
			},
			"max_answer_chars": {
				Type:        "integer",
				Description: "Maximum characters to return. Use -1 for default limit",
				Default:     -1,
			},
		},
		Required: []string{"relative_path"},
	}
}

// CreateTextFileTool creates or overwrites a file
type CreateTextFileTool struct {
	*BaseTool
}

func NewCreateTextFileTool() *CreateTextFileTool {
	return &CreateTextFileTool{
		BaseTool: NewBaseTool(
			"create_text_file",
			"Creates or overwrites a file in the project directory",
			true,
			[]ToolMarker{ToolMarkerCanEdit{}},
		),
	}
}

func (t *CreateTextFileTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	var p struct {
		RelativePath string `json:"relative_path"`
		Content      string `json:"content"`
	}

	if err := ParseParams(params, &p); err != nil {
		return "", err
	}

	project := t.GetProject()
	if project == nil {
		return "", fmt.Errorf("no active project")
	}

	fullPath := filepath.Join(project.GetRoot(), p.RelativePath)
	willOverwrite := util.FileExists(fullPath)

	if err := project.WriteFile(p.RelativePath, p.Content); err != nil {
		return "", err
	}

	msg := fmt.Sprintf("File created: %s", p.RelativePath)
	if willOverwrite {
		msg += " (overwrote existing file)"
	}

	return msg, nil
}

func (t *CreateTextFileTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type: "object",
		Properties: map[string]PropertySchema{
			"relative_path": {
				Type:        "string",
				Description: "The relative path to the file to create",
			},
			"content": {
				Type:        "string",
				Description: "The content to write to the file",
			},
		},
		Required: []string{"relative_path", "content"},
	}
}

// ListDirTool lists files and directories
type ListDirTool struct {
	*BaseTool
}

func NewListDirTool() *ListDirTool {
	return &ListDirTool{
		BaseTool: NewBaseTool(
			"list_dir",
			"Lists files and directories in a given directory",
			true,
			nil,
		),
	}
}

func (t *ListDirTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	var p struct {
		RelativePath     string `json:"relative_path"`
		Recursive        bool   `json:"recursive"`
		SkipIgnoredFiles bool   `json:"skip_ignored_files"`
		MaxAnswerChars   int    `json:"max_answer_chars"`
	}
	p.MaxAnswerChars = -1

	if err := ParseParams(params, &p); err != nil {
		return "", err
	}

	project := t.GetProject()
	if project == nil {
		return "", fmt.Errorf("no active project")
	}

	fullPath := filepath.Join(project.GetRoot(), p.RelativePath)

	if !project.PathExists(p.RelativePath) {
		return "", fmt.Errorf("directory not found: %s", p.RelativePath)
	}

	var isIgnored func(string) bool
	if p.SkipIgnoredFiles {
		isIgnored = project.IsIgnoredPath
	}

	dirs, files, err := util.ListDirectory(fullPath, p.Recursive, isIgnored)
	if err != nil {
		return "", err
	}

	// Convert to relative paths
	projectRoot := project.GetRoot()
	for i, dir := range dirs {
		rel, _ := filepath.Rel(projectRoot, dir)
		dirs[i] = rel
	}
	for i, file := range files {
		rel, _ := filepath.Rel(projectRoot, file)
		files[i] = rel
	}

	result := map[string]interface{}{
		"dirs":  dirs,
		"files": files,
	}

	jsonResult, _ := json.Marshal(result)
	return t.LimitLength(string(jsonResult), p.MaxAnswerChars), nil
}

func (t *ListDirTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type: "object",
		Properties: map[string]PropertySchema{
			"relative_path": {
				Type:        "string",
				Description: "The relative path to the directory to list",
			},
			"recursive": {
				Type:        "boolean",
				Description: "Whether to scan subdirectories recursively",
			},
			"skip_ignored_files": {
				Type:        "boolean",
				Description: "Whether to skip files and directories that are ignored",
				Default:     false,
			},
			"max_answer_chars": {
				Type:        "integer",
				Description: "Maximum characters to return",
				Default:     -1,
			},
		},
		Required: []string{"relative_path", "recursive"},
	}
}

// FindFileTool finds files by pattern
type FindFileTool struct {
	*BaseTool
}

func NewFindFileTool() *FindFileTool {
	return &FindFileTool{
		BaseTool: NewBaseTool(
			"find_file",
			"Finds files matching a file mask within a given directory",
			true,
			nil,
		),
	}
}

func (t *FindFileTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	var p struct {
		FileMask     string `json:"file_mask"`
		RelativePath string `json:"relative_path"`
	}

	if err := ParseParams(params, &p); err != nil {
		return "", err
	}

	project := t.GetProject()
	if project == nil {
		return "", fmt.Errorf("no active project")
	}

	fullPath := filepath.Join(project.GetRoot(), p.RelativePath)

	var files []string

	err := filepath.Walk(fullPath, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}

		if project.IsIgnoredPath(path) {
			if info.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}

		if !info.IsDir() {
			matched, _ := filepath.Match(p.FileMask, filepath.Base(path))
			if matched {
				rel, _ := filepath.Rel(project.GetRoot(), path)
				files = append(files, rel)
			}
		}

		return nil
	})

	if err != nil {
		return "", err
	}

	result := map[string]interface{}{
		"files": files,
	}

	jsonResult, _ := json.Marshal(result)
	return string(jsonResult), nil
}

func (t *FindFileTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type: "object",
		Properties: map[string]PropertySchema{
			"file_mask": {
				Type:        "string",
				Description: "The filename or file mask (using wildcards * or ?) to search for",
			},
			"relative_path": {
				Type:        "string",
				Description: "The relative path to the directory to search in",
			},
		},
		Required: []string{"file_mask", "relative_path"},
	}
}

// SearchForPatternTool searches for a pattern in files
type SearchForPatternTool struct {
	*BaseTool
}

func NewSearchForPatternTool() *SearchForPatternTool {
	return &SearchForPatternTool{
		BaseTool: NewBaseTool(
			"search_for_pattern",
			"Performs a regex search for a pattern in the project",
			true,
			nil,
		),
	}
}

func (t *SearchForPatternTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	var p struct {
		SubstringPattern   string `json:"substring_pattern"`
		ContextLinesBefore int    `json:"context_lines_before"`
		ContextLinesAfter  int    `json:"context_lines_after"`
		RelativePath       string `json:"relative_path"`
		MaxAnswerChars     int    `json:"max_answer_chars"`
	}
	p.MaxAnswerChars = -1

	if err := ParseParams(params, &p); err != nil {
		return "", err
	}

	project := t.GetProject()
	if project == nil {
		return "", fmt.Errorf("no active project")
	}

	searchPath := p.RelativePath
	if searchPath == "" {
		searchPath = "."
	}

	fullPath := filepath.Join(project.GetRoot(), searchPath)

	// Collect all files to search
	var filesToSearch []string

	err := filepath.Walk(fullPath, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}

		if project.IsIgnoredPath(path) {
			if info.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}

		if !info.IsDir() {
			rel, _ := filepath.Rel(project.GetRoot(), path)
			filesToSearch = append(filesToSearch, rel)
		}

		return nil
	})

	if err != nil {
		return "", err
	}

	// Search files
	results, err := util.SearchInFiles(
		project.GetRoot(),
		p.SubstringPattern,
		filesToSearch,
		p.ContextLinesBefore,
		p.ContextLinesAfter,
		project.IsIgnoredPath,
	)

	if err != nil {
		return "", err
	}

	jsonResult, _ := json.Marshal(results)
	return t.LimitLength(string(jsonResult), p.MaxAnswerChars), nil
}

func (t *SearchForPatternTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type: "object",
		Properties: map[string]PropertySchema{
			"substring_pattern": {
				Type:        "string",
				Description: "The regex pattern to search for",
			},
			"context_lines_before": {
				Type:        "integer",
				Description: "Number of lines before match to include",
				Default:     0,
			},
			"context_lines_after": {
				Type:        "integer",
				Description: "Number of lines after match to include",
				Default:     0,
			},
			"relative_path": {
				Type:        "string",
				Description: "Restrict search to this file or directory (empty for whole project)",
				Default:     "",
			},
			"max_answer_chars": {
				Type:        "integer",
				Description: "Maximum characters to return",
				Default:     -1,
			},
		},
		Required: []string{"substring_pattern"},
	}
}

// ReplaceRegexTool replaces content using regex
type ReplaceRegexTool struct {
	*BaseTool
}

func NewReplaceRegexTool() *ReplaceRegexTool {
	return &ReplaceRegexTool{
		BaseTool: NewBaseTool(
			"replace_regex",
			"Replaces content in a file using regular expressions",
			true,
			[]ToolMarker{ToolMarkerCanEdit{}},
		),
	}
}

func (t *ReplaceRegexTool) Apply(ctx context.Context, params map[string]interface{}) (string, error) {
	var p struct {
		RelativePath          string `json:"relative_path"`
		Regex                 string `json:"regex"`
		Repl                  string `json:"repl"`
		AllowMultipleOccurrences bool   `json:"allow_multiple_occurrences"`
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

	fullPath := filepath.Join(project.GetRoot(), p.RelativePath)

	count, err := util.ReplaceInFile(fullPath, p.Regex, p.Repl, p.AllowMultipleOccurrences)
	if err != nil {
		return "", err
	}

	return fmt.Sprintf("Successfully replaced %d occurrence(s)", count), nil
}

func (t *ReplaceRegexTool) Schema() *ToolSchema {
	return &ToolSchema{
		Type: "object",
		Properties: map[string]PropertySchema{
			"relative_path": {
				Type:        "string",
				Description: "The relative path to the file",
			},
			"regex": {
				Type:        "string",
				Description: "Python-style regular expression to match",
			},
			"repl": {
				Type:        "string",
				Description: "Replacement string (may contain backreferences like \\1, \\2)",
			},
			"allow_multiple_occurrences": {
				Type:        "boolean",
				Description: "Whether to allow replacing multiple occurrences",
				Default:     false,
			},
		},
		Required: []string{"relative_path", "regex", "repl"},
	}
}
