MANDATORY: When accessing project context or relevant information stored in .serena/memories,
ALWAYS use Serena's read_memory MCP tool instead of reading files directly. This is required
to optimize token usage and reduce context bloat.

Only fall back to normal file reading tools if the read_memory tool is unavailable.
