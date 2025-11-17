package cache

import (
	"crypto/md5"
	"encoding/gob"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"sync"

	"github.com/TahirRiaz/serena-tf/pkg/lsp"
)

// SymbolCache manages caching of document symbols
type SymbolCache struct {
	cacheDir string
	mutex    sync.RWMutex
}

// NewSymbolCache creates a new symbol cache
func NewSymbolCache(projectRoot string) (*SymbolCache, error) {
	cacheDir := filepath.Join(projectRoot, ".serena-tf", "cache", "terraform")

	if err := os.MkdirAll(cacheDir, 0755); err != nil {
		return nil, fmt.Errorf("failed to create cache directory: %w", err)
	}

	return &SymbolCache{
		cacheDir: cacheDir,
	}, nil
}

// CacheEntry represents a cached symbol entry
type CacheEntry struct {
	ContentHash string
	Symbols     []*lsp.UnifiedSymbolInformation
}

// Get retrieves cached symbols for a file
func (sc *SymbolCache) Get(relativePath string, contentHash string) ([]*lsp.UnifiedSymbolInformation, bool) {
	sc.mutex.RLock()
	defer sc.mutex.RUnlock()

	cacheFile := sc.getCacheFilePath(relativePath)

	// Check if cache file exists
	if _, err := os.Stat(cacheFile); os.IsNotExist(err) {
		return nil, false
	}

	// Read cache file
	file, err := os.Open(cacheFile)
	if err != nil {
		return nil, false
	}
	defer file.Close()

	var entry CacheEntry
	decoder := gob.NewDecoder(file)
	if err := decoder.Decode(&entry); err != nil {
		return nil, false
	}

	// Check if content hash matches
	if entry.ContentHash != contentHash {
		return nil, false
	}

	return entry.Symbols, true
}

// Set stores symbols in cache
func (sc *SymbolCache) Set(relativePath string, contentHash string, symbols []*lsp.UnifiedSymbolInformation) error {
	sc.mutex.Lock()
	defer sc.mutex.Unlock()

	cacheFile := sc.getCacheFilePath(relativePath)

	// Create parent directories
	if err := os.MkdirAll(filepath.Dir(cacheFile), 0755); err != nil {
		return fmt.Errorf("failed to create cache directory: %w", err)
	}

	// Write cache file
	file, err := os.Create(cacheFile)
	if err != nil {
		return fmt.Errorf("failed to create cache file: %w", err)
	}
	defer file.Close()

	entry := CacheEntry{
		ContentHash: contentHash,
		Symbols:     symbols,
	}

	encoder := gob.NewEncoder(file)
	if err := encoder.Encode(&entry); err != nil {
		return fmt.Errorf("failed to encode cache entry: %w", err)
	}

	return nil
}

// getCacheFilePath returns the cache file path for a relative path
func (sc *SymbolCache) getCacheFilePath(relativePath string) string {
	// Create a safe filename from the relative path
	hash := md5.Sum([]byte(relativePath))
	filename := hex.EncodeToString(hash[:]) + ".gob"
	return filepath.Join(sc.cacheDir, filename)
}

// ComputeContentHash computes MD5 hash of content
func ComputeContentHash(content string) string {
	hash := md5.Sum([]byte(content))
	return hex.EncodeToString(hash[:])
}

// Clear clears all cached symbols
func (sc *SymbolCache) Clear() error {
	sc.mutex.Lock()
	defer sc.mutex.Unlock()

	return os.RemoveAll(sc.cacheDir)
}
