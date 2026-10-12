"""Хранилища данных.

Storage — интерфейс, с которым работает OrderManager.
InMemoryStorage — хранилище в памяти (для тестов и запуска без БД).
SQL-хранилища (PostgreSQL, SQLite) — в модуле sql_storage.
"""

from abc import ABC, abstractmethod
from dataclasses import replace

from freelancedesk.core.models import Client, Order


class Storage(ABC):
    """Общий интерфейс хранилища клиентов и заказов."""

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

    @abstractmethod
    def add_order(self, order: Order) -> Order:
        """Сохранить новый заказ и вернуть его с присвоенным id."""

    @abstractmethod
    def update_order(self, order: Order) -> None:
        """Обновить существующий заказ."""

    @abstractmethod
    def delete_order(self, order_id: int) -> None:
        """Удалить заказ."""

    @abstractmethod
    def get_order(self, order_id: int) -> Order | None:
        """Найти заказ по id."""

    @abstractmethod
    def list_orders(self) -> list[Order]:
        """Все заказы."""


class InMemoryStorage(Storage):
    """Хранилище в оперативной памяти. Данные пропадают при выходе."""

    def __init__(self) -> None:
        # Словари «id → объект» имитируют таблицы БД
        self._clients: dict[int, Client] = {}
        self._orders: dict[int, Order] = {}
        # Счётчики id — аналог SERIAL в PostgreSQL
        self._next_client_id = 1
        self._next_order_id = 1

    def add_client(self, client: Client) -> Client:
        # replace() создаёт копию с новым id — исходный объект не меняется
        saved = replace(client, id=self._next_client_id)
        self._clients[saved.id] = saved
        self._next_client_id += 1
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

    def add_order(self, order: Order) -> Order:
        saved = replace(order, id=self._next_order_id)
        self._orders[saved.id] = saved
        self._next_order_id += 1
        return saved

    def update_order(self, order: Order) -> None:
        if order.id not in self._orders:
            raise KeyError(f"Заказ {order.id} не найден")
        self._orders[order.id] = order

    def delete_order(self, order_id: int) -> None:
        self._orders.pop(order_id, None)

    def get_order(self, order_id: int) -> Order | None:
        return self._orders.get(order_id)

    def list_orders(self) -> list[Order]:
        return list(self._orders.values())
