"""Журнал работы программы и обработка непредвиденных ошибок.

Журнал пишется в <папка данных>/logs/freelancedesk.log. Файл не
разрастается: при 1 МБ он переименовывается в .log.1 (хранится три
старых файла). Если в программе случится непредвиденная ошибка, она
попадёт в журнал, а пользователь увидит понятное окно вместо
молчаливого падения.
"""

import logging
import sys
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_NAME = "freelancedesk.log"
log = logging.getLogger("freelancedesk")


def log_dir(data_dir: Path) -> Path:
    return data_dir / "logs"


def setup_logging(data_dir: Path) -> Path:
    """Включить запись журнала в файл. Возвращает путь к файлу."""
    folder = log_dir(data_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / LOG_NAME
    handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3,
                                  encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S"))
    # Повторный вызов (например, в тестах) не плодит обработчики
    for old in list(log.handlers):
        log.removeHandler(old)
        old.close()
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    return path


def install_excepthook(show: Callable[[str], None]) -> None:
    """Перехватывать непредвиденные ошибки.

    sys.excepthook вызывается, когда исключение никто не поймал.
    Записываем его в журнал целиком (с трассировкой), а пользователю
    показываем короткое сообщение через show(текст).
    """
    def handle(kind, error, traceback) -> None:
        if issubclass(kind, KeyboardInterrupt):  # Ctrl+C в консоли
            sys.__excepthook__(kind, error, traceback)
            return
        log.error("Непредвиденная ошибка", exc_info=(kind, error, traceback))
        try:
            show(f"{kind.__name__}: {error}")
        except Exception:  # noqa: BLE001 — окно не должно уронить программу
            log.exception("Не удалось показать окно ошибки")

    sys.excepthook = handle
