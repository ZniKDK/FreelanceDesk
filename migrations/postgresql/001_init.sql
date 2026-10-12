-- Начальная схема БД FreelanceDesk (PostgreSQL).

CREATE TABLE clients (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    client_type VARCHAR(20)  NOT NULL DEFAULT 'person'
                CHECK (client_type IN ('person', 'company')),
    contact     VARCHAR(200) NOT NULL DEFAULT '',
    platform    VARCHAR(100) NOT NULL DEFAULT '',
    note        TEXT         NOT NULL DEFAULT ''
);

CREATE TABLE orders (
    id        SERIAL PRIMARY KEY,
    title     VARCHAR(300)   NOT NULL,
    client_id INTEGER        NOT NULL REFERENCES clients (id),
    amount    NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    deadline  DATE,
    status    VARCHAR(20)    NOT NULL DEFAULT 'new'
              CHECK (status IN ('new', 'in_progress', 'delivered',
                                'paid', 'cancelled')),
    paid_on   DATE
);

CREATE INDEX idx_orders_client ON orders (client_id);
CREATE INDEX idx_orders_paid_on ON orders (paid_on);
