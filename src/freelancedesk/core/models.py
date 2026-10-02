"""Модели данных: клиент, заказ и их перечисления."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


class ClientType(Enum):
    """Тип клиента. От него зависит ставка налога НПД."""

    PERSON = "person"    # физлицо — 4 %
    COMPANY = "company"  # юрлицо или ИП — 6 %


class OrderStatus(Enum):
    """Статус заказа."""

    NEW = "new"
    IN_PROGRESS = "in_progress"
    DELIVERED = "delivered"
    PAID = "paid"
    CANCELLED = "cancelled"


@dataclass
class Client:
    """Клиент (заказчик)."""

    name: str
    client_type: ClientType = ClientType.PERSON
    contact: str = ""
    platform: str = ""   # площадка: Kwork, FL.ru и т. п.
    note: str = ""
    id: int | None = None  # None, пока клиент не сохранён в хранилище


@dataclass
class Order:
    """Заказ от клиента."""

    title: str
    client_id: int
    amount: Decimal
    deadline: date | None = None
    status: OrderStatus = OrderStatus.NEW
    paid_on: date | None = None  # дата оплаты, заполняется при статусе PAID
    id: int | None = None

    def is_overdue(self, today: date) -> bool:
        """Дедлайн прошёл, а заказ ещё не сдан."""
        if self.deadline is None:
            return False
        open_statuses = (OrderStatus.NEW, OrderStatus.IN_PROGRESS)
        return self.status in open_statuses and self.deadline < today
