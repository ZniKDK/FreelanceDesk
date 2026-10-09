"""Диалоги добавления и редактирования клиентов и заказов.

Диалог только собирает данные из полей и возвращает объект модели.
Проверки бизнес-правил делает OrderManager, а не форма.
"""

from datetime import date
from decimal import Decimal

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QHBoxLayout, QLineEdit, QMessageBox,
    QPlainTextEdit, QWidget,
)

from freelancedesk.app.labels import CLIENT_TYPE_LABELS, STATUS_LABELS
from freelancedesk.core.models import Client, Order, OrderStatus


def to_qdate(value: date) -> QDate:
    """datetime.date -> QDate (Qt хранит даты в своём классе)."""
    return QDate(value.year, value.month, value.day)


def make_buttons(dialog: QDialog) -> QDialogButtonBox:
    """Кнопки «ОК» и «Отмена», подключённые к диалогу."""
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
    # accept/reject закрывают диалог с результатом «принято» / «отменено»
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    return buttons


class ClientDialog(QDialog):
    """Форма клиента. Если передан client — режим редактирования."""

    def __init__(self, client: Client | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Клиент" if client else "Новый клиент")
        self.setMinimumWidth(400)
        # Запоминаем id, чтобы при редактировании вернуть того же клиента
        self._client_id = client.id if client else None

        self.name_edit = QLineEdit()
        self.type_combo = QComboBox()
        # addItem(текст, данные): пользователь видит текст, а мы читаем данные
        for client_type, label in CLIENT_TYPE_LABELS.items():
            self.type_combo.addItem(label, client_type)
        self.contact_edit = QLineEdit()
        self.contact_edit.setPlaceholderText("Telegram, e-mail, телефон")
        self.platform_edit = QLineEdit()
        self.platform_edit.setPlaceholderText("Kwork, FL.ru, напрямую…")
        self.note_edit = QPlainTextEdit()
        self.note_edit.setFixedHeight(70)

        # QFormLayout — две колонки «подпись: поле»
        form = QFormLayout(self)
        form.addRow("Имя*:", self.name_edit)
        form.addRow("Тип:", self.type_combo)
        form.addRow("Контакт:", self.contact_edit)
        form.addRow("Площадка:", self.platform_edit)
        form.addRow("Заметка:", self.note_edit)
        form.addRow(make_buttons(self))

        if client:
            self._fill(client)

    def _fill(self, client: Client) -> None:
        """Заполнить поля данными существующего клиента."""
        self.name_edit.setText(client.name)
        self.type_combo.setCurrentIndex(
            self.type_combo.findData(client.client_type))
        self.contact_edit.setText(client.contact)
        self.platform_edit.setText(client.platform)
        self.note_edit.setPlainText(client.note)

    def accept(self) -> None:
        # Не закрываем форму с пустым именем — сразу подсказываем
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Клиент", "Укажите имя клиента.")
            return
        super().accept()

    def client(self) -> Client:
        """Собрать объект Client из полей формы."""
        return Client(
            id=self._client_id,
            name=self.name_edit.text().strip(),
            client_type=self.type_combo.currentData(),
            contact=self.contact_edit.text().strip(),
            platform=self.platform_edit.text().strip(),
            note=self.note_edit.toPlainText().strip(),
        )


class OrderDialog(QDialog):
    """Форма заказа. Если передан order — режим редактирования."""

    def __init__(self, clients: list[Client], order: Order | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Заказ" if order else "Новый заказ")
        self.setMinimumWidth(400)
        self._order_id = order.id if order else None
        # Дату оплаты форма не показывает, но должна сохранить при изменении
        self._paid_on = order.paid_on if order else None

        self.title_edit = QLineEdit()
        self.client_combo = QComboBox()
        for client in clients:
            self.client_combo.addItem(client.name, client.id)

        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0, 100_000_000)
        self.amount_spin.setDecimals(2)
        self.amount_spin.setSuffix(" ₽")
        self.amount_spin.setGroupSeparatorShown(True)  # 1 500,00 ₽

        # Дедлайн необязателен: флажок включает/выключает поле даты
        self.deadline_check = QCheckBox("есть срок")
        self.deadline_edit = QDateEdit(QDate.currentDate().addDays(7))
        self.deadline_edit.setCalendarPopup(True)  # выпадающий календарь
        self.deadline_edit.setDisplayFormat("dd.MM.yyyy")
        self.deadline_check.toggled.connect(self.deadline_edit.setEnabled)
        self.deadline_check.setChecked(True)
        deadline_row = QWidget()
        row_layout = QHBoxLayout(deadline_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(self.deadline_check)
        row_layout.addWidget(self.deadline_edit, 1)

        self.status_combo = QComboBox()
        for status, label in STATUS_LABELS.items():
            self.status_combo.addItem(label, status)

        form = QFormLayout(self)
        form.addRow("Название*:", self.title_edit)
        form.addRow("Клиент*:", self.client_combo)
        form.addRow("Сумма:", self.amount_spin)
        form.addRow("Дедлайн:", deadline_row)
        form.addRow("Статус:", self.status_combo)
        form.addRow(make_buttons(self))

        if order:
            self._fill(order)

    def _fill(self, order: Order) -> None:
        self.title_edit.setText(order.title)
        self.client_combo.setCurrentIndex(
            self.client_combo.findData(order.client_id))
        self.amount_spin.setValue(float(order.amount))
        self.deadline_check.setChecked(order.deadline is not None)
        if order.deadline:
            self.deadline_edit.setDate(to_qdate(order.deadline))
        self.status_combo.setCurrentIndex(
            self.status_combo.findData(order.status))

    def accept(self) -> None:
        if not self.title_edit.text().strip():
            QMessageBox.warning(self, "Заказ", "Укажите название заказа.")
            return
        super().accept()

    def order(self) -> Order:
        """Собрать объект Order из полей формы."""
        status: OrderStatus = self.status_combo.currentData()
        return Order(
            id=self._order_id,
            title=self.title_edit.text().strip(),
            client_id=self.client_combo.currentData(),
            # float -> строка с 2 знаками -> Decimal: без ошибок округления
            amount=Decimal(f"{self.amount_spin.value():.2f}"),
            deadline=(self.deadline_edit.date().toPyDate()
                      if self.deadline_check.isChecked() else None),
            status=status,
            # Старую дату оплаты оставляем, только если заказ всё ещё оплачен;
            # остальное решит OrderManager
            paid_on=self._paid_on if status == OrderStatus.PAID else None,
        )

