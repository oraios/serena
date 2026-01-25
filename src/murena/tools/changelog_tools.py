"""Tools for managing CHANGELOG.md"""

from datetime import datetime
from pathlib import Path

from murena.tools import Tool, ToolMarkerCanEdit


class UpdateChangelogTool(Tool, ToolMarkerCanEdit):
    """
    Updates CHANGELOG.md with a new entry based on recent work.
    Adds entry under the "Unreleased" section with current date.
    """

    def apply(self, description: str, category: str = "Changed") -> str:
        """
        Add entry to CHANGELOG.md

        :param description: Description of the change (e.g., "Improved test performance by 10x")
        :param category: Category of change: Added, Changed, Fixed, Deprecated, Removed, Security
        :return: confirmation message
        """
        project = self.agent.get_active_project_or_raise()
        changelog_path = Path(project.project_root) / "CHANGELOG.md"

        if not changelog_path.exists():
            return f"CHANGELOG.md not found at {changelog_path}"

        # Read existing content
        content = changelog_path.read_text()

        # Find "## [Unreleased]" section
        if "## [Unreleased]" not in content:
            return "CHANGELOG.md doesn't have ## [Unreleased] section"

        # Validate category
        valid_categories = ["Added", "Changed", "Fixed", "Deprecated", "Removed", "Security"]
        if category not in valid_categories:
            return f"Invalid category '{category}'. Must be one of: {', '.join(valid_categories)}"

        # Create new entry
        date_str = datetime.now().strftime("%Y-%m-%d")
        new_entry = f"- {description} ({date_str})"

        # Find or create category section under Unreleased
        category_header = f"### {category}"

        # Insert entry
        lines = content.split("\n")
        insert_idx = None

        for i, line in enumerate(lines):
            if line.strip() == "## [Unreleased]":
                # Look for category header after this
                for j in range(i + 1, len(lines)):
                    if lines[j].strip() == category_header:
                        # Found category, insert after it
                        insert_idx = j + 1
                        break
                    if lines[j].startswith("## "):
                        # Reached next version, need to create category
                        # Insert blank line, category header, and entry
                        lines.insert(i + 1, "")
                        lines.insert(i + 2, category_header)
                        insert_idx = i + 3
                        break
                    if lines[j].startswith("### ") and lines[j].strip() != category_header:
                        # Found a different category, insert our category before it
                        lines.insert(j, "")
                        lines.insert(j + 1, category_header)
                        insert_idx = j + 2
                        break

                # If no section found and we're at the end, create the category
                if insert_idx is None:
                    lines.insert(i + 1, "")
                    lines.insert(i + 2, category_header)
                    insert_idx = i + 3
                break

        if insert_idx is None:
            return "Failed to find insertion point in CHANGELOG.md"

        lines.insert(insert_idx, new_entry)

        # Write back
        changelog_path.write_text("\n".join(lines))

        return f"✅ Added to CHANGELOG.md under {category}: {description}"
