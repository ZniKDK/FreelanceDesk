"""Экран «Клиенты»: таблица клиентов с поиском, заказами и доходом."""

from decimal import Decimal

from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLineEdit

from freelancedesk.app.dialogs import ClientDialog
from freelancedesk.app.labels import CLIENT_TYPE_LABELS
from freelancedesk.app.pages import Page
from freelancedesk.app.theme import C, icon
from freelancedesk.app.widgets import (
    SortItem, button, fill_table, make_table, money_item, selected_id,
)

HEADERS = ["Имя", "Тип", "Контакт", "Площадка", "Заказов", "Получено",
           "Заметка"]


class ClientsPage(Page):
    """Экран «Клиенты»."""

    def __init__(self, app) -> None:
        super().__init__(app, "Клиенты")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск: имя, контакт, площадка")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.addAction(icon("search"),
                                   QLineEdit.ActionPosition.LeadingPosition)
        self.search_edit.setMinimumWidth(260)
        self.search_edit.textChanged.connect(self.refresh)
        new_btn = button("Новый клиент", "plus", "primary", "#ffffff")
        new_btn.setToolTip("Ctrl+Shift+N")
        new_btn.clicked.connect(self.add_client)
        self.header.addWidget(self.search_edit)
        self.header.addWidget(new_btn)

        self.table = make_table(HEADERS)
        # activated — двойной щелчок или Enter по строке
        self.table.activated.connect(self.edit_client)
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
            text = f"{client.name} {client.contact} {client.platform}"
            if needle and needle not in text.casefold():
                continue
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
        fill_table(self.table, rows)

    def _need_client(self) -> int | None:
        client_id = selected_id(self.table)
        if client_id is None:
            self.app.show_error("Выберите клиента в таблице.")
        return client_id

    def add_client(self) -> None:
        dialog = ClientDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.app.run(lambda: self.app.manager.add_client(dialog.client()))

    def edit_client(self) -> None:
        client_id = self._need_client()
        if client_id is None:
            return
        dialog = ClientDialog(self.app.manager.get_client(client_id),
                              parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.app.run(lambda: self.app.manager.update_client(
                dialog.client()))

    def delete_client(self) -> None:
        client_id = self._need_client()
        if client_id is not None and self.app.confirm("Удалить клиента?"):
            self.app.run(lambda: self.app.manager.delete_client(client_id))
