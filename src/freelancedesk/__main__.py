"""Точка входа: python -m freelancedesk."""

import configparser
import sys
from pathlib import Path

from PyQt6.QtCore import QLibraryInfo, QSettings, QTranslator
from PyQt6.QtWidgets import QApplication, QMessageBox

from freelancedesk import __version__, backup
from freelancedesk.app.main_window import MainWindow
from freelancedesk.logs import install_excepthook, log, setup_logging
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


def sqlite_file(config: configparser.ConfigParser,
                data_dir: Path) -> Path | None:
    """Путь к файлу базы, если данные в SQLite (для резервных копий)."""
    if storage_backend(config) == "sqlite":
        return sqlite_path(config, data_dir)
    return None


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

    data_dir = app_dir()
    log_path = setup_logging(data_dir)
    log.info("Запуск FreelanceDesk %s", __version__)
    error = None
    db_path = None
    try:
        config = load_config(data_dir / "config.ini")
        storage, storage_label = open_storage(config, data_dir)
        db_path = sqlite_file(config, data_dir)
        log.info("Данные: %s", storage_label)
    except (OSError, KeyError, ValueError, configparser.Error,
            *DB_ERRORS) as exc:
        # Без базы приложение всё равно запускается, но честно
        # предупреждает, что данные не сохранятся
        storage = InMemoryStorage()
        storage_label = "в памяти — данные НЕ сохраняются"
        error = str(exc)
        log.error("Не удалось открыть базу: %s", exc)

    # Размер окна, фильтры, цель и тема — в отдельном ini-файле (не в реестре)
    settings = QSettings(str(data_dir / "ui_state.ini"),
                         QSettings.Format.IniFormat)
    # Тему включаем до создания окна, чтобы оно сразу было в нужных цветах
    apply_theme(app, settings.value("theme", "light"))
    # Цепочка зависимостей: хранилище → менеджер → окно
    window = MainWindow(OrderManager(storage), settings=settings,
                        data_dir=data_dir, storage_label=storage_label,
                        db_path=db_path)

    def show_crash(text: str) -> None:
        """Непредвиденная ошибка: понятное окно вместо падения."""
        QMessageBox.critical(
            window, "FreelanceDesk",
            "Что-то пошло не так, но данные в порядке — программа "
            f"продолжит работу.\n\n{text}\n\nПодробности записаны "
            f"в журнал:\n{log_path}")

    install_excepthook(show_crash)
    window.show()
    # Еженедельная резервная копия — тихо, с коротким уведомлением
    if db_path is not None and backup.auto_backup_due(
            backup.backup_dir(data_dir)):
        try:
            backup.create_backup(db_path, backup.backup_dir(data_dir))
            window.notify("Создана еженедельная резервная копия")
            log.info("Еженедельная резервная копия создана")
        except Exception:  # noqa: BLE001 — копия не должна мешать работе
            log.exception("Не удалось создать еженедельную копию")
    if error:
        QMessageBox.warning(
            window, "FreelanceDesk",
            f"Не удалось открыть базу данных:\n{error}\n\n"
            "Программа работает без сохранения данных. Проверьте настройки "
            f"в файле {data_dir / 'config.ini'}.")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
