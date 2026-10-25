"""OrderManager — бизнес-логика: проверки, статусы, платежи, отчёты, налог.

Как считаются деньги:
- цена заказа — сколько ожидаем получить;
- платежи — сколько реально пришло (с датой и отметкой о чеке);
- налог НПД начисляется с каждого платежа по ставке клиента
  (4 % физлицо, 6 % юрлицо/ИП) и попадает в месяц даты платежа;
- «на руки» = пришло − налог; «осталось получить» = цена − пришло.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

from freelancedesk.core.models import (
    OPEN_STATUSES, Client, ClientType, Order, OrderStatus, Payment,
)
from freelancedesk.core.storage import Storage

# Ставки налога на профессиональный доход (НПД)
TAX_RATES = {
    ClientType.PERSON: Decimal("0.04"),
    ClientType.COMPANY: Decimal("0.06"),
}

# Налог за месяц платится до этого числа следующего месяца
TAX_PAYMENT_DAY = 28

# Подпись для клиентов без указанной площадки в отчёте «по площадкам»
NO_PLATFORM = "Без площадки"

ZERO = Decimal("0")
CENT = Decimal("0.01")


def round_money(value: Decimal) -> Decimal:
    """Округлить до копеек по правилам математики (0,005 → 0,01)."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


class PaymentState(Enum):
    """Состояние оплаты заказа — вычисляется по платежам."""

    UNPAID = "unpaid"
    PARTIAL = "partial"
    PAID = "paid"


class OrderView(Enum):
    """Готовые выборки заказов."""

    ACTIVE = "active"                  # в работе или ждёт оплаты
    AWAITING_PAYMENT = "awaiting"      # сдан, но деньги пришли не все
    OVERDUE = "overdue"                # срок прошёл, не сдан
    DUE_TODAY = "due_today"            # сдать сегодня
    NO_RECEIPT = "no_receipt"          # есть платёж без чека
    DONE = "done"                      # сдан и оплачен
    ALL = "all"                        # все заказы


@dataclass(frozen=True)
class OrderMoney:
    """Деньги по одному заказу."""

    price: Decimal          # цена заказа
    received: Decimal       # сколько пришло
    tax: Decimal            # налог с пришедших денег
    without_receipt: int    # платежей без чека

    @property
    def remaining(self) -> Decimal:
        """Сколько ещё должны (переплата не делает долг отрицательным)."""
        return max(self.price - self.received, ZERO)

    @property
    def net(self) -> Decimal:
        """Сколько остаётся после налога."""
        return self.received - self.tax

    @property
    def state(self) -> PaymentState:
        if self.received <= 0:
            return PaymentState.UNPAID
        if self.received >= self.price:
            return PaymentState.PAID
        return PaymentState.PARTIAL

    @property
    def progress(self) -> float:
        """Доля оплаты от 0 до 1 (для полоски прогресса)."""
        if self.price <= 0:
            return 1.0 if self.received > 0 else 0.0
        return min(float(self.received / self.price), 1.0)


@dataclass(frozen=True)
class PeriodSummary:
    """Итоги за период: сколько пришло, налог и на руки."""

    income: Decimal
    tax: Decimal
    payments: int = 0

    @property
    def net(self) -> Decimal:
        return self.income - self.tax


@dataclass(frozen=True)
class Attention:
    """Сколько заказов требуют внимания прямо сейчас."""

    due_today: int
    overdue: int
    no_receipt: int

    @property
    def total(self) -> int:
        return self.due_today + self.overdue + self.no_receipt


@dataclass(frozen=True)
class Awaiting:
    """Сданные, но не оплаченные полностью заказы."""

    orders: int
    amount: Decimal


@dataclass(frozen=True)
class TaxDue:
    """Налог за прошлый месяц и срок его уплаты."""

    month: date      # первое число месяца, за который платим
    amount: Decimal
    due_date: date   # крайний срок уплаты


@dataclass(frozen=True)
class ClientStats:
    """Сводка по клиенту: сколько заказов и сколько денег пришло."""

    orders: int
    income: Decimal


def month_start(day: date) -> date:
    """Первое число месяца, в котором находится day."""
    return day.replace(day=1)


def add_months(first_day: date, months: int) -> date:
    """Сдвинуть первое число месяца на months месяцев (можно назад)."""
    # Считаем месяцы «сквозным» номером: год * 12 + (месяц - 1)
    index = first_day.year * 12 + first_day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def month_end(first_day: date) -> date:
    """Последний день месяца: первое число следующего минус один день."""
    return add_months(first_day, 1) - timedelta(days=1)


class OrderManager:
    """Посредник между интерфейсом и хранилищем."""

    def __init__(self, storage: Storage) -> None:
        # Хранилище передаётся снаружи: SqliteStorage, DbStorage или
        # InMemoryStorage. Менеджеру всё равно, какое именно.
        self._storage = storage

    # ------------------------------------------------------------------
    # Клиенты
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_client(client: Client) -> None:
        if not client.name.strip():
            raise ValueError("Имя клиента не может быть пустым")

    def add_client(self, client: Client) -> Client:
        self._validate_client(client)
        return self._storage.add_client(client)

    def update_client(self, client: Client) -> None:
        self._validate_client(client)
        self._storage.update_client(client)

    def get_client(self, client_id: int) -> Client | None:
        return self._storage.get_client(client_id)

    def list_clients(self) -> list[Client]:
        """Клиенты по алфавиту. casefold() — сравнение без учёта регистра,
        работает и для кириллицы (в отличие от NOCASE в SQLite)."""
        return sorted(self._storage.list_clients(),
                      key=lambda c: c.name.casefold())

    def delete_client(self, client_id: int) -> None:
        # Нельзя удалить клиента, у которого есть заказы
        if any(o.client_id == client_id for o in self._storage.list_orders()):
            raise ValueError("У клиента есть заказы — сначала удалите их")
        self._storage.delete_client(client_id)

    def client_stats(self) -> dict[int, ClientStats]:
        """Число заказов и пришедшие деньги по каждому клиенту."""
        orders = self._storage.list_orders()
        client_of = {o.id: o.client_id for o in orders}
        counts: dict[int, int] = {}
        for order in orders:
            counts[order.client_id] = counts.get(order.client_id, 0) + 1
        income: dict[int, Decimal] = {}
        for payment in self._storage.list_payments():
            cid = client_of.get(payment.order_id)
            income[cid] = income.get(cid, ZERO) + payment.amount
        return {cid: ClientStats(counts[cid], income.get(cid, ZERO))
                for cid in counts}

    # ------------------------------------------------------------------
    # Заказы
    # ------------------------------------------------------------------

    def _validate_order(self, order: Order) -> None:
        """Общие проверки для создания и изменения заказа."""
        if not order.title.strip():
            raise ValueError("Название заказа не может быть пустым")
        if order.amount < 0:
            raise ValueError("Цена заказа не может быть отрицательной")
        if self._storage.get_client(order.client_id) is None:
            raise ValueError(f"Клиент {order.client_id} не найден")

    @staticmethod
    def _normalize(order: Order, today: date | None) -> None:
        """Привести поля заказа в согласованное состояние.

        - Сдан, но даты сдачи нет — ставим сегодняшнюю (today можно
          передать явно, чтобы тесты не зависели от текущей даты).
        - Вернули в работу — даты сдачи больше нет.
        - Ссылка без http(s):// — дописываем https://, чтобы её можно
          было открыть в браузере.
        """
        if order.status == OrderStatus.DELIVERED:
            if order.delivered_on is None:
                order.delivered_on = today or date.today()
        elif order.status in OPEN_STATUSES:
            order.delivered_on = None
        order.link = order.link.strip()
        if order.link and "://" not in order.link:
            order.link = "https://" + order.link

    def add_order(self, order: Order, today: date | None = None) -> Order:
        self._validate_order(order)
        self._normalize(order, today)
        return self._storage.add_order(order)

    def update_order(self, order: Order, today: date | None = None) -> None:
        self._validate_order(order)
        self._normalize(order, today)
        self._storage.update_order(order)

    def get_order(self, order_id: int) -> Order | None:
        return self._storage.get_order(order_id)

    def delete_order(self, order_id: int) -> None:
        """Удалить заказ вместе с его платежами."""
        self._storage.delete_order(order_id)

    def _existing_order(self, order_id: int) -> Order:
        order = self._storage.get_order(order_id)
        if order is None:
            raise ValueError(f"Заказ {order_id} не найден")
        return order

    def change_status(self, order_id: int, status: OrderStatus,
                      today: date | None = None) -> Order:
        """Сменить статус работы. При сдаче ставится сегодняшняя дата."""
        order = self._existing_order(order_id)
        if order.status == status:
            return order  # ничего не меняется — дату сдачи не трогаем
        order.status = status
        order.delivered_on = None
        self._normalize(order, today)
        self._storage.update_order(order)
        return order

    # ------------------------------------------------------------------
    # Платежи
    # ------------------------------------------------------------------

    def _validate_payment(self, payment: Payment) -> None:
        if payment.amount <= 0:
            raise ValueError("Сумма платежа должна быть больше нуля")
        self._existing_order(payment.order_id)

    def add_payment(self, payment: Payment) -> Payment:
        self._validate_payment(payment)
        return self._storage.add_payment(payment)

    def update_payment(self, payment: Payment) -> None:
        self._validate_payment(payment)
        self._storage.update_payment(payment)

    def delete_payment(self, payment_id: int) -> None:
        self._storage.delete_payment(payment_id)

    def get_payment(self, payment_id: int) -> Payment | None:
        return self._storage.get_payment(payment_id)

    def set_receipt(self, payment_id: int, issued: bool = True) -> Payment:
        """Отметить, что чек по платежу выбит в «Мой налог»."""
        payment = self._storage.get_payment(payment_id)
        if payment is None:
            raise ValueError(f"Платёж {payment_id} не найден")
        payment.receipt_issued = issued
        self._storage.update_payment(payment)
        return payment

    def payments_for(self, order_id: int) -> list[Payment]:
        """Платежи заказа по дате."""
        return [p for p in self._storage.list_payments()
                if p.order_id == order_id]

    def payments_in_period(self, start: date, end: date) -> list[Payment]:
        """Все платежи с датой в периоде (включительно), по дате."""
        return [p for p in self._storage.list_payments()
                if start <= p.paid_on <= end]

    def _rates_by_order(self) -> dict[int, Decimal]:
        """Ставка налога для каждого заказа (по типу его клиента)."""
        types = {c.id: c.client_type for c in self._storage.list_clients()}
        return {o.id: TAX_RATES[types.get(o.client_id, ClientType.PERSON)]
                for o in self._storage.list_orders()}

    def payment_tax(self, payment: Payment) -> Decimal:
        """Налог с одного платежа, округлённый до копеек."""
        rate = self._rates_by_order().get(payment.order_id,
                                          TAX_RATES[ClientType.PERSON])
        return round_money(payment.amount * rate)

    def money_all(self) -> dict[int, OrderMoney]:
        """Деньги по всем заказам сразу — один проход по платежам."""
        rates = self._rates_by_order()
        received: dict[int, Decimal] = {}
        tax: dict[int, Decimal] = {}
        no_receipt: dict[int, int] = {}
        for p in self._storage.list_payments():
            received[p.order_id] = received.get(p.order_id, ZERO) + p.amount
            tax[p.order_id] = (tax.get(p.order_id, ZERO)
                               + p.amount * rates.get(p.order_id, ZERO))
            if not p.receipt_issued:
                no_receipt[p.order_id] = no_receipt.get(p.order_id, 0) + 1
        return {
            o.id: OrderMoney(price=o.amount,
                             received=received.get(o.id, ZERO),
                             tax=round_money(tax.get(o.id, ZERO)),
                             without_receipt=no_receipt.get(o.id, 0))
            for o in self._storage.list_orders()
        }

    def money(self, order_id: int) -> OrderMoney:
        """Деньги по одному заказу."""
        return self.money_all()[order_id]

    # ------------------------------------------------------------------
    # Выборки
    # ------------------------------------------------------------------

    @staticmethod
    def _matches(view: OrderView, order: Order, money: OrderMoney,
                 today: date) -> bool:
        """Подходит ли заказ под выборку."""
        unpaid = money.state != PaymentState.PAID
        if view == OrderView.ACTIVE:
            return (order.status in OPEN_STATUSES
                    or (order.status == OrderStatus.DELIVERED and unpaid))
        if view == OrderView.AWAITING_PAYMENT:
            return order.status == OrderStatus.DELIVERED and unpaid
        if view == OrderView.OVERDUE:
            return order.is_overdue(today)
        if view == OrderView.DUE_TODAY:
            return order.is_due_on(today)
        if view == OrderView.NO_RECEIPT:
            return money.without_receipt > 0
        if view == OrderView.DONE:
            return order.status == OrderStatus.DELIVERED and not unpaid
        return True  # ALL

    def list_orders(self, view: OrderView = OrderView.ALL, search: str = "",
                    status: OrderStatus | None = None,
                    today: date | None = None) -> list[Order]:
        """Заказы с фильтрами.

        view — готовая выборка; status — только один статус работы;
        search — поиск по названию, описанию и имени клиента без учёта
        регистра.
        """
        today = today or date.today()
        money = self.money_all()
        orders = [o for o in self._storage.list_orders()
                  if self._matches(view, o, money[o.id], today)]
        if status is not None:
            orders = [o for o in orders if o.status == status]
        if search:
            needle = search.casefold()
            names = {c.id: c.name for c in self._storage.list_clients()}
            orders = [
                o for o in orders
                if needle in o.title.casefold()
                or needle in o.description.casefold()
                or needle in names.get(o.client_id, "").casefold()
            ]
        return orders

    def view_counts(self, today: date) -> dict[OrderView, int]:
        """Сколько заказов в каждой выборке (для подписей фильтров)."""
        money = self.money_all()
        orders = self._storage.list_orders()
        return {view: sum(self._matches(view, o, money[o.id], today)
                          for o in orders)
                for view in OrderView}

    def order_views(self, order_id: int, today: date) -> list[OrderView]:
        """В каких выборках сейчас находится заказ (кроме «Все»)."""
        order = self._existing_order(order_id)
        money = self.money(order_id)
        return [view for view in OrderView if view != OrderView.ALL
                and self._matches(view, order, money, today)]

    def attention(self, today: date) -> Attention:
        """Что горит: сдать сегодня, просрочено, платежи без чека."""
        counts = self.view_counts(today)
        return Attention(due_today=counts[OrderView.DUE_TODAY],
                         overdue=counts[OrderView.OVERDUE],
                         no_receipt=counts[OrderView.NO_RECEIPT])

    def awaiting_payment(self) -> Awaiting:
        """Сколько денег ждём за уже сданную работу."""
        money = self.money_all()
        waiting = [money[o.id] for o in self._storage.list_orders()
                   if o.status == OrderStatus.DELIVERED
                   and money[o.id].state != PaymentState.PAID]
        return Awaiting(orders=len(waiting),
                        amount=sum((m.remaining for m in waiting), ZERO))

    def upcoming(self, today: date, limit: int = 5) -> list[Order]:
        """Ближайшие сроки: несданные заказы, начиная с просроченных."""
        orders = [o for o in self._storage.list_orders()
                  if o.status in OPEN_STATUSES and o.deadline is not None]
        return sorted(orders, key=lambda o: o.deadline)[:limit]

    # ------------------------------------------------------------------
    # Отчёты
    # ------------------------------------------------------------------

    def summary(self, start: date, end: date) -> PeriodSummary:
        """Сколько пришло за период, налог и на руки."""
        rates = self._rates_by_order()
        payments = self.payments_in_period(start, end)
        income = sum((p.amount for p in payments), ZERO)
        tax = sum((p.amount * rates.get(p.order_id, ZERO) for p in payments),
                  ZERO)
        return PeriodSummary(income=income, tax=round_money(tax),
                             payments=len(payments))

    def income_by_month(self, today: date,
                        months: int = 12) -> list[tuple[date, Decimal]]:
        """Поступления по месяцам за последние months месяцев, включая
        текущий. Список (первое число месяца, сумма) от старых к новым."""
        first = add_months(month_start(today), -(months - 1))
        totals = {add_months(first, i): ZERO for i in range(months)}
        last = month_end(month_start(today))
        for payment in self.payments_in_period(first, last):
            totals[month_start(payment.paid_on)] += payment.amount
        return list(totals.items())

    def income_by_platform(self, start: date,
                           end: date) -> list[tuple[str, Decimal]]:
        """Поступления за период по площадкам, от большего к меньшему."""
        platforms = {c.id: c.platform.strip() or NO_PLATFORM
                     for c in self._storage.list_clients()}
        client_of = {o.id: o.client_id for o in self._storage.list_orders()}
        totals: dict[str, Decimal] = {}
        for payment in self.payments_in_period(start, end):
            name = platforms.get(client_of.get(payment.order_id), NO_PLATFORM)
            totals[name] = totals.get(name, ZERO) + payment.amount
        return sorted(totals.items(), key=lambda item: item[1], reverse=True)

    def tax_due(self, today: date) -> TaxDue:
        """Налог за прошлый месяц: его нужно заплатить до 28-го числа
        текущего месяца."""
        this_month = month_start(today)
        last_month = add_months(this_month, -1)
        tax = self.summary(last_month, month_end(last_month)).tax
        return TaxDue(month=last_month, amount=tax,
                      due_date=this_month.replace(day=TAX_PAYMENT_DAY))
