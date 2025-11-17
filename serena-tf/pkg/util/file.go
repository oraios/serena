package util

import (
	"bufio"
	"fmt"
	"io/ioutil"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/go-git/go-git/v5/plumbing/format/gitignore"
)

// ReadFile reads a file and returns its content
func ReadFile(path string) (string, error) {
	content, err := ioutil.ReadFile(path)
	if err != nil {
		return "", err
	}
	return string(content), nil
}

// WriteFile writes content to a file
func WriteFile(path string, content string) error {
	// Create parent directories
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("failed to create directory: %w", err)
	}

	return ioutil.WriteFile(path, []byte(content), 0644)
}

// FileExists checks if a file exists
func FileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

// IsDirectory checks if path is a directory
func IsDirectory(path string) bool {
	info, err := os.Stat(path)
	if err != nil {
		return false
	}
	return info.IsDir()
}

// ListDirectory lists files and directories in a path
func ListDirectory(path string, recursive bool, isIgnored func(string) bool) ([]string, []string, error) {
	var dirs []string
	var files []string

	if recursive {
		err := filepath.Walk(path, func(p string, info os.FileInfo, err error) error {
			if err != nil {
				return err
			}

			// Skip ignored paths
			if isIgnored != nil && isIgnored(p) {
				if info.IsDir() {
					return filepath.SkipDir
				}
				return nil
			}

			// Skip root
			if p == path {
				return nil
			}

			if info.IsDir() {
				dirs = append(dirs, p)
			} else {
				files = append(files, p)
			}

			return nil
		})
		return dirs, files, err
	}

	// Non-recursive
	entries, err := ioutil.ReadDir(path)
	if err != nil {
		return nil, nil, err
	}

	for _, entry := range entries {
		fullPath := filepath.Join(path, entry.Name())

		if isIgnored != nil && isIgnored(fullPath) {
			continue
		}

		if entry.IsDir() {
			dirs = append(dirs, fullPath)
		} else {
			files = append(files, fullPath)
		}
	}

	return dirs, files, nil
}

// SearchInFiles searches for a pattern in files
func SearchInFiles(
	rootPath string,
	pattern string,
	paths []string,
	contextLinesBefore int,
	contextLinesAfter int,
	isIgnored func(string) bool,
) ([]SearchResult, error) {
	regex, err := regexp.Compile("(?s)" + pattern) // (?s) enables DOTALL
	if err != nil {
		return nil, fmt.Errorf("invalid regex pattern: %w", err)
	}

	var results []SearchResult

	for _, relPath := range paths {
		fullPath := filepath.Join(rootPath, relPath)

		if isIgnored != nil && isIgnored(fullPath) {
			continue
		}

		content, err := ReadFile(fullPath)
		if err != nil {
			continue
		}

		lines := strings.Split(content, "\n")

		// Search line by line
		for i, line := range lines {
			if regex.MatchString(line) {
				// Extract context
				start := i - contextLinesBefore
				if start < 0 {
					start = 0
				}

				end := i + contextLinesAfter + 1
				if end > len(lines) {
					end = len(lines)
				}

				contextLines := lines[start:end]

				results = append(results, SearchResult{
					FilePath:     relPath,
					LineNumber:   i + 1,
					Line:         line,
					ContextLines: contextLines,
					ContextStart: start + 1,
				})
			}
		}
	}

	return results, nil
}

// SearchResult represents a search result
type SearchResult struct {
	FilePath     string
	LineNumber   int
	Line         string
	ContextLines []string
	ContextStart int
}

// ReplaceInFile replaces content in a file using regex
func ReplaceInFile(path string, pattern string, replacement string, allowMultiple bool) (int, error) {
	content, err := ReadFile(path)
	if err != nil {
		return 0, err
	}

	regex, err := regexp.Compile("(?ms)" + pattern) // (?ms) enables DOTALL and MULTILINE
	if err != nil {
		return 0, fmt.Errorf("invalid regex pattern: %w", err)
	}

	// Find all matches
	matches := regex.FindAllStringIndex(content, -1)

	if len(matches) == 0 {
		return 0, fmt.Errorf("no matches found")
	}

	if !allowMultiple && len(matches) > 1 {
		return 0, fmt.Errorf("pattern matches %d occurrences, but allowMultiple is false", len(matches))
	}

	// Replace
	newContent := regex.ReplaceAllString(content, replacement)

	if err := WriteFile(path, newContent); err != nil {
		return 0, err
	}

	return len(matches), nil
}

// GetLinesFromFile gets a range of lines from a file
func GetLinesFromFile(path string, startLine, endLine int) ([]string, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	var lines []string
	scanner := bufio.NewScanner(file)
	lineNum := 0

	for scanner.Scan() {
		if lineNum >= startLine && (endLine == -1 || lineNum <= endLine) {
			lines = append(lines, scanner.Text())
		}
		lineNum++

		if endLine != -1 && lineNum > endLine {
			break
		}
	}

	if err := scanner.Err(); err != nil {
		return nil, err
	}

	return lines, nil
}

// DeleteLines deletes a range of lines from a file
func DeleteLines(path string, startLine, endLine int) error {
	content, err := ReadFile(path)
	if err != nil {
		return err
	}

	lines := strings.Split(content, "\n")

	if startLine < 0 || endLine >= len(lines) || startLine > endLine {
		return fmt.Errorf("invalid line range")
	}

	// Remove lines
	newLines := append(lines[:startLine], lines[endLine+1:]...)

	newContent := strings.Join(newLines, "\n")

	return WriteFile(path, newContent)
}

// InsertAtLine inserts content at a specific line
func InsertAtLine(path string, line int, content string) error {
	existingContent, err := ReadFile(path)
	if err != nil {
		return err
	}

	lines := strings.Split(existingContent, "\n")

	if line < 0 || line > len(lines) {
		return fmt.Errorf("invalid line number")
	}

	// Ensure content ends with newline
	if !strings.HasSuffix(content, "\n") {
		content += "\n"
	}

	// Insert content
	insertLines := strings.Split(strings.TrimSuffix(content, "\n"), "\n")
	newLines := append(lines[:line], append(insertLines, lines[line:]...)...)

	newContent := strings.Join(newLines, "\n")

	return WriteFile(path, newContent)
}

// LoadGitignore loads gitignore patterns from a directory
func LoadGitignore(rootPath string) (gitignore.Matcher, error) {
	gitignorePath := filepath.Join(rootPath, ".gitignore")

	if !FileExists(gitignorePath) {
		// Return a matcher that matches nothing
		return gitignore.NewMatcher([]gitignore.Pattern{}), nil
	}

	file, err := os.Open(gitignorePath)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	var patterns []gitignore.Pattern
	scanner := bufio.NewScanner(file)
	lineNum := 1

	for scanner.Scan() {
		line := scanner.Text()
		line = strings.TrimSpace(line)

		// Skip empty lines and comments
		if line == "" || strings.HasPrefix(line, "#") {
			lineNum++
			continue
		}

		// Parse pattern
		pattern := gitignore.ParsePattern(line, nil)
		patterns = append(patterns, pattern)

		lineNum++
	}

	if err := scanner.Err(); err != nil {
		return nil, err
	}

	return gitignore.NewMatcher(patterns), nil
}
