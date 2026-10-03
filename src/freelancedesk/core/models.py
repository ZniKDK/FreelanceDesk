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


# Заказ «в работе», пока его не сдали: только у таких бывает просрочка
OPEN_STATUSES = (OrderStatus.NEW, OrderStatus.IN_PROGRESS)
# Активные — всё, что ещё не закрыто оплатой или отменой
ACTIVE_STATUSES = (OrderStatus.NEW, OrderStatus.IN_PROGRESS,
                   OrderStatus.DELIVERED)


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
    description: str = ""        # описание, ТЗ, заметки по заказу
    link: str = ""               # ссылка на заказ (Kwork, переписка, ТЗ)
    receipt_issued: bool = False  # чек выбит в «Мой налог»
    id: int | None = None

    def is_overdue(self, today: date) -> bool:
        """Дедлайн прошёл, а заказ ещё не сдан."""
        if self.deadline is None:
            return False
        return self.status in OPEN_STATUSES and self.deadline < today

    def is_due_on(self, day: date) -> bool:
        """Срок сдачи — в этот день, и заказ ещё не сдан."""
        return self.status in OPEN_STATUSES and self.deadline == day

    def needs_receipt(self) -> bool:
        """Оплачен, но чек в «Мой налог» ещё не выбит.

        По закону о НПД чек нужно сформировать при каждой оплате —
        это легко забыть, поэтому программа напоминает.
        """
        return self.status == OrderStatus.PAID and not self.receipt_issued
