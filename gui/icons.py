"""Small hand-drawn monochrome icon set.

System icon themes turned out unreliable across distros/desktop
environments in testing — some icons were missing entirely (falling
back to faint default arrows), others came through in full color from
the theme, and contrast on dark themes was inconsistent. These are
instead drawn at runtime with QPainter using the current palette's
window-text color, so they always match the active theme and stay
visible on light or dark backgrounds alike.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def make_icon(draw_fn, color: QColor, size: int = 20) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(color, max(1.4, size / 11))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    draw_fn(painter, size)
    painter.end()
    return QIcon(pixmap)


def _line(p: QPainter, x1, y1, x2, y2):
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def draw_back(p: QPainter, s: int):
    m = s * 0.28
    _line(p, s - m, m, m, s / 2)
    _line(p, m, s / 2, s - m, s - m)


def draw_refresh(p: QPainter, s: int):
    cx, cy, r = s / 2, s / 2, s * 0.32
    rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
    p.drawArc(rect, 40 * 16, 280 * 16)
    ang = math.radians(40)
    tip = QPointF(cx + r * math.cos(ang), cy - r * math.sin(ang))
    _line(p, tip.x(), tip.y(), tip.x() - s * 0.03, tip.y() - s * 0.16)
    _line(p, tip.x(), tip.y(), tip.x() + s * 0.15, tip.y() - s * 0.06)


def draw_folder(p: QPainter, s: int):
    w, h = s * 0.78, s * 0.56
    x, y = (s - w) / 2, (s - h) / 2 + s * 0.06
    tab = w * 0.4
    path = QPainterPath()
    path.moveTo(x, y + h)
    path.lineTo(x, y + h * 0.2)
    path.lineTo(x + tab, y + h * 0.2)
    path.lineTo(x + tab + s * 0.06, y)
    path.lineTo(x + w, y)
    path.lineTo(x + w, y + h)
    path.closeSubpath()
    p.drawPath(path)


def draw_photos(p: QPainter, s: int):
    w, h = s * 0.72, s * 0.54
    x, y = (s - w) / 2, (s - h) / 2 + s * 0.08
    p.drawRoundedRect(QRectF(x, y, w, h), s * 0.06, s * 0.06)
    _line(p, x + w * 0.22, y, x + w * 0.4, y - h * 0.22)
    _line(p, x + w * 0.4, y - h * 0.22, x + w * 0.62, y - h * 0.22)
    _line(p, x + w * 0.62, y - h * 0.22, x + w * 0.78, y)
    p.drawEllipse(QRectF(x + w * 0.32, y + h * 0.18, w * 0.36, w * 0.36))


def draw_upload(p: QPainter, s: int):
    cx = s / 2
    top, bottom = s * 0.22, s * 0.78
    _line(p, cx, bottom, cx, top)
    _line(p, cx, top, cx - s * 0.18, top + s * 0.2)
    _line(p, cx, top, cx + s * 0.18, top + s * 0.2)


def draw_download(p: QPainter, s: int):
    cx = s / 2
    top, bottom = s * 0.22, s * 0.78
    _line(p, cx, top, cx, bottom)
    _line(p, cx, bottom, cx - s * 0.18, bottom - s * 0.2)
    _line(p, cx, bottom, cx + s * 0.18, bottom - s * 0.2)


def draw_login(p: QPainter, s: int):
    x0 = s * 0.58
    _line(p, x0, s * 0.2, x0, s * 0.8)
    _line(p, x0, s * 0.2, s * 0.78, s * 0.2)
    _line(p, x0, s * 0.8, s * 0.78, s * 0.8)
    _line(p, s * 0.2, s * 0.5, x0 - s * 0.04, s * 0.5)
    _line(p, x0 - s * 0.04, s * 0.5, x0 - s * 0.2, s * 0.5 - s * 0.15)
    _line(p, x0 - s * 0.04, s * 0.5, x0 - s * 0.2, s * 0.5 + s * 0.15)


def draw_logout(p: QPainter, s: int):
    x0 = s * 0.42
    _line(p, x0, s * 0.2, x0, s * 0.8)
    _line(p, x0, s * 0.2, s * 0.22, s * 0.2)
    _line(p, x0, s * 0.8, s * 0.22, s * 0.8)
    _line(p, x0, s * 0.5, s * 0.8, s * 0.5)
    _line(p, s * 0.8, s * 0.5, s * 0.64, s * 0.5 - s * 0.15)
    _line(p, s * 0.8, s * 0.5, s * 0.64, s * 0.5 + s * 0.15)


def draw_about(p: QPainter, s: int):
    p.drawEllipse(QRectF(s * 0.1, s * 0.1, s * 0.8, s * 0.8))
    color = p.pen().color()
    p.setBrush(color)
    p.drawEllipse(QRectF(s * 0.46, s * 0.26, s * 0.08, s * 0.08))
    p.setBrush(Qt.NoBrush)
    _line(p, s * 0.5, s * 0.44, s * 0.5, s * 0.72)


def draw_file(p: QPainter, s: int):
    w, h = s * 0.56, s * 0.72
    x, y = (s - w) / 2, (s - h) / 2
    fold = w * 0.32
    path = QPainterPath()
    path.moveTo(x, y)
    path.lineTo(x + w - fold, y)
    path.lineTo(x + w, y + fold)
    path.lineTo(x + w, y + h)
    path.lineTo(x, y + h)
    path.closeSubpath()
    p.drawPath(path)
    _line(p, x + w - fold, y, x + w - fold, y + fold)
    _line(p, x + w - fold, y + fold, x + w, y + fold)


DRAWERS = {
    "back": draw_back,
    "refresh": draw_refresh,
    "folder": draw_folder,
    "photos": draw_photos,
    "upload": draw_upload,
    "download": draw_download,
    "login": draw_login,
    "logout": draw_logout,
    "about": draw_about,
    "file": draw_file,
}
