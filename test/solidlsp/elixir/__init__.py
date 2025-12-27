def _test_expert_available() -> str:
    """Test if Expert is available and return error reason if not."""
    # Try to import and check Elixir availability
    try:
        from solidlsp.language_servers.elixir_tools.elixir_tools import ElixirTools

        # Check if Elixir is installed
        elixir_version = ElixirTools._get_elixir_version()
        if not elixir_version:
            return "Elixir is not installed or not in PATH"

        return ""  # No error, Expert should be available

    except ImportError as e:
        return f"Failed to import ElixirTools: {e}"
    except Exception as e:
        return f"Error checking Expert availability: {e}"


EXPERT_UNAVAILABLE_REASON = _test_expert_available()
EXPERT_UNAVAILABLE = bool(EXPERT_UNAVAILABLE_REASON)
