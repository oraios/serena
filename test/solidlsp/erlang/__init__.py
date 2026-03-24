import platform


def _test_erlang_ls_available() -> str:
    """Test if ELP (Erlang Language Platform) is available and return error reason if not."""
    if platform.system() == "Windows":
        return "ELP does not support Windows"

    try:
        from solidlsp.language_servers.elp_language_server import ErlangLanguagePlatform

        # Check if ELP binary is installed
        elp_path = ErlangLanguagePlatform._find_elp()
        if not elp_path:
            return "ELP binary 'elp' not found in PATH"

        # Check if Erlang/OTP is installed (required by ELP)
        if not ErlangLanguagePlatform._check_erlang_installation():
            return "Erlang/OTP is not installed or not in PATH"

        return ""  # No error, ELP should be available

    except ImportError as e:
        return f"Failed to import ErlangLanguagePlatform: {e}"
    except Exception as e:
        return f"Error checking ELP availability: {e}"


ERLANG_LS_UNAVAILABLE_REASON = _test_erlang_ls_available()
ERLANG_LS_UNAVAILABLE = bool(ERLANG_LS_UNAVAILABLE_REASON)
