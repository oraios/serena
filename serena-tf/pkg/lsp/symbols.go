package lsp

import (
	"fmt"
	"io/ioutil"
	"os"
	"path/filepath"
	"strings"
)

// SymbolRetriever handles symbol operations
type SymbolRetriever struct {
	terraformLS *TerraformLS
	projectRoot string
	cache       SymbolCache
}

// SymbolCache interface for caching
type SymbolCache interface {
	Get(relativePath string, contentHash string) ([]*UnifiedSymbolInformation, bool)
	Set(relativePath string, contentHash string, symbols []*UnifiedSymbolInformation) error
}

// NewSymbolRetriever creates a new symbol retriever
func NewSymbolRetriever(terraformLS *TerraformLS, projectRoot string, cache SymbolCache) *SymbolRetriever {
	return &SymbolRetriever{
		terraformLS: terraformLS,
		projectRoot: projectRoot,
		cache:       cache,
	}
}

// GetDocumentSymbols retrieves symbols for a document
func (sr *SymbolRetriever) GetDocumentSymbols(relativePath string) ([]*UnifiedSymbolInformation, error) {
	absolutePath := filepath.Join(sr.projectRoot, relativePath)

	// Read file content
	content, err := ioutil.ReadFile(absolutePath)
	if err != nil {
		return nil, fmt.Errorf("failed to read file: %w", err)
	}

	// Compute content hash
	contentHash := computeContentHash(string(content))

	// Check cache
	if cached, found := sr.cache.Get(relativePath, contentHash); found {
		return cached, nil
	}

	// Open document in LSP
	uri := pathToURI(absolutePath)
	if err := sr.terraformLS.client.DidOpen(uri, "terraform", string(content)); err != nil {
		return nil, fmt.Errorf("failed to open document: %w", err)
	}
	defer sr.terraformLS.client.DidClose(uri)

	// Request symbols
	symbols, err := sr.terraformLS.client.DocumentSymbols(uri)
	if err != nil {
		return nil, fmt.Errorf("failed to get document symbols: %w", err)
	}

	// Convert to unified format
	unified := sr.convertToUnified(symbols, relativePath, string(content))

	// Cache the result
	if err := sr.cache.Set(relativePath, contentHash, unified); err != nil {
		// Log error but don't fail
		fmt.Fprintf(os.Stderr, "Warning: failed to cache symbols: %v\n", err)
	}

	return unified, nil
}

// convertToUnified converts LSP symbols to unified format
func (sr *SymbolRetriever) convertToUnified(symbols []DocumentSymbol, relativePath string, content string) []*UnifiedSymbolInformation {
	var result []*UnifiedSymbolInformation
	lines := strings.Split(content, "\n")

	for _, symbol := range symbols {
		unified := sr.convertSymbolToUnified(&symbol, relativePath, "", nil, lines)
		result = append(result, unified)
	}

	return result
}

// convertSymbolToUnified converts a single symbol to unified format
func (sr *SymbolRetriever) convertSymbolToUnified(
	symbol *DocumentSymbol,
	relativePath string,
	parentPath string,
	parent *UnifiedSymbolInformation,
	lines []string,
) *UnifiedSymbolInformation {
	// Build name path
	namePath := symbol.Name
	if parentPath != "" {
		namePath = parentPath + "/" + symbol.Name
	}

	// Extract body
	body := extractBody(symbol.Range, lines)

	unified := &UnifiedSymbolInformation{
		Name:           symbol.Name,
		NamePath:       namePath,
		Kind:           symbol.Kind,
		RelativePath:   relativePath,
		Range:          symbol.Range,
		SelectionRange: symbol.SelectionRange,
		Body:           body,
		Parent:         parent,
	}

	// Process children
	for _, child := range symbol.Children {
		childUnified := sr.convertSymbolToUnified(&child, relativePath, namePath, unified, lines)
		unified.Children = append(unified.Children, childUnified)
	}

	return unified
}

// extractBody extracts the body text for a range
func extractBody(r Range, lines []string) string {
	if r.Start.Line >= len(lines) || r.End.Line >= len(lines) {
		return ""
	}

	if r.Start.Line == r.End.Line {
		line := lines[r.Start.Line]
		if r.Start.Character >= len(line) {
			return ""
		}
		endChar := r.End.Character
		if endChar > len(line) {
			endChar = len(line)
		}
		return line[r.Start.Character:endChar]
	}

	var bodyLines []string

	// First line
	firstLine := lines[r.Start.Line]
	if r.Start.Character < len(firstLine) {
		bodyLines = append(bodyLines, firstLine[r.Start.Character:])
	}

	// Middle lines
	for i := r.Start.Line + 1; i < r.End.Line; i++ {
		bodyLines = append(bodyLines, lines[i])
	}

	// Last line
	if r.End.Line < len(lines) {
		lastLine := lines[r.End.Line]
		endChar := r.End.Character
		if endChar > len(lastLine) {
			endChar = len(lastLine)
		}
		bodyLines = append(bodyLines, lastLine[:endChar])
	}

	return strings.Join(bodyLines, "\n")
}

// FindSymbolsByName finds symbols by name pattern
func (sr *SymbolRetriever) FindSymbolsByName(
	namePath string,
	withinPath string,
	substringMatching bool,
	includeKinds []SymbolKind,
	excludeKinds []SymbolKind,
) ([]*UnifiedSymbolInformation, error) {
	// Determine which files to search
	var filesToSearch []string

	if withinPath == "" {
		// Search all Terraform files
		err := filepath.Walk(sr.projectRoot, func(path string, info os.FileInfo, err error) error {
			if err != nil {
				return err
			}

			if info.IsDir() {
				// Check if directory should be ignored
				if sr.terraformLS.IsIgnoredPath(path) {
					return filepath.SkipDir
				}
				return nil
			}

			if IsTerraformFile(path) {
				relPath, _ := filepath.Rel(sr.projectRoot, path)
				filesToSearch = append(filesToSearch, relPath)
			}

			return nil
		})
		if err != nil {
			return nil, err
		}
	} else {
		// Search within specific path
		fullPath := filepath.Join(sr.projectRoot, withinPath)
		info, err := os.Stat(fullPath)
		if err != nil {
			return nil, err
		}

		if info.IsDir() {
			// Search directory
			err := filepath.Walk(fullPath, func(path string, info os.FileInfo, err error) error {
				if err != nil {
					return err
				}

				if info.IsDir() {
					if sr.terraformLS.IsIgnoredPath(path) {
						return filepath.SkipDir
					}
					return nil
				}

				if IsTerraformFile(path) {
					relPath, _ := filepath.Rel(sr.projectRoot, path)
					filesToSearch = append(filesToSearch, relPath)
				}

				return nil
			})
			if err != nil {
				return nil, err
			}
		} else {
			// Single file
			filesToSearch = append(filesToSearch, withinPath)
		}
	}

	// Search each file
	var results []*UnifiedSymbolInformation

	for _, filePath := range filesToSearch {
		symbols, err := sr.GetDocumentSymbols(filePath)
		if err != nil {
			// Log but continue
			fmt.Fprintf(os.Stderr, "Warning: failed to get symbols for %s: %v\n", filePath, err)
			continue
		}

		// Search symbols
		matches := sr.searchSymbols(symbols, namePath, substringMatching, includeKinds, excludeKinds)
		results = append(results, matches...)
	}

	return results, nil
}

// searchSymbols searches symbols recursively
func (sr *SymbolRetriever) searchSymbols(
	symbols []*UnifiedSymbolInformation,
	namePath string,
	substringMatching bool,
	includeKinds []SymbolKind,
	excludeKinds []SymbolKind,
) []*UnifiedSymbolInformation {
	var results []*UnifiedSymbolInformation

	for _, symbol := range symbols {
		// Check if symbol matches
		if sr.symbolMatches(symbol, namePath, substringMatching, includeKinds, excludeKinds) {
			results = append(results, symbol)
		}

		// Search children
		if len(symbol.Children) > 0 {
			childMatches := sr.searchSymbols(symbol.Children, namePath, substringMatching, includeKinds, excludeKinds)
			results = append(results, childMatches...)
		}
	}

	return results
}

// symbolMatches checks if a symbol matches the criteria
func (sr *SymbolRetriever) symbolMatches(
	symbol *UnifiedSymbolInformation,
	namePath string,
	substringMatching bool,
	includeKinds []SymbolKind,
	excludeKinds []SymbolKind,
) bool {
	// Check kind filters
	if len(excludeKinds) > 0 {
		for _, kind := range excludeKinds {
			if symbol.Kind == kind {
				return false
			}
		}
	}

	if len(includeKinds) > 0 {
		found := false
		for _, kind := range includeKinds {
			if symbol.Kind == kind {
				found = true
				break
			}
		}
		if !found {
			return false
		}
	}

	// Check name path matching
	return sr.namePathMatches(symbol.NamePath, namePath, substringMatching)
}

// namePathMatches checks if a name path matches the pattern
func (sr *SymbolRetriever) namePathMatches(symbolNamePath, pattern string, substringMatching bool) bool {
	// Handle absolute vs relative patterns
	isAbsolutePattern := strings.HasPrefix(pattern, "/")
	pattern = strings.Trim(pattern, "/")

	// Split into segments
	patternSegments := strings.Split(pattern, "/")
	symbolSegments := strings.Split(symbolNamePath, "/")

	// For absolute patterns, first segment must match
	if isAbsolutePattern {
		if len(patternSegments) > len(symbolSegments) {
			return false
		}

		// Check if pattern matches from the start
		for i, segment := range patternSegments {
			if i == len(patternSegments)-1 {
				// Last segment - check with substring matching
				if substringMatching {
					if !strings.Contains(symbolSegments[i], segment) {
						return false
					}
				} else {
					if symbolSegments[i] != segment {
						return false
					}
				}
			} else {
				// Intermediate segments must match exactly
				if symbolSegments[i] != segment {
					return false
				}
			}
		}
		return true
	}

	// For relative patterns
	if len(patternSegments) == 1 {
		// Single segment - match any symbol name
		lastSegment := symbolSegments[len(symbolSegments)-1]
		if substringMatching {
			return strings.Contains(lastSegment, pattern)
		}
		return lastSegment == pattern
	}

	// Multiple segments - match the tail
	if len(patternSegments) > len(symbolSegments) {
		return false
	}

	// Check if the tail matches
	offset := len(symbolSegments) - len(patternSegments)
	for i, segment := range patternSegments {
		symbolSegment := symbolSegments[offset+i]

		if i == len(patternSegments)-1 {
			// Last segment - check with substring matching
			if substringMatching {
				if !strings.Contains(symbolSegment, segment) {
					return false
				}
			} else {
				if symbolSegment != segment {
					return false
				}
			}
		} else {
			// Intermediate segments must match exactly
			if symbolSegment != segment {
				return false
			}
		}
	}

	return true
}

// computeContentHash computes MD5 hash of content
func computeContentHash(content string) string {
	// This is implemented in cache package, but we need it here too
	// For now, we'll use a simple implementation
	return fmt.Sprintf("%x", content) // Placeholder
}
