import os
import shutil
import sys


def _check_pascal_available() -> bool:
    """Check if Pascal language server (pasls) or Free Pascal Compiler (fpc) is available."""
    # Check for pasls in PATH
    if shutil.which("pasls"):
        return True
    # Check for fpc (required to build pasls)
    if shutil.which("fpc"):
        return True
    return False


def _check_delphi_available() -> bool:
    """Check if Delphi language server (DelphiLSP) is available.

    DelphiLSP is only available on Windows as part of RAD Studio.
    """
    # Delphi is Windows-only
    if sys.platform != "win32":
        return False

    # Check for DelphiLSP in PATH
    if shutil.which("DelphiLSP"):
        return True

    # Check common RAD Studio installation paths
    program_files = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    rad_studio_base = os.path.join(program_files, "Embarcadero", "Studio")

    if os.path.isdir(rad_studio_base):
        # Check for any version of RAD Studio
        try:
            for version in os.listdir(rad_studio_base):
                delphilsp_path = os.path.join(rad_studio_base, version, "bin", "DelphiLSP.exe")
                if os.path.isfile(delphilsp_path):
                    return True
        except OSError:
            pass

    return False


PASCAL_AVAILABLE = _check_pascal_available()
DELPHI_AVAILABLE = _check_delphi_available()


def is_pascal_available() -> bool:
    """Return True if Pascal language server can be used."""
    return PASCAL_AVAILABLE


def is_delphi_available() -> bool:
    """Return True if Delphi language server can be used (Windows only)."""
    return DELPHI_AVAILABLE
