"""Экран «Главная»: деньги за месяц, налог, что горит и ближайшие сроки."""

from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGridLayout, QHBoxLayout, QInputDialog, QListWidget, QListWidgetItem,
)

from freelancedesk.app import animations
from freelancedesk.app.labels import (
    DAYS, MONTH_PREPOSITIONAL, ORDERS, deadline_text, format_date,
    format_long_date, format_money, format_month, plural,
)
from freelancedesk.app.pages import Page
from freelancedesk.app.theme import C, icon
from freelancedesk.app.widgets import Card, StatCard, button, label, \
    thin_progress
from freelancedesk.core.manager import OrderView, month_start


class DashboardPage(Page):
    """Экран «Главная» — то, что важно увидеть сразу после запуска."""

    def __init__(self, app) -> None:
        super().__init__(app, "Главная")
        self.date_label = label("", "muted")
        self.header.insertWidget(1, self.date_label)

        # --- Четыре карточки с главными цифрами ---
        cards = QGridLayout()
        cards.setSpacing(12)
        self.income_card = StatCard("Получено в этом месяце")
        self.goal_bar = thin_progress(0)
        self.income_card.body.insertWidget(3, self.goal_bar)
        goal_btn = button("Изменить цель", kind="ghost")
        goal_btn.clicked.connect(self.ask_goal)
        self.income_card.body.addWidget(goal_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self.awaiting_card = StatCard("Ждёт оплаты")
        self.tax_card = StatCard("Налог к уплате")
        self.net_card = StatCard("На руки в этом месяце")
        for col, card in enumerate((self.income_card, self.awaiting_card,
                                    self.tax_card, self.net_card)):
            cards.addWidget(card, 0, col)
            cards.setColumnStretch(col, 1)  # все колонки одной ширины
        self.layout_.addLayout(cards)

        # --- Два списка: «Горит» и «Ближайшие сроки» ---
        lists = QHBoxLayout()
        lists.setSpacing(12)
        self.hot_list = self._make_list()
        self.upcoming_list = self._make_list()
        hot_card = Card("Требует внимания")
        hot_card.body.addWidget(self.hot_list)
        upcoming_card = Card("Ближайшие сроки")
        upcoming_card.body.addWidget(self.upcoming_list)
        lists.addWidget(hot_card)
        lists.addWidget(upcoming_card)
        self.layout_.addLayout(lists, 1)

    def _make_list(self) -> QListWidget:
        """Список заказов без рамки; щелчок открывает заказ."""
        widget = QListWidget()
        widget.setStyleSheet("QListWidget { border: none; }")
        widget.itemClicked.connect(self._open_item)
        return widget

    def _open_item(self, item: QListWidgetItem) -> None:
        order_id = item.data(Qt.ItemDataRole.UserRole)
        if order_id is not None:
            self.app.open_order(order_id)

    @staticmethod
    def _add_item(widget: QListWidget, text: str, icon_name: str,
                  color: str, order_id: int | None = None) -> None:
        item = QListWidgetItem(icon(icon_name, color), text)
        item.setData(Qt.ItemDataRole.UserRole, order_id)
        if order_id is None:
            item.setFlags(Qt.ItemFlag.NoItemFlags)  # просто надпись
        widget.addItem(item)

    # ------------------------------------------------------------------

    def ask_goal(self) -> None:
        """Спросить цель на месяц в маленьком окне."""
        value, ok = QInputDialog.getInt(
            self, "Цель на месяц", "Сколько хотите получить за месяц, ₽:",
            self.app.goal(), 0, 10_000_000, 5_000)
        if ok:
            self.app.set_goal(value)

    def refresh(self) -> None:
        today = self.app.today()
        manager = self.app.manager
        self.date_label.setText(format_long_date(today))
        month_word = MONTH_PREPOSITIONAL[today.month - 1]

        # Получено и цель
        month = manager.summary(month_start(today), today)
        self.income_card.caption.setText(f"Получено в {month_word}")
        goal = self.app.goal()
        if goal:
            percent = min(100, int(month.income * 100 / goal))
            hint = (f"цель {format_money(Decimal(goal), False)}"
                    f" · {percent} %")
            animations.animate_value(self.goal_bar, percent)
        else:
            hint = "цель не задана"
            self.goal_bar.setValue(0)
        self.goal_bar.setVisible(bool(goal))
        self.income_card.set_money(month.income, hint)

        # Ждёт оплаты за сданную работу
        awaiting = manager.awaiting_payment()
        self.awaiting_card.set_money(
            awaiting.amount,
            f"{awaiting.orders} {plural(awaiting.orders, ORDERS)} сдано, "
            "денег ещё нет" if awaiting.orders else "все сданные оплачены")

        # Налог за прошлый месяц
        due = manager.tax_due(today)
        days_left = (due.due_date - today).days
        if due.amount <= 0:
            tax_hint = f"за {format_month(due.month)} налога нет"
        elif days_left >= 0:
            tax_hint = (f"за {format_month(due.month)}, до "
                        f"{format_date(due.due_date)} — осталось "
                        f"{days_left} {plural(days_left, DAYS)}")
        else:
            tax_hint = (f"за {format_month(due.month)}: срок прошёл, "
                        "проверьте «Мой налог»")
        self.tax_card.set_money(due.amount, tax_hint, kopecks=True)

        self.net_card.caption.setText(f"На руки в {month_word}")
        self.net_card.set_money(month.net, f"налог {format_money(month.tax)}")

        self._fill_hot(today)
        self._fill_upcoming(today)

    def _fill_hot(self, today) -> None:
        manager = self.app.manager
        names = {c.id: c.name for c in manager.list_clients()}
        self.hot_list.clear()
        groups = [
            (OrderView.OVERDUE, "triangle-alert", C["danger"]),
            (OrderView.DUE_TODAY, "clock", C["warning"]),
            (OrderView.NO_RECEIPT, "receipt", C["warning"]),
            (OrderView.AWAITING_PAYMENT, "hand-coins", C["text2"]),
        ]
        money = manager.money_all()
        seen = set()  # один заказ — одна строка, по самому важному поводу
        for view, icon_name, color in groups:
            for order in manager.list_orders(view, today=today):
                if order.id in seen:
                    continue
                seen.add(order.id)
                if view == OrderView.NO_RECEIPT:
                    why = "оплата без чека в «Мой налог»"
                elif view == OrderView.AWAITING_PAYMENT:
                    why = (f"ждёт оплаты "
                           f"{format_money(money[order.id].remaining, False)}")
                else:
                    why = deadline_text(order, today)[0]
                self._add_item(self.hot_list,
                               f"{order.title} — {names.get(order.client_id)}"
                               f": {why}", icon_name, color, order.id)
        if not seen:
            self._add_item(self.hot_list, "Всё под контролем: просрочек и "
                           "долгов нет", "circle-check", C["success"])

    def _fill_upcoming(self, today) -> None:
        manager = self.app.manager
        names = {c.id: c.name for c in manager.list_clients()}
        self.upcoming_list.clear()
        orders = manager.upcoming(today, limit=7)
        for order in orders:
            when, tone = deadline_text(order, today)
            color = {"danger": C["danger"], "warning": C["warning"]}.get(
                tone, C["text2"])
            self._add_item(self.upcoming_list,
                           f"{format_date(order.deadline)[:5]}  {order.title}"
                           f" — {names.get(order.client_id)} ({when})",
                           "calendar", color, order.id)
        if not orders:
            self._add_item(self.upcoming_list, "Сроков нет. Новые заказы "
                           "появятся здесь", "calendar", C["text2"])
