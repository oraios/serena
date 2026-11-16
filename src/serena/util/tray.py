# SPDX-License-Identifier: GPL-3.0-or-later

import io
import sys
from typing import TYPE_CHECKING, Any

from PIL import Image

if TYPE_CHECKING:
    import pystray


def create_tray_icon(*args: Any, **kwargs: Any) -> "pystray.Icon":
    """
    Creates a system tray icon that matches the platform's native appearance.

    On macOS, the icon image is marked as a template image, so that the menu bar recolours it for
    light, dark and tinted menu bars, as it does for native status items. A template image uses only
    the alpha channel of the icon. The image is furthermore rendered with two pixels per point, so that
    it is sharp on high-resolution (Retina) screens. pystray provides no API for either, so the private
    method that creates the ``NSImage`` is overridden, which couples this function to the pinned pystray version.

    :param args: positional arguments for ``pystray.Icon``
    :param kwargs: keyword arguments for ``pystray.Icon``
    :return: the (not yet running) tray icon
    """
    # import pystray locally, because the import fails when there is no display
    import pystray

    if sys.platform != "darwin":
        return pystray.Icon(*args, **kwargs)

    class MacOSMenuBarIcon(pystray.Icon):
        _PIXELS_PER_POINT = 2
        """
        the number of bitmap pixels per point, i.e. the highest backing scale factor of macOS screens.
        It is fixed rather than read from the connected screens, because pystray does not re-render the icon
        when a screen with a higher scale factor is connected later; a screen with a lower scale factor
        downsamples the bitmap without loss of sharpness.
        """

        def _assert_image(self) -> None:
            # import macOS-only modules locally, because they are unavailable on other platforms
            from AppKit import NSImage  # ty: ignore[unresolved-import]  (macOS only)
            from Foundation import NSData  # ty: ignore[unresolved-import]  (macOS only)

            # keep the cached image as long as the menu bar height is unchanged
            thickness = int(self._status_bar.thickness())
            point_size = (thickness, thickness)
            if self._icon_image and self._icon_image.size() == point_size:
                return

            # scale the source image to the pixel size of the bitmap
            source = self._icon
            assert source is not None
            pixel_size = (thickness * self._PIXELS_PER_POINT, thickness * self._PIXELS_PER_POINT)
            if source.size == pixel_size:
                bitmap = source
            else:
                bitmap = Image.new("RGBA", pixel_size)
                bitmap.paste(source.resize(pixel_size, Image.Resampling.LANCZOS))

            # create a template image whose point size matches the menu bar height, such that macOS maps its pixels
            # to the screen's backing scale and recolours it for the menu bar's appearance
            buffer = io.BytesIO()
            bitmap.save(buffer, "png")
            image = NSImage.alloc().initWithData_(NSData(buffer.getvalue()))
            image.setSize_(point_size)
            image.setTemplate_(True)
            self._icon_image = image
            self._status_item.button().setImage_(image)

    return MacOSMenuBarIcon(*args, **kwargs)
