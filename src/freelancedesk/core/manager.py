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
        return self._storage.list_clients()

    def delete_client(self, client_id: int) -> None:
        # Нельзя удалить клиента, у которого есть заказы
        if any(o.client_id == client_id for o in self._storage.list_orders()):
            raise ValueError("У клиента есть заказы — сначала удалите их")
        self._storage.delete_client(client_id)

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
    def _sync_paid_on(order: Order, today: date | None) -> None:
        """Согласовать дату оплаты со статусом.

        Оплачен, но даты нет — ставим сегодняшнюю (today можно передать
        явно, чтобы тесты не зависели от текущей даты).
        Не оплачен — даты оплаты быть не должно.
        """
        if order.status == OrderStatus.PAID:
            if order.paid_on is None:
                order.paid_on = today or date.today()
        else:
            order.paid_on = None

    def add_order(self, order: Order, today: date | None = None) -> Order:
        self._validate_order(order)
        self._sync_paid_on(order, today)
        return self._storage.add_order(order)

    def update_order(self, order: Order, today: date | None = None) -> None:
        self._validate_order(order)
        self._sync_paid_on(order, today)
        self._storage.update_order(order)

    def get_order(self, order_id: int) -> Order | None:
        return self._storage.get_order(order_id)

    def delete_order(self, order_id: int) -> None:
        self._storage.delete_order(order_id)

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
        # При повторной оплате дата обновляется на новую
        order.paid_on = None
        self._sync_paid_on(order, today)
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
