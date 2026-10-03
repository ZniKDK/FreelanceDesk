"""Модели данных: клиент, заказ, платёж и их перечисления.

Работа и оплата у заказа независимы:
- статус работы (новый → в работе → сдан) пользователь меняет сам;
- оплата складывается из платежей — сколько денег реально пришло.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


class ClientType(Enum):
    """Тип клиента. От него зависит ставка налога НПД."""

    PERSON = "person"    # физлицо — 4 %
    COMPANY = "company"  # юрлицо или ИП — 6 %


class ContactMethod(Enum):
    """Предпочтительный способ связи с клиентом."""

    EMAIL = "email"
    PHONE = "phone"
    MESSENGER = "messenger"


# Мессенджеры для выбора в форме клиента
MESSENGER_APPS = ["Telegram", "WhatsApp", "VK", "MAX", "Другой"]


class OrderStatus(Enum):
    """Статус работы по заказу (оплата сюда не входит)."""

    NEW = "new"
    IN_PROGRESS = "in_progress"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


# Работа ещё не сдана: только у таких заказов бывает просрочка
OPEN_STATUSES = (OrderStatus.NEW, OrderStatus.IN_PROGRESS)


@dataclass
class Client:
    """Клиент (заказчик)."""

    name: str
    client_type: ClientType = ClientType.PERSON
    email: str = ""
    phone: str = ""
    messenger: str = ""      # ник или номер: @ivan, +7 900…
    messenger_app: str = ""  # Telegram, WhatsApp, VK, MAX, Другой
    preferred_contact: ContactMethod | None = None  # как удобнее связаться
    platform: str = ""   # площадка: Kwork, FL.ru и т. п.
    note: str = ""
    id: int | None = None  # None, пока клиент не сохранён в хранилище


@dataclass
class Order:
    """Заказ от клиента."""

    title: str
    client_id: int
    amount: Decimal              # цена заказа — сколько ожидаем получить
    deadline: date | None = None
    status: OrderStatus = OrderStatus.NEW
    delivered_on: date | None = None  # когда сдан; ставится автоматически
    description: str = ""        # описание, ТЗ, заметки по заказу
    link: str = ""               # ссылка на заказ (Kwork, переписка, ТЗ)
    id: int | None = None

    def is_overdue(self, today: date) -> bool:
        """Дедлайн прошёл, а работа ещё не сдана."""
        if self.deadline is None:
            return False
        return self.status in OPEN_STATUSES and self.deadline < today

    def is_due_on(self, day: date) -> bool:
        """Срок сдачи — в этот день, и работа ещё не сдана."""
        return self.status in OPEN_STATUSES and self.deadline == day


@dataclass
class Payment:
    """Поступление денег по заказу.

    amount — сколько реально пришло (на Kwork — уже без комиссии
    площадки): именно с этой суммы платится налог НПД.
    """

    order_id: int
    amount: Decimal
    paid_on: date
    receipt_issued: bool = False  # чек выбит в «Мой налог»
    id: int | None = None
