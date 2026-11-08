# SPDX-License-Identifier: GPL-3.0-or-later

import io

from AppKit import NSImage  # ty: ignore[unresolved-import]  (macOS only)
from Foundation import NSData  # ty: ignore[unresolved-import]  (macOS only)
from PIL import Image
from pystray._darwin import Icon


class MacOSTrayIcon(Icon):
    """
    pystray menu bar icon for macOS which is rendered sharply on high-resolution (Retina) screens.

    pystray renders the icon bitmap with one pixel per point of the menu bar height, which macOS upscales
    on screens with a backing scale factor above 1, so the icon appears blurry there.
    This class renders the bitmap at the highest backing scale factor of macOS screens instead, which a screen
    with a lower scale factor downsamples without loss of sharpness.
    Since it overrides a private method of pystray, it is coupled to the pinned pystray version.
    """

    _PIXELS_PER_POINT = 2
    """
    the number of bitmap pixels per point, i.e. the highest backing scale factor of macOS screens.
    It is fixed rather than read from the connected screens, because pystray does not re-render the icon
    when a screen with a higher scale factor is connected later.
    """

    def _assert_image(self) -> None:
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

        # create an image whose point size matches the menu bar height, such that macOS maps its pixels to the screen's backing scale
        buffer = io.BytesIO()
        bitmap.save(buffer, "png")
        self._icon_image = NSImage.alloc().initWithData_(NSData(buffer.getvalue()))
        self._icon_image.setSize_(point_size)
        self._status_item.button().setImage_(self._icon_image)
