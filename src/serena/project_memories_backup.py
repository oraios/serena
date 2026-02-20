"""
MemoriesManager with directory grouping and frontmatter support.
Implements Issue #1055: https://github.com/oraios/serena/issues/1055
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any, List


class MemoriesManager:
    """
    Manages project memories with support for:
    - Directory grouping (e.g., "auth/login_logic")
    - Optional YAML frontmatter (e.g., summary field)
    - Topic-based filtering
    - Memory renaming/moving
    """

    def __init__(self, project_root: str):
        from serena.constants import SERENA_FILE_ENCODING
        from serena.paths import get_serena_managed_in_project_dir
        
        self._memory_dir = Path(get_serena_managed_in_project_dir(project_root)) / "memories"
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        self._encoding = SERENA_FILE_ENCODING

    def get_memory_file_path(self, name: str) -> Path:
        """
        Get the file path for a memory, supporting subdirectories.
        
        Args:
            name: Memory name, can include "/" for subdirectories 
                  (e.g., "auth/login_logic")
        
        Returns:
            Path to the memory file
        """
        # Strip .md extension if present
        name = name.replace(".md", "")
        
        # Split by "/" to handle subdirectories
        parts = name.split("/")
        filename = f"{parts[-1]}.md"
        
        if len(parts) > 1:
            # Create subdirectory path
            subdir = self._memory_dir / "/".join(parts[:-1])
            subdir.mkdir(parents=True, exist_ok=True)
            return subdir / filename
        
        return self._memory_dir / filename

    def parse_frontmatter(self, content: str) -> tuple[Optional[Dict[str, Any]], str]:
        """
        Parse YAML frontmatter from memory content.
        
        Args:
            content: Raw memory content
        
        Returns:
            Tuple of (frontmatter_dict or None, body_content)
        """
        if not content.startswith("---"):
            return None, content
        
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None, content
        
        try:
            import yaml
            frontmatter = yaml.safe_load(parts[1])
            body = parts[2].strip()
            return frontmatter if frontmatter else None, body
        except Exception:
            # If YAML parsing fails, return content as-is
            return None, content

    def load_memory(self, name: str) -> str:
        """
        Load a memory by name.
        
        Args:
            name: Memory name (can include subdirectories)
        
        Returns:
            Memory content
        """
        memory_file_path = self.get_memory_file_path(name)
        if not memory_file_path.exists():
            return f"Memory file {name} not found, consider creating it with the `write_memory` tool if you need it."
        with open(memory_file_path, encoding=self._encoding) as f:
            return f.read()

    def save_memory(self, name: str, content: str, summary: Optional[str] = None) -> str:
        """
        Save a memory with optional frontmatter summary.
        
        Args:
            name: Memory name (can include subdirectories)
            content: Memory content
            summary: Optional summary for frontmatter
        
        Returns:
            Success message
        """
        memory_file_path = self.get_memory_file_path(name)
        
        # Add frontmatter if summary is provided
        if summary:
            frontmatter = f"---\nsummary: {summary}\n---\n\n"
            content = frontmatter + content
        
        with open(memory_file_path, "w", encoding=self._encoding) as f:
            f.write(content)
        return f"Memory {name} written."

    def list_memories(self, topic: str = "") -> List[Dict[str, str]]:
        """
        List memories, optionally filtered by topic (subdirectory).
        
        Args:
            topic: Optional topic/subdirectory filter (e.g., "auth")
        
        Returns:
            List of memory info dicts with 'name' and optional 'summary'
        """
        memories = []
        
        if topic:
            # Only list memories in specified subdirectory
            search_dir = self._memory_dir / topic.replace("/", os.sep)
            if not search_dir.exists():
                return []
        else:
            search_dir = self._memory_dir
        
        # Recursively find all .md files
        for md_file in search_dir.rglob("*.md"):
            # Calculate relative path as memory name
            rel_path = md_file.relative_to(self._memory_dir)
            name = str(rel_path.with_suffix("")).replace(os.sep, "/")
            
            # Read and parse frontmatter
            content = md_file.read_text(encoding=self._encoding)
            frontmatter, _ = self.parse_frontmatter(content)
            
            memory_info = {"name": name}
            if frontmatter and "summary" in frontmatter:
                memory_info["summary"] = frontmatter["summary"]
            
            memories.append(memory_info)
        
        # Sort alphabetically by name
        return sorted(memories, key=lambda x: x["name"])

    def delete_memory(self, name: str) -> str:
        """
        Delete a memory by name.
        
        Args:
            name: Memory name
        
        Returns:
            Success message
        """
        memory_file_path = self.get_memory_file_path(name)
        if not memory_file_path.exists():
            return f"Memory {name} not found."
        memory_file_path.unlink()
        return f"Memory {name} deleted."

    def rename_memory(self, old_name: str, new_name: str) -> str:
        """
        Rename or move a memory file.
        
        Args:
            old_name: Current memory name
            new_name: New memory name (can include "/" to move to subdirectory)
        
        Returns:
            Success message
        """
        old_path = self.get_memory_file_path(old_name)
        new_path = self.get_memory_file_path(new_name)
        
        if not old_path.exists():
            return f"Memory {old_name} not found."
        
        # Ensure target directory exists
        new_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Move/rename the file
        old_path.rename(new_path)
        return f"Memory renamed from {old_name} to {new_name}."
