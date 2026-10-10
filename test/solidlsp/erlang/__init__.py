def _test_erlang_available() -> str:
    """Test if Erlang/OTP and an ELP-supported platform are available."""
    # Try to import and check Erlang availability
    try:
        from solidlsp.language_servers.erlang_language_server import ErlangLanguageServer

        # Check if Erlang/OTP is installed
        erlang_version = ErlangLanguageServer._get_erlang_version()
        if not erlang_version:
            return "Erlang/OTP is not installed or not in PATH"

        if not hasattr(ErlangLanguageServer, "DependencyProvider"):
            return "ELP dependency provider is unavailable"

        from solidlsp.ls_utils import PlatformUtils

        current_platform = PlatformUtils.get_platform_id()
        if current_platform not in ErlangLanguageServer.DependencyProvider._SUPPORTED_PLATFORM_IDS:
            return f"ELP does not provide a binary for platform {current_platform}"

        # Check if rebar3 is available (required by the Erlang fixture project).
        rebar3_available = ErlangLanguageServer._check_rebar3_available()
        if not rebar3_available:
            return "rebar3 is not installed or not in PATH (required for project compilation)"

        return ""  # No error, ELP should be available or downloadable for this platform

    except ImportError as e:
        return f"Failed to import ErlangLanguageServer: {e}"
    except Exception as e:
        return f"Error checking ELP availability: {e}"


ERLANG_UNAVAILABLE_REASON = _test_erlang_available()
ERLANG_UNAVAILABLE = bool(ERLANG_UNAVAILABLE_REASON)
