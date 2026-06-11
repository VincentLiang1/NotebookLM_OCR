"""Render PDF pages to images via PyMuPDF."""
from __future__ import annotations

import numpy as np
import pymupdf


def render_page(page: pymupdf.Page, dpi: int) -> tuple[np.ndarray, bytes]:
    """Render a page at the given DPI.

    Returns (rgb_array, png_bytes); the same render feeds both OCR and the
    slide background picture.
    """
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n
    )
    if pix.n == 4:  # safety: drop alpha if a colorspace sneaks one in
        img = img[:, :, :3]
    return img, pix.tobytes("png")
