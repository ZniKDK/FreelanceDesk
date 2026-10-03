"""OrderManager — бизнес-логика: проверки, статусы, отчёты и налог НПД."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

from freelancedesk.core.models import (
    ACTIVE_STATUSES, Client, ClientType, Order, OrderStatus,
)
from freelancedesk.core.storage import Storage

# Ставки налога на профессиональный доход (НПД)
TAX_RATES = {
    ClientType.PERSON: Decimal("0.04"),
    ClientType.COMPANY: Decimal("0.06"),
}

# Налог за месяц платится до этого числа следующего месяца (422-ФЗ, ст. 11)
TAX_PAYMENT_DAY = 28

# Подпись для клиентов без указанной площадки в отчёте «по площадкам»
NO_PLATFORM = "Без площадки"


class OrderView(Enum):
    """Готовые выборки заказов (помимо фильтра по одному статусу)."""

    ALL = "all"                # все заказы
    ACTIVE = "active"          # не оплачены и не отменены
    OVERDUE = "overdue"        # срок прошёл, не сдан
    DUE_TODAY = "due_today"    # сдать сегодня
    NO_RECEIPT = "no_receipt"  # оплачен, а чек не выбит


@dataclass(frozen=True)
class PeriodSummary:
    """Итоги за период: доход, налог и доход после налога."""

    income: Decimal
    tax: Decimal

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
class TaxDue:
    """Налог за прошлый месяц и срок его уплаты."""

    month: date      # первое число месяца, за который платим
    amount: Decimal
    due_date: date   # крайний срок уплаты


@dataclass(frozen=True)
class ClientStats:
    """Сводка по клиенту: сколько заказов и сколько он заплатил."""

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

    # --- Клиенты ---

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
        """Число заказов и оплаченная сумма по каждому клиенту."""
        counts: dict[int, int] = {}
        income: dict[int, Decimal] = {}
        for order in self._storage.list_orders():
            counts[order.client_id] = counts.get(order.client_id, 0) + 1
            if order.status == OrderStatus.PAID:
                income[order.client_id] = (income.get(order.client_id,
                                                      Decimal("0"))
                                           + order.amount)
        return {cid: ClientStats(counts[cid], income.get(cid, Decimal("0")))
                for cid in counts}

    # --- Заказы ---

    def _validate_order(self, order: Order) -> None:
        """Общие проверки для создания и изменения заказа."""
        if not order.title.strip():
            raise ValueError("Название заказа не может быть пустым")
        if order.amount < 0:
            raise ValueError("Сумма заказа не может быть отрицательной")
        if self._storage.get_client(order.client_id) is None:
            raise ValueError(f"Клиент {order.client_id} не найден")

    @staticmethod
    def _normalize(order: Order, today: date | None) -> None:
        """Привести поля заказа в согласованное состояние.

        - Оплачен, но даты нет — ставим сегодняшнюю (today можно передать
          явно, чтобы тесты не зависели от текущей даты).
        - Не оплачен — нет ни даты оплаты, ни чека.
        - Ссылка без http(s):// — дописываем https://, чтобы её можно
          было открыть в браузере.
        """
        if order.status == OrderStatus.PAID:
            if order.paid_on is None:
                order.paid_on = today or date.today()
        else:
            order.paid_on = None
            order.receipt_issued = False
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
        self._storage.delete_order(order_id)

    def _get_existing_order(self, order_id: int) -> Order:
        order = self._storage.get_order(order_id)
        if order is None:
            raise ValueError(f"Заказ {order_id} не найден")
        return order

    def change_status(self, order_id: int, status: OrderStatus,
                      today: date | None = None) -> Order:
        """Сменить статус. При оплате проставляется сегодняшняя дата."""
        order = self._get_existing_order(order_id)
        if order.status == status:
            return order  # ничего не меняется — дату оплаты не трогаем
        order.status = status
        order.paid_on = None  # при новой оплате дата — сегодняшняя
        self._normalize(order, today)
        self._storage.update_order(order)
        return order

    def set_receipt(self, order_id: int, issued: bool = True) -> Order:
        """Отметить, что чек в «Мой налог» выбит (или снять отметку)."""
        order = self._get_existing_order(order_id)
        if issued and order.status != OrderStatus.PAID:
            raise ValueError("Чек выбивается только по оплаченному заказу")
        order.receipt_issued = issued
        self._storage.update_order(order)
        return order

    def list_orders(self, status: OrderStatus | None = None,
                    search: str = "", view: OrderView = OrderView.ALL,
                    today: date | None = None) -> list[Order]:
        """Заказы с фильтрами.

        status — только один статус; view — готовая выборка (активные,
        просроченные...); search — поиск по названию, описанию и имени
        клиента без учёта регистра.
        """
        today = today or date.today()
        orders = self._storage.list_orders()
        if status is not None:
            orders = [o for o in orders if o.status == status]

        # Словарь «выборка -> условие»: каждое условие — функция от заказа
        conditions = {
            OrderView.ALL: lambda o: True,
            OrderView.ACTIVE: lambda o: o.status in ACTIVE_STATUSES,
            OrderView.OVERDUE: lambda o: o.is_overdue(today),
            OrderView.DUE_TODAY: lambda o: o.is_due_on(today),
            OrderView.NO_RECEIPT: lambda o: o.needs_receipt(),
        }
        orders = [o for o in orders if conditions[view](o)]

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

    def overdue_orders(self, today: date) -> list[Order]:
        return [o for o in self._storage.list_orders() if o.is_overdue(today)]

    def attention(self, today: date) -> Attention:
        """Что горит: сдать сегодня, просрочено, оплачено без чека."""
        orders = self._storage.list_orders()
        return Attention(
            due_today=sum(o.is_due_on(today) for o in orders),
            overdue=sum(o.is_overdue(today) for o in orders),
            no_receipt=sum(o.needs_receipt() for o in orders),
        )

    # --- Отчёты ---

    def _paid_in_period(self, start: date, end: date) -> list[Order]:
        """Оплаченные заказы с датой оплаты в периоде (включительно)."""
        return [o for o in self._storage.list_orders()
                if o.status == OrderStatus.PAID and o.paid_on is not None
                and start <= o.paid_on <= end]

    def summary(self, start: date, end: date) -> PeriodSummary:
        """Доход и налог по оплаченным заказам за период."""
        # Один запрос клиентов на весь отчёт, а не на каждый заказ
        types = {c.id: c.client_type for c in self._storage.list_clients()}
        income = Decimal("0")
        tax = Decimal("0")
        for order in self._paid_in_period(start, end):
            # Ставка зависит от того, кто платит: физлицо или юрлицо/ИП
            client_type = types.get(order.client_id, ClientType.PERSON)
            income += order.amount
            tax += order.amount * TAX_RATES[client_type]
        # Налог округляем до копеек
        tax = tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return PeriodSummary(income=income, tax=tax)

    def income_by_month(self, today: date,
                        months: int = 12) -> list[tuple[date, Decimal]]:
        """Доход по месяцам за последние months месяцев, включая текущий.

        Возвращает список (первое число месяца, доход) от старых к новым.
        """
        first = add_months(month_start(today), -(months - 1))
        totals = {add_months(first, i): Decimal("0") for i in range(months)}
        for order in self._paid_in_period(first, month_end(month_start(today))):
            totals[month_start(order.paid_on)] += order.amount
        return list(totals.items())

    def income_by_platform(self, start: date,
                           end: date) -> list[tuple[str, Decimal]]:
        """Доход за период по площадкам клиентов, от большего к меньшему."""
        platforms = {c.id: c.platform.strip() or NO_PLATFORM
                     for c in self._storage.list_clients()}
        totals: dict[str, Decimal] = {}
        for order in self._paid_in_period(start, end):
            name = platforms.get(order.client_id, NO_PLATFORM)
            totals[name] = totals.get(name, Decimal("0")) + order.amount
        return sorted(totals.items(), key=lambda item: item[1], reverse=True)

    def tax_due(self, today: date) -> TaxDue:
        """Налог за прошлый месяц: его нужно заплатить до 28-го числа
        текущего месяца."""
        this_month = month_start(today)
        last_month = add_months(this_month, -1)
        tax = self.summary(last_month, month_end(last_month)).tax
        return TaxDue(month=last_month, amount=tax,
                      due_date=this_month.replace(day=TAX_PAYMENT_DAY))
