"""Ширина, порядок и видимость столбцов таблицы.

Каждый столбец получает долю ширины («вес»): например, имя — 18 частей,
телефон — 13. При любом размере окна таблица делит ширину по этим долям,
поэтому после разворачивания и сворачивания окна столбцы не «плывут».

В режиме настройки (Настройки → Настроить таблицы) пользователь тянет
границы столбцов, перетаскивает заголовки и скрывает лишнее через
правую кнопку по шапке. По «Готово» доли, порядок и скрытые столбцы
сохраняются в ui_state.ini.
"""

from contextlib import contextmanager

from PyQt6.QtCore import QEvent, QObject, QSettings, Qt
from PyQt6.QtWidgets import QHeaderView, QMenu, QTableWidget

MIN_WIDTH = 60  # пикселей: уже столбец становится нечитаемым


def _to_list(value, cast) -> list:
    """'1,2,3' из ini-файла -> [1, 2, 3]; пустое значение -> []."""
    if not value:
        return []
    if isinstance(value, (list, tuple)):  # QSettings иногда сам делит по ","
        items = value
    else:
        items = str(value).split(",")
    return [cast(item) for item in items if str(item).strip()]


class ColumnLayout(QObject):
    """Управляет столбцами одной таблицы.

    key — имя таблицы в настройках ('clients', 'finance_payments');
    weights — доли ширины столбцов по умолчанию.
    """

    def __init__(self, table: QTableWidget, key: str, weights: list[int],
                 settings: QSettings | None = None) -> None:
        super().__init__(table)
        self.table = table
        self.key = key
        self.defaults = [float(w) for w in weights]
        self.weights = list(self.defaults)
        self.hidden: set[int] = set()
        self.settings = settings
        self.editing = False
        # Больше нуля, пока столбцы меняет сама программа: такие
        # изменения ширины не считаются действиями пользователя
        self._quiet = 0

        header = table.horizontalHeader()
        self.header = header
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setMinimumSectionSize(MIN_WIDTH)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._header_menu)
        header.sectionResized.connect(self._section_resized)
        # Пересчитываем ширины, когда меняется размер области строк
        # (viewport). Размер самой таблицы не подходит: её событие приходит
        # раньше, чем обновится viewport, и столбцы отставали на шаг —
        # после «развернуть — свернуть» они брали ширину прошлого окна
        table.viewport().installEventFilter(self)
        self._load()

    @contextmanager
    def _by_program(self):
        """Внутри блока изменения ширины не меняют сохранённые доли."""
        self._quiet += 1
        try:
            yield
        finally:
            self._quiet -= 1

    @property
    def count(self) -> int:
        return self.table.columnCount()

    def visible_columns(self) -> list[int]:
        """Видимые столбцы в том порядке, в каком они стоят на экране."""
        order = [self.header.logicalIndex(v) for v in range(self.count)]
        return [c for c in order if c not in self.hidden]

    # ------------------------------------------------------------------
    # Ширины
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 — имя задано Qt
        if event.type() == QEvent.Type.Resize and not self.editing:
            self.fit()
        return False

    def fit(self) -> None:
        """Разделить ширину таблицы между видимыми столбцами по долям."""
        columns = self.visible_columns()
        available = self.table.viewport().width()
        if not columns or available <= 0:
            return
        total = sum(self.weights[c] for c in columns) or 1
        widths = {c: max(MIN_WIDTH, int(available * self.weights[c] / total))
                  for c in columns}
        # Последнему столбцу — остаток, чтобы справа не было щели
        last = columns[-1]
        widths[last] = max(MIN_WIDTH,
                           available - sum(widths[c] for c in columns[:-1]))
        with self._by_program():
            for column, width in widths.items():
                self.header.resizeSection(column, width)

    def _section_resized(self, column: int, _old: int, _new: int) -> None:
        """Пользователь потянул границу — запоминаем новые доли."""
        if not self.editing or self._quiet:
            return
        columns = self.visible_columns()
        total = sum(self.header.sectionSize(c) for c in columns) or 1
        for c in columns:
            self.weights[c] = self.header.sectionSize(c) * 100 / total

    # ------------------------------------------------------------------
    # Режим настройки
    # ------------------------------------------------------------------

    def set_editing(self, editing: bool) -> None:
        """Включить или выключить режим настройки столбцов."""
        self.editing = editing
        mode = (QHeaderView.ResizeMode.Interactive if editing
                else QHeaderView.ResizeMode.Fixed)
        self.header.setSectionResizeMode(mode)
        self.header.setSectionsMovable(editing)
        # Свойство читает QSS: в режиме настройки шапка подсвечена
        self.header.setProperty("editing", editing)
        self.header.style().unpolish(self.header)
        self.header.style().polish(self.header)
        if not editing:
            self.save()
            self.fit()

    def reset(self) -> None:
        """Вернуть ширины, порядок и видимость столбцов по умолчанию."""
        self.weights = list(self.defaults)
        self.hidden.clear()
        with self._by_program():
            for logical in range(self.count):
                self.header.setSectionHidden(logical, False)
                self.header.moveSection(self.header.visualIndex(logical),
                                        logical)
            self.fit()
        self.save()

    def set_hidden(self, column: int, hidden: bool) -> None:
        """Скрыть или показать столбец (последний видимый скрыть нельзя)."""
        if hidden and len(self.visible_columns()) <= 1:
            return
        if hidden:
            self.hidden.add(column)
        else:
            self.hidden.discard(column)
        with self._by_program():
            self.header.setSectionHidden(column, hidden)
            self.fit()

    def _header_menu(self, position) -> None:
        """Правая кнопка по шапке в режиме настройки: какие столбцы видны."""
        if not self.editing:
            return
        menu = QMenu(self.table)
        for column in range(self.count):
            title = self.table.horizontalHeaderItem(column).text()
            action = menu.addAction(title)
            action.setCheckable(True)
            action.setChecked(column not in self.hidden)
            action.toggled.connect(
                lambda shown, c=column: self.set_hidden(c, not shown))
        menu.exec(self.header.mapToGlobal(position))

    # ------------------------------------------------------------------
    # Сохранение
    # ------------------------------------------------------------------

    def _setting(self, name: str) -> str:
        return f"tables/{self.key}/{name}"

    def save(self) -> None:
        if self.settings is None:
            return
        order = [self.header.logicalIndex(v) for v in range(self.count)]
        self.settings.setValue(self._setting("weights"),
                               ",".join(f"{w:.2f}" for w in self.weights))
        self.settings.setValue(self._setting("order"),
                               ",".join(map(str, order)))
        self.settings.setValue(self._setting("hidden"),
                               ",".join(map(str, sorted(self.hidden))))

    def _load(self) -> None:
        if self.settings is None:
            return
        with self._by_program():
            self._load_saved()

    def _load_saved(self) -> None:
        weights = _to_list(self.settings.value(self._setting("weights")),
                           float)
        if len(weights) == self.count:
            self.weights = weights
        order = _to_list(self.settings.value(self._setting("order")), int)
        if sorted(order) == list(range(self.count)):
            for visual, logical in enumerate(order):
                self.header.moveSection(self.header.visualIndex(logical),
                                        visual)
        hidden = _to_list(self.settings.value(self._setting("hidden")), int)
        for column in hidden:
            if 0 <= column < self.count:
                self.hidden.add(column)
                self.header.setSectionHidden(column, True)
