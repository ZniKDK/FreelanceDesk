"""Интеграционные тесты DbStorage на реальном PostgreSQL.

Работают с отдельной базой <name>_test (по умолчанию freelancedesk_test),
чтобы не трогать рабочие данные. Если config.ini нет или база недоступна,
тесты пропускаются (skip), а не падают.
"""

from datetime import date
from decimal import Decimal

import psycopg
import pytest

from freelancedesk.config import build_dsn, load_config
from freelancedesk.core.manager import OrderManager
from freelancedesk.core.models import Client, ClientType, Order, OrderStatus
from freelancedesk.core.storage import DbStorage
from freelancedesk.migrate import apply_migrations


@pytest.fixture(scope="module")
def test_dsn() -> str:
    """Строка подключения к тестовой базе + применённые миграции."""
    try:
        config = load_config()
        dsn = build_dsn(config, dbname=config["database"]["name"] + "_test")
        apply_migrations(dsn)
    except (FileNotFoundError, KeyError, psycopg.OperationalError) as exc:
        pytest.skip(f"Тестовая БД недоступна: {exc}")
    return dsn


@pytest.fixture
def storage(test_dsn):
    """Чистое хранилище для каждого теста."""
    # TRUNCATE очищает таблицы, RESTART IDENTITY сбрасывает счётчики id
    with psycopg.connect(test_dsn) as conn:
        conn.execute("TRUNCATE orders, clients RESTART IDENTITY")
    db = DbStorage(test_dsn)
    yield db
    db.close()


def test_migrations_are_idempotent(test_dsn):
    # Повторный запуск ничего не применяет
    assert apply_migrations(test_dsn) == []


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
    saved = storage.add_order(Order(title="Бот", client_id=client.id,
                                    amount=Decimal("1500.50"),
                                    deadline=date(2026, 10, 10)))
    loaded = storage.get_order(saved.id)
    # Decimal, date и enum должны вернуться из БД теми же типами
    assert loaded == saved
    assert isinstance(loaded.amount, Decimal)
    assert loaded.status is OrderStatus.NEW


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
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
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
