"""Оформление приложения: светлая и тёмная темы, стили (QSS), иконки.

QSS — это «CSS для Qt»: те же селекторы и свойства, только для виджетов.
Цвета текущей темы лежат в словаре C. При смене темы словарь
перезаполняется, стили пересобираются, а окно строит экраны заново.

Кроме QSS программа задаёт и палитру Qt (QPalette): по ней рисуются
выпадающие списки, календарь, окна сообщений. Без неё Windows в тёмном
режиме подмешивает свои цвета, и текст сливается с фоном.

Иконки — набор Lucide (лицензия ISC, resources/icons/LICENSE-lucide.txt).
"""

import tempfile
from functools import cache
from pathlib import Path

from PyQt6.QtCore import QByteArray, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

from freelancedesk.config import resource_dir
from freelancedesk.core.manager import PaymentState
from freelancedesk.core.models import OrderStatus

LIGHT = {
    "bg": "#f5f6f8",            # фон окна
    "surface": "#ffffff",       # карточки, списки, поля ввода
    "sidebar": "#eceff3",       # боковое меню
    "hover": "#eef1f5",         # подсветка при наведении
    "border": "#e2e5ea",        # тонкие рамки
    "border_strong": "#cfd4dc",  # рамки полей ввода и кнопок
    "track": "#e9ecf0",         # фон полоски прогресса
    "alt_row": "#fafbfc",       # чередование строк таблицы
    "text": "#1f2328",          # основной текст
    "text2": "#667085",         # второстепенный текст
    "accent": "#2f6fdf",        # главный цвет (кнопка «Новый заказ»)
    "accent_hover": "#2560c7",
    "accent_bg": "#e7effd",     # фон выбранного пункта меню и фильтра
    "accent_text": "#1d4fae",
    "selected": "#f1f6fe",      # фон выбранной строки списка
    "chart_bar": "#9dbcf0",     # столбцы диаграммы
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
    "tooltip_bg": "#1f2328",
    "tooltip_text": "#ffffff",
    "toast_link": "#8db4ff",    # кнопка в уведомлении (на тёмном фоне)
}

DARK = {
    "bg": "#15171c",
    "surface": "#1e2128",
    "sidebar": "#191b21",
    "hover": "#2a2e37",
    "border": "#2c3039",
    "border_strong": "#3c414c",
    "track": "#2c3039",
    "alt_row": "#22252d",
    "text": "#e6e8eb",
    "text2": "#98a1b0",
    "accent": "#4c8dff",
    "accent_hover": "#6a9fff",
    "accent_bg": "#1e3256",
    "accent_text": "#a9c7ff",
    "selected": "#212a3a",
    "chart_bar": "#34507f",
    "success": "#3fbf7f",
    "success_bg": "#16372a",
    "success_text": "#7fd8a8",
    "warning": "#e0a33a",
    "warning_bg": "#3a2d12",
    "warning_text": "#f0c674",
    "danger": "#f06a6a",
    "danger_bg": "#3b1d1f",
    "danger_text": "#ff9a9a",
    "neutral_bg": "#2a2e37",
    "neutral_text": "#b8bfcc",
    "tooltip_bg": "#e6e8eb",
    "tooltip_text": "#15171c",
    "toast_link": "#1d4fae",
}

# Цвета текущей темы. Это один и тот же словарь на всё время работы:
# при смене темы меняется его содержимое (см. apply_theme)
C = dict(LIGHT)

# Режимы темы: (ключ, подпись в меню)
THEME_MODES = [("light", "Светлая"), ("dark", "Тёмная"),
               ("system", "Как в системе")]

STATUS_TEXT = {
    OrderStatus.NEW: "Новый",
    OrderStatus.IN_PROGRESS: "В работе",
    OrderStatus.DELIVERED: "Сдан",
    OrderStatus.CANCELLED: "Отменён",
}


def is_dark() -> bool:
    """Включена ли сейчас тёмная тема."""
    return C["bg"] == DARK["bg"]


def status_chip(status: OrderStatus) -> tuple[str, str, str]:
    """Метка статуса работы: (текст, фон, цвет текста) в текущей теме."""
    colors = {
        OrderStatus.NEW: ("neutral_bg", "neutral_text"),
        OrderStatus.IN_PROGRESS: ("accent_bg", "accent_text"),
        OrderStatus.DELIVERED: ("success_bg", "success_text"),
        OrderStatus.CANCELLED: ("neutral_bg", "text2"),
    }
    bg, fg = colors[status]
    return STATUS_TEXT[status], C[bg], C[fg]


def payment_bar_color(state: PaymentState) -> str:
    """Цвет полоски оплаты: серая — нет денег, жёлтая — часть, зелёная — всё."""
    return {PaymentState.UNPAID: C["border_strong"],
            PaymentState.PARTIAL: C["warning"],
            PaymentState.PAID: C["success"]}[state]


def tone_color(tone: str) -> str:
    """Цвет текста срока по «тону» из labels.deadline_text."""
    return {"danger": C["danger_text"],
            "warning": C["warning_text"]}.get(tone, C["text2"])


def _svg_text(name: str, color: str) -> str:
    """SVG-иконка Lucide с подменой currentColor на нужный цвет."""
    path = resource_dir() / "resources" / "icons" / f"{name}.svg"
    return path.read_text(encoding="utf-8").replace("currentColor", color)


def icon_file(name: str, color: str) -> str:
    """Путь к перекрашенной иконке-файлу — для QSS (url(...)).

    QSS умеет брать картинки только из файлов, поэтому складываем
    перекрашенные копии во временную папку системы.
    """
    folder = Path(tempfile.gettempdir()) / "freelancedesk-icons"
    folder.mkdir(exist_ok=True)
    path = folder / f"{name}-{color.lstrip('#')}.svg"
    if not path.exists():
        path.write_text(_svg_text(name, color), encoding="utf-8")
    return path.as_posix()  # QSS понимает только прямые слэши


def build_style() -> str:
    """Собрать таблицу стилей QSS из цветов текущей темы."""
    down = icon_file("chevron-down", C["text2"])
    check = icon_file("check", C["accent"])
    up = icon_file("chevron-up", C["text2"])
    return f"""
QWidget {{ color: {C['text']}; }}
QMainWindow, QDialog, QMessageBox, QWidget#page, QStackedWidget {{
    background: {C['bg']}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

QFrame#sidebar {{ background: {C['sidebar']};
    border-right: 1px solid {C['border']}; }}
QLabel#appTitle {{ font-size: 13pt; font-weight: 600; padding: 2px 10px; }}
QFrame#sidebar QPushButton {{ text-align: left; padding: 8px 10px;
    border: none; border-radius: 6px; background: transparent;
    color: {C['text2']}; }}
QFrame#sidebar QPushButton:hover {{ background: {C['hover']}; }}
QFrame#sidebar QPushButton:checked {{ color: {C['accent_text']};
    background: transparent; }}
QFrame#sidebar QPushButton:checked:hover {{ background: transparent; }}
QFrame#navIndicator {{ background: {C['accent_bg']}; border-radius: 6px; }}
QFrame#sidebar QPushButton::menu-indicator {{ image: none; width: 0; }}

QLabel#pageTitle {{ font-size: 17pt; font-weight: 600; }}
QLabel[role="muted"] {{ color: {C['text2']}; }}
QLabel[role="caption"] {{ color: {C['text2']}; font-size: 9pt; }}
QLabel[role="value"] {{ font-size: 17pt; font-weight: 600; }}
QLabel[role="section"] {{ font-weight: 600; font-size: 11pt; }}

QFrame#card {{ background: {C['surface']}; border: 1px solid {C['border']};
    border-radius: 10px; }}
QFrame#moneyBox {{ background: {C['bg']}; border-radius: 8px; }}
QFrame#toast {{ background: {C['tooltip_bg']}; border-radius: 8px; }}
QFrame#toast QLabel {{ color: {C['tooltip_text']}; }}
QFrame#toast QPushButton {{ color: {C['toast_link']};
    background: transparent; border: none; font-weight: 600;
    padding: 2px 6px; }}

QPushButton {{ background: {C['surface']}; color: {C['text']};
    border: 1px solid {C['border_strong']}; border-radius: 6px;
    padding: 6px 12px; }}
QPushButton:hover {{ background: {C['hover']}; }}
QPushButton:pressed {{ background: {C['border']}; }}
QPushButton:disabled {{ color: {C['text2']}; }}
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
    background: {C['surface']}; color: {C['text']};
    border: 1px solid {C['border_strong']}; border-radius: 6px;
    padding: 5px 8px; selection-background-color: {C['accent']};
    selection-color: white; }}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QPlainTextEdit:focus {{ border-color: {C['accent']}; }}
QLineEdit:disabled, QDateEdit:disabled {{ color: {C['text2']};
    background: {C['bg']}; }}

QComboBox, QDateEdit {{ padding-right: 26px; }}
QComboBox::drop-down, QDateEdit::drop-down {{ subcontrol-origin: padding;
    subcontrol-position: center right; width: 24px; border: none; }}
QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url({down});
    width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{ background: {C['surface']};
    color: {C['text']}; border: 1px solid {C['border']}; outline: 0;
    padding: 4px; selection-background-color: {C['accent_bg']};
    selection-color: {C['accent_text']}; }}

QSpinBox, QDoubleSpinBox {{ padding-right: 22px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; width: 20px; border: none;
    background: transparent; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-position: top right; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-position: bottom right; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({up});
    width: 10px; height: 10px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({down});
    width: 10px; height: 10px; }}

QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background: {C['surface']}; }}
QCalendarWidget QToolButton {{ color: {C['text']}; background: transparent;
    border: none; padding: 4px 8px; }}
QCalendarWidget QToolButton:hover {{ background: {C['hover']};
    border-radius: 4px; }}
QCalendarWidget QAbstractItemView {{ background: {C['surface']};
    color: {C['text']}; selection-background-color: {C['accent']};
    selection-color: white; outline: 0; }}
QCalendarWidget QAbstractItemView:disabled {{ color: {C['text2']}; }}

QCheckBox {{ spacing: 8px; }}

QListWidget, QTableWidget {{ background: {C['surface']};
    border: 1px solid {C['border']}; border-radius: 10px; outline: none; }}
QListWidget::item {{ border-bottom: 1px solid {C['border']}; }}
QListWidget::item:hover {{ background: {C['hover']}; }}
QListWidget::item:selected {{ background: {C['selected']};
    color: {C['text']}; }}
QTableWidget {{ gridline-color: transparent;
    selection-background-color: {C['accent_bg']};
    selection-color: {C['text']};
    alternate-background-color: {C['alt_row']}; }}
QHeaderView::section {{ background: {C['surface']}; border: none;
    border-bottom: 1px solid {C['border']};
    border-right: 1px solid {C['border']}; padding: 6px 8px;
    color: {C['text2']}; font-weight: 600; }}
QHeaderView[editing="true"]::section {{ background: {C['accent_bg']};
    color: {C['accent_text']}; border-right: 1px dashed {C['accent']}; }}
QTableView::item {{ border-right: 1px solid {C['border']};
    padding: 0 6px; }}
QFrame#editBar {{ background: {C['accent_bg']}; border-radius: 8px; }}
QFrame#editBar QLabel {{ color: {C['accent_text']}; }}
QTableCornerButton::section {{ background: {C['surface']}; border: none; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px;
    margin: 2px; }}
QScrollBar::handle:vertical {{ background: {C['border_strong']};
    border-radius: 3px; min-height: 32px; }}
QScrollBar::handle:horizontal {{ background: {C['border_strong']};
    border-radius: 3px; min-width: 32px; }}
QScrollBar::handle:hover {{ background: {C['text2']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: 10px; }}
QSplitter::handle:hover {{ background: {C['border']}; border-radius: 3px; }}

QProgressBar {{ border: none; background: {C['track']}; border-radius: 3px;
    max-height: 6px; min-height: 6px; }}
QProgressBar::chunk {{ background: {C['success']}; border-radius: 3px; }}

QMenu {{ background: {C['surface']}; color: {C['text']};
    border: 1px solid {C['border']}; padding: 4px; }}
QMenu::item {{ padding: 6px 24px 6px 28px; border-radius: 4px; }}
QMenu::item:selected {{ background: {C['accent_bg']};
    color: {C['accent_text']}; }}
QMenu::item:checked {{ color: {C['accent_text']}; }}
QMenu::indicator {{ width: 16px; height: 16px; left: 6px; }}
QMenu::indicator:checked {{ image: url({check}); }}
QMenu::separator {{ height: 1px; background: {C['border']};
    margin: 4px 8px; }}
QToolTip {{ background: {C['tooltip_bg']}; color: {C['tooltip_text']};
    border: none; padding: 4px 8px; }}
"""


def make_palette() -> QPalette:
    """Палитра Qt в цветах текущей темы — для стандартных окон и списков."""
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: C["bg"],
        QPalette.ColorRole.WindowText: C["text"],
        QPalette.ColorRole.Base: C["surface"],
        QPalette.ColorRole.AlternateBase: C["alt_row"],
        QPalette.ColorRole.Text: C["text"],
        QPalette.ColorRole.Button: C["surface"],
        QPalette.ColorRole.ButtonText: C["text"],
        QPalette.ColorRole.Highlight: C["accent"],
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.ToolTipBase: C["tooltip_bg"],
        QPalette.ColorRole.ToolTipText: C["tooltip_text"],
        QPalette.ColorRole.PlaceholderText: C["text2"],
        QPalette.ColorRole.Link: C["accent"],
        QPalette.ColorRole.Mid: C["border_strong"],
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    # Неактивные элементы — приглушённым цветом
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText,
                 QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role,
                         QColor(C["text2"]))
    return palette


def resolve_mode(app: QApplication, mode: str) -> str:
    """'system' -> 'light' или 'dark' по настройке Windows."""
    if mode != "system":
        return mode
    scheme = app.styleHints().colorScheme()
    return "dark" if scheme == Qt.ColorScheme.Dark else "light"


def apply_theme(app: QApplication, mode: str = "light") -> str:
    """Включить тему для всего приложения. Возвращает 'light' или 'dark'.

    mode — 'light', 'dark' или 'system' (как в Windows).
    """
    resolved = resolve_mode(app, mode)
    C.clear()
    C.update(DARK if resolved == "dark" else LIGHT)
    icon.cache_clear()  # иконки рисуются цветом темы — перерисовать
    # Fusion — встроенный стиль Qt, одинаково выглядит везде и хорошо
    # дружит с QSS (системный стиль Windows часть свойств игнорирует)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setPalette(make_palette())
    app.setStyleSheet(build_style())
    return resolved


@cache  # каждую иконку нужного цвета рисуем один раз
def icon(name: str, color: str | None = None, size: int = 18) -> QIcon:
    """Иконка Lucide нужного цвета (по умолчанию — второстепенный текст).

    SVG-файлы Lucide рисуют линии цветом currentColor. Подменяем его
    на нужный цвет и рисуем картинку с запасом по чёткости (×2).
    """
    svg = _svg_text(name, color or C["text2"])
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
