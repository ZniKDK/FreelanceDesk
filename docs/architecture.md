# Архитектура FreelanceDesk

## Слои

```
Экраны и формы (freelancedesk.app, PyQt6)
  MainWindow ── боковое меню ── DashboardPage, OrdersPage, ClientsPage, FinancePage
        │  вызывают методы
        ▼
OrderManager (freelancedesk.core.manager) — проверки, статусы, платежи,
        │                                   деньги по заказу, отчёты, налог
        │  работает через интерфейс Storage
        ▼
Storage ── InMemoryStorage (тесты, запуск без БД)
       └── SqlStorage (общие SQL-запросы)
              ├── SqliteStorage ──► файл SQLite (по умолчанию)
              └── DbStorage ──────► PostgreSQL
```

## Модель данных

```
Client 1 ──< Order 1 ──< Payment
```

- `Order.status` — статус работы: новый, в работе, сдан, отменён. Меняется пользователем.
- `Payment` — поступление денег: сумма, дата, отметка о чеке. У заказа их может быть несколько (предоплата, остаток).
- Состояние оплаты (`PaymentState`: не оплачен, частично, оплачен) не хранится, а вычисляется из платежей.
- Налог НПД начисляется с каждого платежа по ставке клиента (4 % физлицо, 6 % юрлицо/ИП) и относится к месяцу даты платежа.

## Модули

| Модуль | Классы | Назначение |
|---|---|---|
| `core/models.py` | `Client`, `Order`, `Payment`, `ClientType`, `OrderStatus` | Данные предметной области |
| `core/storage.py` | `Storage`, `InMemoryStorage` | Интерфейс хранилища и хранилище в памяти |
| `core/sql_storage.py` | `SqlStorage`, `SqliteStorage`, `DbStorage` | Хранение в SQLite и PostgreSQL |
| `core/manager.py` | `OrderManager`, `OrderMoney`, `PaymentState`, `OrderView`, `PeriodSummary`, `TaxDue` | Бизнес-логика, деньги, выборки, отчёты, налог |
| `app/main_window.py` | `MainWindow` | Окно, боковое меню, общие услуги для экранов |
| `app/pages/dashboard.py` | `DashboardPage` | Главная: деньги за месяц, налог, что горит, сроки |
| `app/pages/orders.py` | `OrdersPage`, `OrderRow`, `OrderPanel` | Список заказов и карточка с платежами |
| `app/pages/clients.py` | `ClientsPage` | Клиенты |
| `app/pages/finance.py` | `FinancePage` | Поступления за период, диаграмма, журнал платежей |
| `app/dialogs.py` | `ClientDialog`, `OrderDialog`, `PaymentDialog` | Формы ввода |
| `app/widgets.py` | `Card`, `StatCard`, `BarChart`, `SortItem` | Общие виджеты |
| `app/theme.py` | — | Цвета, стили QSS, иконки Lucide |
| `app/labels.py` | — | Русские подписи, деньги, даты, сроки словами |
| `config.py` | — | Папка данных пользователя, `config.ini`, выбор хранилища |
| `migrate.py` | — | Применение SQL-миграций, учёт в `schema_migrations` |

## Правила

- `core` не импортирует Qt: логику можно тестировать без интерфейса.
- `OrderManager` не знает, где лежат данные, — он получает `Storage` в конструкторе.
- Экраны не меняют данные напрямую: всё через `MainWindow.run`, который показывает ошибку окном и обновляет все экраны.
- Все SQL-запросы параметризованы (`%s`) — защита от SQL-инъекций.
- Схема БД меняется только новыми файлами в `migrations/sqlite/` и `migrations/postgresql/` с одинаковыми номерами; старые файлы не правятся. Миграции применяются при запуске.
