"""Сделать иконку программы resources/app.ico.

Иконка: белый портфель (Lucide «briefcase») на синем скруглённом
квадрате. ICO содержит сразу несколько размеров (16–256 пикселей),
Windows сам выбирает подходящий для панели задач, ярлыка и проводника.

Запуск: python tools/make_icon.py
"""

import sys
from pathlib import Path

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
ACCENT = "#2f6fdf"


def render(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(ACCENT))
    radius = size * 0.22
    painter.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)
    svg = (ROOT / "resources" / "icons" / "briefcase.svg").read_text(
        encoding="utf-8").replace("currentColor", "#ffffff")
    margin = size * 0.2
    QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(
        painter, QRectF(margin, margin, size - 2 * margin, size - 2 * margin))
    painter.end()
    return image


def main() -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841 — нужен для отрисовки
    target = ROOT / "resources" / "app.ico"
    # Qt записывает в ICO одно изображение; Windows масштабирует его сам,
    # поэтому берём самый крупный размер — так иконка чёткая везде
    if not render(256).save(str(target), "ICO"):
        raise SystemExit("Не удалось сохранить иконку")
    render(256).save(str(ROOT / "resources" / "app.png"), "PNG")
    print("Готово:", target)


if __name__ == "__main__":
    main()
