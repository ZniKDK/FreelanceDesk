"""Оформление приложения: цвета, шрифт, стили (QSS) и иконки.

QSS — это «CSS для Qt»: те же селекторы и свойства, только для виджетов.
Цвета собраны в словарь C, чтобы менять тему в одном месте.
Иконки — набор Lucide (лицензия ISC, resources/icons/LICENSE-lucide.txt).
"""

from functools import cache

from PyQt6.QtCore import QByteArray, QSize, Qt
from PyQt6.QtGui import QFont, QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

from freelancedesk.config import resource_dir
from freelancedesk.core.manager import PaymentState
from freelancedesk.core.models import OrderStatus

# Палитра светлой темы
C = {
    "bg": "#f5f6f8",            # фон окна
    "surface": "#ffffff",       # карточки, списки, поля ввода
    "sidebar": "#eceff3",       # боковое меню
    "hover": "#eef1f5",         # подсветка при наведении
    "border": "#e2e5ea",        # тонкие рамки
    "border_strong": "#cfd4dc",  # рамки полей ввода и кнопок
    "track": "#e9ecf0",         # фон полоски прогресса
    "text": "#1f2328",          # основной текст
    "text2": "#667085",         # второстепенный текст
    "accent": "#2f6fdf",        # главный цвет (кнопка «Новый заказ»)
    "accent_hover": "#2560c7",
    "accent_bg": "#e7effd",     # фон выбранного пункта меню и фильтра
    "selected": "#f1f6fe",      # фон выбранной строки списка
    "accent_text": "#1d4fae",
    "success": "#1f9d55",
    "success_bg": "#e3f4ea",
    "success_text": "#17663a",
    "warning": "#c27c0e",
    "warning_bg": "#fdf3dc",
    "warning_text": "#8a5a00",
    "danger": "#d64545",
    "danger_bg": "#fdecec",
    "danger_text": "#a32d2d",
    "neutral_bg": "#eef0f3",
    "neutral_text": "#4b5563",
}

# Метки статусов работы: (текст, фон, цвет текста)
STATUS_CHIPS = {
    OrderStatus.NEW: ("Новый", C["neutral_bg"], C["neutral_text"]),
    OrderStatus.IN_PROGRESS: ("В работе", C["accent_bg"], C["accent_text"]),
    OrderStatus.DELIVERED: ("Сдан", C["success_bg"], C["success_text"]),
    OrderStatus.CANCELLED: ("Отменён", C["neutral_bg"], C["text2"]),
}

# Метки состояния оплаты
PAYMENT_CHIPS = {
    PaymentState.UNPAID: ("Не оплачен", C["neutral_bg"], C["neutral_text"]),
    PaymentState.PARTIAL: ("Частично", C["warning_bg"], C["warning_text"]),
    PaymentState.PAID: ("Оплачен", C["success_bg"], C["success_text"]),
}

# Цвет полоски оплаты по состоянию
PAYMENT_BAR_COLORS = {
    PaymentState.UNPAID: C["border_strong"],
    PaymentState.PARTIAL: C["warning"],
    PaymentState.PAID: C["success"],
}

STYLE = f"""
QWidget {{ color: {C['text']}; }}
QMainWindow, QWidget#page, QStackedWidget {{ background: {C['bg']}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

QFrame#sidebar {{ background: {C['sidebar']};
    border-right: 1px solid {C['border']}; }}
QLabel#appTitle {{ font-size: 13pt; font-weight: 600; padding: 2px 10px; }}
QFrame#sidebar QPushButton {{ text-align: left; padding: 8px 10px;
    border: none; border-radius: 6px; background: transparent;
    color: {C['text2']}; }}
QFrame#sidebar QPushButton:hover {{ background: {C['hover']}; }}
QFrame#sidebar QPushButton:checked {{ background: {C['accent_bg']};
    color: {C['accent_text']}; font-weight: 600; }}

QLabel#pageTitle {{ font-size: 17pt; font-weight: 600; }}
QLabel[role="muted"] {{ color: {C['text2']}; }}
QLabel[role="caption"] {{ color: {C['text2']}; font-size: 9pt; }}
QLabel[role="value"] {{ font-size: 17pt; font-weight: 600; }}
QLabel[role="section"] {{ font-weight: 600; font-size: 11pt; }}

QFrame#card {{ background: {C['surface']}; border: 1px solid {C['border']};
    border-radius: 10px; }}
QFrame#moneyBox {{ background: {C['bg']}; border-radius: 8px; }}

QPushButton {{ background: {C['surface']};
    border: 1px solid {C['border_strong']}; border-radius: 6px;
    padding: 6px 12px; }}
QPushButton:hover {{ background: {C['hover']}; }}
QPushButton:pressed {{ background: {C['border']}; }}
QPushButton[kind="primary"] {{ background: {C['accent']}; color: white;
    border: none; font-weight: 600; }}
QPushButton[kind="primary"]:hover {{ background: {C['accent_hover']}; }}
QPushButton[kind="ghost"] {{ border: none; background: transparent;
    padding: 4px 6px; }}
QPushButton[kind="ghost"]:hover {{ background: {C['hover']}; }}
QPushButton[kind="danger"] {{ color: {C['danger_text']}; }}
QPushButton[kind="chip"] {{ border-radius: 13px; padding: 4px 12px;
    border: 1px solid {C['border']}; color: {C['text2']}; }}
QPushButton[kind="chip"]:checked {{ background: {C['accent_bg']};
    color: {C['accent_text']}; border-color: {C['accent_bg']}; }}
QPushButton[kind="segment"] {{ border-radius: 0; padding: 6px 4px;
    border: 1px solid {C['border_strong']}; color: {C['text2']}; }}
QPushButton[kind="segment"]:checked {{ background: {C['accent_bg']};
    color: {C['accent_text']}; font-weight: 600; }}
QPushButton[kind="receipt"] {{ border-radius: 10px; padding: 2px 8px;
    border: none; background: {C['warning_bg']};
    color: {C['warning_text']}; }}
QPushButton[kind="receipt"]:checked {{ background: {C['success_bg']};
    color: {C['success_text']}; }}

QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{
    background: {C['surface']}; border: 1px solid {C['border_strong']};
    border-radius: 6px; padding: 5px 8px; }}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QPlainTextEdit:focus {{ border-color: {C['accent']}; }}
QLineEdit:disabled, QDateEdit:disabled {{ color: {C['text2']};
    background: {C['bg']}; }}

QListWidget, QTableWidget {{ background: {C['surface']};
    border: 1px solid {C['border']}; border-radius: 10px; outline: none; }}
QListWidget::item {{ border-bottom: 1px solid {C['border']}; }}
QListWidget::item:hover {{ background: {C['hover']}; }}
QListWidget::item:selected {{ background: {C['selected']};
    color: {C['text']}; }}
QTableWidget {{ gridline-color: transparent;
    selection-background-color: {C['accent_bg']};
    selection-color: {C['text']}; alternate-background-color: #fafbfc; }}
QHeaderView::section {{ background: {C['surface']}; border: none;
    border-bottom: 1px solid {C['border']}; padding: 6px 8px;
    color: {C['text2']}; font-weight: 600; }}

QProgressBar {{ border: none; background: {C['track']}; border-radius: 3px;
    max-height: 6px; min-height: 6px; }}
QProgressBar::chunk {{ background: {C['success']}; border-radius: 3px; }}

QMenuBar {{ background: {C['surface']};
    border-bottom: 1px solid {C['border']}; padding: 2px 4px; }}
QMenuBar::item {{ background: transparent; padding: 4px 10px;
    border-radius: 4px; }}
QMenuBar::item:selected {{ background: {C['hover']}; }}
QMenu {{ background: {C['surface']}; border: 1px solid {C['border']};
    padding: 4px; }}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {C['accent_bg']};
    color: {C['accent_text']}; }}
QToolTip {{ background: {C['text']}; color: white; border: none;
    padding: 4px 8px; }}
"""


def apply_theme(app: QApplication) -> None:
    """Включить оформление для всего приложения."""
    # Fusion — встроенный стиль Qt, одинаково выглядит везде и хорошо
    # дружит с QSS (системный стиль Windows часть свойств игнорирует)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE)


@cache  # каждую иконку нужного цвета рисуем один раз
def icon(name: str, color: str = C["text2"], size: int = 18) -> QIcon:
    """Иконка Lucide нужного цвета.

    SVG-файлы Lucide рисуют линии цветом currentColor. Подменяем его
    на нужный цвет и рисуем картинку с запасом по чёткости (×2).
    """
    path = resource_dir() / "resources" / "icons" / f"{name}.svg"
    svg = path.read_text(encoding="utf-8").replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(QSize(size * 2, size * 2))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


def chip_style(background: str, color: str) -> str:
    """Стиль метки-«таблетки» (статус, оплата)."""
    return (f"background: {background}; color: {color}; border-radius: 9px;"
            " padding: 2px 8px; font-size: 9pt;")
