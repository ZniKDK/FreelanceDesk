"""Хранилища данных.

Storage — интерфейс, с которым работает OrderManager.
InMemoryStorage — хранилище в памяти (для тестов и демо).
DbStorage — хранилище в PostgreSQL.
"""

from abc import ABC, abstractmethod
from dataclasses import replace

import psycopg
from psycopg.rows import dict_row

from freelancedesk.core.models import Client, ClientType, Order, OrderStatus


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


class DbStorage(Storage):
    """Хранилище в PostgreSQL (через psycopg 3).

    Схема таблиц — в migrations/001_init.sql.
    Все запросы параметризованы (%s), поэтому SQL-инъекции невозможны:
    значения передаются в базу отдельно от текста запроса.
    """

    # Порядок колонок в SELECT — должен совпадать с полями моделей
    _CLIENT_COLUMNS = "id, name, client_type, contact, platform, note"
    _ORDER_COLUMNS = "id, title, client_id, amount, deadline, status, paid_on"

    def __init__(self, dsn: str) -> None:
        # dsn — строка подключения, собирается в config.build_dsn().
        # autocommit=True: каждый запрос сразу сохраняется в базе.
        # dict_row: строки результата приходят как словари {колонка: значение}.
        self._conn = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)

    def close(self) -> None:
        """Закрыть соединение с базой."""
        self._conn.close()

    # --- Преобразование строк БД в объекты моделей ---

    @staticmethod
    def _to_client(row: dict) -> Client:
        # В базе тип хранится строкой ('person'), в модели — как ClientType
        return Client(
            id=row["id"],
            name=row["name"],
            client_type=ClientType(row["client_type"]),
            contact=row["contact"],
            platform=row["platform"],
            note=row["note"],
        )

    @staticmethod
    def _to_order(row: dict) -> Order:
        # NUMERIC из PostgreSQL psycopg сам превращает в Decimal,
        # DATE — в datetime.date
        return Order(
            id=row["id"],
            title=row["title"],
            client_id=row["client_id"],
            amount=row["amount"],
            deadline=row["deadline"],
            status=OrderStatus(row["status"]),
            paid_on=row["paid_on"],
        )

    # --- Клиенты ---

    def add_client(self, client: Client) -> Client:
        # RETURNING id — PostgreSQL сразу возвращает id новой строки
        row = self._conn.execute(
            "INSERT INTO clients (name, client_type, contact, platform, note)"
            " VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (client.name, client.client_type.value, client.contact,
             client.platform, client.note),
        ).fetchone()
        return replace(client, id=row["id"])

    def update_client(self, client: Client) -> None:
        cur = self._conn.execute(
            "UPDATE clients SET name = %s, client_type = %s, contact = %s,"
            " platform = %s, note = %s WHERE id = %s",
            (client.name, client.client_type.value, client.contact,
             client.platform, client.note, client.id),
        )
        # rowcount — сколько строк изменилось; 0 значит, клиента нет
        if cur.rowcount == 0:
            raise KeyError(f"Клиент {client.id} не найден")

    def delete_client(self, client_id: int) -> None:
        self._conn.execute("DELETE FROM clients WHERE id = %s", (client_id,))

    def get_client(self, client_id: int) -> Client | None:
        row = self._conn.execute(
            f"SELECT {self._CLIENT_COLUMNS} FROM clients WHERE id = %s",
            (client_id,),
        ).fetchone()
        return self._to_client(row) if row else None

    def list_clients(self) -> list[Client]:
        rows = self._conn.execute(
            f"SELECT {self._CLIENT_COLUMNS} FROM clients ORDER BY name"
        ).fetchall()
        return [self._to_client(row) for row in rows]

    # --- Заказы ---

    def add_order(self, order: Order) -> Order:
        row = self._conn.execute(
            "INSERT INTO orders (title, client_id, amount, deadline, status,"
            " paid_on) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (order.title, order.client_id, order.amount, order.deadline,
             order.status.value, order.paid_on),
        ).fetchone()
        return replace(order, id=row["id"])

    def update_order(self, order: Order) -> None:
        cur = self._conn.execute(
            "UPDATE orders SET title = %s, client_id = %s, amount = %s,"
            " deadline = %s, status = %s, paid_on = %s WHERE id = %s",
            (order.title, order.client_id, order.amount, order.deadline,
             order.status.value, order.paid_on, order.id),
        )
        if cur.rowcount == 0:
            raise KeyError(f"Заказ {order.id} не найден")

    def delete_order(self, order_id: int) -> None:
        self._conn.execute("DELETE FROM orders WHERE id = %s", (order_id,))

    def get_order(self, order_id: int) -> Order | None:
        row = self._conn.execute(
            f"SELECT {self._ORDER_COLUMNS} FROM orders WHERE id = %s",
            (order_id,),
        ).fetchone()
        return self._to_order(row) if row else None

    def list_orders(self) -> list[Order]:
        # Сначала заказы с ближайшим дедлайном; без дедлайна — в конце
        rows = self._conn.execute(
            f"SELECT {self._ORDER_COLUMNS} FROM orders"
            " ORDER BY deadline NULLS LAST, id"
        ).fetchall()
        return [self._to_order(row) for row in rows]
