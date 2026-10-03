"""Общие виджеты и помощники для экранов приложения.

Цвета берутся из theme.C в момент создания или отрисовки виджета,
поэтому после смены темы новые виджеты сразу получают новые цвета.
"""

from collections.abc import Callable
from decimal import Decimal

from PyQt6.QtCore import QPoint, QPropertyAnimation, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QAbstractItemView, QFrame, QGraphicsOpacityEffect, QHBoxLayout,
    QHeaderView, QLabel, QProgressBar, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from freelancedesk.app import animations
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
           icon_color: str | None = None) -> QPushButton:
    """Кнопка с иконкой и видом из темы: primary, ghost, danger, chip."""
    widget = QPushButton(text)
    if kind:
        widget.setProperty("kind", kind)
    if icon_name:
        widget.setIcon(icon(icon_name, icon_color))
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    return widget


def set_fitting_text(widget: QPushButton, text: str, padding: int = 30
                     ) -> None:
    """Задать текст кнопки и ширину, в которую он точно поместится.

    Qt считает ширину кнопки без учёта отступов из QSS, поэтому
    длинные подписи («Сдать сегодня 1») обрезались. Считаем сами:
    ширина текста в пикселях + отступы слева и справа.
    """
    widget.setText(text)
    width = widget.fontMetrics().horizontalAdvance(text) + padding
    widget.setMinimumWidth(width)


def chip(text: str, background: str, color: str) -> QLabel:
    """Метка-«таблетка» для статуса или оплаты."""
    widget = QLabel(text)
    widget.setStyleSheet(chip_style(background, color))
    widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return widget


def bar_style(color: str) -> str:
    """Стиль заполнения полоски прогресса нужного цвета."""
    return f"QProgressBar::chunk {{ background: {color}; }}"


def thin_progress(value: float, color: str | None = None) -> QProgressBar:
    """Тонкая полоска прогресса: value от 0 до 1."""
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(round(value * 100))
    bar.setTextVisible(False)
    bar.setStyleSheet(bar_style(color or C["success"]))
    return bar


def clear_layout(layout) -> None:
    """Убрать все виджеты из слоя.

    hide() сразу убирает виджет с экрана, deleteLater удаляет его
    безопасно, когда Qt закончит текущую обработку событий.
    (Раньше здесь был setParent(None) — от него виджет на миг
    становился отдельным пустым окном.)
    """
    while layout.count():
        widget = layout.takeAt(0).widget()
        if widget is not None:
            widget.hide()
            widget.deleteLater()


class Card(QFrame):
    """Карточка со скруглёнными углами (стиль #card в теме)."""

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
        self._number: Decimal | None = None
        for widget in (self.caption, self.value, self.hint):
            self.body.addWidget(widget)
        self.body.addStretch(1)

    def set(self, value: str, hint: str = "") -> None:
        self.value.setText(value)
        self.hint.setText(hint)

    def set_money(self, amount: Decimal, hint: str = "",
                  kopecks: bool = False) -> None:
        """Показать сумму; при изменении число плавно «досчитывает»."""
        self.hint.setText(hint)
        start = self._number if self._number is not None else Decimal("0")
        self._number = amount

        def show(value: float) -> None:
            # Кадр анимации — float; округляем до копеек и переводим
            # в Decimal через строку, чтобы не было «хвостов» float
            self.value.setText(format_money(Decimal(str(round(value, 2))),
                                            kopecks))

        animations.count_up(self, float(start), float(amount), show)


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
    При новых данных столбцы плавно вырастают.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._data: list[tuple[str, Decimal]] = []
        self._grow = 1.0  # доля высоты столбцов, анимируется от 0 до 1
        self.setMinimumHeight(200)

    def set_data(self, data: list[tuple[str, Decimal]]) -> None:
        changed = data != self._data
        self._data = data
        if changed:
            animations.progress_animation(self, self._set_grow, 600)
        self.update()  # попросить Qt перерисовать виджет (вызовет paintEvent)

    def replay(self) -> None:
        """Проиграть рост столбцов заново (при открытии экрана)."""
        animations.progress_animation(self, self._set_grow, 600)

    def _set_grow(self, value: float) -> None:
        self._grow = value
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 — имя задано Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text_color = QColor(C["text2"])
        painter.setPen(text_color)

        if not self._data or all(v == 0 for _, v in self._data):
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Здесь появятся поступления по месяцам")
            return

        # Область столбцов: поля сверху под значения, снизу под подписи
        area = QRectF(self.rect()).adjusted(4, 22, -4, -24)
        max_value = max(v for _, v in self._data)
        slot = area.width() / len(self._data)  # ширина места под столбец
        bar_width = min(slot * 0.62, 36)

        for i, (caption, value) in enumerate(self._data):
            left = area.left() + i * slot
            full = area.height() * float(value / max_value)
            height = max(full * self._grow, 2 if value > 0 else 0)
            bar = QRectF(left + (slot - bar_width) / 2,
                         area.bottom() - height, bar_width, height)
            is_last = i == len(self._data) - 1  # текущий месяц — ярче
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(C["accent"] if is_last
                                    else C["chart_bar"]))
            painter.drawRoundedRect(bar, 3, 3)

            painter.setPen(text_color)
            # Подпись месяца под столбцом
            painter.drawText(QRectF(left, area.bottom() + 4, slot, 18),
                             Qt.AlignmentFlag.AlignHCenter, caption)
            # Сумма над столбцом — когда столбец почти вырос
            if value > 0 and self._grow > 0.8:
                painter.drawText(QRectF(left, bar.top() - 18, slot, 16),
                                 Qt.AlignmentFlag.AlignHCenter,
                                 format_short_money(value))


class Toast(QFrame):
    """Всплывающее уведомление внизу окна: «Статус: Сдан» [Показать].

    Висит поверх содержимого (не в слое), выезжает снизу, через
    несколько секунд тает. Кнопка действия необязательна.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 10, 10)
        layout.setSpacing(12)
        self.text = QLabel()
        self.action = QPushButton()
        self.action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action.clicked.connect(self._on_action)
        layout.addWidget(self.text)
        layout.addWidget(self.action)
        self._callback: Callable[[], None] | None = None
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        # Таймер скрытия: перезапускается при каждом новом сообщении
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self.hide()

    def show_message(self, text: str, action_text: str = "",
                     callback: Callable[[], None] | None = None,
                     timeout: int = 4000) -> None:
        self.text.setText(text)
        self._callback = callback
        self.action.setVisible(bool(action_text and callback))
        self.action.setText(action_text)
        self.adjustSize()
        end = self._home()
        self.show()
        self.raise_()  # поверх остальных виджетов окна
        if animations.ENABLED:
            self._animate(b"opacity", self._effect, 0.0, 1.0, 180)
            self._animate(b"pos", self, end + QPoint(0, 16), end, 220)
        else:
            self._effect.setOpacity(1.0)
            self.move(end)
        self._timer.start(timeout)

    # Отступ слева, который не занимать (ширина бокового меню)
    left_margin = 0

    def _home(self) -> QPoint:
        """Место уведомления: по центру области экранов, над нижним краем."""
        parent = self.parentWidget()
        area = parent.width() - self.left_margin
        return QPoint(self.left_margin + (area - self.width()) // 2,
                      parent.height() - self.height() - 72)

    def reposition(self) -> None:
        """Вызывается при изменении размера окна."""
        if self.isVisible():
            self.move(self._home())

    def dismiss(self) -> None:
        if not self.isVisible():
            return
        if animations.ENABLED:
            fade = self._animate(b"opacity", self._effect, 1.0, 0.0, 250)
            fade.finished.connect(self.hide)
        else:
            self.hide()

    def _on_action(self) -> None:
        callback = self._callback
        self.dismiss()
        if callback is not None:
            callback()

    def _animate(self, prop: bytes, target, start, end, duration
                 ) -> QPropertyAnimation:
        animation = QPropertyAnimation(target, prop, self)
        animation.setDuration(duration)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setEasingCurve(animations.EASING)
        # Храним ссылку, чтобы анимацию не удалил сборщик мусора
        setattr(self, f"_anim_{prop.decode()}", animation)
        animation.start()
        return animation
