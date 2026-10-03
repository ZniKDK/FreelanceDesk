"""Тесты резервных копий и журнала."""

import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta

from freelancedesk import backup
from freelancedesk.logs import install_excepthook, setup_logging


def make_db(path, value: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
        conn.execute("DELETE FROM t")
        conn.execute("INSERT INTO t VALUES (?)", (value,))


def read_db(path) -> str:
    with sqlite3.connect(path) as conn:
        return conn.execute("SELECT v FROM t").fetchone()[0]


def test_create_backup_copies_data(tmp_path):
    db = tmp_path / "app.db"
    make_db(db, "заказы")
    copy = backup.create_backup(db, tmp_path / "backups")
    assert copy.exists() and read_db(copy) == "заказы"


def test_only_last_copies_are_kept(tmp_path):
    db = tmp_path / "app.db"
    make_db(db, "x")
    folder = tmp_path / "backups"
    start = datetime(2026, 1, 1)
    for i in range(backup.KEEP + 3):
        path = backup.create_backup(db, folder, now=start + timedelta(hours=i))
        # Время изменения файла — по порядку создания
        stamp = (start + timedelta(hours=i)).timestamp()
        os.utime(path, (stamp, stamp))
    assert len(backup.list_backups(folder)) == backup.KEEP


def test_auto_backup_due(tmp_path):
    db = tmp_path / "app.db"
    make_db(db, "x")
    folder = tmp_path / "backups"
    assert backup.auto_backup_due(folder)  # копий ещё нет
    copy = backup.create_backup(db, folder)
    now = datetime.fromtimestamp(copy.stat().st_mtime)
    assert not backup.auto_backup_due(folder, now + timedelta(days=6))
    assert backup.auto_backup_due(folder, now + timedelta(days=7))


def test_restore_replaces_db_and_keeps_safety_copy(tmp_path):
    db = tmp_path / "app.db"
    folder = tmp_path / "backups"
    make_db(db, "старое")
    old_copy = backup.create_backup(db, folder,
                                    now=datetime(2026, 1, 1))
    make_db(db, "новое")

    safety = backup.restore_backup(old_copy, db, folder)

    assert read_db(db) == "старое"
    assert read_db(safety) == "новое"  # текущая база не потерялась


def test_log_file_and_excepthook(tmp_path):
    path = setup_logging(tmp_path)
    shown = []
    old_hook = sys.excepthook
    install_excepthook(shown.append)
    try:
        try:
            raise RuntimeError("тестовый сбой")
        except RuntimeError:
            sys.excepthook(*sys.exc_info())
    finally:
        sys.excepthook = old_hook
    for handler in logging.getLogger("freelancedesk").handlers:
        handler.flush()
    text = path.read_text(encoding="utf-8")
    assert "тестовый сбой" in text and "Traceback" in text
    assert shown == ["RuntimeError: тестовый сбой"]
