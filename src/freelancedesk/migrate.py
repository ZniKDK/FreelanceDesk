"""Применение SQL-миграций к базе данных.

Запуск вручную: python -m freelancedesk.migrate
(приложение само применяет миграции при старте).

Миграции — файлы migrations/<СУБД>/NNN_название.sql, отдельно для
PostgreSQL и SQLite: синтаксис у них немного разный. Применяются по
порядку имён, каждая один раз. Список применённых хранится в таблице
schema_migrations, поэтому повторный запуск безопасен.
"""

import sqlite3
from pathlib import Path

import psycopg

from freelancedesk.config import (
    app_dir, build_dsn, load_config, resource_dir, sqlite_path,
    storage_backend,
)

# Служебная таблица. CURRENT_TIMESTAMP понимают обе СУБД.
SCHEMA_TABLE_SQL = (
    "CREATE TABLE IF NOT EXISTS schema_migrations ("
    " name VARCHAR(255) PRIMARY KEY,"
    " applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
)


def migrations_dir(dialect: str) -> Path:
    """Папка с миграциями для 'postgresql' или 'sqlite'."""
    return resource_dir() / "migrations" / dialect


def pending(directory: Path, done: set[str]) -> list[Path]:
    """Файлы миграций, которые ещё не применены, по порядку."""
    # sorted() даёт порядок 001, 002, ... — поэтому номера с нулями
    return [p for p in sorted(directory.glob("*.sql")) if p.name not in done]


def apply_postgres_migrations(dsn: str,
                              directory: Path | None = None) -> list[str]:
    """Применить новые миграции к PostgreSQL. Возвращает имена файлов."""
    directory = directory or migrations_dir("postgresql")
    applied_now = []
    with psycopg.connect(dsn) as conn:
        conn.execute(SCHEMA_TABLE_SQL)
        conn.commit()
        done = {row[0] for row in
                conn.execute("SELECT name FROM schema_migrations")}
        for path in pending(directory, done):
            # Миграция и запись о ней — в одной транзакции:
            # при ошибке не останется «наполовину применённой» схемы
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO schema_migrations (name) VALUES (%s)",
                    (path.name,))
            applied_now.append(path.name)
    return applied_now


def apply_sqlite_migrations(db_path: Path,
                            directory: Path | None = None) -> list[str]:
    """Применить новые миграции к файлу SQLite. Возвращает имена файлов."""
    directory = directory or migrations_dir("sqlite")
    applied_now = []
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(SCHEMA_TABLE_SQL)
        conn.commit()
        done = {row[0] for row in
                conn.execute("SELECT name FROM schema_migrations")}
        for path in pending(directory, done):
            # executescript выполняет сразу несколько команд из файла.
            # BEGIN ... COMMIT делают миграцию атомарной, как в PostgreSQL.
            # Имя файла экранируем: одинарная кавычка удваивается.
            name = path.name.replace("'", "''")
            script = (f"BEGIN;\n{path.read_text(encoding='utf-8')}\n"
                      f"INSERT INTO schema_migrations (name) "
                      f"VALUES ('{name}');\nCOMMIT;")
            try:
                conn.executescript(script)
            except sqlite3.Error:
                # При ошибке посреди скрипта транзакция остаётся открытой
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            applied_now.append(path.name)
    finally:
        conn.close()
    return applied_now


def main() -> None:
    config = load_config()
    if storage_backend(config) == "postgresql":
        applied = apply_postgres_migrations(build_dsn(config))
    else:
        path = sqlite_path(config, app_dir())
        path.parent.mkdir(parents=True, exist_ok=True)
        applied = apply_sqlite_migrations(path)
    if applied:
        print("Применены миграции:", ", ".join(applied))
    else:
        print("Новых миграций нет — база в актуальном состоянии.")


if __name__ == "__main__":
    main()
