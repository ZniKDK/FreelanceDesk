"""Чтение настроек из config/config.ini."""

import configparser
from pathlib import Path

# Корень проекта: src/freelancedesk/config.py -> на три уровня выше
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.ini"


def load_config(path: Path = CONFIG_PATH) -> configparser.ConfigParser:
    """Загрузить config.ini. Если файла нет — подсказать, откуда его взять."""
    if not path.exists():
        raise FileNotFoundError(
            f"Нет файла {path}. Скопируйте config/config.example.ini "
            "в config/config.ini и укажите параметры БД."
        )
    config = configparser.ConfigParser()
    config.read(path, encoding="utf-8")
    return config


def build_dsn(config: configparser.ConfigParser) -> str:
    """Собрать строку подключения к PostgreSQL из секции [database]."""
    db = config["database"]
    return (
        f"host={db.get('host', 'localhost')} "
        f"port={db.get('port', '5432')} "
        f"dbname={db['name']} "
        f"user={db['user']} "
        f"password={db['password']}"
    )
