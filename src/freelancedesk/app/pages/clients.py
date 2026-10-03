"""Экран «Клиенты»: таблица клиентов с контактами, заказами и доходом."""

from decimal import Decimal

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLineEdit, QMenu

from freelancedesk.app.dialogs import ClientDialog
from freelancedesk.app.labels import CLIENT_TYPE_SHORT
from freelancedesk.app.pages import Page
from freelancedesk.app.theme import C, icon
from freelancedesk.app.widgets import (
    SortItem, button, fill_table, make_table, money_item, selected_id,
)
from freelancedesk.core.manager import contact_url
from freelancedesk.core.models import Client, ContactMethod

HEADERS = ["Имя", "Тип", "Площадка", "Почта", "Телефон", "Мессенджер",
           "Заказов", "Получено", "Заметка"]
# Доли ширины столбцов по умолчанию (в том же порядке, что HEADERS)
WEIGHTS = [16, 12, 10, 16, 13, 15, 7, 10, 9]
# В каком столбце какой способ связи — чтобы выделить предпочтительный
CONTACT_COLUMNS = {ContactMethod.EMAIL: 3, ContactMethod.PHONE: 4,
                   ContactMethod.MESSENGER: 5}


def messenger_text(client: Client) -> str:
    """'@ivan · Telegram' или просто ник, если мессенджер не указан."""
    if not client.messenger:
        return ""
    if client.messenger_app and client.messenger_app != "Другой":
        return f"{client.messenger} · {client.messenger_app}"
    return client.messenger


class ClientsPage(Page):
    """Экран «Клиенты»."""

    def __init__(self, app) -> None:
        super().__init__(app, "Клиенты")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            "Поиск: имя, почта, телефон, мессенджер")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.addAction(icon("search"),
                                   QLineEdit.ActionPosition.LeadingPosition)
        self.search_edit.setMinimumWidth(280)
        self.search_edit.textChanged.connect(self.refresh)
        new_btn = button("Новый клиент", "plus", "primary", "#ffffff")
        new_btn.setToolTip("Ctrl+Shift+N")
        new_btn.clicked.connect(self.add_client)
        self.header.addWidget(self.search_edit)
        self.header.addWidget(new_btn)

        self.table = make_table(
            HEADERS, empty=("Клиентов пока нет",
                            "Добавьте первого кнопкой «Новый клиент»"))
        # Доли ширины, порядок и видимость столбцов — с сохранением
        self.columns = app.register_table(self.table, "clients", WEIGHTS)
        # activated — двойной щелчок или Enter по строке
        self.table.activated.connect(self.edit_client)
        self.table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_menu)
        self.layout_.addWidget(self.table, 1)

        actions = QHBoxLayout()
        edit_btn = button("Изменить", "pencil")
        edit_btn.clicked.connect(self.edit_client)
        delete_btn = button("Удалить", "trash-2", "danger", C["danger_text"])
        delete_btn.clicked.connect(self.delete_client)
        actions.addWidget(edit_btn)
        actions.addWidget(delete_btn)
        actions.addStretch(1)
        self.layout_.addLayout(actions)

    def refresh(self) -> None:
        manager = self.app.manager
        stats = manager.client_stats()
        needle = self.search_edit.text().strip().casefold()
        rows = []
        for client in manager.list_clients():
            text = " ".join((client.name, client.email, client.phone,
                             client.messenger, client.platform))
            if needle and needle not in text.casefold():
                continue
            client_stats = stats.get(client.id)
            count = client_stats.orders if client_stats else 0
            income = client_stats.income if client_stats else Decimal("0")
            items = [
                SortItem(client.name),
                SortItem(CLIENT_TYPE_SHORT[client.client_type]),
                SortItem(client.platform),
                SortItem(client.email),
                SortItem(client.phone),
                SortItem(messenger_text(client)),
                SortItem(str(count), count),
                money_item(income),
                SortItem(client.note),
            ]
            # Обрезанный текст («Постоянны…») виден целиком при наведении
            for item in items:
                if item.text():
                    item.setToolTip(item.text())
            # Предпочтительный способ связи — жирным
            if client.preferred_contact:
                cell = items[CONTACT_COLUMNS[client.preferred_contact]]
                font = QFont(cell.font())
                font.setBold(True)
                cell.setFont(font)
                cell.setToolTip(f"{cell.text()} — клиенту удобнее "
                                "связываться так")
            rows.append((client.id, items))
        fill_table(self.table, rows)

    def _need_client(self) -> int | None:
        client_id = selected_id(self.table)
        if client_id is None:
            self.app.show_error("Выберите клиента в таблице.")
        return client_id

    def _show_menu(self, position) -> None:
        """Правая кнопка по клиенту: связаться, изменить, удалить."""
        row = self.table.rowAt(position.y())
        if row < 0:
            return
        self.table.selectRow(row)
        client = self.app.manager.get_client(selected_id(self.table))
        menu = QMenu(self)
        contacts = [(ContactMethod.EMAIL, "Написать на почту", "external-link"),
                    (ContactMethod.PHONE, "Позвонить", "external-link"),
                    (ContactMethod.MESSENGER, "Открыть мессенджер",
                     "external-link")]
        for method, text, icon_name in contacts:
            url = contact_url(client, method)
            action = menu.addAction(icon(icon_name), text,
                                    lambda url=url: self.open_url(url))
            action.setEnabled(url is not None)
        menu.addSeparator()
        menu.addAction(icon("pencil"), "Изменить…", self.edit_client)
        menu.addAction(icon("trash-2", C["danger_text"]), "Удалить",
                       self.delete_client)
        menu.exec(self.table.viewport().mapToGlobal(position))

    @staticmethod
    def open_url(url: str | None) -> None:
        """Открыть ссылку: почтовую программу, звонилку, мессенджер."""
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def add_client(self) -> None:
        dialog = ClientDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if self.app.run(lambda: self.app.manager.add_client(
                    dialog.client())):
                self.app.notify("Клиент добавлен")

    def edit_client(self) -> None:
        client_id = self._need_client()
        if client_id is None:
            return
        dialog = ClientDialog(self.app.manager.get_client(client_id),
                              parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if self.app.run(lambda: self.app.manager.update_client(
                    dialog.client())):
                self.app.notify("Клиент сохранён")

    def delete_client(self) -> None:
        client_id = self._need_client()
        if client_id is not None and self.app.confirm("Удалить клиента?"):
            if self.app.run(lambda: self.app.manager.delete_client(
                    client_id)):
                self.app.notify("Клиент удалён")
