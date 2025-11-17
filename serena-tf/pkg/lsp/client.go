package lsp

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
)

// Client represents an LSP client
type Client struct {
	cmd            *exec.Cmd
	stdin          io.WriteCloser
	stdout         io.ReadCloser
	stderr         io.ReadCloser
	nextID         atomic.Int64
	pendingCalls   map[interface{}]chan *JSONRPCMessage
	pendingMutex   sync.RWMutex
	running        bool
	runningMutex   sync.Mutex
	ctx            context.Context
	cancel         context.CancelFunc
	rootURI        string
	capabilities   *ServerCapabilities
}

// NewClient creates a new LSP client
func NewClient(command string, args []string, rootURI string) (*Client, error) {
	ctx, cancel := context.WithCancel(context.Background())

	cmd := exec.CommandContext(ctx, command, args...)

	stdin, err := cmd.StdinPipe()
	if err != nil {
		cancel()
		return nil, fmt.Errorf("failed to create stdin pipe: %w", err)
	}

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		cancel()
		return nil, fmt.Errorf("failed to create stdout pipe: %w", err)
	}

	stderr, err := cmd.StderrPipe()
	if err != nil {
		cancel()
		return nil, fmt.Errorf("failed to create stderr pipe: %w", err)
	}

	client := &Client{
		cmd:          cmd,
		stdin:        stdin,
		stdout:       stdout,
		stderr:       stderr,
		pendingCalls: make(map[interface{}]chan *JSONRPCMessage),
		ctx:          ctx,
		cancel:       cancel,
		rootURI:      rootURI,
	}

	return client, nil
}

// Start starts the LSP client
func (c *Client) Start() error {
	c.runningMutex.Lock()
	defer c.runningMutex.Unlock()

	if c.running {
		return fmt.Errorf("client already running")
	}

	if err := c.cmd.Start(); err != nil {
		return fmt.Errorf("failed to start LSP server: %w", err)
	}

	c.running = true

	// Start reading responses
	go c.readLoop()

	// Start reading stderr
	go c.readStderr()

	return nil
}

// Initialize sends the initialize request
func (c *Client) Initialize() (*InitializeResult, error) {
	params := InitializeParams{
		RootURI: c.rootURI,
		Capabilities: ClientCapabilities{
			TextDocument: TextDocumentClientCapabilities{
				Synchronization: &TextDocumentSyncCapabilities{
					DynamicRegistration: false,
					DidSave:             true,
				},
				DocumentSymbol: &DocumentSymbolCapabilities{
					DynamicRegistration:          false,
					HierarchicalDocumentSymbolSupport: true,
				},
				Definition: &DefinitionCapabilities{
					DynamicRegistration: false,
				},
				References: &ReferencesCapabilities{
					DynamicRegistration: false,
				},
				Hover: &HoverCapabilities{
					DynamicRegistration: false,
				},
				Rename: &RenameCapabilities{
					DynamicRegistration: false,
				},
			},
		},
	}

	response, err := c.Call("initialize", params)
	if err != nil {
		return nil, err
	}

	var result InitializeResult
	if err := json.Unmarshal(response.Result, &result); err != nil {
		return nil, fmt.Errorf("failed to unmarshal initialize result: %w", err)
	}

	c.capabilities = &result.Capabilities

	// Send initialized notification
	if err := c.Notify("initialized", map[string]interface{}{}); err != nil {
		return nil, err
	}

	return &result, nil
}

// Call sends a request and waits for response
func (c *Client) Call(method string, params interface{}) (*JSONRPCMessage, error) {
	id := c.nextID.Add(1)

	paramsJSON, err := json.Marshal(params)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal params: %w", err)
	}

	msg := JSONRPCMessage{
		JSONRPC: "2.0",
		ID:      id,
		Method:  method,
		Params:  paramsJSON,
	}

	responseChan := make(chan *JSONRPCMessage, 1)

	c.pendingMutex.Lock()
	c.pendingCalls[id] = responseChan
	c.pendingMutex.Unlock()

	if err := c.send(&msg); err != nil {
		c.pendingMutex.Lock()
		delete(c.pendingCalls, id)
		c.pendingMutex.Unlock()
		return nil, err
	}

	response := <-responseChan

	if response.Error != nil {
		return nil, response.Error
	}

	return response, nil
}

// Notify sends a notification (no response expected)
func (c *Client) Notify(method string, params interface{}) error {
	paramsJSON, err := json.Marshal(params)
	if err != nil {
		return fmt.Errorf("failed to marshal params: %w", err)
	}

	msg := JSONRPCMessage{
		JSONRPC: "2.0",
		Method:  method,
		Params:  paramsJSON,
	}

	return c.send(&msg)
}

// send sends a message to the server
func (c *Client) send(msg *JSONRPCMessage) error {
	data, err := json.Marshal(msg)
	if err != nil {
		return fmt.Errorf("failed to marshal message: %w", err)
	}

	header := fmt.Sprintf("Content-Length: %d\r\n\r\n", len(data))

	c.runningMutex.Lock()
	defer c.runningMutex.Unlock()

	if !c.running {
		return fmt.Errorf("client not running")
	}

	if _, err := c.stdin.Write([]byte(header)); err != nil {
		return fmt.Errorf("failed to write header: %w", err)
	}

	if _, err := c.stdin.Write(data); err != nil {
		return fmt.Errorf("failed to write data: %w", err)
	}

	return nil
}

// readLoop reads responses from the server
func (c *Client) readLoop() {
	reader := bufio.NewReader(c.stdout)

	for {
		select {
		case <-c.ctx.Done():
			return
		default:
		}

		// Read headers
		headers := make(map[string]string)
		for {
			line, err := reader.ReadString('\n')
			if err != nil {
				if err != io.EOF {
					log.Printf("Error reading header: %v", err)
				}
				return
			}

			line = strings.TrimSpace(line)
			if line == "" {
				break
			}

			parts := strings.SplitN(line, ":", 2)
			if len(parts) == 2 {
				headers[strings.TrimSpace(parts[0])] = strings.TrimSpace(parts[1])
			}
		}

		// Get content length
		contentLengthStr, ok := headers["Content-Length"]
		if !ok {
			continue
		}

		contentLength, err := strconv.Atoi(contentLengthStr)
		if err != nil {
			log.Printf("Invalid Content-Length: %v", err)
			continue
		}

		// Read content
		content := make([]byte, contentLength)
		if _, err := io.ReadFull(reader, content); err != nil {
			log.Printf("Error reading content: %v", err)
			return
		}

		// Parse message
		var msg JSONRPCMessage
		if err := json.Unmarshal(content, &msg); err != nil {
			log.Printf("Error unmarshaling message: %v", err)
			continue
		}

		// Handle message
		if msg.ID != nil {
			// Response to a call
			c.pendingMutex.Lock()
			if ch, ok := c.pendingCalls[msg.ID]; ok {
				ch <- &msg
				delete(c.pendingCalls, msg.ID)
			}
			c.pendingMutex.Unlock()
		} else {
			// Notification from server
			// Could handle server notifications here if needed
		}
	}
}

// readStderr reads stderr from the server
func (c *Client) readStderr() {
	scanner := bufio.NewScanner(c.stderr)
	for scanner.Scan() {
		log.Printf("[LSP stderr] %s", scanner.Text())
	}
}

// DidOpen sends a didOpen notification
func (c *Client) DidOpen(uri, languageID, text string) error {
	params := DidOpenTextDocumentParams{
		TextDocument: TextDocumentItem{
			URI:        uri,
			LanguageID: languageID,
			Version:    1,
			Text:       text,
		},
	}

	return c.Notify("textDocument/didOpen", params)
}

// DidChange sends a didChange notification
func (c *Client) DidChange(uri string, version int, text string) error {
	params := DidChangeTextDocumentParams{
		TextDocument: VersionedTextDocumentIdentifier{
			URI:     uri,
			Version: version,
		},
		ContentChanges: []TextDocumentContentChangeEvent{
			{
				Text: text,
			},
		},
	}

	return c.Notify("textDocument/didChange", params)
}

// DidClose sends a didClose notification
func (c *Client) DidClose(uri string) error {
	params := DidCloseTextDocumentParams{
		TextDocument: TextDocumentIdentifier{
			URI: uri,
		},
	}

	return c.Notify("textDocument/didClose", params)
}

// DocumentSymbols requests document symbols
func (c *Client) DocumentSymbols(uri string) ([]DocumentSymbol, error) {
	params := DocumentSymbolParams{
		TextDocument: TextDocumentIdentifier{
			URI: uri,
		},
	}

	response, err := c.Call("textDocument/documentSymbol", params)
	if err != nil {
		return nil, err
	}

	var symbols []DocumentSymbol
	if err := json.Unmarshal(response.Result, &symbols); err != nil {
		return nil, fmt.Errorf("failed to unmarshal document symbols: %w", err)
	}

	return symbols, nil
}

// Definition requests the definition of a symbol
func (c *Client) Definition(uri string, position Position) ([]Location, error) {
	params := DefinitionParams{
		TextDocument: TextDocumentIdentifier{
			URI: uri,
		},
		Position: position,
	}

	response, err := c.Call("textDocument/definition", params)
	if err != nil {
		return nil, err
	}

	// Handle both single location and array of locations
	var locations []Location
	var singleLocation Location

	if err := json.Unmarshal(response.Result, &singleLocation); err == nil && singleLocation.URI != "" {
		locations = []Location{singleLocation}
	} else if err := json.Unmarshal(response.Result, &locations); err != nil {
		return nil, fmt.Errorf("failed to unmarshal definition: %w", err)
	}

	return locations, nil
}

// References requests references to a symbol
func (c *Client) References(uri string, position Position, includeDeclaration bool) ([]Location, error) {
	params := ReferenceParams{
		TextDocument: TextDocumentIdentifier{
			URI: uri,
		},
		Position: position,
		Context: ReferenceContext{
			IncludeDeclaration: includeDeclaration,
		},
	}

	response, err := c.Call("textDocument/references", params)
	if err != nil {
		return nil, err
	}

	var locations []Location
	if err := json.Unmarshal(response.Result, &locations); err != nil {
		return nil, fmt.Errorf("failed to unmarshal references: %w", err)
	}

	return locations, nil
}

// Hover requests hover information
func (c *Client) Hover(uri string, position Position) (*Hover, error) {
	params := HoverParams{
		TextDocument: TextDocumentIdentifier{
			URI: uri,
		},
		Position: position,
	}

	response, err := c.Call("textDocument/hover", params)
	if err != nil {
		return nil, err
	}

	if bytes.Equal(response.Result, []byte("null")) {
		return nil, nil
	}

	var hover Hover
	if err := json.Unmarshal(response.Result, &hover); err != nil {
		return nil, fmt.Errorf("failed to unmarshal hover: %w", err)
	}

	return &hover, nil
}

// Rename requests to rename a symbol
func (c *Client) Rename(uri string, position Position, newName string) (*WorkspaceEdit, error) {
	params := RenameParams{
		TextDocument: TextDocumentIdentifier{
			URI: uri,
		},
		Position: position,
		NewName:  newName,
	}

	response, err := c.Call("textDocument/rename", params)
	if err != nil {
		return nil, err
	}

	var edit WorkspaceEdit
	if err := json.Unmarshal(response.Result, &edit); err != nil {
		return nil, fmt.Errorf("failed to unmarshal workspace edit: %w", err)
	}

	return &edit, nil
}

// Shutdown sends a shutdown request
func (c *Client) Shutdown() error {
	_, err := c.Call("shutdown", nil)
	return err
}

// Exit sends an exit notification
func (c *Client) Exit() error {
	return c.Notify("exit", nil)
}

// Close closes the client
func (c *Client) Close() error {
	c.runningMutex.Lock()
	defer c.runningMutex.Unlock()

	if !c.running {
		return nil
	}

	// Send shutdown and exit
	_ = c.Shutdown()
	_ = c.Exit()

	c.cancel()
	c.running = false

	// Close pipes
	_ = c.stdin.Close()

	// Wait for process to exit
	_ = c.cmd.Wait()

	return nil
}

// GetCapabilities returns the server capabilities
func (c *Client) GetCapabilities() *ServerCapabilities {
	return c.capabilities
}
