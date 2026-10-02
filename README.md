# FreelanceDesk

Десктоп-приложение для учёта заказов фрилансера: клиенты, заказы, статусы, доход за период и налог самозанятого (НПД).

> Статус: в разработке (v0.1.0). Готова бизнес-логика с тестами, интерфейс и работа с БД — в процессе.

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

Для работы с PostgreSQL:

1. Создайте базу `freelancedesk` и выполните `migrations/001_init.sql`.
2. Скопируйте `config/config.example.ini` в `config/config.ini` и укажите параметры подключения.

## Тесты

```powershell
pytest
```

## Структура

```
src/freelancedesk/
├── core/          # логика без Qt: модели, хранилища, OrderManager
└── app/           # интерфейс на PyQt6
tests/             # unit-тесты
migrations/        # SQL-схема БД
config/            # шаблон настроек
docs/              # архитектура
```

Подробнее — в [docs/architecture.md](docs/architecture.md).

## Лицензия

MIT
