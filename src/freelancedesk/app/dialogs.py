"""Формы: клиент, заказ, платёж.

Форма только собирает данные из полей и возвращает объект модели.
Проверки бизнес-правил делает OrderManager, а не форма.
"""

from datetime import date, timedelta
from decimal import Decimal

from PyQt6.QtCore import QDate, QPropertyAnimation
from PyQt6.QtWidgets import (
    QCheckBox, QDateEdit, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QWidget,
)

from freelancedesk.app import animations
from freelancedesk.app.labels import (
    CLIENT_TYPE_LABELS, PLATFORMS, STATUS_LABELS, format_money,
)
from freelancedesk.app.widgets import AnimatedComboBox
from freelancedesk.core.models import Client, Order, OrderStatus, Payment


def to_qdate(value: date) -> QDate:
    """datetime.date -> QDate (Qt хранит даты в своём классе)."""
    return QDate(value.year, value.month, value.day)


def make_date_edit(value: date) -> QDateEdit:
    """Поле даты с выпадающим календарём в формате ДД.ММ.ГГГГ."""
    edit = QDateEdit(to_qdate(value))
    edit.setCalendarPopup(True)
    edit.setDisplayFormat("dd.MM.yyyy")
    return edit


def make_money_spin() -> QDoubleSpinBox:
    """Поле суммы в рублях с копейками и пробелами между тысячами."""
    spin = QDoubleSpinBox()
    spin.setRange(0, 100_000_000)
    spin.setDecimals(2)
    spin.setSuffix(" ₽")
    spin.setGroupSeparatorShown(True)  # 1 500,00 ₽
    return spin


def spin_to_decimal(spin: QDoubleSpinBox) -> Decimal:
    """float из поля -> Decimal без ошибок округления (через строку)."""
    return Decimal(f"{spin.value():.2f}")


def make_buttons(dialog: QDialog, ok_text: str = "Сохранить"
                 ) -> QDialogButtonBox:
    """Кнопки «Сохранить» и «Отмена», подключённые к диалогу."""
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
    buttons.button(QDialogButtonBox.StandardButton.Ok).setText(ok_text)
    buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty(
        "kind", "primary")
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


def make_form(dialog: QDialog) -> QFormLayout:
    """Форма «подпись: поле» с удобными отступами."""
    form = QFormLayout(dialog)
    form.setContentsMargins(20, 18, 20, 16)
    form.setVerticalSpacing(10)
    form.setHorizontalSpacing(14)
    return form


class Dialog(QDialog):
    """Окно формы, которое плавно проявляется при открытии."""

    def showEvent(self, event) -> None:  # noqa: N802 — имя задано Qt
        super().showEvent(event)
        if animations.ENABLED:
            # windowOpacity — прозрачность всего окна от 0 до 1
            self._show_animation = QPropertyAnimation(self, b"windowOpacity",
                                                      self)
            self._show_animation.setDuration(160)
            self._show_animation.setStartValue(0.0)
            self._show_animation.setEndValue(1.0)
            self._show_animation.start()


class ClientDialog(Dialog):
    """Форма клиента. Если передан client — режим редактирования."""

    def __init__(self, client: Client | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Клиент" if client else "Новый клиент")
        self.setMinimumWidth(440)
        # Запоминаем id, чтобы при редактировании вернуть того же клиента
        self._client_id = client.id if client else None

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Иван Петров или ООО «Ромашка»")
        self.type_combo = AnimatedComboBox()
        # addItem(текст, данные): пользователь видит текст, а мы читаем данные
        for client_type, text in CLIENT_TYPE_LABELS.items():
            self.type_combo.addItem(text, client_type)
        self.contact_edit = QLineEdit()
        self.contact_edit.setPlaceholderText("@telegram, почта или телефон")
        # Редактируемый список: можно выбрать площадку или вписать свою
        self.platform_combo = AnimatedComboBox()
        self.platform_combo.setEditable(True)
        self.platform_combo.addItems(PLATFORMS)
        self.platform_combo.setCurrentText("")
        self.note_edit = QPlainTextEdit()
        self.note_edit.setFixedHeight(70)

        form = make_form(self)
        form.addRow("Имя", self.name_edit)
        form.addRow("Тип", self.type_combo)
        form.addRow("Контакт", self.contact_edit)
        form.addRow("Площадка", self.platform_combo)
        form.addRow("Заметка", self.note_edit)
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


class OrderDialog(Dialog):
    """Форма заказа. Если передан order — режим редактирования.

    Оплаты здесь нет: деньги вносятся платежами в карточке заказа.
    """

    def __init__(self, clients: list[Client], order: Order | None = None,
                 parent=None, today: date | None = None) -> None:
        super().__init__(parent)
        today = today or date.today()
        self.setWindowTitle("Заказ" if order else "Новый заказ")
        self.setMinimumWidth(480)
        self._order_id = order.id if order else None
        # Дату сдачи форма не показывает, но сохраняет при изменении
        self._delivered_on = order.delivered_on if order else None

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Telegram-бот для записи клиентов")
        self.client_combo = AnimatedComboBox()
        for client in clients:
            self.client_combo.addItem(client.name, client.id)

        self.amount_spin = make_money_spin()

        # Дедлайн необязателен: флажок включает/выключает поле даты
        self.deadline_check = QCheckBox("есть срок")
        self.deadline_edit = make_date_edit(today + timedelta(days=7))
        self.deadline_check.toggled.connect(self.deadline_edit.setEnabled)
        self.deadline_check.setChecked(True)

        self.status_combo = AnimatedComboBox()
        for status, text in STATUS_LABELS.items():
            self.status_combo.addItem(text, status)

        self.link_edit = QLineEdit()
        self.link_edit.setPlaceholderText("https://kwork.ru/track/…")
        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlaceholderText(
            "ТЗ, договорённости, заметки")
        self.description_edit.setFixedHeight(100)

        form = make_form(self)
        form.addRow("Название", self.title_edit)
        form.addRow("Клиент", self.client_combo)
        form.addRow("Цена", self.amount_spin)
        form.addRow("Дедлайн", row_widget(self.deadline_check,
                                          self.deadline_edit))
        form.addRow("Статус", self.status_combo)
        form.addRow("Ссылка", self.link_edit)
        form.addRow("Описание", self.description_edit)
        hint = QLabel("Деньги по заказу добавляются платежами "
                      "в карточке заказа.")
        hint.setProperty("role", "caption")
        form.addRow(hint)
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
        self.link_edit.setText(order.link)
        self.description_edit.setPlainText(order.description)

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
            amount=spin_to_decimal(self.amount_spin),
            deadline=(self.deadline_edit.date().toPyDate()
                      if self.deadline_check.isChecked() else None),
            status=status,
            # Дату сдачи сохраняем, только если заказ всё ещё сдан;
            # иначе её поставит или уберёт OrderManager
            delivered_on=(self._delivered_on
                          if status == OrderStatus.DELIVERED else None),
            link=self.link_edit.text().strip(),
            description=self.description_edit.toPlainText().strip(),
        )


class PaymentDialog(Dialog):
    """Форма платежа: сколько пришло, когда и выбит ли чек.

    order_id — заказ, к которому относится платёж;
    suggested — сумма по умолчанию (обычно остаток по заказу);
    payment — существующий платёж для редактирования.
    """

    def __init__(self, order_id: int, suggested: Decimal = Decimal("0"),
                 payment: Payment | None = None, parent=None,
                 today: date | None = None) -> None:
        super().__init__(parent)
        today = today or date.today()
        self.setWindowTitle("Платёж" if payment else "Новый платёж")
        self.setMinimumWidth(400)
        self._order_id = order_id
        self._payment_id = payment.id if payment else None

        self.amount_spin = make_money_spin()
        self.amount_spin.setValue(float(payment.amount if payment
                                        else suggested))
        self.date_edit = make_date_edit(payment.paid_on if payment
                                        else today)
        self.receipt_check = QCheckBox("чек выбит в «Мой налог»")
        self.receipt_check.setChecked(bool(payment and
                                           payment.receipt_issued))

        form = make_form(self)
        form.addRow("Сумма", self.amount_spin)
        if suggested > 0 and payment is None:
            hint = QLabel(f"Остаток по заказу: {format_money(suggested)}")
            hint.setProperty("role", "caption")
            form.addRow("", hint)
        form.addRow("Дата", self.date_edit)
        form.addRow("", self.receipt_check)
        note = QLabel("Укажите сумму, которая пришла вам: на Kwork — "
                      "уже без комиссии. С неё считается налог.")
        note.setProperty("role", "caption")
        note.setWordWrap(True)
        form.addRow(note)
        form.addRow(make_buttons(self))

    def accept(self) -> None:
        if self.amount_spin.value() <= 0:
            QMessageBox.warning(self, "Платёж", "Укажите сумму платежа.")
            return
        super().accept()

    def payment(self) -> Payment:
        """Собрать объект Payment из полей формы."""
        return Payment(
            id=self._payment_id,
            order_id=self._order_id,
            amount=spin_to_decimal(self.amount_spin),
            paid_on=self.date_edit.date().toPyDate(),
            receipt_issued=self.receipt_check.isChecked(),
        )
