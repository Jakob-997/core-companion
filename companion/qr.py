"""One QR renderer for both wallet modes; no image-library dependency."""

import qrcode
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap


def qr_pixmap(payload, size=320):
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,
                         box_size=1, border=4)
    code.add_data(payload)
    code.make(fit=True)
    matrix = code.get_matrix()
    modules = len(matrix)
    image = QImage(modules, modules, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFFFF)
    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if dark:
                image.setPixel(x, y, 0xFF000000)
    # Whole pixels per module preserve sharp edges and the quiet zone.
    pixels = modules * max(1, size // modules)
    return QPixmap.fromImage(image).scaled(
        pixels, pixels, Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.FastTransformation,
    )
