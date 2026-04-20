import os
import platform


def system_has_usable_display() -> bool:
    system = platform.system()

    # macOS and native Windows: assume display is available for desktop usage
    if system == "Darwin" or system == "Windows":
        return True

    # Other systems, assumed to be Unix-like (Linux, FreeBSD, Cygwin/MSYS, etc.):
    # detect display availability since users may operate in CLI contexts
    else:
        # Check X11 or Wayland - if environment variables are set to non-empty values, assume display is usable
        display = os.environ.get("DISPLAY", "")
        wayland_display = os.environ.get("WAYLAND_DISPLAY", "")

        if display or wayland_display:
            return True

        return False
