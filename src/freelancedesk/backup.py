"""Резервные копии базы SQLite.

Копия делается встроенным механизмом SQLite (backup API): он копирует
базу целиком и согласованно, даже если программа в этот момент с ней
работает. Копии лежат в <папка данных>/backups, хранятся последние 10.

Для PostgreSQL копии делаются средствами сервера (pg_dump) — программа
этим не занимается.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

KEEP = 10                 # сколько копий хранить
AUTO_EVERY = timedelta(days=7)  # как часто делать копию автоматически
PREFIX = "freelancedesk-"


def backup_dir(data_dir: Path) -> Path:
    return data_dir / "backups"


def list_backups(folder: Path) -> list[Path]:
    """Копии от новых к старым."""
    if not folder.exists():
        return []
    return sorted(folder.glob(f"{PREFIX}*.db"),
                  key=lambda p: p.stat().st_mtime, reverse=True)


def _copy(source: Path, target: Path) -> None:
    """Скопировать базу SQLite через backup API."""
    src = sqlite3.connect(source)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def create_backup(db_path: Path, folder: Path,
                  now: datetime | None = None) -> Path:
    """Сделать копию базы. Старые копии сверх KEEP удаляются."""
    folder.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    target = folder / f"{PREFIX}{stamp}.db"
    _copy(db_path, target)
    for old in list_backups(folder)[KEEP:]:
        old.unlink()
    return target


def auto_backup_due(folder: Path, now: datetime | None = None) -> bool:
    """Пора ли делать еженедельную копию."""
    backups = list_backups(folder)
    if not backups:
        return True
    last = datetime.fromtimestamp(backups[0].stat().st_mtime)
    return (now or datetime.now()) - last >= AUTO_EVERY


def restore_backup(backup: Path, db_path: Path, folder: Path) -> Path:
    """Заменить базу копией.

    Перед этим текущая база сама сохраняется в копию — на случай, если
    восстановили не ту. Возвращает путь к этой страховочной копии.
    Соединение программы с базой перед восстановлением нужно закрыть.
    """
    safety = create_backup(db_path, folder)
    _copy(backup, db_path)
    return safety
