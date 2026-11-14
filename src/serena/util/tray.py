# SPDX-License-Identifier: GPL-3.0-or-later

import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pystray


def create_tray_icon(*args: Any, **kwargs: Any) -> "pystray.Icon":
    """
    Creates a system tray icon that matches the platform's native appearance.

    On macOS, the icon image is marked as a template image, so that the menu bar recolours it for
    light, dark and tinted menu bars, as it does for native status items. A template image uses only
    the alpha channel of the icon. pystray provides no API for this, so the private method that creates
    the ``NSImage`` is extended.

    :param args: positional arguments for ``pystray.Icon``
    :param kwargs: keyword arguments for ``pystray.Icon``
    :return: the (not yet running) tray icon
    """
    # import pystray locally, because the import fails when there is no display
    import pystray

    if sys.platform != "darwin":
        return pystray.Icon(*args, **kwargs)

    class TemplateImageIcon(pystray.Icon):
        def _assert_image(self) -> None:
            super()._assert_image()
            if self._icon_image is not None:
                self._icon_image.setTemplate_(True)

    return TemplateImageIcon(*args, **kwargs)
