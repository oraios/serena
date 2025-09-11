"""
Test case to verify AndroidLanguageServer request_full_symbol_tree method
handles file path parameters correctly.

This reproduces the error:
ERROR: You passed a file explicitly, but it is ignored. This is probably an error.
File: app/src/main/java/com/farouk/chi/colormaster/CMApplication.kt
"""

import pytest

from solidlsp.language_servers.android_language_server import AndroidLanguageServer


@pytest.mark.android
class TestAndroidFullSymbolTreeFileParameter:
    """Test AndroidLanguageServer request_full_symbol_tree file parameter handling"""

    @pytest.mark.android_readonly
    def test_full_symbol_tree_with_specific_file_error_reproduction(self, shared_android_server: AndroidLanguageServer):
        """
        Test that reproduces the error when request_full_symbol_tree is called
        with a specific file path instead of a directory or None.

        This reproduces the error:
        ERROR: You passed a file explicitly, but it is ignored. This is probably an error.
        File: app/src/main/java/com/farouk/chi/colormaster/CMApplication.kt
        """
        # Test with specific file path that should trigger the warning/error
        kotlin_file_path = "app/src/main/kotlin/com/example/testapp/KotlinUtils.kt"

        try:
            # This should trigger the error about passing a file explicitly
            symbols = shared_android_server.request_full_symbol_tree(within_relative_path=kotlin_file_path, include_body=False)
            print(f"⚠️  File path was accepted: {kotlin_file_path}")
            print(f"Got {len(symbols) if symbols else 0} symbols")

        except Exception as e:
            if "You passed a file explicitly, but it is ignored" in str(e):
                print(f"✅ Expected error reproduced: {e}")
            else:
                print(f"⚠️  Different error (might be expected): {e}")

    @pytest.mark.android_readonly
    def test_full_symbol_tree_with_java_file_path(self, shared_android_server: AndroidLanguageServer):
        """
        Test request_full_symbol_tree with a Java file path to see if the same
        error occurs for Java files as well as Kotlin files.
        """
        # Test with Java file path
        java_file_path = "app/src/main/java/com/example/testapp/MainActivity.java"

        try:
            symbols = shared_android_server.request_full_symbol_tree(within_relative_path=java_file_path, include_body=False)
            print(f"⚠️  Java file path was accepted: {java_file_path}")
            print(f"Got {len(symbols) if symbols else 0} symbols")

        except Exception as e:
            if "You passed a file explicitly, but it is ignored" in str(e):
                print(f"✅ Expected error reproduced for Java file: {e}")
            else:
                print(f"⚠️  Different error for Java file: {e}")

    @pytest.mark.android_readonly
    def test_full_symbol_tree_with_directory_path(self, shared_android_server: AndroidLanguageServer):
        """
        Test request_full_symbol_tree with a directory path, which should be
        the correct usage pattern.
        """
        # Test with directory path (should be correct usage)
        directory_path = "app/src/main/java/com/example/testapp"

        try:
            symbols = shared_android_server.request_full_symbol_tree(within_relative_path=directory_path, include_body=False)
            print(f"✅ Directory path accepted: {directory_path}")
            print(f"Got {len(symbols) if symbols else 0} symbols")

        except Exception as e:
            print(f"Directory path error: {e}")

    @pytest.mark.android_readonly
    def test_full_symbol_tree_with_none_path(self, shared_android_server: AndroidLanguageServer):
        """
        Test request_full_symbol_tree with None path, which should get
        all symbols from the entire project.
        """
        try:
            # Test with None (default) - should get all symbols
            symbols = shared_android_server.request_full_symbol_tree(within_relative_path=None, include_body=False)
            print("✅ None path accepted (full project symbols)")
            print(f"Got {len(symbols) if symbols else 0} symbols")

        except Exception as e:
            print(f"None path error: {e}")

    @pytest.mark.android_fast
    def test_file_vs_directory_detection_for_symbol_tree(self):
        """
        Test that documents the difference between file and directory paths
        for the request_full_symbol_tree method.
        """
        repository_root_path = "/Users/qran/work/serena/test/resources/repos/android/test_repo"

        test_paths = [
            ("app/src/main/kotlin/com/example/testapp/KotlinUtils.kt", "file"),
            ("app/src/main/java/com/example/testapp/MainActivity.java", "file"),
            ("app/src/main/kotlin/com/example/testapp", "directory"),
            ("app/src/main/java/com/example/testapp", "directory"),
            ("app/src/main/java", "directory"),
            ("app/src/main", "directory"),
        ]

        for path, expected_type in test_paths:
            import os

            full_path = os.path.join(repository_root_path, path)

            if os.path.exists(full_path):
                actual_type = "file" if os.path.isfile(full_path) else "directory"
                status = "✅" if actual_type == expected_type else "❌"
                print(f"{status} {path} is a {actual_type} (expected {expected_type})")

                if actual_type == "file":
                    print("   ⚠️  Using this path would trigger: 'You passed a file explicitly, but it is ignored'")
                else:
                    print("   ✅ Using this path should work correctly")
            else:
                print(f"⚠️  {path} does not exist")

    @pytest.mark.android_readonly
    def test_android_symbol_tree_delegation_logic(self, shared_android_server: AndroidLanguageServer):
        """
        Test the delegation logic in AndroidLanguageServer.request_full_symbol_tree
        to understand how it forwards parameters to Java and Kotlin delegates.
        """
        # Test different parameter combinations to understand delegation
        test_cases = [
            (None, False, "Full project, no body"),
            (None, True, "Full project, with body"),
            ("app/src/main/java", False, "Java directory, no body"),
            ("app/src/main/kotlin", False, "Kotlin directory, no body"),
        ]

        for within_path, include_body, description in test_cases:
            try:
                print(f"Testing: {description}")
                print(f"  Parameters: within_relative_path={within_path}, include_body={include_body}")

                symbols = shared_android_server.request_full_symbol_tree(within_relative_path=within_path, include_body=include_body)

                print(f"  Result: {len(symbols) if symbols else 0} symbols")

            except Exception as e:
                if "You passed a file explicitly, but it is ignored" in str(e):
                    print(f"  ⚠️  File warning: {e}")
                else:
                    print(f"  Error: {e}")
            print()

    @pytest.mark.android_readonly
    def test_reproduce_exact_error_scenario(self, shared_android_server: AndroidLanguageServer):
        """
        Test that reproduces the exact scenario from the error message.

        The original error shows a .kt file being passed to request_full_symbol_tree.
        """
        # Reproduce the exact file from the error: CMApplication.kt
        # Using our test equivalent: KotlinUtils.kt
        problematic_file = "app/src/main/kotlin/com/example/testapp/KotlinUtils.kt"

        print(f"Reproducing error with file: {problematic_file}")

        try:
            # This should reproduce the warning/error
            symbols = shared_android_server.request_full_symbol_tree(within_relative_path=problematic_file)

            print("❌ No error occurred - the issue might not be reproduced in test environment")
            print(f"Got {len(symbols) if symbols else 0} symbols")

        except Exception as e:
            if "You passed a file explicitly, but it is ignored" in str(e):
                print(f"✅ REPRODUCED: {e}")
            else:
                print(f"Different error: {e}")

    @pytest.mark.android_readonly
    def test_understand_ignore_patterns_causing_error(self, shared_android_server: AndroidLanguageServer):
        """
        Test that investigates the ignore patterns that cause the error.

        The error occurs when:
        1. A file path is passed to request_full_symbol_tree()
        2. The file is considered 'ignored' by the language server
        3. The base class logs the error and returns []

        For AndroidLanguageServer, this happens because:
        - A .kt file is passed to the Java delegate (which ignores .kt files)
        - A .java file is passed to the Kotlin delegate (which ignores .java files)
        """
        print("Understanding the ignore pattern issue:")
        print()

        # Test cases that demonstrate the problem
        test_files = [
            ("app/src/main/kotlin/com/example/testapp/KotlinUtils.kt", "Kotlin file"),
            ("app/src/main/java/com/example/testapp/MainActivity.java", "Java file"),
        ]

        for file_path, description in test_files:
            print(f"Testing {description}: {file_path}")

            # Check what would happen with each delegate
            java_delegate = shared_android_server.java_ls
            kotlin_delegate = shared_android_server.kotlin_ls

            print(f"  Java delegate would ignore this file: {java_delegate.is_ignored_path(file_path)}")
            print(f"  Kotlin delegate would ignore this file: {kotlin_delegate.is_ignored_path(file_path)}")

            # This explains why we get the error:
            if file_path.endswith(".kt"):
                print("  ⚠️  Java delegate ignores .kt files -> triggers error")
            elif file_path.endswith(".java"):
                print("  ⚠️  Kotlin delegate ignores .java files -> triggers error")

            print()
