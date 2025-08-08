import platform


def _test_erlang_ls_available() -> str:
    """Test if Erlang LS is available and return error reason if not."""
    # Check if we're on Windows (may have different requirements)
    if platform.system() == "Windows":
        # Erlang LS should work on Windows, but may need different checks
        pass

    # Try to import and check Erlang availability
    try:
        from solidlsp.language_servers.erlang_language_server import ErlangLanguageServer

        # Check if Erlang/OTP is installed
        erlang_version = ErlangLanguageServer._get_erlang_version()
        if not erlang_version:
            return "Erlang/OTP is not installed or not in PATH"

        # Check if rebar3 is available (commonly used build tool)
        rebar3_available = ErlangLanguageServer._check_rebar3_available()
        if not rebar3_available:
            return "rebar3 is not installed or not in PATH (required for project compilation)"

        return ""  # No error, Erlang LS should be available

    except ImportError as e:
        return f"Failed to import ErlangLanguageServer: {e}"
    except Exception as e:
        return f"Error checking Erlang LS availability: {e}"


ERLANG_LS_UNAVAILABLE_REASON = _test_erlang_ls_available()
ERLANG_LS_UNAVAILABLE = bool(ERLANG_LS_UNAVAILABLE_REASON)
