"""Диалоги добавления и редактирования клиентов и заказов.

Диалог только собирает данные из полей и возвращает объект модели.
Проверки бизнес-правил делает OrderManager, а не форма.
"""

from datetime import date, timedelta
from decimal import Decimal

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QHBoxLayout, QLineEdit, QMessageBox,
    QPlainTextEdit, QWidget,
)

from freelancedesk.app.labels import (
    CLIENT_TYPE_LABELS, PLATFORMS, STATUS_LABELS,
)
from freelancedesk.core.models import Client, Order, OrderStatus


def to_qdate(value: date) -> QDate:
    """datetime.date -> QDate (Qt хранит даты в своём классе)."""
    return QDate(value.year, value.month, value.day)


def make_date_edit(value: date) -> QDateEdit:
    """Поле даты с выпадающим календарём в формате ДД.ММ.ГГГГ."""
    edit = QDateEdit(to_qdate(value))
    edit.setCalendarPopup(True)
    edit.setDisplayFormat("dd.MM.yyyy")
    return edit


def make_buttons(dialog: QDialog) -> QDialogButtonBox:
    """Кнопки «ОК» и «Отмена», подключённые к диалогу."""
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
    # accept/reject закрывают диалог с результатом «принято» / «отменено»
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    return buttons


def row_widget(*widgets) -> QWidget:
    """Несколько виджетов в одну строку формы (последний растягивается)."""
    box = QWidget()
    layout = QHBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    for widget in widgets[:-1]:
        layout.addWidget(widget)
    layout.addWidget(widgets[-1], 1)
    return box


class ClientDialog(QDialog):
    """Форма клиента. Если передан client — режим редактирования."""

    def __init__(self, client: Client | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Клиент" if client else "Новый клиент")
        self.setMinimumWidth(420)
        # Запоминаем id, чтобы при редактировании вернуть того же клиента
        self._client_id = client.id if client else None

        self.name_edit = QLineEdit()
        self.type_combo = QComboBox()
        # addItem(текст, данные): пользователь видит текст, а мы читаем данные
        for client_type, label in CLIENT_TYPE_LABELS.items():
            self.type_combo.addItem(label, client_type)
        self.contact_edit = QLineEdit()
        self.contact_edit.setPlaceholderText("Telegram, e-mail, телефон")
        # Редактируемый список: можно выбрать площадку или вписать свою
        self.platform_combo = QComboBox()
        self.platform_combo.setEditable(True)
        self.platform_combo.addItems(PLATFORMS)
        self.platform_combo.setCurrentText("")
        self.note_edit = QPlainTextEdit()
        self.note_edit.setFixedHeight(70)

        # QFormLayout — две колонки «подпись: поле»
        form = QFormLayout(self)
        form.addRow("Имя*:", self.name_edit)
        form.addRow("Тип:", self.type_combo)
        form.addRow("Контакт:", self.contact_edit)
        form.addRow("Площадка:", self.platform_combo)
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
        self.platform_combo.setCurrentText(client.platform)
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
            platform=self.platform_combo.currentText().strip(),
            note=self.note_edit.toPlainText().strip(),
        )


class OrderDialog(QDialog):
    """Форма заказа. Если передан order — режим редактирования."""

    def __init__(self, clients: list[Client], order: Order | None = None,
                 parent=None, today: date | None = None) -> None:
        super().__init__(parent)
        today = today or date.today()
        self.setWindowTitle("Заказ" if order else "Новый заказ")
        self.setMinimumWidth(460)
        self._order_id = order.id if order else None

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
        self.deadline_edit = make_date_edit(today + timedelta(days=7))
        self.deadline_check.toggled.connect(self.deadline_edit.setEnabled)
        self.deadline_check.setChecked(True)

        self.status_combo = QComboBox()
        for status, label in STATUS_LABELS.items():
            self.status_combo.addItem(label, status)

        # Оплата: дату можно поправить (оплатили вчера, внесли сегодня) —
        # от неё зависит, в каком месяце считать налог
        self.paid_on_edit = make_date_edit(today)
        self.receipt_check = QCheckBox("чек выбит в «Мой налог»")

        self.link_edit = QLineEdit()
        self.link_edit.setPlaceholderText("https://kwork.ru/…")
        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlaceholderText("ТЗ, договорённости, заметки")
        self.description_edit.setFixedHeight(90)

        form = QFormLayout(self)
        form.addRow("Название*:", self.title_edit)
        form.addRow("Клиент*:", self.client_combo)
        form.addRow("Сумма:", self.amount_spin)
        form.addRow("Дедлайн:", row_widget(self.deadline_check,
                                           self.deadline_edit))
        form.addRow("Статус:", self.status_combo)
        form.addRow("Оплачен:", row_widget(self.paid_on_edit,
                                           self.receipt_check))
        form.addRow("Ссылка:", self.link_edit)
        form.addRow("Описание:", self.description_edit)
        form.addRow(make_buttons(self))

        # Поля оплаты доступны только при статусе «Оплачен»
        self.status_combo.currentIndexChanged.connect(
            self._update_payment_fields)
        if order:
            self._fill(order)
        self._update_payment_fields()

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
        if order.paid_on:
            self.paid_on_edit.setDate(to_qdate(order.paid_on))
        self.receipt_check.setChecked(order.receipt_issued)
        self.link_edit.setText(order.link)
        self.description_edit.setPlainText(order.description)

    def _is_paid(self) -> bool:
        return self.status_combo.currentData() == OrderStatus.PAID

    def _update_payment_fields(self) -> None:
        paid = self._is_paid()
        self.paid_on_edit.setEnabled(paid)
        self.receipt_check.setEnabled(paid)

    def accept(self) -> None:
        if not self.title_edit.text().strip():
            QMessageBox.warning(self, "Заказ", "Укажите название заказа.")
            return
        super().accept()

    def order(self) -> Order:
        """Собрать объект Order из полей формы."""
        paid = self._is_paid()
        return Order(
            id=self._order_id,
            title=self.title_edit.text().strip(),
            client_id=self.client_combo.currentData(),
            # float -> строка с 2 знаками -> Decimal: без ошибок округления
            amount=Decimal(f"{self.amount_spin.value():.2f}"),
            deadline=(self.deadline_edit.date().toPyDate()
                      if self.deadline_check.isChecked() else None),
            status=self.status_combo.currentData(),
            # Не оплачен — даты оплаты и чека нет, сколько бы ни стояло в полях
            paid_on=self.paid_on_edit.date().toPyDate() if paid else None,
            receipt_issued=self.receipt_check.isChecked() and paid,
            link=self.link_edit.text().strip(),
            description=self.description_edit.toPlainText().strip(),
        )
