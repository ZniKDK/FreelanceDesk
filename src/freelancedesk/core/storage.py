"""Хранилища данных.

Storage — интерфейс, с которым работает OrderManager.
InMemoryStorage — хранилище в памяти (для тестов и запуска без БД).
SQL-хранилища (PostgreSQL, SQLite) — в модуле sql_storage.
"""

from abc import ABC, abstractmethod
from dataclasses import replace

from freelancedesk.core.models import Client, Order, Payment


class Storage(ABC):
    """Общий интерфейс хранилища клиентов, заказов и платежей."""

    # --- Клиенты ---

    @abstractmethod
    def add_client(self, client: Client) -> Client:
        """Сохранить нового клиента и вернуть его с присвоенным id."""

    @abstractmethod
    def update_client(self, client: Client) -> None:
        """Обновить существующего клиента."""

    @abstractmethod
    def delete_client(self, client_id: int) -> None:
        """Удалить клиента."""

    @abstractmethod
    def get_client(self, client_id: int) -> Client | None:
        """Найти клиента по id."""

    @abstractmethod
    def list_clients(self) -> list[Client]:
        """Все клиенты."""

    # --- Заказы ---

    @abstractmethod
    def add_order(self, order: Order) -> Order:
        """Сохранить новый заказ и вернуть его с присвоенным id."""

    @abstractmethod
    def update_order(self, order: Order) -> None:
        """Обновить существующий заказ."""

    @abstractmethod
    def delete_order(self, order_id: int) -> None:
        """Удалить заказ вместе с его платежами."""

    @abstractmethod
    def get_order(self, order_id: int) -> Order | None:
        """Найти заказ по id."""

    @abstractmethod
    def list_orders(self) -> list[Order]:
        """Все заказы."""

    # --- Платежи ---

    @abstractmethod
    def add_payment(self, payment: Payment) -> Payment:
        """Сохранить платёж и вернуть его с присвоенным id."""

    @abstractmethod
    def update_payment(self, payment: Payment) -> None:
        """Обновить существующий платёж."""

    @abstractmethod
    def delete_payment(self, payment_id: int) -> None:
        """Удалить платёж."""

    @abstractmethod
    def get_payment(self, payment_id: int) -> Payment | None:
        """Найти платёж по id."""

    @abstractmethod
    def list_payments(self) -> list[Payment]:
        """Все платежи по дате поступления."""


class InMemoryStorage(Storage):
    """Хранилище в оперативной памяти. Данные пропадают при выходе."""

    def __init__(self) -> None:
        # Словари «id → объект» имитируют таблицы БД
        self._clients: dict[int, Client] = {}
        self._orders: dict[int, Order] = {}
        self._payments: dict[int, Payment] = {}
        # Счётчики id — аналог SERIAL в PostgreSQL
        self._next_id = {"client": 1, "order": 1, "payment": 1}

    def _take_id(self, kind: str) -> int:
        """Выдать следующий свободный id для таблицы kind."""
        new_id = self._next_id[kind]
        self._next_id[kind] += 1
        return new_id

    # --- Клиенты ---

    def add_client(self, client: Client) -> Client:
        # replace() создаёт копию с новым id — исходный объект не меняется
        saved = replace(client, id=self._take_id("client"))
        self._clients[saved.id] = saved
        return saved

    def update_client(self, client: Client) -> None:
        if client.id not in self._clients:
            raise KeyError(f"Клиент {client.id} не найден")
        self._clients[client.id] = client

    def delete_client(self, client_id: int) -> None:
        # pop с None по умолчанию: удаление несуществующего id — не ошибка
        self._clients.pop(client_id, None)

    def get_client(self, client_id: int) -> Client | None:
        return self._clients.get(client_id)

    def list_clients(self) -> list[Client]:
        return list(self._clients.values())

    # --- Заказы ---

    def add_order(self, order: Order) -> Order:
        saved = replace(order, id=self._take_id("order"))
        self._orders[saved.id] = saved
        return saved

    def update_order(self, order: Order) -> None:
        if order.id not in self._orders:
            raise KeyError(f"Заказ {order.id} не найден")
        self._orders[order.id] = order

    def delete_order(self, order_id: int) -> None:
        # Сначала платежи заказа — как внешний ключ в настоящей БД
        self._payments = {pid: p for pid, p in self._payments.items()
                          if p.order_id != order_id}
        self._orders.pop(order_id, None)

    def get_order(self, order_id: int) -> Order | None:
        return self._orders.get(order_id)

    def list_orders(self) -> list[Order]:
        return list(self._orders.values())

    # --- Платежи ---

    def add_payment(self, payment: Payment) -> Payment:
        saved = replace(payment, id=self._take_id("payment"))
        self._payments[saved.id] = saved
        return saved

    def update_payment(self, payment: Payment) -> None:
        if payment.id not in self._payments:
            raise KeyError(f"Платёж {payment.id} не найден")
        self._payments[payment.id] = payment

    def delete_payment(self, payment_id: int) -> None:
        self._payments.pop(payment_id, None)

    def get_payment(self, payment_id: int) -> Payment | None:
        return self._payments.get(payment_id)

    def list_payments(self) -> list[Payment]:
        return sorted(self._payments.values(),
                      key=lambda p: (p.paid_on, p.id))
