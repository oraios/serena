package mcp

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os"
	"strconv"
	"strings"
	"sync/atomic"

	"github.com/TahirRiaz/serena-tf/pkg/tools"
)

// Server represents an MCP server
type Server struct {
	stdin      io.Reader
	stdout     io.Writer
	agent      Agent
	nextID     atomic.Int64
	tools      []tools.Tool
}

// Agent interface for the server
type Agent interface {
	GetTools() []tools.Tool
	GetSystemPrompt() string
}

// NewServer creates a new MCP server
func NewServer(agent Agent) *Server {
	return &Server{
		stdin:  os.Stdin,
		stdout: os.Stdout,
		agent:  agent,
		tools:  agent.GetTools(),
	}
}

// Start starts the MCP server
func (s *Server) Start(ctx context.Context) error {
	log.Println("MCP Server starting...")

	reader := bufio.NewReader(s.stdin)

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		// Read headers
		headers := make(map[string]string)
		for {
			line, err := reader.ReadString('\n')
			if err != nil {
				if err == io.EOF {
					return nil
				}
				return fmt.Errorf("error reading header: %w", err)
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
			return err
		}

		// Parse request
		var request JSONRPCRequest
		if err := json.Unmarshal(content, &request); err != nil {
			log.Printf("Error unmarshaling request: %v", err)
			continue
		}

		// Handle request
		response := s.handleRequest(ctx, &request)

		// Send response
		if err := s.sendResponse(response); err != nil {
			log.Printf("Error sending response: %v", err)
		}
	}
}

// handleRequest handles a JSON-RPC request
func (s *Server) handleRequest(ctx context.Context, req *JSONRPCRequest) *JSONRPCResponse {
	switch req.Method {
	case "initialize":
		return s.handleInitialize(req)
	case "tools/list":
		return s.handleToolsList(req)
	case "tools/call":
		return s.handleToolsCall(ctx, req)
	case "prompts/list":
		return s.handlePromptsList(req)
	case "prompts/get":
		return s.handlePromptsGet(req)
	default:
		return &JSONRPCResponse{
			JSONRPC: "2.0",
			ID:      req.ID,
			Error: &JSONRPCError{
				Code:    -32601,
				Message: fmt.Sprintf("Method not found: %s", req.Method),
			},
		}
	}
}

// handleInitialize handles the initialize request
func (s *Server) handleInitialize(req *JSONRPCRequest) *JSONRPCResponse {
	result := map[string]interface{}{
		"protocolVersion": "2024-11-05",
		"capabilities": map[string]interface{}{
			"tools":   map[string]interface{}{},
			"prompts": map[string]interface{}{},
		},
		"serverInfo": map[string]interface{}{
			"name":    "serena-tf",
			"version": "1.0.0",
		},
	}

	resultJSON, _ := json.Marshal(result)

	return &JSONRPCResponse{
		JSONRPC: "2.0",
		ID:      req.ID,
		Result:  resultJSON,
	}
}

// handleToolsList handles the tools/list request
func (s *Server) handleToolsList(req *JSONRPCRequest) *JSONRPCResponse {
	var mcpTools []MCPTool

	for _, tool := range s.tools {
		mcpTools = append(mcpTools, s.convertToolToMCP(tool))
	}

	result := map[string]interface{}{
		"tools": mcpTools,
	}

	resultJSON, _ := json.Marshal(result)

	return &JSONRPCResponse{
		JSONRPC: "2.0",
		ID:      req.ID,
		Result:  resultJSON,
	}
}

// handleToolsCall handles the tools/call request
func (s *Server) handleToolsCall(ctx context.Context, req *JSONRPCRequest) *JSONRPCResponse {
	var params struct {
		Name      string                 `json:"name"`
		Arguments map[string]interface{} `json:"arguments"`
	}

	if err := json.Unmarshal(req.Params, &params); err != nil {
		return &JSONRPCResponse{
			JSONRPC: "2.0",
			ID:      req.ID,
			Error: &JSONRPCError{
				Code:    -32602,
				Message: "Invalid params",
			},
		}
	}

	// Find tool
	var tool tools.Tool
	for _, t := range s.tools {
		if t.Name() == params.Name {
			tool = t
			break
		}
	}

	if tool == nil {
		return &JSONRPCResponse{
			JSONRPC: "2.0",
			ID:      req.ID,
			Error: &JSONRPCError{
				Code:    -32602,
				Message: fmt.Sprintf("Tool not found: %s", params.Name),
			},
		}
	}

	// Execute tool
	output, err := tool.Apply(ctx, params.Arguments)

	result := map[string]interface{}{
		"content": []map[string]interface{}{
			{
				"type": "text",
				"text": output,
			},
		},
	}

	if err != nil {
		result["isError"] = true
		result["content"] = []map[string]interface{}{
			{
				"type": "text",
				"text": err.Error(),
			},
		}
	}

	resultJSON, _ := json.Marshal(result)

	return &JSONRPCResponse{
		JSONRPC: "2.0",
		ID:      req.ID,
		Result:  resultJSON,
	}
}

// handlePromptsList handles the prompts/list request
func (s *Server) handlePromptsList(req *JSONRPCRequest) *JSONRPCResponse {
	result := map[string]interface{}{
		"prompts": []map[string]interface{}{
			{
				"name":        "system",
				"description": "System prompt for the agent",
			},
		},
	}

	resultJSON, _ := json.Marshal(result)

	return &JSONRPCResponse{
		JSONRPC: "2.0",
		ID:      req.ID,
		Result:  resultJSON,
	}
}

// handlePromptsGet handles the prompts/get request
func (s *Server) handlePromptsGet(req *JSONRPCRequest) *JSONRPCResponse {
	systemPrompt := s.agent.GetSystemPrompt()

	result := map[string]interface{}{
		"messages": []map[string]interface{}{
			{
				"role": "system",
				"content": map[string]interface{}{
					"type": "text",
					"text": systemPrompt,
				},
			},
		},
	}

	resultJSON, _ := json.Marshal(result)

	return &JSONRPCResponse{
		JSONRPC: "2.0",
		ID:      req.ID,
		Result:  resultJSON,
	}
}

// convertToolToMCP converts a tool to MCP format
func (s *Server) convertToolToMCP(tool tools.Tool) MCPTool {
	return MCPTool{
		Name:        tool.Name(),
		Description: tool.Description(),
		InputSchema: tool.Schema(),
	}
}

// sendResponse sends a JSON-RPC response
func (s *Server) sendResponse(resp *JSONRPCResponse) error {
	data, err := json.Marshal(resp)
	if err != nil {
		return err
	}

	header := fmt.Sprintf("Content-Length: %d\r\n\r\n", len(data))

	if _, err := s.stdout.Write([]byte(header)); err != nil {
		return err
	}

	if _, err := s.stdout.Write(data); err != nil {
		return err
	}

	return nil
}

// JSONRPCRequest represents a JSON-RPC request
type JSONRPCRequest struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      interface{}     `json:"id,omitempty"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params,omitempty"`
}

// JSONRPCResponse represents a JSON-RPC response
type JSONRPCResponse struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      interface{}     `json:"id,omitempty"`
	Result  json.RawMessage `json:"result,omitempty"`
	Error   *JSONRPCError   `json:"error,omitempty"`
}

// JSONRPCError represents a JSON-RPC error
type JSONRPCError struct {
	Code    int         `json:"code"`
	Message string      `json:"message"`
	Data    interface{} `json:"data,omitempty"`
}

// MCPTool represents a tool in MCP format
type MCPTool struct {
	Name        string             `json:"name"`
	Description string             `json:"description"`
	InputSchema *tools.ToolSchema  `json:"inputSchema"`
}
