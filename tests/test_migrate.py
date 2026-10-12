"""Тесты применения миграций SQLite."""

import sqlite3

import pytest

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
