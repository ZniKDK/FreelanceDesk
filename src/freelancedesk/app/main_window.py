"""Главное окно приложения: вкладки «Заказы», «Клиенты», «Сводка»."""

from collections.abc import Callable
from datetime import date

import psycopg
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QDateEdit, QDialog, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
    QWidget,
)

from freelancedesk.app.dialogs import ClientDialog, OrderDialog, to_qdate
from freelancedesk.app.labels import (
    CLIENT_TYPE_LABELS, STATUS_LABELS, format_date, format_money,
)
from freelancedesk.core.manager import OrderManager

# Ошибки, которые показываем пользователю окном, а не падением программы:
# ValueError/KeyError — нарушены правила OrderManager или хранилища,
# psycopg.Error — проблемы с базой данных
USER_ERRORS = (ValueError, KeyError, psycopg.Error)

# Цвет фона строк с просроченными заказами
OVERDUE_COLOR = QColor("#ffd6d6")


def make_table(headers: list[str]) -> QTableWidget:
    """Таблица только для чтения с выделением целых строк."""
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.verticalHeader().setVisible(False)
    # Первая колонка (название / имя) растягивается на свободное место
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    return table


def selected_id(table: QTableWidget) -> int | None:
    """id записи в выделенной строке (хранится в данных первой ячейки)."""
    row = table.currentRow()
    if row < 0:
        return None
    return table.item(row, 0).data(Qt.ItemDataRole.UserRole)


class MainWindow(QMainWindow):
    """Главное окно. Вся работа с данными идёт через OrderManager."""

    def __init__(self, manager: OrderManager,
                 today: Callable[[], date] = date.today) -> None:
        super().__init__()
        self._manager = manager
        # Функция «какое сегодня число»: в тестах подменяется на фиксированную
        self._today = today
        self.setWindowTitle("FreelanceDesk — учёт заказов")
        self.resize(1000, 600)

        tabs = QTabWidget()
        tabs.addTab(self._build_orders_tab(), "Заказы")
        tabs.addTab(self._build_clients_tab(), "Клиенты")
        tabs.addTab(self._build_summary_tab(), "Сводка")
        self.setCentralWidget(tabs)

        self.refresh()

    # ------------------------------------------------------------------
    # Построение вкладок
    # ------------------------------------------------------------------

    def _build_orders_tab(self) -> QWidget:
        # Фильтр: первый пункт «все» (данные None), дальше статусы
        self.status_filter = QComboBox()
        self.status_filter.addItem("Все статусы", None)
        for status, label in STATUS_LABELS.items():
            self.status_filter.addItem(label, status)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск по названию…")
        # При любом изменении фильтра таблица перестраивается сразу
        self.status_filter.currentIndexChanged.connect(self.refresh_orders)
        self.search_edit.textChanged.connect(self.refresh_orders)

        add_btn = QPushButton("Добавить")
        edit_btn = QPushButton("Изменить")
        delete_btn = QPushButton("Удалить")
        add_btn.clicked.connect(self.add_order)
        edit_btn.clicked.connect(self.edit_order)
        delete_btn.clicked.connect(self.delete_order)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.status_filter)
        toolbar.addWidget(self.search_edit, 1)
        for button in (add_btn, edit_btn, delete_btn):
            toolbar.addWidget(button)

        self.orders_table = make_table(
            ["Название", "Клиент", "Сумма", "Дедлайн", "Статус", "Оплачен"])
        # Двойной щелчок по строке — редактирование
        self.orders_table.doubleClicked.connect(self.edit_order)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addLayout(toolbar)
        layout.addWidget(self.orders_table)
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

        self.clients_table = make_table(
            ["Имя", "Тип", "Контакт", "Площадка", "Заметка"])
        self.clients_table.doubleClicked.connect(self.edit_client)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addLayout(toolbar)
        layout.addWidget(self.clients_table)
        return page

    def _build_summary_tab(self) -> QWidget:
        # По умолчанию — текущий месяц: с 1-го числа по сегодня
        today = self._today()
        self.start_edit = QDateEdit(to_qdate(today.replace(day=1)))
        self.end_edit = QDateEdit(to_qdate(today))
        for edit in (self.start_edit, self.end_edit):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("dd.MM.yyyy")

        calc_btn = QPushButton("Рассчитать")
        calc_btn.clicked.connect(self.calculate_summary)

        self.income_label = QLabel("—")
        self.tax_label = QLabel("—")
        self.net_label = QLabel("—")
        self.overdue_label = QLabel("—")
        # Итоговые суммы выделяем жирным — это главное на вкладке
        for label in (self.income_label, self.tax_label, self.net_label):
            label.setStyleSheet("font-weight: bold;")

        form = QFormLayout()
        form.addRow("С:", self.start_edit)
        form.addRow("По:", self.end_edit)
        form.addRow(calc_btn)
        form.addRow("Доход (оплаченные заказы):", self.income_label)
        form.addRow("Налог НПД:", self.tax_label)
        form.addRow("После налога:", self.net_label)
        form.addRow("Просрочено сейчас:", self.overdue_label)

        # Форму кладём в отдельный виджет ограниченной ширины,
        # иначе поля растягиваются на всё окно
        form_box = QWidget()
        form_box.setLayout(form)
        form_box.setMaximumWidth(420)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(form_box)
        layout.addStretch(1)  # прижать форму к верху
        return page

    # ------------------------------------------------------------------
    # Обновление таблиц
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Перерисовать всё после любого изменения данных."""
        self.refresh_orders()
        self.refresh_clients()
        self.calculate_summary()

    def refresh_orders(self) -> None:
        orders = self._manager.list_orders(
            status=self.status_filter.currentData(),
            search=self.search_edit.text().strip(),
        )
        # Словарь id -> имя, чтобы не искать клиента для каждой строки
        names = {c.id: c.name for c in self._manager.list_clients()}
        today = self._today()

        self.orders_table.setRowCount(len(orders))
        for row, order in enumerate(orders):
            values = [
                order.title,
                names.get(order.client_id, "?"),
                format_money(order.amount),
                format_date(order.deadline),
                STATUS_LABELS[order.status],
                format_date(order.paid_on),
            ]
            overdue = order.is_overdue(today)
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col == 2:  # сумму выравниваем вправо, как в бухгалтерии
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                          | Qt.AlignmentFlag.AlignVCenter)
                if overdue:
                    item.setBackground(OVERDUE_COLOR)
                    item.setToolTip("Срок прошёл, заказ не сдан")
                self.orders_table.setItem(row, col, item)
            # id прячем в данные первой ячейки: на экране его не видно
            self.orders_table.item(row, 0).setData(
                Qt.ItemDataRole.UserRole, order.id)

    def refresh_clients(self) -> None:
        clients = self._manager.list_clients()
        self.clients_table.setRowCount(len(clients))
        for row, client in enumerate(clients):
            values = [client.name, CLIENT_TYPE_LABELS[client.client_type],
                      client.contact, client.platform, client.note]
            for col, text in enumerate(values):
                self.clients_table.setItem(row, col, QTableWidgetItem(text))
            self.clients_table.item(row, 0).setData(
                Qt.ItemDataRole.UserRole, client.id)

    def calculate_summary(self) -> None:
        start = self.start_edit.date().toPyDate()
        end = self.end_edit.date().toPyDate()
        if start > end:
            self._show_error("Начало периода позже конца.")
            return
        summary = self._manager.summary(start, end)
        self.income_label.setText(format_money(summary.income))
        self.tax_label.setText(format_money(summary.tax))
        self.net_label.setText(format_money(summary.net))
        overdue = len(self._manager.overdue_orders(self._today()))
        self.overdue_label.setText(str(overdue))

    # ------------------------------------------------------------------
    # Действия с заказами
    # ------------------------------------------------------------------

    def add_order(self) -> None:
        clients = self._manager.list_clients()
        if not clients:
            self._show_error("Сначала добавьте клиента на вкладке «Клиенты».")
            return
        dialog = OrderDialog(clients, parent=self)
        # exec() открывает окно и ждёт, пока его закроют
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._run(lambda: self._manager.add_order(dialog.order(),
                                                      today=self._today()))

    def edit_order(self) -> None:
        order_id = selected_id(self.orders_table)
        if order_id is None:
            self._show_error("Выберите заказ в таблице.")
            return
        order = self._manager.get_order(order_id)
        dialog = OrderDialog(self._manager.list_clients(), order, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._run(lambda: self._manager.update_order(dialog.order(),
                                                         today=self._today()))

    def delete_order(self) -> None:
        order_id = selected_id(self.orders_table)
        if order_id is None:
            self._show_error("Выберите заказ в таблице.")
            return
        if self._confirm("Удалить выбранный заказ?"):
            self._run(lambda: self._manager.delete_order(order_id))

    # ------------------------------------------------------------------
    # Действия с клиентами
    # ------------------------------------------------------------------

    def add_client(self) -> None:
        dialog = ClientDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._run(lambda: self._manager.add_client(dialog.client()))

    def edit_client(self) -> None:
        client_id = selected_id(self.clients_table)
        if client_id is None:
            self._show_error("Выберите клиента в таблице.")
            return
        dialog = ClientDialog(self._manager.get_client(client_id), parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._run(lambda: self._manager.update_client(dialog.client()))

    def delete_client(self) -> None:
        client_id = selected_id(self.clients_table)
        if client_id is None:
            self._show_error("Выберите клиента в таблице.")
            return
        if self._confirm("Удалить выбранного клиента?"):
            self._run(lambda: self._manager.delete_client(client_id))

    # ------------------------------------------------------------------
    # Вспомогательное
    # ------------------------------------------------------------------

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
