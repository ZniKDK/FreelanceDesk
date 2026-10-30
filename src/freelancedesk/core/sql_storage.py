"""SQL-хранилища: общий код и две реализации.

SqlStorage — все запросы и преобразования, общие для любых SQL-баз.
DbStorage — PostgreSQL (через psycopg 3).
SqliteStorage — SQLite: база-файл, сервер не нужен.

Запросы пишутся один раз с местами для значений %s. Значения
передаются в базу отдельно от текста запроса, поэтому SQL-инъекции
невозможны. Схемы таблиц — в migrations/postgresql и migrations/sqlite.
"""

import sqlite3
from abc import abstractmethod
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from freelancedesk.core.models import (
    Client, ClientType, ContactMethod, Order, OrderStatus, Payment,
)
from freelancedesk.core.storage import Storage

# Ошибки любой из баз — интерфейс показывает их пользователю окном
DB_ERRORS = (psycopg.Error, sqlite3.Error)


def to_date(value) -> date | None:
    """Дата из базы: PostgreSQL отдаёт date, SQLite — строку 'ГГГГ-ММ-ДД'."""
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


class SqlStorage(Storage):
    """Общая часть SQL-хранилищ: запросы и преобразование строк в модели."""

    # Порядок колонок в SELECT — используется в _to_client и _to_order
    _CLIENT_COLUMNS = ("id, name, client_type, email, phone, messenger,"
                       " messenger_app, preferred_contact, platform, note")
    _ORDER_COLUMNS = ("id, title, client_id, amount, deadline, status,"
                      " delivered_on, description, link")
    _PAYMENT_COLUMNS = "id, order_id, amount, paid_on, receipt_issued"

    @abstractmethod
    def _execute(self, sql: str, params: tuple = ()):
        """Выполнить запрос (с местами %s) и вернуть курсор."""

    @abstractmethod
    def close(self) -> None:
        """Закрыть соединение с базой."""

    # --- Преобразование строк БД в объекты моделей ---

    @staticmethod
    def _to_client(row) -> Client:
        # В базе тип хранится строкой ('person'), в модели — как ClientType
        return Client(
            id=row["id"],
            name=row["name"],
            client_type=ClientType(row["client_type"]),
            email=row["email"],
            phone=row["phone"],
            messenger=row["messenger"],
            messenger_app=row["messenger_app"],
            # Пустая строка в базе — «способ не выбран»
            preferred_contact=(ContactMethod(row["preferred_contact"])
                               if row["preferred_contact"] else None),
            platform=row["platform"],
            note=row["note"],
        )

    @staticmethod
    def _to_order(row) -> Order:
        return Order(
            id=row["id"],
            title=row["title"],
            client_id=row["client_id"],
            # PostgreSQL отдаёт Decimal, SQLite — строку; str() уравнивает
            amount=Decimal(str(row["amount"])),
            deadline=to_date(row["deadline"]),
            status=OrderStatus(row["status"]),
            delivered_on=to_date(row["delivered_on"]),
            description=row["description"],
            link=row["link"],
        )

    @staticmethod
    def _to_payment(row) -> Payment:
        return Payment(
            id=row["id"],
            order_id=row["order_id"],
            amount=Decimal(str(row["amount"])),
            paid_on=to_date(row["paid_on"]),
            # SQLite хранит логическое значение числом 0/1
            receipt_issued=bool(row["receipt_issued"]),
        )

    @staticmethod
    def _client_values(client: Client) -> tuple:
        preferred = (client.preferred_contact.value
                     if client.preferred_contact else "")
        return (client.name, client.client_type.value, client.email,
                client.phone, client.messenger, client.messenger_app,
                preferred, client.platform, client.note)

    @staticmethod
    def _order_values(order: Order) -> tuple:
        return (order.title, order.client_id, order.amount, order.deadline,
                order.status.value, order.delivered_on, order.description,
                order.link)

    @staticmethod
    def _payment_values(payment: Payment) -> tuple:
        return (payment.order_id, payment.amount, payment.paid_on,
                payment.receipt_issued)

    # --- Клиенты ---

    def add_client(self, client: Client) -> Client:
        # RETURNING id — база сразу возвращает id новой строки
        row = self._execute(
            "INSERT INTO clients (name, client_type, email, phone,"
            " messenger, messenger_app, preferred_contact, platform, note)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            self._client_values(client),
        ).fetchone()
        return replace(client, id=row["id"])

    def update_client(self, client: Client) -> None:
        cur = self._execute(
            "UPDATE clients SET name = %s, client_type = %s, email = %s,"
            " phone = %s, messenger = %s, messenger_app = %s,"
            " preferred_contact = %s, platform = %s, note = %s"
            " WHERE id = %s",
            self._client_values(client) + (client.id,),
        )
        # rowcount — сколько строк изменилось; 0 значит, клиента нет
        if cur.rowcount == 0:
            raise KeyError(f"Клиент {client.id} не найден")

    def delete_client(self, client_id: int) -> None:
        self._execute("DELETE FROM clients WHERE id = %s", (client_id,))

    def get_client(self, client_id: int) -> Client | None:
        row = self._execute(
            f"SELECT {self._CLIENT_COLUMNS} FROM clients WHERE id = %s",
            (client_id,),
        ).fetchone()
        return self._to_client(row) if row else None

    def list_clients(self) -> list[Client]:
        rows = self._execute(
            f"SELECT {self._CLIENT_COLUMNS} FROM clients ORDER BY id"
        ).fetchall()
        return [self._to_client(row) for row in rows]

    # --- Заказы ---

    def add_order(self, order: Order) -> Order:
        row = self._execute(
            "INSERT INTO orders (title, client_id, amount, deadline, status,"
            " delivered_on, description, link)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            self._order_values(order),
        ).fetchone()
        return replace(order, id=row["id"])

    def update_order(self, order: Order) -> None:
        cur = self._execute(
            "UPDATE orders SET title = %s, client_id = %s, amount = %s,"
            " deadline = %s, status = %s, delivered_on = %s,"
            " description = %s, link = %s WHERE id = %s",
            self._order_values(order) + (order.id,),
        )
        if cur.rowcount == 0:
            raise KeyError(f"Заказ {order.id} не найден")

    def delete_order(self, order_id: int) -> None:
        # Сначала платежи заказа: внешний ключ не даст удалить заказ с ними
        self._execute("DELETE FROM payments WHERE order_id = %s", (order_id,))
        self._execute("DELETE FROM orders WHERE id = %s", (order_id,))

    def get_order(self, order_id: int) -> Order | None:
        row = self._execute(
            f"SELECT {self._ORDER_COLUMNS} FROM orders WHERE id = %s",
            (order_id,),
        ).fetchone()
        return self._to_order(row) if row else None

    def list_orders(self) -> list[Order]:
        # Сначала заказы с ближайшим дедлайном; без дедлайна — в конце
        rows = self._execute(
            f"SELECT {self._ORDER_COLUMNS} FROM orders"
            " ORDER BY deadline NULLS LAST, id"
        ).fetchall()
        return [self._to_order(row) for row in rows]

    # --- Платежи ---

    def add_payment(self, payment: Payment) -> Payment:
        row = self._execute(
            "INSERT INTO payments (order_id, amount, paid_on, receipt_issued)"
            " VALUES (%s, %s, %s, %s) RETURNING id",
            self._payment_values(payment),
        ).fetchone()
        return replace(payment, id=row["id"])

    def update_payment(self, payment: Payment) -> None:
        cur = self._execute(
            "UPDATE payments SET order_id = %s, amount = %s, paid_on = %s,"
            " receipt_issued = %s WHERE id = %s",
            self._payment_values(payment) + (payment.id,),
        )
        if cur.rowcount == 0:
            raise KeyError(f"Платёж {payment.id} не найден")

    def delete_payment(self, payment_id: int) -> None:
        self._execute("DELETE FROM payments WHERE id = %s", (payment_id,))

    def get_payment(self, payment_id: int) -> Payment | None:
        row = self._execute(
            f"SELECT {self._PAYMENT_COLUMNS} FROM payments WHERE id = %s",
            (payment_id,),
        ).fetchone()
        return self._to_payment(row) if row else None

    def list_payments(self) -> list[Payment]:
        rows = self._execute(
            f"SELECT {self._PAYMENT_COLUMNS} FROM payments"
            " ORDER BY paid_on, id"
        ).fetchall()
        return [self._to_payment(row) for row in rows]


class DbStorage(SqlStorage):
    """Хранилище в PostgreSQL."""

    def __init__(self, dsn: str) -> None:
        # dsn — строка подключения, собирается в config.build_dsn().
        # autocommit=True: каждый запрос сразу сохраняется в базе.
        # dict_row: строки результата приходят как словари {колонка: значение}.
        self._conn = psycopg.connect(dsn, autocommit=True,
                                     row_factory=dict_row)

    def _execute(self, sql: str, params: tuple = ()):
        return self._conn.execute(sql, params)

    def close(self) -> None:
        self._conn.close()


class SqliteStorage(SqlStorage):
    """Хранилище в файле SQLite."""

    def __init__(self, path: Path | str) -> None:
        # isolation_level=None — режим autocommit, как у DbStorage
        self._conn = sqlite3.connect(path, isolation_level=None)
        # sqlite3.Row позволяет обращаться к колонкам по имени: row["id"]
        self._conn.row_factory = sqlite3.Row
        # По умолчанию SQLite не проверяет внешние ключи — включаем
        self._conn.execute("PRAGMA foreign_keys = ON")

    @staticmethod
    def _adapt(value):
        """Привести значение Python к типу, который хранит SQLite."""
        if isinstance(value, bool):
            return int(value)          # True -> 1
        if isinstance(value, Decimal):
            return str(value)          # Decimal('1500.50') -> '1500.50'
        if isinstance(value, date):
            return value.isoformat()   # date -> '2026-10-03'
        return value

    def _execute(self, sql: str, params: tuple = ()):
        # sqlite3 использует знак ? вместо %s
        return self._conn.execute(sql.replace("%s", "?"),
                                  tuple(self._adapt(v) for v in params))

    def close(self) -> None:
        self._conn.close()
