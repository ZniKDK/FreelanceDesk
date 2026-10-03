"""Тесты настроек: папка данных, config.ini по умолчанию, путь к SQLite."""

from freelancedesk.config import (
    app_dir, build_dsn, load_config, sqlite_path, storage_backend,
)


def test_app_dir_can_be_overridden(monkeypatch, tmp_path):
    monkeypatch.setenv("FREELANCEDESK_HOME", str(tmp_path))
    assert app_dir() == tmp_path


def test_first_run_creates_sqlite_config(tmp_path):
    path = tmp_path / "sub" / "config.ini"
    config = load_config(path)

    assert path.exists()  # файл создан, его можно править руками
    assert storage_backend(config) == "sqlite"
    assert sqlite_path(config, tmp_path) == tmp_path / "freelancedesk.db"


def test_custom_settings_are_read(tmp_path):
    path = tmp_path / "config.ini"
    path.write_text(
        "[storage]\nbackend = PostgreSQL\n"
        "[sqlite]\npath = D:/data/my.db\n"
        "[database]\nname = fd\nuser = u\npassword = p\n",
        encoding="utf-8")
    config = load_config(path)

    assert storage_backend(config) == "postgresql"  # регистр не важен
    assert sqlite_path(config, tmp_path).as_posix() == "D:/data/my.db"
    assert "dbname=fd" in build_dsn(config)
    assert "dbname=fd_test" in build_dsn(config, dbname="fd_test")
