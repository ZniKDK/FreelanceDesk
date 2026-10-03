"""Настройки приложения и пути к его файлам.

Файлы пользователя лежат в папке данных (Windows: %APPDATA%\\FreelanceDesk):
    config.ini        — где хранить данные: SQLite или PostgreSQL;
    freelancedesk.db  — база SQLite (по умолчанию);
    ui_state.ini      — размер окна, фильтры, цель на месяц.
Папку можно переопределить переменной окружения FREELANCEDESK_HOME
(удобно для тестов и «переносной» версии на флешке).
"""

import configparser
import os
import sys
from pathlib import Path

# Корень проекта: src/freelancedesk/config.py -> на три уровня выше
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Содержимое config.ini, который создаётся при первом запуске
DEFAULT_CONFIG = """\
; Настройки FreelanceDesk.
;
; backend — где хранить данные:
;   sqlite     — файл на этом компьютере, ничего устанавливать не нужно;
;   postgresql — сервер PostgreSQL (заполните секцию [database]).
[storage]
backend = sqlite

[sqlite]
; Путь к файлу базы. Пусто — freelancedesk.db рядом с этим файлом.
path =

[database]
host = localhost
port = 5432
name = freelancedesk
user = freelancedesk
password =
"""


def app_dir() -> Path:
    """Папка с файлами пользователя."""
    custom = os.environ.get("FREELANCEDESK_HOME")
    if custom:
        return Path(custom)
    # APPDATA есть только в Windows; на других системах — домашняя папка
    base = os.environ.get("APPDATA") or Path.home()
    return Path(base) / "FreelanceDesk"


def resource_dir() -> Path:
    """Папка с файлами программы (миграции, иконки).

    В собранном .exe (PyInstaller) файлы распаковываются во временную
    папку sys._MEIPASS, при обычном запуске — это корень проекта.
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # noqa: SLF001 — так устроен PyInstaller
    return PROJECT_ROOT


def load_config(path: Path | None = None) -> configparser.ConfigParser:
    """Прочитать config.ini; при первом запуске — создать с настройками
    по умолчанию (SQLite)."""
    path = path or app_dir() / "config.ini"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    config = configparser.ConfigParser()
    config.read(path, encoding="utf-8")
    return config


def storage_backend(config: configparser.ConfigParser) -> str:
    """Выбранное хранилище: 'sqlite' или 'postgresql'."""
    return config.get("storage", "backend", fallback="sqlite").strip().lower()


def sqlite_path(config: configparser.ConfigParser, base_dir: Path) -> Path:
    """Путь к файлу SQLite: из настроек или по умолчанию в base_dir."""
    custom = config.get("sqlite", "path", fallback="").strip()
    return Path(custom) if custom else base_dir / "freelancedesk.db"


def build_dsn(config: configparser.ConfigParser,
              dbname: str | None = None) -> str:
    """Собрать строку подключения к PostgreSQL из секции [database].

    dbname позволяет подключиться к другой базе с теми же учётными
    данными — так тесты работают с freelancedesk_test.
    """
    db = config["database"]
    return (
        f"host={db.get('host', 'localhost')} "
        f"port={db.get('port', '5432')} "
        f"dbname={dbname or db['name']} "
        f"user={db['user']} "
        f"password={db['password']}"
    )
