"""Главное окно приложения: вкладки «Заказы», «Клиенты», «Сводка»."""

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path

from PyQt6.QtCore import QByteArray, QSettings, Qt, QUrl
from PyQt6.QtGui import QAction, QColor, QDesktopServices, QKeySequence
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMenu,
    QMessageBox, QProgressBar, QPushButton, QSpinBox, QTableWidget,
    QTabWidget, QVBoxLayout, QWidget,
)

from freelancedesk import __version__
from freelancedesk.app.dialogs import (
    ClientDialog, OrderDialog, make_date_edit, to_qdate,
)
from freelancedesk.app.labels import (
    CLIENT_TYPE_LABELS, MONTH_SHORT, STATUS_LABELS, VIEW_LABELS, format_date,
    format_money, format_month,
)
from freelancedesk.app.widgets import AttentionBanner, BarChart, SortItem
from freelancedesk.core.manager import (
    OrderManager, OrderView, add_months, month_end, month_start,
)
from freelancedesk.core.models import Order, OrderStatus
from freelancedesk.core.sql_storage import DB_ERRORS

# Ошибки, которые показываем пользователю окном, а не падением программы:
# ValueError/KeyError — нарушены правила OrderManager или хранилища,
# DB_ERRORS — проблемы с базой данных (PostgreSQL или SQLite)
USER_ERRORS = (ValueError, KeyError, *DB_ERRORS)

# Цвета подсветки строк
OVERDUE_COLOR = QColor("#ffd6d6")     # просрочен
DUE_TODAY_COLOR = QColor("#ffe8c2")   # сдать сегодня
NO_RECEIPT_COLOR = QColor("#fff4ce")  # оплачен, чек не выбит

# Колонки таблицы заказов
ORDER_HEADERS = ["Название", "Клиент", "Сумма", "Дедлайн", "Статус",
                 "Оплачен", "Чек"]
CLIENT_HEADERS = ["Имя", "Тип", "Контакт", "Площадка", "Заказов",
                  "Оплачено", "Заметка"]

# Порядок статусов для сортировки по колонке «Статус»
STATUS_ORDER = {status: i for i, status in enumerate(OrderStatus)}

HOTKEYS_HELP = """\
Ctrl+N — новый заказ
Ctrl+Shift+N — новый клиент
F2 или Enter — изменить выбранное
Delete — удалить выбранное
Ctrl+F — поиск по заказам
Ctrl+R — отметить «чек выбит»
F5 — обновить
Ctrl+Q — выход

Правая кнопка мыши по заказу — быстрая смена статуса,
отметка чека и переход по ссылке."""


def make_table(headers: list[str], sort_column: int = 0) -> QTableWidget:
    """Таблица только для чтения с выделением строк и сортировкой.

    sort_column — колонка, по которой таблица отсортирована при открытии
    (по возрастанию). Пользователь может сменить её щелчком по заголовку.
    """
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    # Первая колонка (название / имя) растягивается на свободное место
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    # По умолчанию Qt сортирует по убыванию — задаём возрастание явно
    header.setSortIndicator(sort_column, Qt.SortOrder.AscendingOrder)
    return table


def selected_id(table: QTableWidget) -> int | None:
    """id записи в выделенной строке (хранится в данных первой ячейки)."""
    row = table.currentRow()
    if row < 0:
        return None
    return table.item(row, 0).data(Qt.ItemDataRole.UserRole)


def fill_table(table: QTableWidget, rows: list[tuple[int, list[SortItem]]]
               ) -> None:
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


def money_item(amount: Decimal) -> SortItem:
    """Ячейка с суммой: выравнивание вправо, сортировка по числу."""
    item = SortItem(format_money(amount), amount)
    item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                          | Qt.AlignmentFlag.AlignVCenter)
    return item


class MainWindow(QMainWindow):
    """Главное окно. Вся работа с данными идёт через OrderManager.

    today — функция «какое сегодня число» (в тестах — фиксированная дата).
    settings — где хранить размер окна, фильтры и цель; None — не хранить.
    data_dir — папка с файлами пользователя (для пункта меню).
    storage_label — подпись в строке состояния: где лежат данные.
    """

    def __init__(self, manager: OrderManager,
                 today: Callable[[], date] = date.today,
                 settings: QSettings | None = None,
                 data_dir: Path | None = None,
                 storage_label: str = "") -> None:
        super().__init__()
        self._manager = manager
        self._today = today
        self._settings = settings
        self._data_dir = data_dir
        self.setWindowTitle("FreelanceDesk — учёт заказов")
        self.resize(1100, 680)

        self.banner = AttentionBanner()
        self.banner.view_requested.connect(self.show_view)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_orders_tab(), "Заказы")
        self.tabs.addTab(self._build_clients_tab(), "Клиенты")
        self.tabs.addTab(self._build_summary_tab(), "Сводка")

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.banner)
        layout.addWidget(self.tabs)
        self.setCentralWidget(central)

        self._build_menu()
        if storage_label:
            self.statusBar().addPermanentWidget(
                QLabel(f"Данные: {storage_label}"))

        self._restore_state()
        self.refresh()

    # ------------------------------------------------------------------
    # Меню и горячие клавиши
    # ------------------------------------------------------------------

    def _action(self, menu: QMenu, text: str, slot: Callable,
                shortcut: str | QKeySequence.StandardKey | None = None
                ) -> QAction:
        """Создать пункт меню с (необязательной) горячей клавишей."""
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _build_menu(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("&Файл")
        if self._data_dir is not None:
            self._action(file_menu, "Открыть папку с данными",
                         self.open_data_dir)
            file_menu.addSeparator()
        self._action(file_menu, "Выход", self.close, "Ctrl+Q")

        work_menu = bar.addMenu("&Работа")
        self._action(work_menu, "Новый заказ", self.add_order, "Ctrl+N")
        self._action(work_menu, "Новый клиент", self.add_client,
                     "Ctrl+Shift+N")
        work_menu.addSeparator()
        self._action(work_menu, "Изменить", self.edit_current, "F2")
        self._action(work_menu, "Удалить", self.delete_current, "Delete")
        self._action(work_menu, "Отметить «чек выбит»",
                     self.toggle_receipt, "Ctrl+R")
        work_menu.addSeparator()
        self._action(work_menu, "Найти заказ", self.focus_search, "Ctrl+F")
        self._action(work_menu, "Обновить", self.refresh, "F5")

        help_menu = bar.addMenu("&Справка")
        self._action(help_menu, "Горячие клавиши", self.show_hotkeys)
        self._action(help_menu, "О программе", self.show_about)

    # ------------------------------------------------------------------
    # Построение вкладок
    # ------------------------------------------------------------------

    def _build_orders_tab(self) -> QWidget:
        # Фильтр: готовые выборки, затем отдельные статусы.
        # Данные пункта — пара (вид фильтра, значение).
        self.order_filter = QComboBox()
        for view, label in VIEW_LABELS.items():
            self.order_filter.addItem(label, ("view", view))
        self.order_filter.insertSeparator(self.order_filter.count())
        for status, label in STATUS_LABELS.items():
            self.order_filter.addItem(f"Статус: {label}", ("status", status))

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            "Поиск по названию, описанию, клиенту…  (Ctrl+F)")
        self.search_edit.setClearButtonEnabled(True)
        # При любом изменении фильтра таблица перестраивается сразу
        self.order_filter.currentIndexChanged.connect(self.refresh_orders)
        self.search_edit.textChanged.connect(self.refresh_orders)

        add_btn = QPushButton("Добавить")
        edit_btn = QPushButton("Изменить")
        delete_btn = QPushButton("Удалить")
        add_btn.clicked.connect(self.add_order)
        edit_btn.clicked.connect(self.edit_order)
        delete_btn.clicked.connect(self.delete_order)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.order_filter)
        toolbar.addWidget(self.search_edit, 1)
        for button in (add_btn, edit_btn, delete_btn):
            toolbar.addWidget(button)

        # Сортировка по дедлайну: самые срочные заказы сверху
        self.orders_table = make_table(ORDER_HEADERS, sort_column=3)
        # activated — двойной щелчок или Enter по строке: редактирование
        self.orders_table.activated.connect(self.edit_order)
        # Правая кнопка мыши — своё контекстное меню
        self.orders_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.orders_table.customContextMenuRequested.connect(
            self._show_order_menu)

        # Итог под таблицей: сколько заказов показано и на какую сумму
        self.orders_total_label = QLabel()

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addLayout(toolbar)
        layout.addWidget(self.orders_table)
        layout.addWidget(self.orders_total_label)
        return page

    def _build_clients_tab(self) -> QWidget:
        add_btn = QPushButton("Добавить")
        edit_btn = QPushButton("Изменить")
        delete_btn = QPushButton("Удалить")
        add_btn.clicked.connect(self.add_client)
        edit_btn.clicked.connect(self.edit_client)
        delete_btn.clicked.connect(self.delete_client)

        toolbar = QHBoxLayout()
        toolbar.addStretch(1)  # прижать кнопки вправо
        for button in (add_btn, edit_btn, delete_btn):
            toolbar.addWidget(button)

        self.clients_table = make_table(CLIENT_HEADERS)
        self.clients_table.activated.connect(self.edit_client)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addLayout(toolbar)
        layout.addWidget(self.clients_table)
        return page

    def _build_summary_tab(self) -> QWidget:
        today = self._today()

        # --- Цель на месяц ---
        self.goal_spin = QSpinBox()
        self.goal_spin.setRange(0, 10_000_000)
        self.goal_spin.setSingleStep(5_000)
        self.goal_spin.setSuffix(" ₽")
        self.goal_spin.setGroupSeparatorShown(True)
        self.goal_spin.setSpecialValueText("не задана")  # так показывается 0
        self.goal_spin.valueChanged.connect(self._goal_changed)
        self.goal_bar = QProgressBar()
        self.goal_bar.setRange(0, 100)
        goal_box = QGroupBox("Цель на этот месяц")
        goal_layout = QFormLayout(goal_box)
        goal_layout.addRow("Хочу заработать:", self.goal_spin)
        goal_layout.addRow(self.goal_bar)

        # --- Налог к уплате ---
        self.tax_due_label = QLabel()
        self.tax_due_label.setWordWrap(True)
        tax_box = QGroupBox("Налог НПД к уплате")
        QVBoxLayout(tax_box).addWidget(self.tax_due_label)

        # --- Произвольный период ---
        self.start_edit = make_date_edit(month_start(today))
        self.end_edit = make_date_edit(today)
        # Пересчёт сразу при смене даты — кнопка «Рассчитать» не нужна
        self.start_edit.dateChanged.connect(self.calculate_summary)
        self.end_edit.dateChanged.connect(self.calculate_summary)

        quick = QHBoxLayout()
        for text, period in (("Этот месяц", "this_month"),
                             ("Прошлый месяц", "last_month"),
                             ("Этот год", "this_year")):
            button = QPushButton(text)
            button.clicked.connect(
                lambda _, period=period: self.set_period(period))
            quick.addWidget(button)

        self.income_label = QLabel("—")
        self.tax_label = QLabel("—")
        self.net_label = QLabel("—")
        # Итоговые суммы выделяем жирным — это главное на вкладке
        for label in (self.income_label, self.tax_label, self.net_label):
            label.setStyleSheet("font-weight: bold;")
        self.platform_label = QLabel()
        self.platform_label.setWordWrap(True)

        period_box = QGroupBox("Доход за период")
        period_form = QFormLayout(period_box)
        period_form.addRow("С:", self.start_edit)
        period_form.addRow("По:", self.end_edit)
        period_form.addRow(quick)
        period_form.addRow("Доход:", self.income_label)
        period_form.addRow("Налог НПД:", self.tax_label)
        period_form.addRow("После налога:", self.net_label)
        period_form.addRow("По площадкам:", self.platform_label)

        left = QVBoxLayout()
        for box in (goal_box, tax_box, period_box):
            left.addWidget(box)
        left.addStretch(1)
        left_widget = QWidget()
        left_widget.setLayout(left)
        left_widget.setMaximumWidth(440)

        # --- Диаграмма по месяцам ---
        self.chart = BarChart()
        chart_box = QGroupBox("Доход по месяцам (последние 12)")
        QVBoxLayout(chart_box).addWidget(self.chart)

        page = QWidget()
        layout = QHBoxLayout(page)
        layout.addWidget(left_widget)
        layout.addWidget(chart_box, 1)
        return page

    # ------------------------------------------------------------------
    # Обновление данных на экране
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Перерисовать всё после любого изменения данных."""
        self.refresh_orders()
        self.refresh_clients()
        self.refresh_summary()
        self.banner.set_attention(self._manager.attention(self._today()))

    def _current_filter(self) -> dict:
        """Параметры для OrderManager.list_orders из выбранного фильтра."""
        kind, value = self.order_filter.currentData()
        return {"view": value} if kind == "view" else {"status": value}

    def refresh_orders(self) -> None:
        today = self._today()
        orders = self._manager.list_orders(
            search=self.search_edit.text().strip(), today=today,
            **self._current_filter())
        # Словарь id -> имя, чтобы не искать клиента для каждой строки
        names = {c.id: c.name for c in self._manager.list_clients()}
        fill_table(self.orders_table,
                   [(o.id, self._order_items(o, names, today))
                    for o in orders])

        total = sum((o.amount for o in orders), Decimal("0"))
        self.orders_total_label.setText(
            f"Показано заказов: {len(orders)} · на сумму {format_money(total)}")

    @staticmethod
    def _order_items(order: Order, names: dict[int, str],
                     today: date) -> list[SortItem]:
        """Ячейки одной строки таблицы заказов с подсветкой."""
        if order.status == OrderStatus.PAID:
            receipt_text = "✓" if order.receipt_issued else "нет"
        else:
            receipt_text = ""
        items = [
            SortItem(order.title),
            SortItem(names.get(order.client_id, "?")),
            money_item(order.amount),
            # Без срока — в конец списка при сортировке по дедлайну
            SortItem(format_date(order.deadline), order.deadline or date.max),
            SortItem(STATUS_LABELS[order.status], STATUS_ORDER[order.status]),
            SortItem(format_date(order.paid_on), order.paid_on or date.min),
            SortItem(receipt_text),
        ]
        if order.is_overdue(today):
            color, hint = OVERDUE_COLOR, "Срок прошёл, заказ не сдан"
        elif order.is_due_on(today):
            color, hint = DUE_TODAY_COLOR, "Сдать сегодня"
        else:
            color, hint = None, ""
        if color is not None:
            for item in items:
                item.setBackground(color)
                item.setToolTip(hint)
        if order.needs_receipt():
            items[-1].setBackground(NO_RECEIPT_COLOR)
            items[-1].setToolTip("Выбейте чек в «Мой налог» (Ctrl+R)")
        if order.description:
            # Описание видно при наведении на название
            items[0].setToolTip(order.description)
        return items

    def refresh_clients(self) -> None:
        stats = self._manager.client_stats()
        rows = []
        for client in self._manager.list_clients():
            client_stats = stats.get(client.id)
            count = client_stats.orders if client_stats else 0
            income = client_stats.income if client_stats else Decimal("0")
            rows.append((client.id, [
                SortItem(client.name),
                SortItem(CLIENT_TYPE_LABELS[client.client_type]),
                SortItem(client.contact),
                SortItem(client.platform),
                SortItem(str(count), count),
                money_item(income),
                SortItem(client.note),
            ]))
        fill_table(self.clients_table, rows)

    def refresh_summary(self) -> None:
        """Цель, налог к уплате, период и диаграмма."""
        today = self._today()

        # Цель: доход с 1-го числа по сегодня против заданной суммы
        month_income = self._manager.summary(month_start(today), today).income
        goal = self.goal_spin.value()
        if goal:
            percent = min(100, int(month_income * 100 / goal))
            self.goal_bar.setValue(percent)
            self.goal_bar.setFormat(
                f"{format_money(month_income)} из {format_money(Decimal(goal))}"
                f" ({percent} %)")
        else:
            self.goal_bar.setValue(0)
            self.goal_bar.setFormat(f"Заработано: {format_money(month_income)}")

        due = self._manager.tax_due(today)
        if due.amount > 0:
            days_left = (due.due_date - today).days
            when = (f"осталось дней: {days_left}" if days_left >= 0
                    else "срок прошёл — проверьте «Мой налог»")
            self.tax_due_label.setText(
                f"За {format_month(due.month)}: <b>{format_money(due.amount)}"
                f"</b><br>Оплатить до {format_date(due.due_date)} ({when})")
        else:
            self.tax_due_label.setText(
                f"За {format_month(due.month)} налога нет.")

        self.calculate_summary()
        self.chart.set_data([
            (MONTH_SHORT[month.month - 1], income)
            for month, income in self._manager.income_by_month(today)])

    def calculate_summary(self) -> None:
        """Доход, налог и площадки за выбранный период."""
        start = self.start_edit.date().toPyDate()
        end = self.end_edit.date().toPyDate()
        if start > end:
            for label in (self.income_label, self.tax_label, self.net_label):
                label.setText("—")
            self.platform_label.setText("Начало периода позже конца")
            return
        summary = self._manager.summary(start, end)
        self.income_label.setText(format_money(summary.income))
        self.tax_label.setText(format_money(summary.tax))
        self.net_label.setText(format_money(summary.net))
        platforms = self._manager.income_by_platform(start, end)
        self.platform_label.setText(
            "<br>".join(f"{name}: {format_money(amount)}"
                        for name, amount in platforms) or "—")

    def set_period(self, period: str) -> None:
        """Быстрый выбор периода на вкладке «Сводка»."""
        today = self._today()
        if period == "last_month":
            start = add_months(month_start(today), -1)
            end = month_end(start)
        elif period == "this_year":
            start, end = today.replace(month=1, day=1), today
        else:  # this_month
            start, end = month_start(today), today
        # Пересчёт вызовется сам через сигнал dateChanged
        self.start_edit.setDate(to_qdate(start))
        self.end_edit.setDate(to_qdate(end))
        self.calculate_summary()

    # ------------------------------------------------------------------
    # Действия с заказами
    # ------------------------------------------------------------------

    def add_order(self) -> None:
        clients = self._manager.list_clients()
        if not clients:
            self._show_error("Сначала добавьте клиента на вкладке «Клиенты».")
            return
        dialog = OrderDialog(clients, parent=self, today=self._today())
        # exec() открывает окно и ждёт, пока его закроют
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._run(lambda: self._manager.add_order(dialog.order(),
                                                      today=self._today()))

    def _selected_order_id(self) -> int | None:
        order_id = selected_id(self.orders_table)
        if order_id is None:
            self._show_error("Выберите заказ в таблице.")
        return order_id

    def edit_order(self) -> None:
        order_id = self._selected_order_id()
        if order_id is None:
            return
        order = self._manager.get_order(order_id)
        dialog = OrderDialog(self._manager.list_clients(), order, parent=self,
                             today=self._today())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._run(lambda: self._manager.update_order(dialog.order(),
                                                         today=self._today()))

    def delete_order(self) -> None:
        order_id = self._selected_order_id()
        if order_id is not None and self._confirm("Удалить выбранный заказ?"):
            self._run(lambda: self._manager.delete_order(order_id))

    def set_status(self, status: OrderStatus) -> None:
        """Сменить статус выбранного заказа (из контекстного меню)."""
        order_id = self._selected_order_id()
        if order_id is not None:
            self._run(lambda: self._manager.change_status(
                order_id, status, today=self._today()))

    def toggle_receipt(self) -> None:
        """Поставить или снять отметку «чек выбит» у выбранного заказа."""
        order_id = self._selected_order_id()
        if order_id is None:
            return
        order = self._manager.get_order(order_id)
        self._run(lambda: self._manager.set_receipt(
            order_id, not order.receipt_issued))

    def open_link(self) -> None:
        """Открыть ссылку заказа в браузере."""
        order_id = self._selected_order_id()
        if order_id is None:
            return
        link = self._manager.get_order(order_id).link
        if link:
            QDesktopServices.openUrl(QUrl(link))
        else:
            self._show_error("У заказа нет ссылки.")

    def _show_order_menu(self, position) -> None:
        """Контекстное меню заказа (правая кнопка мыши)."""
        row = self.orders_table.rowAt(position.y())
        if row < 0:
            return
        self.orders_table.selectRow(row)
        order = self._manager.get_order(selected_id(self.orders_table))

        menu = QMenu(self)
        menu.addAction("Изменить…", self.edit_order)
        status_menu = menu.addMenu("Статус")
        for status, label in STATUS_LABELS.items():
            action = status_menu.addAction(
                label, lambda status=status: self.set_status(status))
            action.setCheckable(True)
            action.setChecked(status == order.status)
        receipt = menu.addAction("Чек выбит", self.toggle_receipt)
        receipt.setCheckable(True)
        receipt.setChecked(order.receipt_issued)
        receipt.setEnabled(order.status == OrderStatus.PAID)
        link = menu.addAction("Открыть ссылку", self.open_link)
        link.setEnabled(bool(order.link))
        menu.addSeparator()
        menu.addAction("Удалить", self.delete_order)
        # exec — показать меню там, где щёлкнули (координаты — в экранные)
        menu.exec(self.orders_table.viewport().mapToGlobal(position))

    def show_view(self, view: OrderView) -> None:
        """Перейти к заказам и включить выборку (из жёлтой плашки)."""
        self.tabs.setCurrentIndex(0)
        self.search_edit.clear()
        for index in range(self.order_filter.count()):
            if self.order_filter.itemData(index) == ("view", view):
                self.order_filter.setCurrentIndex(index)
                break

    def focus_search(self) -> None:
        self.tabs.setCurrentIndex(0)
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    # ------------------------------------------------------------------
    # Действия с клиентами
    # ------------------------------------------------------------------

    def add_client(self) -> None:
        dialog = ClientDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._run(lambda: self._manager.add_client(dialog.client()))

    def _selected_client_id(self) -> int | None:
        client_id = selected_id(self.clients_table)
        if client_id is None:
            self._show_error("Выберите клиента в таблице.")
        return client_id

    def edit_client(self) -> None:
        client_id = self._selected_client_id()
        if client_id is None:
            return
        dialog = ClientDialog(self._manager.get_client(client_id), parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._run(lambda: self._manager.update_client(dialog.client()))

    def delete_client(self) -> None:
        client_id = self._selected_client_id()
        if client_id is not None and self._confirm(
                "Удалить выбранного клиента?"):
            self._run(lambda: self._manager.delete_client(client_id))

    # --- Команды, которые зависят от открытой вкладки (F2, Delete) ---

    def edit_current(self) -> None:
        if self.tabs.currentIndex() == 0:
            self.edit_order()
        elif self.tabs.currentIndex() == 1:
            self.edit_client()

    def delete_current(self) -> None:
        if self.tabs.currentIndex() == 0:
            self.delete_order()
        elif self.tabs.currentIndex() == 1:
            self.delete_client()

    # ------------------------------------------------------------------
    # Справка и служебное
    # ------------------------------------------------------------------

    def open_data_dir(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._data_dir)))

    def show_hotkeys(self) -> None:
        QMessageBox.information(self, "Горячие клавиши", HOTKEYS_HELP)

    def show_about(self) -> None:
        QMessageBox.about(
            self, "О программе",
            f"<b>FreelanceDesk {__version__}</b><br>"
            "Учёт заказов фрилансера: клиенты, сроки, оплаты,<br>"
            "доход и налог самозанятого (НПД).<br><br>"
            "Лицензия MIT · "
            "<a href='https://github.com/ZniKDK/FreelanceDesk'>GitHub</a>")

    def _goal_changed(self) -> None:
        if self._settings is not None:
            self._settings.setValue("goal", self.goal_spin.value())
        self.refresh_summary()

    def _restore_state(self) -> None:
        """Вернуть размер окна, вкладку, фильтр и цель с прошлого запуска."""
        if self._settings is None:
            return
        geometry = self._settings.value("geometry")
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)
        # type=int — значения из ini-файла приходят строками
        self.tabs.setCurrentIndex(self._settings.value("tab", 0, type=int))
        index = self._settings.value("filter", 0, type=int)
        if 0 <= index < self.order_filter.count():
            self.order_filter.setCurrentIndex(index)
        # blockSignals — не сохранять и не пересчитывать во время загрузки
        self.goal_spin.blockSignals(True)
        self.goal_spin.setValue(self._settings.value("goal", 0, type=int))
        self.goal_spin.blockSignals(False)

    def closeEvent(self, event) -> None:  # noqa: N802 — имя задано Qt
        """Перед закрытием окна запомнить его состояние."""
        if self._settings is not None:
            self._settings.setValue("geometry", self.saveGeometry())
            self._settings.setValue("tab", self.tabs.currentIndex())
            self._settings.setValue("filter", self.order_filter.currentIndex())
        super().closeEvent(event)

    def _run(self, action: Callable[[], object]) -> bool:
        """Выполнить действие с данными и обновить окно.

        Ошибку показываем окном с текстом — программа не падает.
        Возвращает True, если действие прошло успешно.
        """
        try:
            action()
        except USER_ERRORS as exc:
            self._show_error(str(exc))
            return False
        self.refresh()
        return True

    def _show_error(self, text: str) -> None:
        QMessageBox.warning(self, "FreelanceDesk", text)

    def _confirm(self, text: str) -> bool:
        answer = QMessageBox.question(self, "FreelanceDesk", text)
        return answer == QMessageBox.StandardButton.Yes
