package lsp

import (
	"encoding/json"
	"fmt"
)

// SymbolKind represents the kind of a symbol
type SymbolKind int

const (
	SymbolKindFile          SymbolKind = 1
	SymbolKindModule        SymbolKind = 2
	SymbolKindNamespace     SymbolKind = 3
	SymbolKindPackage       SymbolKind = 4
	SymbolKindClass         SymbolKind = 5
	SymbolKindMethod        SymbolKind = 6
	SymbolKindProperty      SymbolKind = 7
	SymbolKindField         SymbolKind = 8
	SymbolKindConstructor   SymbolKind = 9
	SymbolKindEnum          SymbolKind = 10
	SymbolKindInterface     SymbolKind = 11
	SymbolKindFunction      SymbolKind = 12
	SymbolKindVariable      SymbolKind = 13
	SymbolKindConstant      SymbolKind = 14
	SymbolKindString        SymbolKind = 15
	SymbolKindNumber        SymbolKind = 16
	SymbolKindBoolean       SymbolKind = 17
	SymbolKindArray         SymbolKind = 18
	SymbolKindObject        SymbolKind = 19
	SymbolKindKey           SymbolKind = 20
	SymbolKindNull          SymbolKind = 21
	SymbolKindEnumMember    SymbolKind = 22
	SymbolKindStruct        SymbolKind = 23
	SymbolKindEvent         SymbolKind = 24
	SymbolKindOperator      SymbolKind = 25
	SymbolKindTypeParameter SymbolKind = 26
)

// Position represents a text position
type Position struct {
	Line      int `json:"line"`
	Character int `json:"character"`
}

// Range represents a text range
type Range struct {
	Start Position `json:"start"`
	End   Position `json:"end"`
}

// Location represents a location in a document
type Location struct {
	URI   string `json:"uri"`
	Range Range  `json:"range"`
}

// DocumentSymbol represents a symbol in a document
type DocumentSymbol struct {
	Name           string           `json:"name"`
	Detail         string           `json:"detail,omitempty"`
	Kind           SymbolKind       `json:"kind"`
	Range          Range            `json:"range"`
	SelectionRange Range            `json:"selectionRange"`
	Children       []DocumentSymbol `json:"children,omitempty"`
}

// UnifiedSymbolInformation represents a unified symbol with additional metadata
type UnifiedSymbolInformation struct {
	Name           string                      `json:"name"`
	NamePath       string                      `json:"name_path"`
	Kind           SymbolKind                  `json:"kind"`
	RelativePath   string                      `json:"relative_path"`
	Range          Range                       `json:"range"`
	SelectionRange Range                       `json:"selection_range"`
	Body           string                      `json:"body,omitempty"`
	Children       []*UnifiedSymbolInformation `json:"children,omitempty"`
	Parent         *UnifiedSymbolInformation   `json:"-"` // Don't serialize parent to avoid cycles
}

// Reference represents a reference to a symbol
type Reference struct {
	Location Location `json:"location"`
	Context  string   `json:"context,omitempty"`
}

// SymbolReference represents a reference with the containing symbol
type SymbolReference struct {
	Symbol *UnifiedSymbolInformation `json:"symbol"`
	Line   int                       `json:"line"`
}

// TextEdit represents a text edit
type TextEdit struct {
	Range   Range  `json:"range"`
	NewText string `json:"newText"`
}

// WorkspaceEdit represents a workspace edit
type WorkspaceEdit struct {
	Changes map[string][]TextEdit `json:"changes"`
}

// Hover represents hover information
type Hover struct {
	Contents interface{} `json:"contents"`
	Range    *Range      `json:"range,omitempty"`
}

// InitializeParams represents initialization parameters
type InitializeParams struct {
	ProcessID             *int                   `json:"processId"`
	RootPath              *string                `json:"rootPath,omitempty"`
	RootURI               string                 `json:"rootUri"`
	InitializationOptions interface{}            `json:"initializationOptions,omitempty"`
	Capabilities          ClientCapabilities     `json:"capabilities"`
	Trace                 string                 `json:"trace,omitempty"`
	WorkspaceFolders      []WorkspaceFolder      `json:"workspaceFolders,omitempty"`
}

// WorkspaceFolder represents a workspace folder
type WorkspaceFolder struct {
	URI  string `json:"uri"`
	Name string `json:"name"`
}

// ClientCapabilities represents client capabilities
type ClientCapabilities struct {
	Workspace    WorkspaceClientCapabilities    `json:"workspace,omitempty"`
	TextDocument TextDocumentClientCapabilities `json:"textDocument,omitempty"`
}

// WorkspaceClientCapabilities represents workspace capabilities
type WorkspaceClientCapabilities struct {
	ApplyEdit              bool                            `json:"applyEdit,omitempty"`
	WorkspaceEdit          *WorkspaceEditCapabilities      `json:"workspaceEdit,omitempty"`
	DidChangeConfiguration *DidChangeConfigurationCapabilities `json:"didChangeConfiguration,omitempty"`
}

// WorkspaceEditCapabilities represents workspace edit capabilities
type WorkspaceEditCapabilities struct {
	DocumentChanges bool `json:"documentChanges,omitempty"`
}

// DidChangeConfigurationCapabilities represents configuration change capabilities
type DidChangeConfigurationCapabilities struct {
	DynamicRegistration bool `json:"dynamicRegistration,omitempty"`
}

// TextDocumentClientCapabilities represents text document capabilities
type TextDocumentClientCapabilities struct {
	Synchronization    *TextDocumentSyncCapabilities `json:"synchronization,omitempty"`
	Completion         *CompletionCapabilities       `json:"completion,omitempty"`
	Hover              *HoverCapabilities            `json:"hover,omitempty"`
	Definition         *DefinitionCapabilities       `json:"definition,omitempty"`
	References         *ReferencesCapabilities       `json:"references,omitempty"`
	DocumentSymbol     *DocumentSymbolCapabilities   `json:"documentSymbol,omitempty"`
	Rename             *RenameCapabilities           `json:"rename,omitempty"`
}

// TextDocumentSyncCapabilities represents text document sync capabilities
type TextDocumentSyncCapabilities struct {
	DynamicRegistration bool `json:"dynamicRegistration,omitempty"`
	WillSave            bool `json:"willSave,omitempty"`
	WillSaveWaitUntil   bool `json:"willSaveWaitUntil,omitempty"`
	DidSave             bool `json:"didSave,omitempty"`
}

// CompletionCapabilities represents completion capabilities
type CompletionCapabilities struct {
	DynamicRegistration bool `json:"dynamicRegistration,omitempty"`
}

// HoverCapabilities represents hover capabilities
type HoverCapabilities struct {
	DynamicRegistration bool `json:"dynamicRegistration,omitempty"`
}

// DefinitionCapabilities represents definition capabilities
type DefinitionCapabilities struct {
	DynamicRegistration bool `json:"dynamicRegistration,omitempty"`
}

// ReferencesCapabilities represents references capabilities
type ReferencesCapabilities struct {
	DynamicRegistration bool `json:"dynamicRegistration,omitempty"`
}

// DocumentSymbolCapabilities represents document symbol capabilities
type DocumentSymbolCapabilities struct {
	DynamicRegistration          bool `json:"dynamicRegistration,omitempty"`
	HierarchicalDocumentSymbolSupport bool `json:"hierarchicalDocumentSymbolSupport,omitempty"`
}

// RenameCapabilities represents rename capabilities
type RenameCapabilities struct {
	DynamicRegistration bool `json:"dynamicRegistration,omitempty"`
	PrepareSupport      bool `json:"prepareSupport,omitempty"`
}

// InitializeResult represents initialization result
type InitializeResult struct {
	Capabilities ServerCapabilities `json:"capabilities"`
	ServerInfo   *ServerInfo        `json:"serverInfo,omitempty"`
}

// ServerInfo represents server information
type ServerInfo struct {
	Name    string `json:"name"`
	Version string `json:"version,omitempty"`
}

// ServerCapabilities represents server capabilities
type ServerCapabilities struct {
	TextDocumentSync   interface{}            `json:"textDocumentSync,omitempty"`
	CompletionProvider interface{}            `json:"completionProvider,omitempty"`
	HoverProvider      interface{}            `json:"hoverProvider,omitempty"`
	DefinitionProvider interface{}            `json:"definitionProvider,omitempty"`
	ReferencesProvider interface{}            `json:"referencesProvider,omitempty"`
	DocumentSymbolProvider interface{}        `json:"documentSymbolProvider,omitempty"`
	RenameProvider     interface{}            `json:"renameProvider,omitempty"`
}

// DidOpenTextDocumentParams represents parameters for didOpen notification
type DidOpenTextDocumentParams struct {
	TextDocument TextDocumentItem `json:"textDocument"`
}

// TextDocumentItem represents a text document
type TextDocumentItem struct {
	URI        string `json:"uri"`
	LanguageID string `json:"languageId"`
	Version    int    `json:"version"`
	Text       string `json:"text"`
}

// DidChangeTextDocumentParams represents parameters for didChange notification
type DidChangeTextDocumentParams struct {
	TextDocument   VersionedTextDocumentIdentifier  `json:"textDocument"`
	ContentChanges []TextDocumentContentChangeEvent `json:"contentChanges"`
}

// VersionedTextDocumentIdentifier represents a versioned text document
type VersionedTextDocumentIdentifier struct {
	URI     string `json:"uri"`
	Version int    `json:"version"`
}

// TextDocumentContentChangeEvent represents a content change event
type TextDocumentContentChangeEvent struct {
	Range       *Range `json:"range,omitempty"`
	RangeLength *int   `json:"rangeLength,omitempty"`
	Text        string `json:"text"`
}

// DidCloseTextDocumentParams represents parameters for didClose notification
type DidCloseTextDocumentParams struct {
	TextDocument TextDocumentIdentifier `json:"textDocument"`
}

// TextDocumentIdentifier represents a text document identifier
type TextDocumentIdentifier struct {
	URI string `json:"uri"`
}

// DocumentSymbolParams represents parameters for document symbol request
type DocumentSymbolParams struct {
	TextDocument TextDocumentIdentifier `json:"textDocument"`
}

// DefinitionParams represents parameters for definition request
type DefinitionParams struct {
	TextDocument TextDocumentIdentifier `json:"textDocument"`
	Position     Position               `json:"position"`
}

// ReferenceParams represents parameters for references request
type ReferenceParams struct {
	TextDocument TextDocumentIdentifier `json:"textDocument"`
	Position     Position               `json:"position"`
	Context      ReferenceContext       `json:"context"`
}

// ReferenceContext represents reference context
type ReferenceContext struct {
	IncludeDeclaration bool `json:"includeDeclaration"`
}

// HoverParams represents parameters for hover request
type HoverParams struct {
	TextDocument TextDocumentIdentifier `json:"textDocument"`
	Position     Position               `json:"position"`
}

// RenameParams represents parameters for rename request
type RenameParams struct {
	TextDocument TextDocumentIdentifier `json:"textDocument"`
	Position     Position               `json:"position"`
	NewName      string                 `json:"newName"`
}

// JSONRPCMessage represents a JSON-RPC message
type JSONRPCMessage struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      interface{}     `json:"id,omitempty"`
	Method  string          `json:"method,omitempty"`
	Params  json.RawMessage `json:"params,omitempty"`
	Result  json.RawMessage `json:"result,omitempty"`
	Error   *JSONRPCError   `json:"error,omitempty"`
}

// JSONRPCError represents a JSON-RPC error
type JSONRPCError struct {
	Code    int         `json:"code"`
	Message string      `json:"message"`
	Data    interface{} `json:"data,omitempty"`
}

// Error returns the error message
func (e *JSONRPCError) Error() string {
	return fmt.Sprintf("JSON-RPC error %d: %s", e.Code, e.Message)
}
