"""Тесты применения миграций SQLite."""

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from freelancedesk.core.models import ContactMethod, OrderStatus
from freelancedesk.core.sql_storage import SqliteStorage
from freelancedesk.migrate import apply_sqlite_migrations, migrations_dir


def applied_names(db_path) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name FROM schema_migrations ORDER BY name")
        return [row[0] for row in rows]


def test_all_migrations_applied_once(tmp_path):
    db = tmp_path / "app.db"
    expected = sorted(p.name for p in migrations_dir("sqlite").glob("*.sql"))

    assert apply_sqlite_migrations(db) == expected
    # Второй запуск ничего не делает
    assert apply_sqlite_migrations(db) == []
    assert applied_names(db) == expected


def test_v02_paid_orders_become_payments(tmp_path):
    """Данные версии 0.2 переезжают в схему с платежами без потерь."""
    db = tmp_path / "app.db"
    v02 = tmp_path / "v02"
    v02.mkdir()
    # Применяем только миграции 001–002, как у пользователя версии 0.2
    for path in sorted(migrations_dir("sqlite").glob("00[12]_*.sql")):
        (v02 / path.name).write_text(path.read_text(encoding="utf-8"),
                                     encoding="utf-8")
    apply_sqlite_migrations(db, v02)
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO clients (name) VALUES ('Иван')")
        conn.execute(
            "INSERT INTO orders (title, client_id, amount, status, paid_on,"
            " receipt_issued) VALUES ('Оплачен', 1, '1500.50', 'paid',"
            " '2026-09-20', 1)")
        conn.execute(
            "INSERT INTO orders (title, client_id, amount, status)"
            " VALUES ('В работе', 1, '700', 'in_progress')")

    # Применятся все следующие миграции: 003 (платежи) и дальше
    assert apply_sqlite_migrations(db)[0] == "003_payments.sql"

    storage = SqliteStorage(db)
    paid, working = storage.list_orders()[0], storage.list_orders()[1]
    payments = storage.list_payments()
    storage.close()
    # Оплаченный заказ стал «сдан» с одним платежом на всю сумму
    assert paid.status == OrderStatus.DELIVERED
    assert paid.delivered_on == date(2026, 9, 20)
    assert len(payments) == 1
    assert payments[0].order_id == paid.id
    assert payments[0].amount == Decimal("1500.50")
    assert payments[0].paid_on == date(2026, 9, 20)
    assert payments[0].receipt_issued is True
    assert working.status == OrderStatus.IN_PROGRESS


def test_failed_migration_is_rolled_back(tmp_path):
    folder = tmp_path / "migrations"
    folder.mkdir()
    (folder / "001_ok.sql").write_text("CREATE TABLE a (x INTEGER);",
                                       encoding="utf-8")
    # Вторая команда с ошибкой: первая не должна остаться в базе
    (folder / "002_bad.sql").write_text(
        "CREATE TABLE b (x INTEGER);\nINSERT INTO nowhere VALUES (1);",
        encoding="utf-8")
    db = tmp_path / "app.db"

    with pytest.raises(sqlite3.Error):
        apply_sqlite_migrations(db, folder)

    assert applied_names(db) == ["001_ok.sql"]
    with sqlite3.connect(db) as conn:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "a" in tables and "b" not in tables


def test_v03_contacts_are_split(tmp_path):
    """Поле «Контакт» версии 0.3 раскладывается по новым полям."""
    db = tmp_path / "app.db"
    v03 = tmp_path / "v03"
    v03.mkdir()
    for path in sorted(migrations_dir("sqlite").glob("00[123]_*.sql")):
        (v03 / path.name).write_text(path.read_text(encoding="utf-8"),
                                     encoding="utf-8")
    apply_sqlite_migrations(db, v03)
    contacts = ["lisa@mail.ru", "+7 (900) 000-00-00", "@ivan",
                "vk.com/petr", ""]
    with sqlite3.connect(db) as conn:
        for i, contact in enumerate(contacts):
            conn.execute("INSERT INTO clients (name, contact) VALUES (?, ?)",
                         (f"Клиент {i}", contact))

    assert apply_sqlite_migrations(db) == ["004_client_contacts.sql"]

    storage = SqliteStorage(db)
    email, phone, tg, vk, empty = storage.list_clients()
    storage.close()
    assert (email.email, email.preferred_contact) == (
        "lisa@mail.ru", ContactMethod.EMAIL)
    assert (phone.phone, phone.preferred_contact) == (
        "+7 (900) 000-00-00", ContactMethod.PHONE)
    assert (tg.messenger, tg.messenger_app) == ("@ivan", "Telegram")
    assert (vk.messenger, vk.messenger_app) == ("vk.com/petr", "")
    assert (empty.email, empty.phone, empty.messenger,
            empty.preferred_contact) == ("", "", "", None)
