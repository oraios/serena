import os
import platform
import sys


def system_has_usable_display() -> bool:
    system = platform.system()

    # macOS
    if system == "Darwin" or system == "Windows" or sys.platform.lower().startswith(("cygwin", "msys")):
        return True

    # Other (assuming Linux/Unix): perform actual detection
    else:
        # Check Wayland
        wayland_display = os.environ.get("WAYLAND_DISPLAY")
        if wayland_display:
            runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
            if runtime_dir:
                socket_path = os.path.join(runtime_dir, wayland_display)
                if os.path.exists(socket_path):
                    try:
                        from wayland import client as wl

                        d = wl.wl_display_connect()
                        if d:
                            wl.wl_display_disconnect(d)
                            return True
                    except Exception:
                        pass

        # Check X11
        display = os.environ.get("DISPLAY")
        if display:
            try:
                from Xlib import display as xlib_display

                d = xlib_display.Display()
                d.close()
                return True
            except Exception:
                pass

        return False
