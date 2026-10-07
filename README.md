# FreelanceDesk

Десктоп-приложение для учёта заказов фрилансера: клиенты, заказы, статусы, доход за период и налог самозанятого (НПД).

> Статус: в разработке (v0.1.0). Готовы бизнес-логика и хранение в PostgreSQL с тестами; интерфейс — в процессе.

## Возможности (MVP)

- Клиенты: добавление, редактирование, удаление; тип клиента — физлицо или юрлицо/ИП.
- Заказы: сумма, дедлайн, статус (новый → в работе → сдан → оплачен / отменён).
- Фильтр по статусу, поиск по названию, подсветка просроченных заказов.
- Сводка за период: доход и налог НПД (4 % с физлиц, 6 % с юрлиц и ИП).

## Стек

Python 3.11+, PyQt6, PostgreSQL (psycopg 3), pytest.

## Установка и запуск

```powershell
git clone https://github.com/ZniKDK/FreelanceDesk.git
cd FreelanceDesk
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

### База данных (PostgreSQL 14+)

1. Создайте пользователя и базу (в `psql` под `postgres`):
   ```sql
   CREATE ROLE freelancedesk LOGIN PASSWORD 'ваш_пароль';
   CREATE DATABASE freelancedesk OWNER freelancedesk;
   CREATE DATABASE freelancedesk_test OWNER freelancedesk;  -- для тестов
   ```
2. Скопируйте `config/config.example.ini` в `config/config.ini` и укажите пароль.
3. Примените миграции:
   ```powershell
   $env:PYTHONPATH = "src"
   python -m freelancedesk.migrate
   ```

Если база недоступна, приложение запускается в режиме «в памяти» (данные не сохраняются).

## Тесты

```powershell
pytest
```

Тесты `tests/test_db_storage.py` работают с базой `freelancedesk_test` и пропускаются, если она недоступна.

## Структура

```
src/freelancedesk/
├── core/          # логика без Qt: модели, хранилища, OrderManager
└── app/           # интерфейс на PyQt6
tests/             # unit-тесты
migrations/        # SQL-миграции (применяет freelancedesk.migrate)
config/            # шаблон настроек
docs/              # архитектура
```

Подробнее — в [docs/architecture.md](docs/architecture.md).

## Лицензия

MIT
