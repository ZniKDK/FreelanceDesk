"""Экран «Клиенты»: таблица клиентов с контактами, заказами и доходом."""

from decimal import Decimal

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QLineEdit, \
    QMenu

from freelancedesk.app.dialogs import ClientDialog
from freelancedesk.app import animations
from freelancedesk.app.labels import (
    CLIENT_TYPE_LABELS, CLIENT_TYPE_SHORT, CONTACT_LABELS,
)
from freelancedesk.app.pages import Page
from freelancedesk.app.theme import C, icon
from freelancedesk.app.widgets import (
    Card, SortItem, button, fill_table, label, make_table, money_item,
    selected_id, wrapped_tip,
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

        # Карточка выбранного клиента: контакты и заметка целиком
        self.details = Card()
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(4)
        self.details_title = label("", "section")
        self.details_contacts = label()
        self.details_contacts.setTextFormat(Qt.TextFormat.RichText)
        self.details_note = label()
        self.details_note.setWordWrap(True)
        self.details_note.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(self.details_title, 0, 0, 1, 2)
        grid.addWidget(self.details_contacts, 1, 0,
                       Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self.details_note, 1, 1, Qt.AlignmentFlag.AlignTop)
        grid.setColumnStretch(1, 1)
        self.details.body.addLayout(grid)
        self.details.hide()
        self.layout_.addWidget(self.details)
        self.table.itemSelectionChanged.connect(self.show_details)

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
            # Обрезанный текст («Постоянны…») виден целиком при наведении;
            # длинная подсказка переносится по строкам
            for item in items:
                if item.text():
                    item.setToolTip(wrapped_tip(item.text()))
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
        self.show_details()

    def show_details(self) -> None:
        """Показать карточку выделенного клиента под таблицей."""
        client_id = selected_id(self.table)
        client = (self.app.manager.get_client(client_id)
                  if client_id is not None else None)
        if client is None:
            self.details.hide()
            return
        was_hidden = self.details.isHidden()
        self.details_title.setText(
            f"{client.name} · {CLIENT_TYPE_LABELS[client.client_type]}")
        lines = []
        values = {ContactMethod.EMAIL: client.email,
                  ContactMethod.PHONE: client.phone,
                  ContactMethod.MESSENGER: messenger_text(client)}
        for method, value in values.items():
            if value:
                star = " ★" if method == client.preferred_contact else ""
                lines.append(f"<span style='color:{C['text2']}'>"
                             f"{CONTACT_LABELS[method]}:</span> "
                             f"{value}{star}")
        self.details_contacts.setText("<br>".join(lines)
                                      or "Контакты не указаны")
        self.details_note.setText(client.note or "Заметки нет")
        self.details.show()
        if was_hidden:
            animations.fade_in(self.details, shift=0)

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
