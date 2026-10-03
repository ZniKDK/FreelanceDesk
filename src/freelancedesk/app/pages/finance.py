"""Экран «Финансы»: поступления за период, налог, площадки, диаграмма,
журнал платежей для сверки с «Мой налог»."""

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QButtonGroup, QGridLayout, QHBoxLayout, QVBoxLayout,
)

from freelancedesk.app.dialogs import make_date_edit, to_qdate
from freelancedesk.app.labels import MONTH_SHORT, format_money, plural
from freelancedesk.app.pages import Page
from freelancedesk.app.theme import C
from freelancedesk.app.widgets import (
    BarChart, Card, SortItem, StatCard, button, clear_layout, fill_table,
    label,
    make_table, money_item, selected_id,
)
from freelancedesk.core.manager import add_months, month_end, month_start

PAYMENT_HEADERS = ["Заказ", "Дата", "Клиент", "Сумма", "Налог", "Чек"]
PAYMENTS = ("платёж", "платежа", "платежей")

# Быстрые периоды: ключ -> подпись кнопки
PERIODS = {"this_month": "Этот месяц", "last_month": "Прошлый месяц",
           "this_year": "Этот год"}


class FinancePage(Page):
    """Экран «Финансы»."""

    def __init__(self, app) -> None:
        super().__init__(app, "Финансы")

        # --- Период: быстрые кнопки и две даты ---
        self.period_group = QButtonGroup(self)
        self.period_buttons = {}
        for key, text in PERIODS.items():
            btn = button(text, kind="chip")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, key=key: self.set_period(key))
            self.period_group.addButton(btn)
            self.period_buttons[key] = btn
            self.header.addWidget(btn)
        today = app.today()
        self.start_edit = make_date_edit(month_start(today))
        self.end_edit = make_date_edit(today)
        self.header.addSpacing(8)
        self.header.addWidget(self.start_edit)
        self.header.addWidget(label("—", "muted"))
        self.header.addWidget(self.end_edit)
        # Даты поменяли вручную — быстрый период больше не выбран
        self.start_edit.dateChanged.connect(self._dates_edited)
        self.end_edit.dateChanged.connect(self._dates_edited)

        # --- Итоги периода ---
        cards = QGridLayout()
        cards.setSpacing(12)
        self.income_card = StatCard("Получено")
        self.tax_card = StatCard("Налог НПД")
        self.net_card = StatCard("На руки")
        for col, card in enumerate((self.income_card, self.tax_card,
                                    self.net_card)):
            cards.addWidget(card, 0, col)
        self.layout_.addLayout(cards)

        # --- Диаграмма и площадки ---
        middle = QHBoxLayout()
        middle.setSpacing(12)
        chart_card = Card("Поступления за 12 месяцев")
        self.chart = BarChart()
        chart_card.body.addWidget(self.chart)
        platform_card = Card("По площадкам за период")
        self.platforms_box = QVBoxLayout()
        platform_card.body.addLayout(self.platforms_box)
        platform_card.body.addStretch(1)
        platform_card.setMinimumWidth(260)
        middle.addWidget(chart_card, 3)
        middle.addWidget(platform_card, 1)
        self.layout_.addLayout(middle)

        # --- Журнал платежей ---
        journal = Card()
        top = QHBoxLayout()
        top.addWidget(label("Платежи за период", "section"))
        top.addStretch(1)
        receipt_btn = button("Чек выбит / не выбит", "receipt")
        receipt_btn.setToolTip("Переключить отметку о чеке у выбранного "
                               "платежа")
        receipt_btn.clicked.connect(self.toggle_receipt)
        top.addWidget(receipt_btn)
        journal.body.addLayout(top)
        self.table = make_table(PAYMENT_HEADERS, sort_column=1,
                                descending=True)
        self.table.activated.connect(self.open_selected_order)
        self.table.setMinimumHeight(180)
        # Таблица внутри карточки — своя рамка не нужна
        self.table.setStyleSheet("QTableWidget { border: none; }")
        journal.body.addWidget(self.table)
        self.layout_.addWidget(journal, 1)

        self.period_buttons["this_month"].setChecked(True)

    # ------------------------------------------------------------------

    def set_period(self, key: str) -> None:
        """Выбрать быстрый период."""
        today = self.app.today()
        if key == "last_month":
            start = add_months(month_start(today), -1)
            end = month_end(start)
        elif key == "this_year":
            start, end = today.replace(month=1, day=1), today
        else:
            start, end = month_start(today), today
        for edit, value in ((self.start_edit, start), (self.end_edit, end)):
            edit.blockSignals(True)  # не считать «ручным» изменением
            edit.setDate(to_qdate(value))
            edit.blockSignals(False)
        self.period_buttons[key].setChecked(True)
        self.refresh()

    def _dates_edited(self) -> None:
        self.period_group.setExclusive(False)
        for btn in self.period_buttons.values():
            btn.setChecked(False)
        self.period_group.setExclusive(True)
        self.refresh()

    def period(self):
        return (self.start_edit.date().toPyDate(),
                self.end_edit.date().toPyDate())

    def refresh(self) -> None:
        manager = self.app.manager
        start, end = self.period()
        if start > end:
            self.income_card.set("—", "начало периода позже конца")
            self.tax_card.set("—")
            self.net_card.set("—")
            fill_table(self.table, [])
            return

        summary = manager.summary(start, end)
        self.income_card.set_money(
            summary.income,
            f"{summary.payments} {plural(summary.payments, PAYMENTS)}")
        self.tax_card.set_money(summary.tax, "4 % с физлиц, 6 % с юрлиц и ИП",
                                kopecks=True)
        self.net_card.set_money(summary.net, "после налога")

        self.chart.set_data([
            (MONTH_SHORT[month.month - 1], amount)
            for month, amount in manager.income_by_month(self.app.today())])

        clear_layout(self.platforms_box)
        platforms = manager.income_by_platform(start, end)
        for name, amount in platforms:
            row = label(f"{name}: <b>{format_money(amount, False)}</b>")
            self.platforms_box.addWidget(row)
        if not platforms:
            self.platforms_box.addWidget(label("Поступлений нет", "muted"))

        orders = {o.id: o for o in manager.list_orders()}
        names = {c.id: c.name for c in manager.list_clients()}
        rows = []
        for payment in manager.payments_in_period(start, end):
            order = orders.get(payment.order_id)
            receipt = SortItem("✓ выбит" if payment.receipt_issued
                               else "не выбит", payment.receipt_issued)
            if not payment.receipt_issued:
                receipt.setForeground(QColor(C["warning_text"]))
            rows.append((payment.id, [
                SortItem(order.title if order else "?"),
                SortItem(payment.paid_on.strftime("%d.%m.%Y"),
                         payment.paid_on),
                SortItem(names.get(order.client_id, "?") if order else "?"),
                money_item(payment.amount),
                money_item(manager.payment_tax(payment)),
                receipt,
            ]))
        fill_table(self.table, rows)

    def toggle_receipt(self) -> None:
        payment_id = selected_id(self.table)
        if payment_id is None:
            self.app.show_error("Выберите платёж в таблице.")
            return
        payment = self.app.manager.get_payment(payment_id)
        self.app.run(lambda: self.app.manager.set_receipt(
            payment_id, not payment.receipt_issued))

    def open_selected_order(self) -> None:
        payment_id = selected_id(self.table)
        if payment_id is not None:
            payment = self.app.manager.get_payment(payment_id)
            self.app.open_order(payment.order_id)
