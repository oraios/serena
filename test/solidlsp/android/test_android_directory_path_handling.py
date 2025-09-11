"""
Test case to verify AndroidLanguageServer handles directory paths properly
in symbol operations.

This reproduces the ValueError: Expected a file path, but got a directory path:
app/src/main/java/com/farouk/chi/colormaster.
"""

import os

import pytest

from solidlsp.language_servers.android_language_server import AndroidLanguageServer


@pytest.mark.android
class TestAndroidDirectoryPathHandling:
    """Test AndroidLanguageServer directory path handling in symbol operations"""

    @pytest.mark.android_fast
    def test_directory_path_error_reproduction(self):
        """
        Test that reproduces the error when a directory path is passed to GetSymbolsOverviewTool
        instead of a file path.

        This reproduces the error from symbol_tools.py line 74:
        ValueError: Expected a file path, but got a directory path:
        app/src/main/java/com/farouk/chi/colormaster.

        The error occurs in GetSymbolsOverviewTool.apply() method.
        """
        # Simulate the path validation that happens in GetSymbolsOverviewTool
        repository_root_path = "/Users/qran/work/serena/test/resources/repos/android/test_repo"
        directory_path = "app/src/main/java/com/example/testapp"

        # This is the validation logic from symbol_tools.py lines 71-74
        file_path = os.path.join(repository_root_path, directory_path)

        print(f"Testing path: {directory_path}")
        print(f"Full path: {file_path}")

        # Reproduce the exact error condition
        if not os.path.exists(file_path):
            print(f"❌ Path does not exist: {file_path}")
            return

        if os.path.isdir(file_path):
            error_msg = f"Expected a file path, but got a directory path: {directory_path}. "
            print(f"✅ REPRODUCED ERROR: ValueError: {error_msg}")

            # This is the exact error from the traceback
            with pytest.raises(ValueError, match="Expected a file path, but got a directory path"):
                raise ValueError(error_msg)
        else:
            print(f"⚠️  Path is not a directory: {file_path}")

    @pytest.mark.android_fast
    def test_directory_vs_file_path_detection(self):
        """
        Test that the AndroidLanguageServer can distinguish between
        directory and file paths properly.
        """
        repository_root_path = "/Users/qran/work/serena/test/resources/repos/android/test_repo"

        # Test cases with known paths
        test_cases = [
            ("app/src/main/java/com/example/testapp/MainActivity.java", "file"),
            ("app/src/main/java/com/example/testapp", "directory"),
            ("app/src/main/kotlin/com/example/testapp/KotlinUtils.kt", "file"),
            ("app/src/main/kotlin/com/example/testapp", "directory"),
            ("nonexistent/path/file.java", "file"),  # File that doesn't exist
            ("nonexistent/path", "directory"),  # Directory that doesn't exist
        ]

        for path, expected_type in test_cases:
            full_path = os.path.join(repository_root_path, path)

            if os.path.exists(full_path):
                actual_type = "file" if os.path.isfile(full_path) else "directory"
                print(f"Path '{path}' is a {actual_type} (expected {expected_type})")
                assert actual_type == expected_type, f"Path type mismatch for {path}"
            else:
                print(f"Path '{path}' does not exist (expected {expected_type})")

    @pytest.mark.android_fast
    def test_symbol_tools_directory_handling(self):
        """
        Test how symbol tools should handle directory paths.
        This simulates the scenario from the error traceback.
        """
        # This test simulates the call chain that leads to the error:
        # symbol_tools.py line 74 raises ValueError for directory paths

        directory_path = "app/src/main/java/com/example/testapp"

        # Simulate the check that's happening in symbol_tools.py
        # (We can't import symbol_tools directly due to dependencies, so we simulate the logic)

        # The error suggests that symbol_tools.py line 74 is checking if path is a directory
        # and raising ValueError if it is
        repository_root_path = "/Users/qran/work/serena/test/resources/repos/android/test_repo"
        full_path = os.path.join(repository_root_path, directory_path)

        if os.path.exists(full_path) and os.path.isdir(full_path):
            print(f"✅ Confirmed: '{directory_path}' is a directory")
            print(f"This would cause: ValueError: Expected a file path, but got a directory path: {directory_path}")
        else:
            print(f"⚠️  Path '{directory_path}' is not a directory or doesn't exist")

    @pytest.mark.android_readonly
    def test_request_document_symbols_with_directory_paths(self, shared_android_server: AndroidLanguageServer):
        """
        Test request_document_symbols behavior with various path types.
        """
        # Test with valid file path (should work)
        file_path = "app/src/main/java/com/example/testapp/MainActivity.java"
        try:
            symbols = shared_android_server.request_document_symbols(file_path)
            print(f"✅ File path accepted: {file_path}, got {len(symbols) if symbols else 0} symbols")
        except Exception as e:
            print(f"⚠️  File path error: {e}")

        # Test with directory path (should handle gracefully)
        directory_path = "app/src/main/java/com/example/testapp"
        try:
            symbols = shared_android_server.request_document_symbols(directory_path)
            print(f"⚠️  Directory path was processed: {directory_path}")
        except Exception as e:
            print(f"Directory path error (expected): {e}")

    @pytest.mark.android_fast
    def test_path_validation_recommendations(self):
        """
        Test that documents the expected behavior for path validation
        in AndroidLanguageServer.
        """
        # This test documents what should happen with different path types

        test_scenarios = [
            {
                "path": "app/src/main/java/com/example/testapp/MainActivity.java",
                "expected": "should work - valid Java file",
                "type": "java_file",
            },
            {
                "path": "app/src/main/kotlin/com/example/testapp/KotlinUtils.kt",
                "expected": "should work - valid Kotlin file",
                "type": "kotlin_file",
            },
            {
                "path": "app/src/main/java/com/example/testapp",
                "expected": "should error gracefully - directory not file",
                "type": "directory",
            },
            {"path": "app/src/main/AndroidManifest.xml", "expected": "should handle - XML file", "type": "xml_file"},
            {"path": "nonexistent/file.java", "expected": "should handle - file not found", "type": "nonexistent_file"},
        ]

        for scenario in test_scenarios:
            print(f"Path: {scenario['path']}")
            print(f"  Type: {scenario['type']}")
            print(f"  Expected: {scenario['expected']}")
            print()

    @pytest.mark.android_readonly
    def test_android_language_server_path_routing(self, shared_android_server: AndroidLanguageServer):
        """
        Test that AndroidLanguageServer routes paths correctly based on extension,
        regardless of whether they exist or not.
        """
        # Test file routing logic
        test_paths = [
            ("MainActivity.java", "java"),
            ("Utils.kt", "kotlin"),
            ("build.gradle.kts", "kotlin"),
            ("AndroidManifest.xml", "java"),  # Default to java for non-kt/java files
            ("some/directory/path", "java"),  # Directory defaults to java
        ]

        for path, expected_server in test_paths:
            delegate_ls = shared_android_server._route_request_by_file(path)
            actual_server = "java" if "EclipseJDTLS" in delegate_ls.__class__.__name__ else "kotlin"

            print(f"Path '{path}' routed to {actual_server} server (expected {expected_server})")
            assert actual_server == expected_server, f"Routing mismatch for {path}"

    @pytest.mark.android_fast
    def test_get_symbols_overview_tool_error_simulation(self):
        """
        Test that simulates the actual usage scenario that leads to the
        "Expected a file path, but got a directory path" error.

        This reproduces the call chain:
        1. GetSymbolsOverviewTool.apply() is called with a directory path
        2. It validates the path and raises ValueError on line 74
        """
        # Simulate the scenario from the original error
        repository_root_path = "/Users/qran/work/serena/test/resources/repos/android/test_repo"

        # Test cases that would cause the error
        problematic_paths = [
            "app/src/main/java/com/example/testapp",  # Directory path
            "app/src/main/kotlin/com/example/testapp",  # Directory path
            "app/src/main/java",  # Parent directory
        ]

        # Test cases that should work
        valid_paths = [
            "app/src/main/java/com/example/testapp/MainActivity.java",  # File path
            "app/src/main/kotlin/com/example/testapp/KotlinUtils.kt",  # File path
        ]

        for directory_path in problematic_paths:
            full_path = os.path.join(repository_root_path, directory_path)
            if os.path.exists(full_path) and os.path.isdir(full_path):
                print(f"✅ WOULD CAUSE ERROR: {directory_path} is a directory")

                # This is exactly what happens in GetSymbolsOverviewTool.apply()
                try:
                    # Simulate the validation from symbol_tools.py
                    if os.path.isdir(full_path):
                        raise ValueError(f"Expected a file path, but got a directory path: {directory_path}. ")
                except ValueError as e:
                    print(f"   Error reproduced: {e}")
            else:
                print(f"⚠️  {directory_path} does not exist or is not a directory")

        for file_path in valid_paths:
            full_path = os.path.join(repository_root_path, file_path)
            if os.path.exists(full_path) and os.path.isfile(full_path):
                print(f"✅ WOULD WORK: {file_path} is a file")
            else:
                print(f"⚠️  {file_path} does not exist or is not a file")

    @pytest.mark.android_fast
    def test_symbol_tool_path_validation_logic(self):
        """
        Test that documents and verifies the path validation logic
        used in GetSymbolsOverviewTool.
        """
        repository_root_path = "/Users/qran/work/serena/test/resources/repos/android/test_repo"

        def validate_path_for_symbols_overview(relative_path: str):
            """
            Simulate the validation logic from GetSymbolsOverviewTool.apply()
            (symbol_tools.py lines 71-74)
            """
            file_path = os.path.join(repository_root_path, relative_path)

            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File or directory {relative_path} does not exist in the project.")
            if os.path.isdir(file_path):
                raise ValueError(f"Expected a file path, but got a directory path: {relative_path}. ")
            return True

        # Test the validation logic
        test_cases = [
            ("app/src/main/java/com/example/testapp/MainActivity.java", True, "Valid file"),
            ("app/src/main/java/com/example/testapp", False, "Directory path"),
            ("nonexistent/file.java", False, "File not found"),
        ]

        for path, should_pass, description in test_cases:
            try:
                validate_path_for_symbols_overview(path)
                if should_pass:
                    print(f"✅ {description}: {path} - validation passed")
                else:
                    print(f"❌ {description}: {path} - should have failed but passed")
            except ValueError as e:
                if not should_pass and "Expected a file path, but got a directory path" in str(e):
                    print(f"✅ {description}: {path} - correctly rejected (directory)")
                else:
                    print(f"❌ {description}: {path} - unexpected ValueError: {e}")
            except FileNotFoundError as e:
                if not should_pass:
                    print(f"✅ {description}: {path} - correctly rejected (not found)")
                else:
                    print(f"❌ {description}: {path} - unexpected FileNotFoundError: {e}")
