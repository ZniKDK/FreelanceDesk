"""Точка входа: python -m freelancedesk."""

import sys

import psycopg
from PyQt6.QtCore import QLibraryInfo, QTranslator
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


def install_russian(app: QApplication) -> QTranslator:
    """Перевести стандартные кнопки Qt (Cancel, Yes, No) на русский.

    Переводы поставляются вместе с PyQt6. Переводчик возвращаем,
    чтобы его не удалил сборщик мусора, пока работает приложение.
    """
    translator = QTranslator()
    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load("qtbase_ru", path):
        app.installTranslator(translator)
    return translator


def main() -> int:
    app = QApplication(sys.argv)
    translator = install_russian(app)  # noqa: F841 — держим ссылку
    # Цепочка зависимостей: хранилище → менеджер → окно
    storage = create_storage()
    manager = OrderManager(storage)
    window = MainWindow(manager)
    if isinstance(storage, InMemoryStorage):
        # Предупреждаем прямо в заголовке: консоль пользователь не видит
        window.setWindowTitle(window.windowTitle()
                              + " (нет БД — данные не сохраняются)")
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
