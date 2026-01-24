"""Tests for ToolDependencyAnalyzer."""

from murena.tool_dependency_analyzer import DependencyGraph, ToolCall, ToolDependencyAnalyzer


class TestDependencyGraph:
    """Test dependency graph wave generation."""

    def test_no_dependencies(self):
        """Test tools with no dependencies execute in one wave."""
        graph = DependencyGraph(dependencies={0: [], 1: [], 2: []})

        waves = graph.get_execution_waves()

        assert len(waves) == 1
        assert set(waves[0]) == {0, 1, 2}

    def test_sequential_dependencies(self):
        """Test fully sequential dependencies."""
        # 0 -> 1 -> 2 (each depends on previous)
        graph = DependencyGraph(dependencies={0: [], 1: [0], 2: [1]})

        waves = graph.get_execution_waves()

        assert len(waves) == 3
        assert waves[0] == [0]
        assert waves[1] == [1]
        assert waves[2] == [2]

    def test_parallel_with_join(self):
        """Test parallel execution with a join point."""
        # 0, 1 run in parallel, then 2 depends on both
        graph = DependencyGraph(dependencies={0: [], 1: [], 2: [0, 1]})

        waves = graph.get_execution_waves()

        assert len(waves) == 2
        assert set(waves[0]) == {0, 1}
        assert waves[1] == [2]

    def test_diamond_pattern(self):
        """Test diamond dependency pattern."""
        # 0 -> 1, 2 -> 3 (diamond shape)
        graph = DependencyGraph(dependencies={0: [], 1: [0], 2: [0], 3: [1, 2]})

        waves = graph.get_execution_waves()

        assert len(waves) == 3
        assert waves[0] == [0]
        assert set(waves[1]) == {1, 2}
        assert waves[2] == [3]


class TestToolDependencyAnalyzer:
    """Test tool dependency analysis."""

    def test_independent_reads(self):
        """Test that independent reads have no dependencies."""
        analyzer = ToolDependencyAnalyzer()

        tools = [
            ToolCall(tool_name="read_file", params={"file_path": "a.py"}, index=0),
            ToolCall(tool_name="read_file", params={"file_path": "b.py"}, index=1),
            ToolCall(tool_name="read_file", params={"file_path": "c.py"}, index=2),
        ]

        graph = analyzer.analyze(tools)

        # All should have no dependencies
        assert graph.dependencies[0] == []
        assert graph.dependencies[1] == []
        assert graph.dependencies[2] == []

    def test_read_after_write(self):
        """Test read-after-write dependency."""
        analyzer = ToolDependencyAnalyzer()

        tools = [
            ToolCall(tool_name="edit_file", params={"file_path": "a.py"}, index=0),
            ToolCall(tool_name="read_file", params={"file_path": "a.py"}, index=1),
        ]

        graph = analyzer.analyze(tools)

        # Read should depend on write
        assert graph.dependencies[0] == []
        assert graph.dependencies[1] == [0]

    def test_write_after_write(self):
        """Test write-after-write dependency."""
        analyzer = ToolDependencyAnalyzer()

        tools = [
            ToolCall(tool_name="edit_file", params={"file_path": "a.py"}, index=0),
            ToolCall(tool_name="edit_file", params={"file_path": "a.py"}, index=1),
        ]

        graph = analyzer.analyze(tools)

        # Second write depends on first
        assert graph.dependencies[0] == []
        assert graph.dependencies[1] == [0]

    def test_symbol_operations_same_file(self):
        """Test that symbol operations on same file are sequential."""
        analyzer = ToolDependencyAnalyzer()

        tools = [
            ToolCall(tool_name="find_symbol", params={"relative_path": "a.py"}, index=0),
            ToolCall(tool_name="replace_symbol_body", params={"relative_path": "a.py"}, index=1),
            ToolCall(tool_name="find_symbol", params={"relative_path": "a.py"}, index=2),
        ]

        graph = analyzer.analyze(tools)

        # All should be sequential
        assert graph.dependencies[0] == []
        assert 0 in graph.dependencies[1]
        assert 0 in graph.dependencies[2] and 1 in graph.dependencies[2]

    def test_mixed_files(self):
        """Test operations on different files can run in parallel."""
        analyzer = ToolDependencyAnalyzer()

        tools = [
            ToolCall(tool_name="edit_file", params={"file_path": "a.py"}, index=0),
            ToolCall(tool_name="edit_file", params={"file_path": "b.py"}, index=1),
            ToolCall(tool_name="read_file", params={"file_path": "a.py"}, index=2),
            ToolCall(tool_name="read_file", params={"file_path": "b.py"}, index=3),
        ]

        graph = analyzer.analyze(tools)

        # Edits can run in parallel
        assert graph.dependencies[0] == []
        assert graph.dependencies[1] == []

        # Read a depends on edit a, but not edit b
        assert graph.dependencies[2] == [0]

        # Read b depends on edit b, but not edit a
        assert graph.dependencies[3] == [1]
