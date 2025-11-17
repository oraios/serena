package editor

import (
	"fmt"
	"path/filepath"
	"strings"

	"github.com/TahirRiaz/serena-tf/pkg/lsp"
	"github.com/TahirRiaz/serena-tf/pkg/util"
)

// CodeEditor handles code editing operations with symbol awareness
type CodeEditor struct {
	projectRoot     string
	symbolRetriever *lsp.SymbolRetriever
	terraformLS     *lsp.TerraformLS
}

// NewCodeEditor creates a new code editor
func NewCodeEditor(projectRoot string, symbolRetriever *lsp.SymbolRetriever, terraformLS *lsp.TerraformLS) *CodeEditor {
	return &CodeEditor{
		projectRoot:     projectRoot,
		symbolRetriever: symbolRetriever,
		terraformLS:     terraformLS,
	}
}

// ReplaceSymbolBody replaces the body of a symbol
func (ce *CodeEditor) ReplaceSymbolBody(namePath, relativePath, newBody string) error {
	// Find the symbol
	symbols, err := ce.symbolRetriever.FindSymbolsByName(namePath, relativePath, false, nil, nil)
	if err != nil {
		return fmt.Errorf("failed to find symbol: %w", err)
	}

	if len(symbols) == 0 {
		return fmt.Errorf("symbol not found: %s", namePath)
	}

	if len(symbols) > 1 {
		return fmt.Errorf("multiple symbols found with name %s, please be more specific", namePath)
	}

	symbol := symbols[0]

	// Read file content
	fullPath := filepath.Join(ce.projectRoot, relativePath)
	content, err := util.ReadFile(fullPath)
	if err != nil {
		return err
	}

	lines := strings.Split(content, "\n")

	// Replace the symbol's range with new body
	startLine := symbol.Range.Start.Line
	endLine := symbol.Range.End.Line

	if startLine >= len(lines) || endLine >= len(lines) {
		return fmt.Errorf("symbol range is out of bounds")
	}

	// Ensure new body ends with newline
	if !strings.HasSuffix(newBody, "\n") {
		newBody += "\n"
	}

	// Replace lines
	newLines := append([]string{}, lines[:startLine]...)
	newLines = append(newLines, strings.TrimSuffix(newBody, "\n"))
	newLines = append(newLines, lines[endLine+1:]...)

	newContent := strings.Join(newLines, "\n")

	return util.WriteFile(fullPath, newContent)
}

// InsertAfterSymbol inserts content after a symbol
func (ce *CodeEditor) InsertAfterSymbol(namePath, relativePath, content string) error {
	// Find the symbol
	symbols, err := ce.symbolRetriever.FindSymbolsByName(namePath, relativePath, false, nil, nil)
	if err != nil {
		return fmt.Errorf("failed to find symbol: %w", err)
	}

	if len(symbols) == 0 {
		return fmt.Errorf("symbol not found: %s", namePath)
	}

	if len(symbols) > 1 {
		return fmt.Errorf("multiple symbols found with name %s, please be more specific", namePath)
	}

	symbol := symbols[0]

	// Insert at the line after symbol end
	insertLine := symbol.Range.End.Line + 1

	return ce.InsertAtLine(relativePath, insertLine, content)
}

// InsertBeforeSymbol inserts content before a symbol
func (ce *CodeEditor) InsertBeforeSymbol(namePath, relativePath, content string) error {
	// Find the symbol
	symbols, err := ce.symbolRetriever.FindSymbolsByName(namePath, relativePath, false, nil, nil)
	if err != nil {
		return fmt.Errorf("failed to find symbol: %w", err)
	}

	if len(symbols) == 0 {
		return fmt.Errorf("symbol not found: %s", namePath)
	}

	if len(symbols) > 1 {
		return fmt.Errorf("multiple symbols found with name %s, please be more specific", namePath)
	}

	symbol := symbols[0]

	// Insert at the symbol's start line
	insertLine := symbol.Range.Start.Line

	return ce.InsertAtLine(relativePath, insertLine, content)
}

// RenameSymbol renames a symbol using LSP
func (ce *CodeEditor) RenameSymbol(namePath, relativePath, newName string) (string, error) {
	// Find the symbol
	symbols, err := ce.symbolRetriever.FindSymbolsByName(namePath, relativePath, false, nil, nil)
	if err != nil {
		return "", fmt.Errorf("failed to find symbol: %w", err)
	}

	if len(symbols) == 0 {
		return "", fmt.Errorf("symbol not found: %s", namePath)
	}

	if len(symbols) > 1 {
		return "", fmt.Errorf("multiple symbols found with name %s, please be more specific", namePath)
	}

	symbol := symbols[0]

	// Use LSP rename
	fullPath := filepath.Join(ce.projectRoot, relativePath)
	uri := pathToURI(fullPath)

	// Use selection range position for rename
	position := symbol.SelectionRange.Start

	workspaceEdit, err := ce.terraformLS.GetClient().Rename(uri, position, newName)
	if err != nil {
		return "", fmt.Errorf("LSP rename failed: %w", err)
	}

	// Apply edits
	if err := ce.applyWorkspaceEdit(workspaceEdit); err != nil {
		return "", fmt.Errorf("failed to apply edits: %w", err)
	}

	return fmt.Sprintf("Successfully renamed %s to %s", symbol.Name, newName), nil
}

// DeleteLines deletes a range of lines
func (ce *CodeEditor) DeleteLines(relativePath string, startLine, endLine int) error {
	fullPath := filepath.Join(ce.projectRoot, relativePath)
	return util.DeleteLines(fullPath, startLine, endLine)
}

// ReplaceLines replaces a range of lines
func (ce *CodeEditor) ReplaceLines(relativePath string, startLine, endLine int, content string) error {
	fullPath := filepath.Join(ce.projectRoot, relativePath)

	// Delete then insert
	if err := util.DeleteLines(fullPath, startLine, endLine); err != nil {
		return err
	}

	return util.InsertAtLine(fullPath, startLine, content)
}

// InsertAtLine inserts content at a specific line
func (ce *CodeEditor) InsertAtLine(relativePath string, line int, content string) error {
	fullPath := filepath.Join(ce.projectRoot, relativePath)
	return util.InsertAtLine(fullPath, line, content)
}

// applyWorkspaceEdit applies LSP workspace edits
func (ce *CodeEditor) applyWorkspaceEdit(edit *lsp.WorkspaceEdit) error {
	if edit == nil || edit.Changes == nil {
		return fmt.Errorf("no edits to apply")
	}

	for uri, textEdits := range edit.Changes {
		path := uriToPath(uri)

		// Read current content
		content, err := util.ReadFile(path)
		if err != nil {
			return fmt.Errorf("failed to read %s: %w", path, err)
		}

		// Apply edits in reverse order (to maintain positions)
		lines := strings.Split(content, "\n")

		// Sort edits by position (reverse)
		for i := len(textEdits) - 1; i >= 0; i-- {
			edit := textEdits[i]

			startLine := edit.Range.Start.Line
			endLine := edit.Range.End.Line
			startChar := edit.Range.Start.Character
			endChar := edit.Range.End.Character

			if startLine >= len(lines) {
				continue
			}

			if startLine == endLine {
				// Single line edit
				line := lines[startLine]
				newLine := line[:startChar] + edit.NewText + line[endChar:]
				lines[startLine] = newLine
			} else {
				// Multi-line edit
				firstPart := lines[startLine][:startChar]
				lastPart := ""
				if endLine < len(lines) {
					lastPart = lines[endLine][endChar:]
				}

				newLines := strings.Split(edit.NewText, "\n")
				replacement := []string{firstPart + newLines[0]}
				if len(newLines) > 1 {
					replacement = append(replacement, newLines[1:len(newLines)-1]...)
					replacement = append(replacement, newLines[len(newLines)-1]+lastPart)
				} else {
					replacement[0] += lastPart
				}

				// Replace range
				lines = append(lines[:startLine], append(replacement, lines[endLine+1:]...)...)
			}
		}

		newContent := strings.Join(lines, "\n")
		if err := util.WriteFile(path, newContent); err != nil {
			return fmt.Errorf("failed to write %s: %w", path, err)
		}
	}

	return nil
}

// pathToURI converts a file path to URI
func pathToURI(path string) string {
	absPath, _ := filepath.Abs(path)
	if strings.Contains(absPath, "\\") {
		absPath = strings.ReplaceAll(absPath, "\\", "/")
	}
	if !strings.HasPrefix(absPath, "/") {
		absPath = "/" + absPath
	}
	return "file://" + absPath
}

// uriToPath converts URI to path
func uriToPath(uri string) string {
	path := strings.TrimPrefix(uri, "file://")
	if len(path) > 2 && path[0] == '/' && path[2] == ':' {
		path = path[1:]
	}
	return filepath.FromSlash(path)
}
