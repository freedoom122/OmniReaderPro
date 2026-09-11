"""Veyrion Workspace icon family.

Hand-built single-style SVG icons (1.6px stroke, round caps, 24px grid)
rendered to QIcon at load time. Consistent weight/metaphor across the app —
no mixed icon sets.
"""
from __future__ import annotations

import hashlib

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_CACHE: dict[tuple[str, str, int], QIcon] = {}

# 24x24 grid, stroke-based, rounded caps/joins, no fills except dots.
_PATHS: dict[str, str] = {
    # -- app identity --
    "app": (
        "<rect x='3.5' y='2.5' width='17' height='19' rx='2' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<path d='M7 7h10M7 10.5h10M7 14h6' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
        "<path d='M8 18.5c1.2-1.8 2.6-1.8 4 0 1.2-1.8 2.6-1.8 4 0' stroke='{c}' stroke-width='1.6' stroke-linecap='round' fill='none'/>"
    ),
    "open": (
        "<path d='M3.5 6.5v11a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-8l-2-2.5h-3a2 2 0 0 0-2 2z' stroke='{c}' stroke-width='1.6' fill='none' stroke-linejoin='round'/>"
    ),
    "save": (
        "<path d='M5 3.5h11L20.5 8v12a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 20V5A1.5 1.5 0 0 1 5 3.5z' stroke='{c}' stroke-width='1.6' fill='none' stroke-linejoin='round'/>"
        "<path d='M7.5 3.5V9h8V3.5' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<rect x='7.5' y='13' width='9' height='7' stroke='{c}' stroke-width='1.6' fill='none'/>"
    ),
    "search": (
        "<circle cx='10.5' cy='10.5' r='6' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<path d='M15.5 15.5 20 20' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
    ),
    "zoom_in": (
        "<circle cx='10.5' cy='10.5' r='6' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<path d='M15.5 15.5 20 20M10.5 7.8v5.4M7.8 10.5h5.4' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
    ),
    "zoom_out": (
        "<circle cx='10.5' cy='10.5' r='6' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<path d='M15.5 15.5 20 20M7.8 10.5h5.4' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
    ),
    "print": (
        "<path d='M7 8V3.5h10V8' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<rect x='3.5' y='8' width='17' height='8' rx='1.5' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<rect x='7' y='13.5' width='10' height='7' stroke='{c}' stroke-width='1.6' fill='none' fill2='none'/>"
    ),
    "library": (
        "<path d='M4 4.5h4v15H4zM10 4.5h4v15h-4z' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<path d='M16.5 5.2l3.6 13.6' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
    ),
    "book": (
        "<path d='M4 4.5c2.5-1.2 5-1.2 8 0 3-1.2 5.5-1.2 8 0v14c-2.5-1.2-5-1.2-8 0-3-1.2-5.5-1.2-8 0z' stroke='{c}' stroke-width='1.6' fill='none' stroke-linejoin='round'/>"
        "<path d='M12 4.5v14' stroke='{c}' stroke-width='1.6'/>"
    ),
    "highlighter": (
        "<path d='M9 15l-3 5.5M12.5 4.5l7 7-6.5 6.5-7-7z' stroke='{c}' stroke-width='1.6' fill='none' stroke-linejoin='round'/>"
        "<path d='M4 20.5h6' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
    ),
    "underline": (
        "<path d='M7 4v6a5 5 0 0 0 10 0V4' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round'/>"
        "<path d='M5.5 20h13' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
    ),
    "strikeout": (
        "<path d='M7 5.5c0-1 2-2 5-2s5 1 5 2.5c0 2.5-10 3-10 5.5' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round'/>"
        "<path d='M4.5 11.5h15' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
        "<path d='M7 17.5c0 1.5 2 2.5 5 2.5s5-1 5-2.5' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round'/>"
    ),
    "note": (
        "<path d='M4 4.5h16v11l-5 5H4z' stroke='{c}' stroke-width='1.6' fill='none' stroke-linejoin='round'/>"
        "<path d='M15 20.5v-5h5' stroke='{c}' stroke-width='1.6' fill='none' stroke-linejoin='round'/>"
    ),
    "ink": (
        "<path d='M4 20c2-6 6-14 10-16 1.5 3 4 9 4 13' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round'/>"
        "<circle cx='9' cy='17' r='1.4' fill='{c}'/>"
    ),
    "shapes": (
        "<rect x='3.5' y='3.5' width='10' height='10' rx='1' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<circle cx='16.5' cy='16.5' r='4' stroke='{c}' stroke-width='1.6' fill='none'/>"
    ),
    "stamp": (
        "<path d='M9 10V6a3 3 0 0 1 6 0v4' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round'/>"
        "<path d='M4 14.5c0-2 2.5-3.5 8-3.5s8 1.5 8 3.5v2H4z' stroke='{c}' stroke-width='1.6' fill='none' stroke-linejoin='round'/>"
        "<path d='M5 20h14' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
    ),
    "bookmark": (
        "<path d='M7 3.5h10v17l-5-4-5 4z' stroke='{c}' stroke-width='1.6' fill='none' stroke-linejoin='round'/>"
    ),
    "toc": (
        "<path d='M4 5.5h5M4 10h5M4 14.5h5M4 19h5' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
        "<path d='M12 5.5h8M12 10h8M12 14.5h8M12 19h8' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
    ),
    "thumbnails": (
        "<rect x='3.5' y='3.5' width='7.5' height='7.5' rx='1' stroke='{c}' stroke-width='1.5' fill='none'/>"
        "<rect x='13' y='3.5' width='7.5' height='7.5' rx='1' stroke='{c}' stroke-width='1.5' fill='none'/>"
        "<rect x='3.5' y='13' width='7.5' height='7.5' rx='1' stroke='{c}' stroke-width='1.5' fill='none'/>"
        "<rect x='13' y='13' width='7.5' height='7.5' rx='1' stroke='{c}' stroke-width='1.5' fill='none'/>"
    ),
    "rotate": (
        "<path d='M4.5 10a8 8 0 1 1 2.3 6.5' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round'/>"
        "<path d='M4.5 5v5h5' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round' stroke-linejoin='round'/>"
    ),
    "trash": (
        "<path d='M4.5 6.5h15M9.5 6V4.5a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1V6M6.5 6.5l1 13a1.5 1.5 0 0 0 1.5 1.4h6a1.5 1.5 0 0 0 1.5-1.4l1-13' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round'/>"
    ),
    "settings": (
        "<circle cx='12' cy='12' r='3' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<path d='M12 2.8v3M12 18.2v3M21.2 12h-3M5.8 12h-3M18.5 5.5l-2.1 2.1M7.6 16.4l-2.1 2.1M18.5 18.5l-2.1-2.1M7.6 7.6 5.5 5.5' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
    ),
    "sun": (
        "<circle cx='12' cy='12' r='4' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<path d='M12 3v2.2M12 18.8V21M21 12h-2.2M5.2 12H3M18.4 5.6l-1.6 1.6M7.2 16.8l-1.6 1.6M18.4 18.4l-1.6-1.6M7.2 7.2 5.6 5.6' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
    ),
    "moon": (
        "<path d='M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z' stroke='{c}' stroke-width='1.6' fill='none' stroke-linejoin='round'/>"
    ),
    "speaker": (
        "<path d='M4 9.5v5h3.5L12 19V5L7.5 9.5H4z' stroke='{c}' stroke-width='1.6' fill='none' stroke-linejoin='round'/>"
        "<path d='M15.5 9a4.5 4.5 0 0 1 0 6M18 6.5a8 8 0 0 1 0 11' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round'/>"
    ),
    "globe": (
        "<circle cx='12' cy='12' r='8.5' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<path d='M3.5 12h17M12 3.5c2.5 2.3 3.8 5.2 3.8 8.5s-1.3 6.2-3.8 8.5c-2.5-2.3-3.8-5.2-3.8-8.5S9.5 5.8 12 3.5z' stroke='{c}' stroke-width='1.6' fill='none'/>"
    ),
    "lock": (
        "<rect x='5.5' y='10.5' width='13' height='9.5' rx='1.5' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<path d='M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round'/>"
        "<circle cx='12' cy='15.2' r='1.4' fill='{c}'/>"
    ),
    "unlock": (
        "<rect x='5.5' y='10.5' width='13' height='9.5' rx='1.5' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<path d='M8.5 10.5V8a3.5 3.5 0 0 1 6.8-1' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round'/>"
    ),
    "shield": (
        "<path d='M12 3l7.5 2.5v6c0 4.5-3 8-7.5 9.5C7.5 19.5 4.5 16 4.5 11.5v-6z' stroke='{c}' stroke-width='1.6' fill='none' stroke-linejoin='round'/>"
        "<path d='M9 11.5l2.2 2.2L15.5 9.4' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round' stroke-linejoin='round'/>"
    ),
    "signature": (
        "<path d='M4 17c3-1 4.5-8 7-8s1 7 3.5 7S17 12 20 12' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round'/>"
        "<path d='M4 20.5h16' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
    ),
    "ocr": (
        "<path d='M3.5 8V4.5H8M16 4.5h4.5V8M20.5 16v4.5H16M8 20.5H3.5V16' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round'/>"
        "<path d='M7 9h10M7 12.5h7' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
    ),
    "convert": (
        "<path d='M4 8h13l-3-3M20 16H7l3 3' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round' stroke-linejoin='round'/>"
    ),
    "compare": (
        "<rect x='3.5' y='4.5' width='7' height='15' rx='1' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<rect x='13.5' y='4.5' width='7' height='15' rx='1' stroke='{c}' stroke-width='1.6' fill='none'/>"
    ),
    "split": (
        "<rect x='3.5' y='4.5' width='17' height='15' rx='1.5' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<path d='M12 4.5v15' stroke='{c}' stroke-width='1.6'/>"
    ),
    "present": (
        "<rect x='3.5' y='4' width='17' height='12' rx='1.5' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<path d='M12 16v3M8 21l4-2 4 2' stroke='{c}' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/>"
    ),
    "focus": (
        "<path d='M4 8.5V5.5a1 1 0 0 1 1-1h3M15.5 4.5h3a1 1 0 0 1 1 1v3M20 15.5v3a1 1 0 0 1-1 1h-3M8.5 19.5h-3a1 1 0 0 1-1-1v-3' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round'/>"
        "<circle cx='12' cy='12' r='2.5' stroke='{c}' stroke-width='1.6' fill='none'/>"
    ),
    "fullscreen": (
        "<path d='M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round' stroke-linejoin='round'/>"
    ),
    "keyboard": (
        "<rect x='3' y='7' width='18' height='10.5' rx='1.5' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<path d='M6.5 10.5h1M10 10.5h1M13.5 10.5h1M17 10.5h1M8 14h8' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
    ),
    "plugin": (
        "<path d='M9 3.5v4M15 3.5v4' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
        "<path d='M6.5 7.5h11a1 1 0 0 1 1 1v4a6.5 6.5 0 0 1-13 0v-4a1 1 0 0 1 1-1z' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<path d='M12 12v3' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
    ),
    "task": (
        "<circle cx='12' cy='12' r='8.5' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<path d='M12 7.5V12l3 2.5' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round' stroke-linejoin='round'/>"
    ),
    "command": (
        "<path d='M9 9H6.5A2.5 2.5 0 1 1 9 6.5V9zm0 0v6m0-6h6m-6 6H6.5A2.5 2.5 0 1 0 9 17.5V15zm6-6h2.5A2.5 2.5 0 1 0 15 6.5V9zm0 0v6m0 0h2.5A2.5 2.5 0 1 1 15 17.5V15z' stroke='{c}' stroke-width='1.6' fill='none' stroke-linejoin='round'/>"
    ),
    "star": (
        "<path d='M12 3.8l2.5 5 5.5.8-4 3.9.95 5.5L12 16.4l-4.95 2.6L8 13.5l-4-3.9 5.5-.8z' stroke='{c}' stroke-width='1.6' fill='none' stroke-linejoin='round'/>"
    ),
    "star_filled": (
        "<path d='M12 3.8l2.5 5 5.5.8-4 3.9.95 5.5L12 16.4l-4.95 2.6L8 13.5l-4-3.9 5.5-.8z' fill='{c}'/>"
    ),
    "tag": (
        "<path d='M3.5 12.5v-8a1 1 0 0 1 1-1h8l8 8-9 9z' stroke='{c}' stroke-width='1.6' fill='none' stroke-linejoin='round'/>"
        "<circle cx='8' cy='8' r='1.4' fill='{c}'/>"
    ),
    "folder": (
        "<path d='M3.5 6.5v11a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-8l-2-2.5h-3a2 2 0 0 0-2 2z' stroke='{c}' stroke-width='1.6' fill='none' stroke-linejoin='round'/>"
    ),
    "info": (
        "<circle cx='12' cy='12' r='8.5' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<path d='M12 11v5' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
        "<circle cx='12' cy='8' r='1.2' fill='{c}'/>"
    ),
    "warning": (
        "<path d='M12 4L2.8 19.5h18.4z' stroke='{c}' stroke-width='1.6' fill='none' stroke-linejoin='round'/>"
        "<path d='M12 10v4' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
        "<circle cx='12' cy='16.7' r='1.1' fill='{c}'/>"
    ),
    "close": (
        "<path d='M6 6l12 12M18 6L6 18' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
    ),
    "plus": (
        "<path d='M12 5v14M5 12h14' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
    ),
    "arrow_left": ("<path d='M14.5 5.5L8 12l6.5 6.5' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round' stroke-linejoin='round'/>"),
    "arrow_right": ("<path d='M9.5 5.5L16 12l-6.5 6.5' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round' stroke-linejoin='round'/>"),
    "arrow_up": ("<path d='M12 19V5M5.5 11.5L12 5l6.5 6.5' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round' stroke-linejoin='round'/>"),
    "arrow_down": ("<path d='M12 5v14M5.5 12.5L12 19l6.5-6.5' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round' stroke-linejoin='round'/>"),
    "redact": (
        "<rect x='4' y='10' width='16' height='4.5' fill='{c}'/>"
        "<path d='M6.5 6.5h11M6.5 18.5h11' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
    ),
    "merge": (
        "<path d='M7 4v6a4 4 0 0 0 4 4h6' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round'/>"
        "<path d='M13.5 10.5L17 14l-3.5 3.5' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round' stroke-linejoin='round'/>"
        "<path d='M7 20v-3' stroke='{c}' stroke-width='1.6' stroke-linecap='round'/>"
    ),
    "properties": (
        "<circle cx='12' cy='12' r='8.5' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<path d='M12 8v.1M9.5 15.5c.8-1 1.7-1.5 2.5-1.5s1.7.5 2.5 1.5' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round'/>"
    ),
    "history": (
        "<path d='M4.5 12a7.5 7.5 0 1 1 2.2 5.3' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round'/>"
        "<path d='M4.5 8v4h4' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round' stroke-linejoin='round'/>"
        "<path d='M12 8.5V12l2.5 2' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round' stroke-linejoin='round'/>"
    ),
    "page": (
        "<path d='M6 3.5h8L19 8.5v12H6z' stroke='{c}' stroke-width='1.6' fill='none' stroke-linejoin='round'/>"
        "<path d='M14 3.5V9h5' stroke='{c}' stroke-width='1.6' fill='none' stroke-linejoin='round'/>"
    ),
    "pages": (
        "<rect x='7' y='3.5' width='13.5' height='17' rx='1.5' stroke='{c}' stroke-width='1.6' fill='none'/>"
        "<path d='M4 6.5v13A1.5 1.5 0 0 0 5.5 21H17' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round'/>"
    ),
    "text": (
        "<path d='M5 6V4.5h14V6M12 4.5V19.5M9 19.5h6' stroke='{c}' stroke-width='1.6' fill='none' stroke-linecap='round'/>"
    ),
    "eye": (
        "<path d='M2.5 12S6 5.8 12 5.8 21.5 12 21.5 12 18 18.2 12 18.2 2.5 12 2.5 12z' stroke='{c}' stroke-width='1.6' fill='none' stroke-linejoin='round'/>"
        "<circle cx='12' cy='12' r='2.8' stroke='{c}' stroke-width='1.6' fill='none'/>"
    ),
}


def icon(name: str, color: str = "#2A2721", size: int = 24) -> QIcon:
    """Get the named icon in the given color (cached)."""
    key = (name, color, size)
    if key in _CACHE:
        return _CACHE[key]
    body = _PATHS.get(name)
    if body is None:
        body = _PATHS["page"]
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' "
           f"width='{size}' height='{size}'>{body.format(c=color)}</svg>")
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(size * 2, size * 2)  # 2x for crisp HiDPI
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, size * 2, size * 2))
    painter.end()
    ic = QIcon(pm)
    _CACHE[key] = ic
    return ic


def pixmap(name: str, color: str, size: int = 24) -> QPixmap:
    return icon(name, color, size).pixmap(size, size)


def available_icons() -> list[str]:
    return sorted(_PATHS.keys())


def app_icon_base64() -> str:
    """The app icon as SVG markup for the window icon."""
    body = _PATHS["app"]
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' "
           f"width='64' height='64'>{body.format(c='#C7522A')}</svg>")
    return svg


def make_window_icon() -> QIcon:
    """Render the app icon at several sizes for the window/taskbar."""
    result = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        svg = (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' "
               f"width='{size * 2}' height='{size * 2}'>"
               f"{_PATHS['app'].format(c='#C7522A')}</svg>")
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        img = QImage(size * 2, size * 2, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing, True)
        renderer.render(painter, QRectF(0, 0, size * 2, size * 2))
        painter.end()
        pm = QPixmap.fromImage(img)
        result.addPixmap(pm)
    return result
