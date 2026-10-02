"""Точка входа: python -m freelancedesk."""

import sys

import psycopg
from PyQt6.QtWidgets import QApplication

from freelancedesk.app.main_window import MainWindow
from freelancedesk.config import build_dsn, load_config
from freelancedesk.core.manager import OrderManager
from freelancedesk.core.storage import DbStorage, InMemoryStorage, Storage


def create_storage() -> Storage:
    """Подключиться к PostgreSQL; если не вышло — работать в памяти."""
    try:
        return DbStorage(build_dsn(load_config()))
    except (FileNotFoundError, KeyError, psycopg.OperationalError) as exc:
        # Без базы приложение всё равно запускается — удобно для демо.
        # Данные в этом режиме не сохраняются после выхода.
        print(f"БД недоступна ({exc}). Данные хранятся только в памяти.",
              file=sys.stderr)
        return InMemoryStorage()


def main() -> int:
    app = QApplication(sys.argv)
    # Цепочка зависимостей: хранилище → менеджер → окно
    manager = OrderManager(create_storage())
    window = MainWindow(manager)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
