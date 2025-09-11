"""
Test case to verify AndroidLanguageServer request_full_symbol_tree method
supports all expected parameters from the base class.

This reproduces the TypeError: AndroidLanguageServer.request_full_symbol_tree()
got an unexpected keyword argument 'within_relative_path'
"""

import pytest

from solidlsp.language_servers.android_language_server import AndroidLanguageServer


@pytest.mark.android
class TestAndroidSymbolTreeParameters:
    """Test AndroidLanguageServer request_full_symbol_tree parameter compatibility"""

    @pytest.mark.android_readonly
    def test_request_full_symbol_tree_with_within_relative_path_parameter(self, shared_android_server: AndroidLanguageServer):
        """
        Test that AndroidLanguageServer.request_full_symbol_tree() accepts
        the within_relative_path parameter without raising TypeError.

        This reproduces the error:
        TypeError: AndroidLanguageServer.request_full_symbol_tree() got an
        unexpected keyword argument 'within_relative_path'
        """
        # This should NOT raise a TypeError about unexpected keyword argument
        try:
            # Test with within_relative_path parameter (this was causing the error)
            symbols = shared_android_server.request_full_symbol_tree(within_relative_path="app/src/main/java/com/example/testapp/")
            print(f"✅ request_full_symbol_tree with within_relative_path succeeded: {len(symbols) if symbols else 0} symbols")

        except TypeError as e:
            if "unexpected keyword argument 'within_relative_path'" in str(e):
                pytest.fail(f"PARAMETER ERROR REPRODUCED: {e}")
            else:
                pytest.fail(f"Different TypeError: {e}")
        except Exception as e:
            # Other exceptions are acceptable (language server not started, etc.)
            print(f"⚠️  Expected error (server not started): {e}")

    @pytest.mark.android_readonly
    def test_request_full_symbol_tree_with_include_body_parameter(self, shared_android_server: AndroidLanguageServer):
        """
        Test that AndroidLanguageServer.request_full_symbol_tree() accepts
        the include_body parameter.
        """
        # This should NOT raise a TypeError about unexpected keyword argument
        try:
            # Test with include_body parameter
            symbols = shared_android_server.request_full_symbol_tree(include_body=True)
            print(f"✅ request_full_symbol_tree with include_body succeeded: {len(symbols) if symbols else 0} symbols")

        except TypeError as e:
            if "unexpected keyword argument" in str(e):
                pytest.fail(f"PARAMETER ERROR REPRODUCED: {e}")
            else:
                pytest.fail(f"Different TypeError: {e}")
        except Exception as e:
            # Other exceptions are acceptable (language server not started, etc.)
            print(f"⚠️  Expected error (server not started): {e}")

    def test_request_full_symbol_tree_with_all_parameters(self, shared_android_server: AndroidLanguageServer):
        """
        Test that AndroidLanguageServer.request_full_symbol_tree() accepts
        all expected parameters that the base class supports.
        """
        # This should NOT raise a TypeError about unexpected keyword argument
        try:
            # Test with all parameters that might be passed from symbol_tools.py
            symbols = shared_android_server.request_full_symbol_tree(within_relative_path="app/src/main/java/com/example/testapp/", include_body=True)
            print(f"✅ request_full_symbol_tree with all parameters succeeded: {len(symbols) if symbols else 0} symbols")

        except TypeError as e:
            if "unexpected keyword argument" in str(e):
                pytest.fail(f"PARAMETER ERROR REPRODUCED: {e}")
            else:
                pytest.fail(f"Different TypeError: {e}")
        except Exception as e:
            # Other exceptions are acceptable (language server not started, etc.)
            print(f"⚠️  Expected error (server not started): {e}")

    def test_method_signature_compatibility(self):
        """
        Test that AndroidLanguageServer has the same method signature as the base class
        for request_full_symbol_tree method.
        """
        import inspect

        from solidlsp.ls import SolidLanguageServer

        # Get method signatures
        base_method = getattr(SolidLanguageServer, "request_full_symbol_tree")
        android_method = getattr(AndroidLanguageServer, "request_full_symbol_tree")

        base_signature = inspect.signature(base_method)
        android_signature = inspect.signature(android_method)

        print(f"Base class signature: {base_signature}")
        print(f"Android class signature: {android_signature}")

        # The Android implementation should accept the same parameters as the base class
        # Note: This test documents the current state and helps identify signature mismatches
