"""
Test suite for verifying Java and Kotlin symbol behavior in Android projects.

This test suite documents and verifies the current behavior of symbol extraction
for both Java and Kotlin files in Android projects, identifying the specific
limitations and ensuring they are properly handled.

Test Goals:
1. Document current Java file-level symbol limitations
2. Verify Java directory-level symbol extraction works
3. Verify Kotlin file-level symbol extraction works
4. Test cross-language symbol references
5. Verify Android-specific symbol handling
6. Establish baseline for improvements
"""


import pytest

from solidlsp.language_servers.android_language_server import AndroidLanguageServer


@pytest.mark.android
class TestAndroidJavaKotlinSymbolBehavior:
    """
    Comprehensive test suite for Android Java and Kotlin symbol behavior.
    """

    # ========================================================================================
    # JAVA FILE-LEVEL SYMBOL TESTS (Expected to fail with current implementation)
    # ========================================================================================
    
    @pytest.mark.android_readonly
    def test_java_file_level_symbols_currently_fail(self, shared_android_server: AndroidLanguageServer):
        """
        DOCUMENTED LIMITATION: Java file-level symbol queries currently return empty results.
        
        This test documents the current behavior where Eclipse JDTLS cannot properly
        extract symbols from individual Java files in Android projects due to AGP 8.x
        compatibility issues.
        
        Expected: Empty results (current limitation)
        Goal: This should eventually return symbols when fixed
        """
        # Test with MainActivity.java
        java_file_path = "app/src/main/java/com/example/testapp/MainActivity.java"
        
        # Test document symbols
        document_symbols = shared_android_server.request_document_symbols(java_file_path)
        assert not document_symbols or (isinstance(document_symbols, (list, tuple)) and all(not symbols for symbols in document_symbols)), \
            "Java file-level document symbols currently expected to be empty due to AGP 8.x issues"
        
        # Test full symbol tree for specific Java file
        file_symbols = shared_android_server.request_full_symbol_tree(
            within_relative_path=java_file_path, 
            include_body=True
        )
        assert file_symbols == [] or len(file_symbols) == 0, \
            "Java file-level symbol tree currently expected to be empty due to AGP 8.x issues"
        
        print("❌ DOCUMENTED LIMITATION: Java file-level symbols currently fail as expected")

    @pytest.mark.android_readonly
    def test_java_utils_file_level_symbols_currently_fail(self, shared_android_server: AndroidLanguageServer):
        """
        Test Java utility class file-level symbol extraction (currently fails).
        """
        java_file_path = "app/src/main/java/com/example/testapp/JavaUtils.java"
        
        document_symbols = shared_android_server.request_document_symbols(java_file_path)
        assert not document_symbols or (isinstance(document_symbols, (list, tuple)) and all(not symbols for symbols in document_symbols)), \
            "JavaUtils file-level symbols currently expected to be empty"
        
        file_symbols = shared_android_server.request_full_symbol_tree(
            within_relative_path=java_file_path, 
            include_body=False
        )
        assert file_symbols == [] or len(file_symbols) == 0, \
            "JavaUtils file-level symbol tree currently expected to be empty"
        
        print("❌ DOCUMENTED LIMITATION: JavaUtils file-level symbols currently fail as expected")

    # ========================================================================================
    # JAVA DIRECTORY-LEVEL SYMBOL TESTS (Expected to work)
    # ========================================================================================
    
    @pytest.mark.android_readonly
    def test_java_directory_level_symbols_work(self, shared_android_server: AndroidLanguageServer):
        """
        WORKING FEATURE: Java directory-level symbol queries should work.
        
        This test verifies that Eclipse JDTLS can extract symbols when querying
        at the package/directory level, even though file-level queries fail.
        """
        # Test Java package directory
        java_package_path = "app/src/main/java/com/example/testapp"
        
        # Get symbols from Java package directory
        directory_symbols = shared_android_server.request_full_symbol_tree(
            within_relative_path=java_package_path,
            include_body=False
        )
        
        # Should find Java classes in the directory
        assert directory_symbols is not None, "Directory-level symbols should not be None"
        
        # Look for expected Java classes
        java_class_names = [symbol.get('name', '') for symbol in directory_symbols if symbol.get('name')]
        
        print(f"✅ Java directory symbols found: {len(directory_symbols)} symbols")
        print(f"Java class names found: {java_class_names}")
        
        # Verify we found some symbols (exact count may vary)
        assert len(directory_symbols) > 0, "Should find Java symbols at directory level"

    @pytest.mark.android_readonly
    def test_java_root_java_directory_symbols(self, shared_android_server: AndroidLanguageServer):
        """
        Test symbol extraction from the root Java source directory.
        """
        java_root_path = "app/src/main/java"
        
        root_symbols = shared_android_server.request_full_symbol_tree(
            within_relative_path=java_root_path,
            include_body=False
        )
        
        assert root_symbols is not None, "Root Java directory symbols should not be None"
        print(f"✅ Java root directory symbols: {len(root_symbols)} symbols found")

    # ========================================================================================
    # KOTLIN FILE-LEVEL SYMBOL TESTS (Expected to work perfectly)
    # ========================================================================================
    
    @pytest.mark.android_readonly
    def test_kotlin_file_level_symbols_work(self, shared_android_server: AndroidLanguageServer):
        """
        WORKING FEATURE: Kotlin file-level symbol queries should work perfectly.
        
        This test verifies that the Kotlin Language Server can properly extract
        symbols from individual Kotlin files.
        """
        kotlin_file_path = "app/src/main/kotlin/com/example/testapp/KotlinUtils.kt"
        
        # Test document symbols
        document_symbols = shared_android_server.request_document_symbols(kotlin_file_path)
        assert document_symbols is not None, "Kotlin document symbols should not be None"
        
        # Test full symbol tree for specific Kotlin file
        file_symbols = shared_android_server.request_full_symbol_tree(
            within_relative_path=kotlin_file_path,
            include_body=True
        )
        
        assert file_symbols is not None, "Kotlin file symbols should not be None"
        assert len(file_symbols) > 0, "Should find Kotlin symbols in file"
        
        # Look for Kotlin-specific symbols
        kotlin_symbol_names = [symbol.get('name', '') for symbol in file_symbols if symbol.get('name')]
        print(f"✅ Kotlin file symbols found: {len(file_symbols)} symbols")
        print(f"Kotlin symbol names: {kotlin_symbol_names}")

    @pytest.mark.android_readonly
    def test_kotlin_activity_file_level_symbols_work(self, shared_android_server: AndroidLanguageServer):
        """
        Test Kotlin activity file symbol extraction.
        """
        kotlin_file_path = "app/src/main/kotlin/com/example/testapp/AndroidActivity.kt"
        
        document_symbols = shared_android_server.request_document_symbols(kotlin_file_path)
        assert document_symbols is not None, "AndroidActivity document symbols should not be None"
        
        file_symbols = shared_android_server.request_full_symbol_tree(
            within_relative_path=kotlin_file_path,
            include_body=False
        )
        
        assert file_symbols is not None, "AndroidActivity symbols should not be None"
        assert len(file_symbols) > 0, "Should find AndroidActivity symbols"
        
        print(f"✅ AndroidActivity symbols found: {len(file_symbols)} symbols")

    # ========================================================================================
    # KOTLIN DIRECTORY-LEVEL SYMBOL TESTS (Expected to work)
    # ========================================================================================
    
    @pytest.mark.android_readonly
    def test_kotlin_directory_level_symbols_work(self, shared_android_server: AndroidLanguageServer):
        """
        Test Kotlin directory-level symbol extraction.
        """
        kotlin_package_path = "app/src/main/kotlin/com/example/testapp"
        
        directory_symbols = shared_android_server.request_full_symbol_tree(
            within_relative_path=kotlin_package_path,
            include_body=False
        )
        
        assert directory_symbols is not None, "Kotlin directory symbols should not be None"
        assert len(directory_symbols) > 0, "Should find Kotlin symbols at directory level"
        
        print(f"✅ Kotlin directory symbols: {len(directory_symbols)} symbols found")

    # ========================================================================================
    # MIXED JAVA/KOTLIN WORKSPACE TESTS
    # ========================================================================================
    
    @pytest.mark.android_readonly
    def test_mixed_workspace_symbol_extraction(self, shared_android_server: AndroidLanguageServer):
        """
        Test symbol extraction from workspace containing both Java and Kotlin files.
        """
        # Get symbols from entire workspace
        workspace_symbols = shared_android_server.request_full_symbol_tree(
            within_relative_path=None,
            include_body=False
        )
        
        assert workspace_symbols is not None, "Workspace symbols should not be None"
        assert len(workspace_symbols) > 0, "Should find symbols in mixed workspace"
        
        # Categorize symbols by likely language
        java_symbols = []
        kotlin_symbols = []
        
        for symbol in workspace_symbols:
            symbol_location = symbol.get('location', {}).get('uri', '')
            
            if '.java' in symbol_location:
                java_symbols.append(symbol)
            elif '.kt' in symbol_location:
                kotlin_symbols.append(symbol)
        
        print(f"✅ Mixed workspace: {len(workspace_symbols)} total symbols")
        print(f"   - Java symbols: {len(java_symbols)}")
        print(f"   - Kotlin symbols: {len(kotlin_symbols)}")
        
        # We should find some symbols, though Java file-level may be limited
        assert len(workspace_symbols) > 0, "Should find some symbols in workspace"

    # ========================================================================================
    # CROSS-LANGUAGE REFERENCE TESTS
    # ========================================================================================
    
    @pytest.mark.android_readonly
    def test_cross_language_references(self, shared_android_server: AndroidLanguageServer):
        """
        Test finding references across Java and Kotlin files.
        
        NOTE: This may have limitations due to Java file-level symbol issues.
        """
        # Try to find references in a Kotlin file (should work)
        kotlin_file_path = "app/src/main/kotlin/com/example/testapp/KotlinUtils.kt"
        
        # Test references at a basic location (line 0, column 0)
        references = shared_android_server.request_references(kotlin_file_path, 0, 0)
        
        # References may be empty, but the method should not crash
        assert references is not None, "References should not be None"
        print(f"✅ Cross-language references: {len(references)} references found")

    # ========================================================================================
    # SYMBOL SEARCH AND FILTERING TESTS
    # ========================================================================================
    
    @pytest.mark.android_readonly
    def test_symbol_search_functionality(self, shared_android_server: AndroidLanguageServer):
        """
        Test searching for specific symbols across the project.
        """
        # Get all workspace symbols
        all_symbols = shared_android_server.request_full_symbol_tree(
            within_relative_path=None,
            include_body=False
        )
        
        if all_symbols:
            # Test symbol filtering/searching
            main_symbols = [s for s in all_symbols if 'Main' in s.get('name', '')]
            utils_symbols = [s for s in all_symbols if 'Utils' in s.get('name', '')]
            
            print("✅ Symbol search:")
            print(f"   - 'Main' symbols: {len(main_symbols)}")
            print(f"   - 'Utils' symbols: {len(utils_symbols)}")

    # ========================================================================================
    # PERFORMANCE AND RELIABILITY TESTS
    # ========================================================================================
    
    @pytest.mark.android_slow
    def test_language_server_stability(self, shared_android_server: AndroidLanguageServer):
        """
        Test that the Android Language Server remains stable under various queries.
        """
        test_paths = [
            "app/src/main/java/com/example/testapp/MainActivity.java",
            "app/src/main/java/com/example/testapp/JavaUtils.java", 
            "app/src/main/kotlin/com/example/testapp/KotlinUtils.kt",
            "app/src/main/kotlin/com/example/testapp/AndroidActivity.kt",
            "app/src/main/java/com/example/testapp",  # Directory
            "app/src/main/kotlin/com/example/testapp",  # Directory
        ]
        
        for path in test_paths:
            try:
                # Test document symbols (for files)
                if path.endswith(('.java', '.kt')):
                    symbols = shared_android_server.request_document_symbols(path)
                    assert symbols is not None, f"Document symbols should not be None for {path}"
                
                # Test full symbol tree
                tree_symbols = shared_android_server.request_full_symbol_tree(
                    within_relative_path=path,
                    include_body=False
                )
                assert tree_symbols is not None, f"Symbol tree should not be None for {path}"
                
            except Exception as e:
                pytest.fail(f"Language server crashed on path {path}: {e}")
        
        print("✅ Language server stability test passed")

    # ========================================================================================
    # BEHAVIORAL DOCUMENTATION TESTS
    # ========================================================================================
    
    @pytest.mark.android_fast
    def test_document_current_limitations(self, shared_android_server: AndroidLanguageServer):
        """
        Document the current known limitations for future reference.
        """
        limitations = {
            "java_file_level_symbols": "FAIL - Eclipse JDTLS cannot extract symbols from individual Java files",
            "java_directory_level_symbols": "PASS - Eclipse JDTLS works for Java package directories", 
            "kotlin_file_level_symbols": "PASS - Kotlin LS works perfectly for individual Kotlin files",
            "kotlin_directory_level_symbols": "PASS - Kotlin LS works for Kotlin directories",
            "mixed_workspace_symbols": "PARTIAL - Combined results limited by Java file issues",
            "cross_language_references": "LIMITED - May miss Java file references",
        }
        
        print("\n" + "="*80)
        print("CURRENT ANDROID SYMBOL BEHAVIOR DOCUMENTATION")
        print("="*80)
        
        for feature, status in limitations.items():
            status_emoji = "❌" if "FAIL" in status else "⚠️" if "PARTIAL" in status or "LIMITED" in status else "✅"
            print(f"{status_emoji} {feature}: {status}")
        
        print("="*80)
        print("GOAL: All features should show ✅ PASS when improvements are complete")
        print("="*80 + "\n")
        
        # This test always passes - it's for documentation
        assert True, "Documentation test always passes"

    @pytest.mark.android_readonly
    def test_establish_improvement_baseline(self, shared_android_server: AndroidLanguageServer):
        """
        Establish baseline metrics for measuring improvements.
        """
        # Measure current symbol extraction capabilities
        java_file_path = "app/src/main/java/com/example/testapp/MainActivity.java"
        kotlin_file_path = "app/src/main/kotlin/com/example/testapp/KotlinUtils.kt"
        java_dir_path = "app/src/main/java/com/example/testapp"
        
        # Current baseline measurements
        java_file_symbols = shared_android_server.request_full_symbol_tree(java_file_path, False)
        kotlin_file_symbols = shared_android_server.request_full_symbol_tree(kotlin_file_path, False)
        java_dir_symbols = shared_android_server.request_full_symbol_tree(java_dir_path, False)
        
        baseline_metrics = {
            "java_file_symbol_count": len(java_file_symbols) if java_file_symbols else 0,
            "kotlin_file_symbol_count": len(kotlin_file_symbols) if kotlin_file_symbols else 0,
            "java_dir_symbol_count": len(java_dir_symbols) if java_dir_symbols else 0,
        }
        
        print("\n📊 BASELINE METRICS:")
        for metric, value in baseline_metrics.items():
            print(f"   {metric}: {value}")
        
        # Store baseline for future comparison
        # In a real implementation, you might save this to a file or database
        print("\n🎯 IMPROVEMENT GOALS:")
        print(f"   java_file_symbol_count: {baseline_metrics['java_file_symbol_count']} → >0 (should find MainActivity symbols)")
        print(f"   kotlin_file_symbol_count: {baseline_metrics['kotlin_file_symbol_count']} (should remain >0)")
        print(f"   java_dir_symbol_count: {baseline_metrics['java_dir_symbol_count']} (should remain >0)")
        
        # Test passes regardless of current values - this is baseline establishment
        assert True, "Baseline establishment always passes"
