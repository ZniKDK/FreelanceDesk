"""Применение SQL-миграций к базе данных.

Запуск: python -m freelancedesk.migrate

Миграции — файлы migrations/NNN_название.sql. Они применяются по порядку
имён, каждая один раз. Список применённых хранится в таблице
schema_migrations, поэтому повторный запуск безопасен.
"""

from pathlib import Path

import psycopg

from freelancedesk.config import PROJECT_ROOT, build_dsn, load_config

MIGRATIONS_DIR = PROJECT_ROOT / "migrations"


def apply_migrations(dsn: str,
                     migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Применить новые миграции. Возвращает имена применённых файлов."""
    applied_now = []
    with psycopg.connect(dsn) as conn:
        # Служебная таблица: какие миграции уже выполнены
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " name VARCHAR(255) PRIMARY KEY,"
            " applied_at TIMESTAMP NOT NULL DEFAULT now())"
        )
        conn.commit()
        done = {row[0] for row in
                conn.execute("SELECT name FROM schema_migrations")}

        # sorted() даёт порядок 001, 002, ... — поэтому номера с нулями
        for path in sorted(migrations_dir.glob("*.sql")):
            if path.name in done:
                continue
            # Миграция и запись о ней — в одной транзакции:
            # при ошибке не останется «наполовину применённой» схемы
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO schema_migrations (name) VALUES (%s)",
                    (path.name,))
            applied_now.append(path.name)
    return applied_now


def main() -> None:
    dsn = build_dsn(load_config())
    applied = apply_migrations(dsn)
    if applied:
        print("Применены миграции:", ", ".join(applied))
    else:
        print("Новых миграций нет — база в актуальном состоянии.")


if __name__ == "__main__":
    main()
