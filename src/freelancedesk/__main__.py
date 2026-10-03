"""Точка входа: python -m freelancedesk."""

import configparser
import sys
from pathlib import Path

from PyQt6.QtCore import QLibraryInfo, QSettings, QTranslator
from PyQt6.QtWidgets import QApplication, QMessageBox

from freelancedesk.app.main_window import MainWindow
from freelancedesk.app.theme import apply_theme
from freelancedesk.config import (
    app_dir, build_dsn, load_config, sqlite_path, storage_backend,
)
from freelancedesk.core.manager import OrderManager
from freelancedesk.core.sql_storage import DB_ERRORS, DbStorage, SqliteStorage
from freelancedesk.core.storage import InMemoryStorage, Storage
from freelancedesk.migrate import (
    apply_postgres_migrations, apply_sqlite_migrations,
)


def open_storage(config: configparser.ConfigParser,
                 data_dir: Path) -> tuple[Storage, str]:
    """Открыть хранилище из настроек и обновить схему базы.

    Возвращает (хранилище, подпись для строки состояния).
    Миграции применяются автоматически: после обновления программы
    пользователю не нужно ничего запускать вручную.
    """
    backend = storage_backend(config)
    if backend == "sqlite":
        path = sqlite_path(config, data_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        apply_sqlite_migrations(path)
        return SqliteStorage(path), f"SQLite — {path}"
    if backend == "postgresql":
        dsn = build_dsn(config)
        apply_postgres_migrations(dsn)
        db = config["database"]
        return DbStorage(dsn), f"PostgreSQL — {db.get('host')}/{db['name']}"
    raise ValueError(f"Неизвестное хранилище «{backend}» в config.ini: "
                     "укажите sqlite или postgresql")


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
    app.setApplicationName("FreelanceDesk")
    translator = install_russian(app)  # noqa: F841 — держим ссылку
    apply_theme(app)

    data_dir = app_dir()
    error = None
    try:
        config = load_config(data_dir / "config.ini")
        storage, storage_label = open_storage(config, data_dir)
    except (OSError, KeyError, ValueError, configparser.Error,
            *DB_ERRORS) as exc:
        # Без базы приложение всё равно запускается, но честно
        # предупреждает, что данные не сохранятся
        storage = InMemoryStorage()
        storage_label = "в памяти — данные НЕ сохраняются"
        error = str(exc)

    # Размер окна, фильтры и цель — в отдельном ini-файле (не в реестре)
    settings = QSettings(str(data_dir / "ui_state.ini"),
                         QSettings.Format.IniFormat)
    # Цепочка зависимостей: хранилище → менеджер → окно
    window = MainWindow(OrderManager(storage), settings=settings,
                        data_dir=data_dir, storage_label=storage_label)
    window.show()
    if error:
        QMessageBox.warning(
            window, "FreelanceDesk",
            f"Не удалось открыть базу данных:\n{error}\n\n"
            "Программа работает без сохранения данных. Проверьте настройки "
            f"в файле {data_dir / 'config.ini'}.")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
