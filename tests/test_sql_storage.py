"""Интеграционные тесты SQL-хранилищ: SQLite и PostgreSQL.

Каждый тест запускается дважды — на SqliteStorage (временный файл)
и на DbStorage (база <name>_test из config/config.ini проекта).
Если PostgreSQL недоступен, его вариант пропускается (skip).
"""

from datetime import date
from decimal import Decimal
from functools import cache

import psycopg
import pytest

from freelancedesk.config import PROJECT_ROOT, build_dsn, load_config
from freelancedesk.core.manager import OrderManager
from freelancedesk.core.models import Client, ClientType, Order, OrderStatus
from freelancedesk.core.sql_storage import DB_ERRORS, DbStorage, SqliteStorage
from freelancedesk.migrate import (
    apply_postgres_migrations, apply_sqlite_migrations,
)

DEV_CONFIG = PROJECT_ROOT / "config" / "config.ini"


@cache  # подключаемся и применяем миграции один раз на все тесты
def postgres_test_dsn() -> str | None:
    """Строка подключения к тестовой базе PostgreSQL или None."""
    if not DEV_CONFIG.exists():
        return None
    try:
        config = load_config(DEV_CONFIG)
        dsn = build_dsn(config, dbname=config["database"]["name"] + "_test")
        apply_postgres_migrations(dsn)
    except (KeyError, psycopg.OperationalError):
        return None
    return dsn


@pytest.fixture(params=["sqlite", "postgresql"])
def storage(request, tmp_path):
    """Чистое хранилище для каждого теста — на обеих СУБД."""
    if request.param == "sqlite":
        path = tmp_path / "test.db"
        apply_sqlite_migrations(path)
        db = SqliteStorage(path)
    else:
        dsn = postgres_test_dsn()
        if dsn is None:
            pytest.skip("Тестовая БД PostgreSQL недоступна")
        # TRUNCATE очищает таблицы, RESTART IDENTITY сбрасывает счётчики id
        with psycopg.connect(dsn) as conn:
            conn.execute("TRUNCATE orders, clients RESTART IDENTITY")
        db = DbStorage(dsn)
    yield db
    db.close()


def test_client_roundtrip(storage):
    saved = storage.add_client(Client(name="ООО Ромашка",
                                      client_type=ClientType.COMPANY,
                                      platform="Kwork"))
    assert saved.id == 1
    assert storage.get_client(saved.id) == saved


def test_update_and_delete_client(storage):
    client = storage.add_client(Client(name="Иван"))
    client.contact = "@ivan"
    storage.update_client(client)
    assert storage.get_client(client.id).contact == "@ivan"

    storage.delete_client(client.id)
    assert storage.get_client(client.id) is None


def test_update_missing_client_raises(storage):
    with pytest.raises(KeyError):
        storage.update_client(Client(name="Нет такого", id=999))


def test_order_roundtrip_keeps_types(storage):
    client = storage.add_client(Client(name="Иван"))
    saved = storage.add_order(Order(
        title="Бот", client_id=client.id, amount=Decimal("1500.50"),
        deadline=date(2026, 10, 10), status=OrderStatus.PAID,
        paid_on=date(2026, 10, 3), description="ТЗ в переписке",
        link="https://kwork.ru/track/1", receipt_issued=True))
    loaded = storage.get_order(saved.id)
    # Decimal, date, bool и enum должны вернуться из БД теми же типами
    assert loaded == saved
    assert isinstance(loaded.amount, Decimal)
    assert loaded.receipt_issued is True


def test_update_order(storage):
    client = storage.add_client(Client(name="Иван"))
    order = storage.add_order(Order(title="Бот", client_id=client.id,
                                    amount=Decimal("100")))
    order.amount = Decimal("250.75")
    order.description = "Добавили админку"
    storage.update_order(order)
    assert storage.get_order(order.id) == order


def test_orders_sorted_by_deadline(storage):
    client = storage.add_client(Client(name="Иван"))
    for title, deadline in (("Без срока", None),
                            ("Поздний", date(2026, 12, 1)),
                            ("Ранний", date(2026, 10, 5))):
        storage.add_order(Order(title=title, client_id=client.id,
                                amount=Decimal("100"), deadline=deadline))
    titles = [o.title for o in storage.list_orders()]
    assert titles == ["Ранний", "Поздний", "Без срока"]


def test_db_rejects_order_for_missing_client(storage):
    # Внешний ключ в БД — вторая линия защиты после OrderManager
    with pytest.raises(DB_ERRORS):
        storage.add_order(Order(title="Бот", client_id=999,
                                amount=Decimal("100")))


def test_manager_summary_on_database(storage):
    # Тот же сценарий, что и в test_manager.py, но на настоящей базе
    manager = OrderManager(storage)
    person = manager.add_client(Client(name="Иван"))
    company = manager.add_client(Client(name="ООО",
                                        client_type=ClientType.COMPANY))
    for client, amount in ((person, "1000"), (company, "2000")):
        order = manager.add_order(Order(title="Заказ", client_id=client.id,
                                        amount=Decimal(amount)))
        manager.change_status(order.id, OrderStatus.PAID,
                              today=date(2026, 10, 2))

    result = manager.summary(date(2026, 10, 1), date(2026, 10, 31))
    assert result.income == Decimal("3000")
    assert result.tax == Decimal("160.00")
