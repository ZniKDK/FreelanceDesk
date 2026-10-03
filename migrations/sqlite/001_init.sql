-- Начальная схема БД FreelanceDesk (SQLite).
-- Отличия от PostgreSQL: нет SERIAL и NUMERIC с точностью,
-- поэтому id — INTEGER PRIMARY KEY, сумма и даты хранятся текстом.

CREATE TABLE clients (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    client_type TEXT NOT NULL DEFAULT 'person'
                CHECK (client_type IN ('person', 'company')),
    contact     TEXT NOT NULL DEFAULT '',
    platform    TEXT NOT NULL DEFAULT '',
    note        TEXT NOT NULL DEFAULT ''
);

CREATE TABLE orders (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    title     TEXT    NOT NULL,
    client_id INTEGER NOT NULL REFERENCES clients (id),
    -- Сумма строкой ('1500.50'): Decimal без ошибок округления float
    amount    TEXT    NOT NULL CHECK (CAST(amount AS REAL) >= 0),
    deadline  TEXT,   -- дата в формате ГГГГ-ММ-ДД, сортируется как текст
    status    TEXT    NOT NULL DEFAULT 'new'
              CHECK (status IN ('new', 'in_progress', 'delivered',
                                'paid', 'cancelled')),
    paid_on   TEXT
);

CREATE INDEX idx_orders_client ON orders (client_id);
CREATE INDEX idx_orders_paid_on ON orders (paid_on);
