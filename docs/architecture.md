# Архитектура FreelanceDesk

## Слои

```
MainWindow, диалоги (freelancedesk.app, PyQt6)
        │  вызывает методы
        ▼
OrderManager (freelancedesk.core.manager) — проверки, статусы, доход, налог
        │  работает через интерфейс Storage
        ▼
Storage ── InMemoryStorage (тесты, запуск без БД)
       └── SqlStorage (общие SQL-запросы)
              ├── SqliteStorage ──► файл SQLite (по умолчанию)
              └── DbStorage ──────► PostgreSQL
```

## Модули

| Модуль | Классы | Назначение |
|---|---|---|
| `core/models.py` | `Client`, `Order`, `ClientType`, `OrderStatus` | Данные предметной области |
| `core/storage.py` | `Storage`, `InMemoryStorage` | Интерфейс хранилища и хранилище в памяти |
| `core/sql_storage.py` | `SqlStorage`, `SqliteStorage`, `DbStorage` | Хранение в SQLite и PostgreSQL |
| `core/manager.py` | `OrderManager`, `OrderView`, `PeriodSummary`, `Attention`, `TaxDue` | Бизнес-логика, выборки, отчёты, налог |
| `app/main_window.py` | `MainWindow` | Главное окно |
| `app/dialogs.py` | `ClientDialog`, `OrderDialog` | Формы ввода |
| `app/labels.py` | — | Русские подписи статусов и типов, формат денег и дат |
| `app/widgets.py` | `SortItem`, `BarChart`, `AttentionBanner` | Сортируемые ячейки, диаграмма, плашка «Требует внимания» |
| `config.py` | — | Папка данных пользователя, чтение `config.ini`, выбор хранилища |
| `migrate.py` | — | Применение SQL-миграций, учёт в `schema_migrations` |

## Правила

- `core` не импортирует Qt: логику можно тестировать без интерфейса.
- `OrderManager` не знает, где лежат данные, — он получает `Storage` в конструкторе.
- Налог НПД: 4 % с оплат от физлиц, 6 % — от юрлиц и ИП.
- Все SQL-запросы параметризованы (`%s`) — защита от SQL-инъекций.
- Схема БД меняется только новыми файлами в `migrations/sqlite/` и `migrations/postgresql/` с одинаковыми номерами; старые файлы не правятся. Миграции применяются при запуске.
- Интерфейс не проверяет бизнес-правила сам: ошибки `OrderManager` (`ValueError`) и БД (`psycopg.Error`) показываются окном через `MainWindow._run`.
