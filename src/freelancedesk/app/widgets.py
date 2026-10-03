"""Небольшие виджеты для главного окна."""

from decimal import Decimal

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QTableWidgetItem, QWidget,
)

from freelancedesk.app.labels import format_short_money
from freelancedesk.core.manager import Attention, OrderView


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


class BarChart(QWidget):
    """Столбчатая диаграмма, нарисованная вручную через QPainter.

    Внешние библиотеки графиков не нужны: столбцы — это прямоугольники,
    подписи — текст. Данные: список пар (подпись, значение).
    """

    BAR_COLOR = QColor("#4a90d9")
    LAST_BAR_COLOR = QColor("#2e6db0")  # текущий месяц — темнее

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._data: list[tuple[str, Decimal]] = []
        self.setMinimumHeight(220)

    def set_data(self, data: list[tuple[str, Decimal]]) -> None:
        self._data = data
        self.update()  # попросить Qt перерисовать виджет (вызовет paintEvent)

    def paintEvent(self, event) -> None:  # noqa: N802 — имя задано Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text_color = self.palette().windowText().color()
        painter.setPen(text_color)

        if not self._data or all(v == 0 for _, v in self._data):
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Пока нет оплаченных заказов")
            return

        # Область столбцов: поля сверху под значения, снизу под подписи
        area = QRectF(self.rect()).adjusted(8, 22, -8, -24)
        max_value = max(v for _, v in self._data)
        slot = area.width() / len(self._data)  # ширина места под столбец
        bar_width = slot * 0.6

        for i, (label, value) in enumerate(self._data):
            left = area.left() + i * slot
            height = area.height() * float(value / max_value)
            bar = QRectF(left + (slot - bar_width) / 2,
                         area.bottom() - height, bar_width, height)
            is_last = i == len(self._data) - 1
            painter.fillRect(bar, self.LAST_BAR_COLOR if is_last
                             else self.BAR_COLOR)

            # Подпись месяца под столбцом
            painter.drawText(QRectF(left, area.bottom() + 4, slot, 18),
                             Qt.AlignmentFlag.AlignHCenter, label)
            # Сумма над столбцом (только если она есть)
            if value > 0:
                painter.drawText(QRectF(left, bar.top() - 18, slot, 16),
                                 Qt.AlignmentFlag.AlignHCenter,
                                 format_short_money(value))


class AttentionBanner(QFrame):
    """Жёлтая плашка над вкладками: что горит прямо сейчас.

    Каждая цифра — кнопка: нажал «Просрочено: 1» — в таблице
    остались только просроченные заказы.
    """

    # Сигнал: пользователь выбрал выборку заказов
    view_requested = pyqtSignal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("attentionBanner")
        # Цвета заданы явно, чтобы плашку было видно и в тёмной теме
        self.setStyleSheet(
            "#attentionBanner { background: #fff4ce; border: 1px solid #e6c84f;"
            " border-radius: 4px; }"
            "#attentionBanner QLabel, #attentionBanner QPushButton"
            " { color: #5c4500; }"
            "#attentionBanner QPushButton { border: none;"
            " text-decoration: underline; padding: 2px 6px; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.addWidget(QLabel("Требует внимания:"))

        self.buttons: dict[OrderView, QPushButton] = {}
        for view in (OrderView.OVERDUE, OrderView.DUE_TODAY,
                     OrderView.NO_RECEIPT):
            button = QPushButton()
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            # view=view — «запоминаем» значение для каждой кнопки,
            # иначе все лямбды увидят последнее значение цикла
            button.clicked.connect(
                lambda _, view=view: self.view_requested.emit(view))
            layout.addWidget(button)
            self.buttons[view] = button
        layout.addStretch(1)

    def set_attention(self, attention: Attention) -> None:
        """Обновить цифры; если ничего не горит — спрятать плашку."""
        counts = {
            OrderView.OVERDUE: ("Просрочено", attention.overdue),
            OrderView.DUE_TODAY: ("Сдать сегодня", attention.due_today),
            OrderView.NO_RECEIPT: ("Оплачено без чека", attention.no_receipt),
        }
        for view, (text, count) in counts.items():
            self.buttons[view].setText(f"{text}: {count}")
            self.buttons[view].setVisible(count > 0)
        self.setVisible(attention.total > 0)
