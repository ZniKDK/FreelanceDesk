"""Общие виджеты и помощники для экранов приложения."""

from decimal import Decimal

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QAbstractItemView, QFrame, QHeaderView, QLabel, QProgressBar,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from freelancedesk.app.labels import format_money, format_short_money
from freelancedesk.app.theme import C, chip_style, icon


def label(text: str = "", role: str = "") -> QLabel:
    """Надпись с ролью из темы: muted, caption, value, section."""
    widget = QLabel(text)
    if role:
        # Свойство role читает QSS: QLabel[role="muted"] { ... }
        widget.setProperty("role", role)
    return widget


def button(text: str, icon_name: str = "", kind: str = "",
           icon_color: str = C["text2"]) -> QPushButton:
    """Кнопка с иконкой и видом из темы: primary, ghost, danger, chip."""
    widget = QPushButton(text)
    if kind:
        widget.setProperty("kind", kind)
    if icon_name:
        widget.setIcon(icon(icon_name, icon_color))
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    return widget


def chip(text: str, background: str, color: str) -> QLabel:
    """Метка-«таблетка» для статуса или оплаты."""
    widget = QLabel(text)
    widget.setStyleSheet(chip_style(background, color))
    widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return widget


def thin_progress(value: float, color: str = C["success"]) -> QProgressBar:
    """Тонкая полоска прогресса: value от 0 до 1."""
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(round(value * 100))
    bar.setTextVisible(False)
    # Цвет заполнения меняем только у этой полоски
    bar.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; }}")
    return bar


def clear_layout(layout) -> None:
    """Убрать все виджеты из слоя.

    setParent(None) сразу снимает виджет с экрана, а deleteLater удаляет
    его безопасно, когда Qt закончит текущую обработку событий. Без
    setParent старый виджет на мгновение остаётся видимым «призраком».
    """
    while layout.count():
        widget = layout.takeAt(0).widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()


class Card(QFrame):
    """Белая карточка со скруглёнными углами (стиль #card в теме)."""

    def __init__(self, title: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 14, 16, 14)
        self.body.setSpacing(8)
        if title:
            self.body.addWidget(label(title, "section"))


class StatCard(Card):
    """Карточка с показателем: подпись, крупное число, пояснение."""

    def __init__(self, caption: str, parent=None) -> None:
        super().__init__(parent=parent)
        self.caption = label(caption, "muted")
        self.value = label("—", "value")
        self.hint = label("", "caption")
        self.hint.setWordWrap(True)
        for widget in (self.caption, self.value, self.hint):
            self.body.addWidget(widget)
        self.body.addStretch(1)

    def set(self, value: str, hint: str = "") -> None:
        self.value.setText(value)
        self.hint.setText(hint)


class SortItem(QTableWidgetItem):
    """Ячейка таблицы со своим ключом сортировки.

    Обычная ячейка сортируется по тексту, и тогда «9 000 ₽» оказывается
    больше «10 000 ₽», а даты сортируются по дню, а не по году.
    Здесь сортировка идёт по настоящему значению: числу, дате, номеру.
    """

    def __init__(self, text: str, sort_key=None) -> None:
        super().__init__(text)
        # Без ключа сортируем по тексту без учёта регистра
        self.sort_key = text.casefold() if sort_key is None else sort_key

    def __lt__(self, other: QTableWidgetItem) -> bool:
        # __lt__ — оператор «меньше»; Qt вызывает его при сортировке
        if isinstance(other, SortItem):
            return self.sort_key < other.sort_key
        return super().__lt__(other)


def money_item(amount: Decimal) -> SortItem:
    """Ячейка с суммой: выравнивание вправо, сортировка по числу."""
    item = SortItem(format_money(amount), amount)
    item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                          | Qt.AlignmentFlag.AlignVCenter)
    return item


def make_table(headers: list[str], sort_column: int = 0,
               descending: bool = False) -> QTableWidget:
    """Таблица только для чтения: выделение строк, сортировка по клику.

    sort_column — колонка, по которой таблица отсортирована при открытии.
    """
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(34)  # высота строки
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
    order = (Qt.SortOrder.DescendingOrder if descending
             else Qt.SortOrder.AscendingOrder)
    header.setSortIndicator(sort_column, order)
    return table


def selected_id(table: QTableWidget) -> int | None:
    """id записи в выделенной строке (хранится в данных первой ячейки)."""
    row = table.currentRow()
    if row < 0 or table.item(row, 0) is None:
        return None
    return table.item(row, 0).data(Qt.ItemDataRole.UserRole)


def fill_table(table: QTableWidget,
               rows: list[tuple[int, list[QTableWidgetItem]]]) -> None:
    """Заполнить таблицу строками (id записи, ячейки).

    Во время заполнения сортировку отключаем: иначе Qt пересортировывает
    таблицу после каждой ячейки, и строки перемешиваются.
    """
    keep_id = selected_id(table)  # чтобы после обновления выделение осталось
    table.setSortingEnabled(False)
    table.setRowCount(len(rows))
    for row, (record_id, items) in enumerate(rows):
        for col, item in enumerate(items):
            table.setItem(row, col, item)
        # id прячем в данные первой ячейки: на экране его не видно
        table.item(row, 0).setData(Qt.ItemDataRole.UserRole, record_id)
    table.setSortingEnabled(True)
    if keep_id is not None:
        for row in range(table.rowCount()):
            if table.item(row, 0).data(Qt.ItemDataRole.UserRole) == keep_id:
                table.selectRow(row)
                break


class BarChart(QWidget):
    """Столбчатая диаграмма, нарисованная вручную через QPainter.

    Внешние библиотеки графиков не нужны: столбцы — это прямоугольники,
    подписи — текст. Данные: список пар (подпись, значение).
    """

    BAR_COLOR = QColor("#9dbcf0")
    LAST_BAR_COLOR = QColor(C["accent"])  # текущий месяц — ярче

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._data: list[tuple[str, Decimal]] = []
        self.setMinimumHeight(200)

    def set_data(self, data: list[tuple[str, Decimal]]) -> None:
        self._data = data
        self.update()  # попросить Qt перерисовать виджет (вызовет paintEvent)

    def paintEvent(self, event) -> None:  # noqa: N802 — имя задано Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(C["text2"]))

        if not self._data or all(v == 0 for _, v in self._data):
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Здесь появятся поступления по месяцам")
            return

        # Область столбцов: поля сверху под значения, снизу под подписи
        area = QRectF(self.rect()).adjusted(4, 22, -4, -24)
        max_value = max(v for _, v in self._data)
        slot = area.width() / len(self._data)  # ширина места под столбец
        bar_width = min(slot * 0.62, 36)
        painter.setPen(Qt.PenStyle.NoPen)

        for i, (caption, value) in enumerate(self._data):
            left = area.left() + i * slot
            height = max(area.height() * float(value / max_value),
                         2 if value > 0 else 0)
            bar = QRectF(left + (slot - bar_width) / 2,
                         area.bottom() - height, bar_width, height)
            is_last = i == len(self._data) - 1
            painter.setBrush(self.LAST_BAR_COLOR if is_last
                             else self.BAR_COLOR)
            painter.drawRoundedRect(bar, 3, 3)

            painter.setPen(QColor(C["text2"]))
            # Подпись месяца под столбцом
            painter.drawText(QRectF(left, area.bottom() + 4, slot, 18),
                             Qt.AlignmentFlag.AlignHCenter, caption)
            # Сумма над столбцом (только если она есть)
            if value > 0:
                painter.drawText(QRectF(left, bar.top() - 18, slot, 16),
                                 Qt.AlignmentFlag.AlignHCenter,
                                 format_short_money(value))
            painter.setPen(Qt.PenStyle.NoPen)
