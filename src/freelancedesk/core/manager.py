"""OrderManager — бизнес-логика: проверки, смена статусов, доход и налог."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from freelancedesk.core.models import Client, ClientType, Order, OrderStatus
from freelancedesk.core.storage import Storage

# Ставки налога на профессиональный доход (НПД)
TAX_RATES = {
    ClientType.PERSON: Decimal("0.04"),
    ClientType.COMPANY: Decimal("0.06"),
}


@dataclass(frozen=True)
class PeriodSummary:
    """Итоги за период: доход, налог и доход после налога."""

    income: Decimal
    tax: Decimal

    @property
    def net(self) -> Decimal:
        return self.income - self.tax


class OrderManager:
    """Посредник между интерфейсом и хранилищем."""

    def __init__(self, storage: Storage) -> None:
        # Хранилище передаётся снаружи: в программе — DbStorage,
        # в тестах — InMemoryStorage. Менеджеру всё равно, какое именно.
        self._storage = storage

    # --- Клиенты ---

    def add_client(self, client: Client) -> Client:
        if not client.name.strip():
            raise ValueError("Имя клиента не может быть пустым")
        return self._storage.add_client(client)

    def list_clients(self) -> list[Client]:
        return self._storage.list_clients()

    def delete_client(self, client_id: int) -> None:
        # Нельзя удалить клиента, у которого есть заказы
        if any(o.client_id == client_id for o in self._storage.list_orders()):
            raise ValueError("У клиента есть заказы — сначала удалите их")
        self._storage.delete_client(client_id)

    # --- Заказы ---

    def add_order(self, order: Order) -> Order:
        if not order.title.strip():
            raise ValueError("Название заказа не может быть пустым")
        if order.amount < 0:
            raise ValueError("Сумма заказа не может быть отрицательной")
        if self._storage.get_client(order.client_id) is None:
            raise ValueError(f"Клиент {order.client_id} не найден")
        return self._storage.add_order(order)

    def list_orders(self, status: OrderStatus | None = None,
                    search: str = "") -> list[Order]:
        """Заказы с фильтром по статусу и поиском по названию."""
        orders = self._storage.list_orders()
        if status is not None:
            orders = [o for o in orders if o.status == status]
        if search:
            needle = search.lower()
            orders = [o for o in orders if needle in o.title.lower()]
        return orders

    def change_status(self, order_id: int, status: OrderStatus,
                      today: date | None = None) -> Order:
        """Сменить статус. При оплате проставляется дата оплаты."""
        order = self._storage.get_order(order_id)
        if order is None:
            raise ValueError(f"Заказ {order_id} не найден")
        order.status = status
        if status == OrderStatus.PAID:
            # today можно передать явно — так тесты не зависят от текущей даты
            order.paid_on = today or date.today()
        else:
            # Ушёл из «оплачен» — дата оплаты больше не актуальна
            order.paid_on = None
        self._storage.update_order(order)
        return order

    def overdue_orders(self, today: date) -> list[Order]:
        return [o for o in self._storage.list_orders() if o.is_overdue(today)]

    # --- Отчёты ---

    def summary(self, start: date, end: date) -> PeriodSummary:
        """Доход и налог по оплаченным заказам за период (включительно)."""
        income = Decimal("0")
        tax = Decimal("0")
        for order in self._storage.list_orders():
            if order.status != OrderStatus.PAID or order.paid_on is None:
                continue
            if not start <= order.paid_on <= end:
                continue
            # Ставка зависит от того, кто платит: физлицо или юрлицо/ИП
            client = self._storage.get_client(order.client_id)
            client_type = client.client_type if client else ClientType.PERSON
            income += order.amount
            tax += order.amount * TAX_RATES[client_type]
        # Налог округляем до копеек
        tax = tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return PeriodSummary(income=income, tax=tax)
