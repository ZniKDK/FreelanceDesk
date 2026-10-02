# Архитектура FreelanceDesk

## Слои

```
MainWindow, диалоги (freelancedesk.app, PyQt6)
        │  вызывает методы
        ▼
OrderManager (freelancedesk.core.manager) — проверки, статусы, доход, налог
        │  работает через интерфейс Storage
        ▼
Storage ── InMemoryStorage (тесты, демо)
       └── DbStorage ──► PostgreSQL (схема: migrations/001_init.sql)
```

## Модули

| Модуль | Классы | Назначение |
|---|---|---|
| `core/models.py` | `Client`, `Order`, `ClientType`, `OrderStatus` | Данные предметной области |
| `core/storage.py` | `Storage`, `InMemoryStorage`, `DbStorage` | Сохранение и загрузка данных |
| `core/manager.py` | `OrderManager`, `PeriodSummary` | Бизнес-логика |
| `app/main_window.py` | `MainWindow` | Главное окно |
| `app/dialogs.py` | `ClientDialog`, `OrderDialog` | Формы ввода |
| `config.py` | — | Чтение `config/config.ini` |

## Правила

- `core` не импортирует Qt: логику можно тестировать без интерфейса.
- `OrderManager` не знает, где лежат данные, — он получает `Storage` в конструкторе.
- Налог НПД: 4 % с оплат от физлиц, 6 % — от юрлиц и ИП.
