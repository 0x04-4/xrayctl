"""terminal qr rendering."""
from __future__ import annotations

from typing import Optional


def render_qr(text: str) -> Optional[str]:
    try:
        import qrcode
    except ImportError:
        return None

    qr = qrcode.QRCode(border=1)
    qr.add_data(text)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    lines = ["".join("██" if cell else "  " for cell in row) for row in matrix]
    return "\n".join(lines)
