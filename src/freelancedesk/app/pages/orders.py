"""Экран «Заказы»: фильтры, список заказов и карточка выбранного заказа.

«Липкий» заказ: если поменять статус и заказ перестанет подходить под
фильтр, он не исчезает сразу — строка остаётся (полупрозрачной, с
пометкой, куда перешёл заказ), карточка открыта. Строка уходит, когда
пользователь сменит фильтр или поиск, либо выберет другой заказ и
данные обновятся.
"""

from datetime import date

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QButtonGroup, QDialog, QFrame, QGraphicsOpacityEffect, QGridLayout,
    QHBoxLayout, QLineEdit, QListWidgetItem, QMenu, QProgressBar,
    QScrollArea, QSplitter, QStackedLayout, QVBoxLayout, QWidget,
)

from freelancedesk.app import animations
from freelancedesk.app.dialogs import OrderDialog, PaymentDialog
from freelancedesk.app.labels import (
    STATUS_LABELS, VIEW_LABELS, deadline_text, format_date, format_money,
    format_short_money,
)
from freelancedesk.app.pages import Page
from freelancedesk.app.theme import (
    C, icon, payment_bar_color, status_chip, tone_color,
)
from freelancedesk.app.widgets import (
    AnimatedComboBox, FilterStrip, HintListWidget, SmoothScroller,
    bar_style, button, chip, clear_layout, label, set_fitting_text,
    thin_progress,
)
from freelancedesk.core.manager import (
    TAX_RATES, OrderMoney, OrderView, PaymentState,
)
from freelancedesk.core.models import (
    OPEN_STATUSES, ClientType, Order, OrderStatus, Payment,
)

# Варианты сортировки списка
SORTS = {"deadline": "По сроку", "amount": "По цене", "new": "Сначала новые"}

# Ключ фильтра «Отменённые» (это статус, а не выборка OrderView)
CANCELLED_KEY = "cancelled"

# Куда «переезжает» заказ: самая подходящая выборка для подсказки
DESTINATION_ORDER = [OrderView.DONE, OrderView.AWAITING_PAYMENT,
                     OrderView.ACTIVE]


def money_caption(order: Order, money: OrderMoney) -> tuple[str, str]:
    """Короткая подпись оплаты для строки списка и её цвет."""
    if money.state == PaymentState.PAID:
        return "оплачен", C["success_text"]
    if order.status == OrderStatus.DELIVERED:
        return f"ждёт {format_short_money(money.remaining)}", \
            C["warning_text"]
    return (f"{format_short_money(money.received)} / "
            f"{format_short_money(money.price)}"), C["text2"]


class OrderRow(QWidget):
    """Строка списка заказов: название, клиент и срок, статус, оплата.

    moved_to — подпись выборки, куда ушёл «липкий» заказ (строка тогда
    полупрозрачная и с пометкой).
    """

    def __init__(self, order: Order, client_name: str, money: OrderMoney,
                 today: date, moved_to: str = "") -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(12)

        text = QVBoxLayout()
        text.setSpacing(2)
        self.title = label(order.title)
        self.title.setStyleSheet("font-weight: 600;" if order.status !=
                                 OrderStatus.CANCELLED else
                                 f"color: {C['text2']};")
        when, tone = deadline_text(order, today)
        extra = (f" · <span style='color:{C['accent_text']}'>перешёл в "
                 f"«{moved_to}»</span>" if moved_to else "")
        # Подпись с HTML: срок подкрашивается (красный — просрочен)
        self.subtitle = label(
            f"{client_name} · <span style='color:{tone_color(tone)}'>"
            f"{when}</span>{extra}", "caption")
        text.addWidget(self.title)
        text.addWidget(self.subtitle)
        layout.addLayout(text, 1)

        caption, bg, fg = status_chip(order.status)
        status = chip(caption, bg, fg)
        status.setFixedSize(80, 22)
        layout.addWidget(status, 0, Qt.AlignmentFlag.AlignVCenter)

        pay = QVBoxLayout()
        pay.setSpacing(4)
        pay_text, pay_color = money_caption(order, money)
        self.money_label = label(pay_text, "caption")
        self.money_label.setStyleSheet(f"color: {pay_color};")
        self.money_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        pay.addWidget(self.money_label)
        pay.addWidget(thin_progress(money.progress,
                                    payment_bar_color(money.state)))
        pay_box = QWidget()
        pay_box.setLayout(pay)
        pay_box.setFixedWidth(110)
        layout.addWidget(pay_box)

        if moved_to:
            # Полупрозрачная строка: «я здесь временно»
            effect = QGraphicsOpacityEffect(self)
            effect.setOpacity(0.55)
            self.setGraphicsEffect(effect)


class OrderPanel(QWidget):
    """Карточка выбранного заказа справа от списка."""

    def __init__(self, page: "OrdersPage") -> None:
        super().__init__()
        self.page = page
        self.app = page.app
        self.order: Order | None = None

        # Два состояния: «ничего не выбрано» и карточка заказа
        self.stack = QStackedLayout(self)
        empty = label("Выберите заказ<br>"
                      "<span style='font-size:10pt; font-weight:600'>"
                      "детали и платежи появятся здесь</span>")
        empty.setTextFormat(Qt.TextFormat.RichText)
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setStyleSheet(f"font-size: 15pt; font-weight: 700;"
                            f" color: {C['text2']};")
        faded = QGraphicsOpacityEffect(empty)
        faded.setOpacity(0.55)  # подсказка «растворена» в фоне
        empty.setGraphicsEffect(faded)
        self.stack.addWidget(empty)
        self.content = QWidget()
        self.stack.addWidget(self.content)
        body = QVBoxLayout(self.content)
        body.setContentsMargins(18, 16, 18, 16)
        body.setSpacing(12)

        self.title = label()
        self.title.setStyleSheet("font-size: 14pt; font-weight: 600;")
        self.title.setWordWrap(True)
        self.subtitle = label("", "muted")
        body.addWidget(self.title)
        body.addWidget(self.subtitle)

        # --- Статус работы: три кнопки-сегмента ---
        segments = QHBoxLayout()
        segments.setSpacing(0)
        self.status_group = QButtonGroup(self)
        self.status_buttons: dict[OrderStatus, object] = {}
        for status in OPEN_STATUSES + (OrderStatus.DELIVERED,):
            btn = button(STATUS_LABELS[status], kind="segment")
            btn.setCheckable(True)
            # status=status — запоминаем значение для каждой кнопки
            btn.clicked.connect(
                lambda _, status=status: self.page.set_status(status))
            self.status_group.addButton(btn)
            self.status_buttons[status] = btn
            segments.addWidget(btn)
        body.addLayout(segments)
        self.cancelled_label = label("Заказ отменён", "muted")
        body.addWidget(self.cancelled_label)

        # --- Деньги по заказу ---
        money_box = QFrame()
        money_box.setObjectName("moneyBox")
        grid = QGridLayout(money_box)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setVerticalSpacing(6)
        self.received_label = label()
        self.received_label.setStyleSheet("font-weight: 600;")
        self.money_bar = QProgressBar()
        self.money_bar.setRange(0, 100)
        self.money_bar.setTextVisible(False)
        self.tax_label = label()
        self.net_label = label()
        self.net_label.setStyleSheet(f"color: {C['success_text']};"
                                     " font-weight: 600;")
        self.remaining_label = label()
        grid.addWidget(label("Получено", "muted"), 0, 0)
        grid.addWidget(self.received_label, 0, 1, Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self.money_bar, 1, 0, 1, 2)
        rows = [("Налог НПД", self.tax_label), ("На руки", self.net_label),
                ("Осталось получить", self.remaining_label)]
        for row, (caption, value) in enumerate(rows, start=2):
            grid.addWidget(label(caption, "muted"), row, 0)
            grid.addWidget(value, row, 1, Qt.AlignmentFlag.AlignRight)
        body.addWidget(money_box)

        # --- Платежи ---
        pay_header = QHBoxLayout()
        pay_header.addWidget(label("Платежи", "section"))
        pay_header.addStretch(1)
        self.add_payment_btn = button("Платёж", "plus")
        self.add_payment_btn.setToolTip("Добавить платёж (Ctrl+P)")
        self.add_payment_btn.clicked.connect(self.page.add_payment)
        pay_header.addWidget(self.add_payment_btn)
        body.addLayout(pay_header)
        self.payments_box = QVBoxLayout()
        self.payments_box.setSpacing(0)
        body.addLayout(self.payments_box)

        # --- Детали ---
        body.addWidget(label("Детали", "section"))
        self.deadline_label = label()
        self.link_btn = button("Открыть ссылку", "external-link", "ghost")
        self.link_btn.clicked.connect(self.page.open_link)
        self.description = label()
        self.description.setWordWrap(True)
        self.description.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        body.addWidget(self.deadline_label)
        body.addWidget(self.link_btn, 0, Qt.AlignmentFlag.AlignLeft)
        body.addWidget(self.description)
        body.addStretch(1)

        # --- Кнопки ---
        actions = QHBoxLayout()
        edit_btn = button("Изменить", "pencil")
        edit_btn.clicked.connect(self.page.edit_order)
        self.cancel_btn = button("Отменить заказ", "x")
        self.cancel_btn.clicked.connect(self.page.toggle_cancel)
        delete_btn = button("Удалить", "trash-2", "danger", C["danger_text"])
        delete_btn.clicked.connect(self.page.delete_order)
        for widget in (edit_btn, self.cancel_btn):
            actions.addWidget(widget)
        actions.addStretch(1)
        actions.addWidget(delete_btn)
        body.addLayout(actions)

    def show_order(self, order_id: int | None) -> None:
        """Показать заказ (или заглушку, если ничего не выбрано)."""
        manager = self.app.manager
        previous_id = self.order.id if self.order else None
        self.order = manager.get_order(order_id) if order_id else None
        if self.order is None:
            self.stack.setCurrentIndex(0)
            return
        self.stack.setCurrentIndex(1)
        order = self.order
        client = manager.get_client(order.client_id)
        money = manager.money(order.id)
        client_type = client.client_type if client else ClientType.PERSON
        rate = TAX_RATES[client_type] * 100

        self.title.setText(order.title)
        kind = "юрлицо/ИП" if client_type == ClientType.COMPANY else "физлицо"
        self.subtitle.setText(
            f"{client.name if client else '?'} · {kind}, НПД {rate:.0f} %")

        # Статус: при «отменён» ни один сегмент не выбран
        cancelled = order.status == OrderStatus.CANCELLED
        self.status_group.setExclusive(False)
        for status, btn in self.status_buttons.items():
            btn.setChecked(status == order.status)
            btn.setEnabled(not cancelled)
        self.status_group.setExclusive(True)
        self.cancelled_label.setVisible(cancelled)
        self.cancel_btn.setText("Вернуть в работу" if cancelled
                                else "Отменить заказ")

        self.received_label.setText(
            f"{format_money(money.received, False)} из "
            f"{format_money(money.price, False)}")
        self.money_bar.setStyleSheet(bar_style(payment_bar_color(money.state)))
        new_order = previous_id != order.id
        if new_order:
            self.money_bar.setValue(0)  # для нового заказа — рост с нуля
        animations.animate_value(self.money_bar, round(money.progress * 100))
        self.tax_label.setText(format_money(money.tax))
        self.net_label.setText(format_money(money.net))
        self.remaining_label.setText(format_money(money.remaining))

        self._fill_payments(manager.payments_for(order.id))

        when, tone = deadline_text(order, self.app.today())
        deadline = format_date(order.deadline) or "не задан"
        self.deadline_label.setText(
            f"Дедлайн: {deadline} · <span style='color:"
            f"{tone_color(tone)}'>{when}</span>")
        self.link_btn.setVisible(bool(order.link))
        self.link_btn.setToolTip(order.link)
        self.description.setText(order.description or "Описания нет")

        if new_order:
            animations.fade_in(self.content, shift=0)

    def _fill_payments(self, payments: list[Payment]) -> None:
        """Перестроить список платежей."""
        clear_layout(self.payments_box)
        if not payments:
            self.payments_box.addWidget(label(
                "Денег по заказу пока не было", "caption"))
            return
        for payment in payments:
            self.payments_box.addWidget(self._payment_row(payment))

    def _payment_row(self, payment: Payment) -> QWidget:
        row = QFrame()
        row.setStyleSheet(f"QFrame {{ border-top: 1px solid {C['border']}; }}"
                          " QLabel, QPushButton { border-top: none; }")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.addWidget(label(payment.paid_on.strftime("%d.%m.%Y"), "muted"))
        amount = label(format_money(payment.amount, False))
        amount.setStyleSheet("font-weight: 600; border-top: none;")
        layout.addWidget(amount)
        tax = self.app.manager.payment_tax(payment)
        layout.addWidget(label(f"налог {format_money(tax)}", "caption"))
        layout.addStretch(1)

        receipt = button("чек ✓" if payment.receipt_issued else "нет чека",
                         kind="receipt")
        receipt.setCheckable(True)
        receipt.setChecked(payment.receipt_issued)
        receipt.setToolTip("Отметить, выбит ли чек в «Мой налог»")
        receipt.clicked.connect(
            lambda _, pid=payment.id: self.page.toggle_receipt(pid))
        edit = button("", "pencil", "ghost")
        edit.setToolTip("Изменить платёж")
        edit.clicked.connect(
            lambda _, pid=payment.id: self.page.edit_payment(pid))
        delete = button("", "trash-2", "ghost")
        delete.setToolTip("Удалить платёж")
        delete.clicked.connect(
            lambda _, pid=payment.id: self.page.delete_payment(pid))
        for widget in (receipt, edit, delete):
            layout.addWidget(widget)
        return row


class OrdersPage(Page):
    """Экран «Заказы»."""

    def __init__(self, app) -> None:
        super().__init__(app, "Заказы")
        # «Липкий» заказ: остаётся в списке, даже если ушёл из фильтра
        self.pinned_id: int | None = None

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск: название, описание, клиент")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.addAction(icon("search"),
                                   QLineEdit.ActionPosition.LeadingPosition)
        self.search_edit.setMinimumWidth(280)
        self.search_edit.textChanged.connect(self._filters_changed)
        self.sort_combo = AnimatedComboBox()
        for key, text in SORTS.items():
            self.sort_combo.addItem(text, key)
        self.sort_combo.currentIndexChanged.connect(self.refresh)
        new_btn = button("Новый заказ", "plus", "primary", "#ffffff")
        new_btn.setToolTip("Ctrl+N")
        new_btn.clicked.connect(self.add_order)
        for widget in (self.search_edit, self.sort_combo, new_btn):
            self.header.addWidget(widget)

        # --- Фильтры-«таблетки» с числом заказов ---
        # Лента: одинаковый шаг, кнопки по ширине текста; если не
        # помещается — крутится колёсиком и тянется мышью
        self.chip_strip = FilterStrip(spacing=6)
        self.chip_group = QButtonGroup(self)
        self.chips: dict[object, object] = {}
        for key in list(VIEW_LABELS) + [CANCELLED_KEY]:
            chip_btn = button("", kind="chip")
            chip_btn.setCheckable(True)
            chip_btn.clicked.connect(self._filters_changed)
            self.chip_group.addButton(chip_btn)
            self.chips[key] = chip_btn
            self.chip_strip.add(chip_btn)
        self.chips[OrderView.ACTIVE].setChecked(True)
        self.layout_.addWidget(self.chip_strip)

        # --- Список и карточка, разделённые перетаскиваемой границей ---
        self.list = HintListWidget()
        self.list.setObjectName("orderList")
        self.list.currentItemChanged.connect(self._selection_changed)
        self.list.itemDoubleClicked.connect(self.edit_order)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._show_menu)

        self.panel = OrderPanel(self)
        panel_frame = QFrame()
        panel_frame.setObjectName("card")
        QVBoxLayout(panel_frame).addWidget(self.panel)
        panel_frame.layout().setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidget(panel_frame)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(360)
        SmoothScroller(scroll)

        splitter = QSplitter()
        splitter.addWidget(self.list)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setChildrenCollapsible(False)
        self.layout_.addWidget(splitter, 1)

    # ------------------------------------------------------------------
    # Фильтры и список
    # ------------------------------------------------------------------

    def current_filter_key(self):
        for key, chip_btn in self.chips.items():
            if chip_btn.isChecked():
                return key
        return OrderView.ALL

    def set_filter(self, key) -> None:
        self.chips[key].setChecked(True)
        self._filters_changed()

    def _filters_changed(self) -> None:
        """Сменили фильтр или поиск — «липкий» заказ больше не держим."""
        self.pinned_id = None
        self.refresh()

    def _orders(self) -> list[Order]:
        """Заказы по выбранному фильтру и поиску."""
        key = self.current_filter_key()
        manager = self.app.manager
        search = self.search_edit.text().strip()
        if key == CANCELLED_KEY:
            return manager.list_orders(OrderView.ALL, search,
                                       status=OrderStatus.CANCELLED,
                                       today=self.app.today())
        return manager.list_orders(key, search, today=self.app.today())

    def _sorted(self, orders: list[Order]) -> list[Order]:
        sort = self.sort_combo.currentData()
        if sort == "amount":
            return sorted(orders, key=lambda o: (-o.amount, -o.id))
        if sort == "new":
            return sorted(orders, key=lambda o: -o.id)
        # По сроку: сначала несданные с дедлайном (срочные сверху),
        # потом остальные — новые выше старых
        return sorted(orders, key=lambda o: (
            o.status not in OPEN_STATUSES or o.deadline is None,
            o.deadline or date.max, -o.id))

    def destination_label(self, order: Order) -> str:
        """Подпись фильтра, в котором теперь находится заказ."""
        if order.status == OrderStatus.CANCELLED:
            return "Отменённые"
        views = self.app.manager.order_views(order.id, self.app.today())
        for view in DESTINATION_ORDER:
            if view in views:
                return VIEW_LABELS[view]
        return VIEW_LABELS[OrderView.ALL]

    def destination_key(self, order: Order):
        """Ключ фильтра, в котором теперь находится заказ."""
        if order.status == OrderStatus.CANCELLED:
            return CANCELLED_KEY
        views = self.app.manager.order_views(order.id, self.app.today())
        return next((v for v in DESTINATION_ORDER if v in views),
                    OrderView.ALL)

    def refresh(self) -> None:
        today = self.app.today()
        manager = self.app.manager
        counts = manager.view_counts(today)
        cancelled = len(manager.list_orders(status=OrderStatus.CANCELLED,
                                            today=today))
        for key, chip_btn in self.chips.items():
            text = (f"Отменённые {cancelled}" if key == CANCELLED_KEY
                    else f"{VIEW_LABELS[key]} {counts[key]}")
            set_fitting_text(chip_btn, text)

        keep_id = self.selected_order_id()
        names = {c.id: c.name for c in manager.list_clients()}
        money = manager.money_all()
        orders = self._orders()
        visible = {o.id for o in orders}
        # «Липкий» заказ ушёл из фильтра — оставляем его в списке
        pinned = manager.get_order(self.pinned_id) if self.pinned_id else None
        if pinned is not None and pinned.id not in visible:
            orders.append(pinned)
        else:
            pinned = None

        # blockSignals — не дёргать карточку на каждой строке при заполнении
        self.list.blockSignals(True)
        self.list.clear()
        for order in self._sorted(orders):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, order.id)
            moved_to = (self.destination_label(order)
                        if pinned is not None and order.id == pinned.id
                        else "")
            row = OrderRow(order, names.get(order.client_id, "?"),
                           money[order.id], today, moved_to)
            item.setSizeHint(row.sizeHint())
            self.list.addItem(item)
            self.list.setItemWidget(item, row)
        # Пустой список рисует подсказку на фоне (HintListWidget)
        if self.search_edit.text().strip():
            self.list.empty_hint = ("Ничего не нашлось",
                                    "Попробуйте другое слово или фильтр")
        else:
            self.list.empty_hint = ("Здесь пусто",
                                    "Смените фильтр или создайте заказ")
        self.list.viewport().update()
        self.list.blockSignals(False)

        if keep_id is None or not self.select_order(keep_id):
            self.panel.show_order(None)

    def selected_order_id(self) -> int | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def select_order(self, order_id: int) -> bool:
        """Выделить заказ в списке; False — его нет в текущем фильтре."""
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == order_id:
                self.list.blockSignals(True)
                self.list.setCurrentItem(item)
                self.list.blockSignals(False)
                self.panel.show_order(order_id)
                return True
        return False

    def show_order(self, order_id: int) -> None:
        """Открыть заказ: если фильтр его прячет — показать «Все»."""
        if not self.select_order(order_id):
            self.search_edit.blockSignals(True)
            self.search_edit.clear()
            self.search_edit.blockSignals(False)
            self.set_filter(OrderView.ALL)
            self.select_order(order_id)

    def _selection_changed(self, current, _previous) -> None:
        order_id = current.data(Qt.ItemDataRole.UserRole) if current else None
        if order_id != self.pinned_id:
            # Выбрали другой заказ — «липкий» уйдёт при следующем обновлении
            self.pinned_id = None
        self.panel.show_order(order_id)

    def _show_menu(self, position) -> None:
        """Контекстное меню заказа (правая кнопка мыши)."""
        item = self.list.itemAt(position)
        if item is None or item.data(Qt.ItemDataRole.UserRole) is None:
            return
        self.list.setCurrentItem(item)
        order = self.app.manager.get_order(item.data(Qt.ItemDataRole.UserRole))
        menu = QMenu(self)
        menu.addAction(icon("pencil"), "Изменить…", self.edit_order)
        menu.addAction(icon("hand-coins"), "Добавить платёж…",
                       self.add_payment)
        status_menu = menu.addMenu("Статус работы")
        for status, text in STATUS_LABELS.items():
            action = status_menu.addAction(
                text, lambda status=status: self.set_status(status))
            action.setCheckable(True)
            action.setChecked(status == order.status)
        link = menu.addAction(icon("external-link"), "Открыть ссылку",
                              self.open_link)
        link.setEnabled(bool(order.link))
        menu.addSeparator()
        menu.addAction(icon("trash-2", C["danger_text"]), "Удалить",
                       self.delete_order)
        # exec — показать меню там, где щёлкнули (координаты — в экранные)
        menu.exec(self.list.viewport().mapToGlobal(position))

    # ------------------------------------------------------------------
    # Действия с заказом
    # ------------------------------------------------------------------

    def _need_order(self) -> int | None:
        order_id = self.selected_order_id()
        if order_id is None:
            self.app.show_error("Выберите заказ в списке.")
        return order_id

    def _change_selected(self, order_id: int, action, message: str) -> None:
        """Изменить выбранный заказ, не теряя его из списка.

        Заказ становится «липким». Если он ушёл из текущего фильтра,
        уведомление предлагает перейти туда, где он теперь.
        """
        self.pinned_id = order_id
        if not self.app.run(action):
            return
        order = self.app.manager.get_order(order_id)
        visible = {o.id for o in self._orders()}
        if order is not None and order_id not in visible:
            target = self.destination_key(order)
            self.app.notify(
                f"{message}. Заказ перешёл в «{self.destination_label(order)}»",
                "Показать", lambda: self._go_to(target, order_id))
        else:
            self.app.notify(message)

    def _go_to(self, key, order_id: int) -> None:
        """Переключить фильтр и выделить заказ."""
        self.set_filter(key)
        self.select_order(order_id)

    def add_order(self) -> None:
        clients = self.app.manager.list_clients()
        if not clients:
            self.app.show_error("Сначала добавьте клиента на экране "
                                "«Клиенты».")
            return
        dialog = OrderDialog(clients, parent=self, today=self.app.today())
        # exec() открывает окно и ждёт, пока его закроют
        if dialog.exec() == QDialog.DialogCode.Accepted:
            created = []
            if self.app.run(lambda: created.append(self.app.manager.add_order(
                    dialog.order(), today=self.app.today()))):
                self.show_order(created[0].id)
                self.app.notify("Заказ создан")

    def edit_order(self) -> None:
        order_id = self._need_order()
        if order_id is None:
            return
        manager = self.app.manager
        dialog = OrderDialog(manager.list_clients(),
                             manager.get_order(order_id), parent=self,
                             today=self.app.today())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._change_selected(
                order_id, lambda: manager.update_order(
                    dialog.order(), today=self.app.today()),
                "Заказ сохранён")

    def delete_order(self) -> None:
        order_id = self._need_order()
        if order_id is None:
            return
        payments = self.app.manager.payments_for(order_id)
        extra = (f"\nВместе с ним удалятся платежи: {len(payments)}."
                 if payments else "")
        if self.app.confirm(f"Удалить заказ?{extra}"):
            if self.app.run(lambda: self.app.manager.delete_order(order_id)):
                self.app.notify("Заказ удалён")

    def set_status(self, status: OrderStatus) -> None:
        order_id = self._need_order()
        if order_id is not None:
            self._change_selected(
                order_id, lambda: self.app.manager.change_status(
                    order_id, status, today=self.app.today()),
                f"Статус: {STATUS_LABELS[status]}")

    def toggle_cancel(self) -> None:
        """Отменить заказ или вернуть отменённый в работу."""
        order_id = self._need_order()
        if order_id is None:
            return
        order = self.app.manager.get_order(order_id)
        if order.status == OrderStatus.CANCELLED:
            self.set_status(OrderStatus.IN_PROGRESS)
        elif self.app.confirm("Отменить заказ? Платежи по нему останутся."):
            self.set_status(OrderStatus.CANCELLED)

    def open_link(self) -> None:
        order_id = self._need_order()
        if order_id is None:
            return
        link = self.app.manager.get_order(order_id).link
        if link:
            QDesktopServices.openUrl(QUrl(link))
        else:
            self.app.show_error("У заказа нет ссылки.")

    # ------------------------------------------------------------------
    # Платежи
    # ------------------------------------------------------------------

    def add_payment(self) -> None:
        order_id = self._need_order()
        if order_id is None:
            return
        remaining = self.app.manager.money(order_id).remaining
        dialog = PaymentDialog(order_id, remaining, parent=self,
                               today=self.app.today())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            payment = dialog.payment()
            self._change_selected(
                order_id, lambda: self.app.manager.add_payment(payment),
                f"Платёж {format_money(payment.amount, False)} добавлен")

    def edit_payment(self, payment_id: int) -> None:
        payment = self.app.manager.get_payment(payment_id)
        dialog = PaymentDialog(payment.order_id, payment=payment,
                               parent=self, today=self.app.today())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._change_selected(
                payment.order_id, lambda: self.app.manager.update_payment(
                    dialog.payment()), "Платёж сохранён")

    def delete_payment(self, payment_id: int) -> None:
        payment = self.app.manager.get_payment(payment_id)
        if self.app.confirm(
                f"Удалить платёж {format_money(payment.amount)} "
                f"от {format_date(payment.paid_on)}?"):
            self._change_selected(
                payment.order_id,
                lambda: self.app.manager.delete_payment(payment_id),
                "Платёж удалён")

    def toggle_receipt(self, payment_id: int) -> None:
        payment = self.app.manager.get_payment(payment_id)
        issued = not payment.receipt_issued
        self._change_selected(
            payment.order_id,
            lambda: self.app.manager.set_receipt(payment_id, issued),
            "Чек отмечен" if issued else "Отметка о чеке снята")
