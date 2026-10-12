-- Описание, ссылка и отметка о чеке для заказов (PostgreSQL).

ALTER TABLE orders
    ADD COLUMN description    TEXT         NOT NULL DEFAULT '',
    ADD COLUMN link           VARCHAR(500) NOT NULL DEFAULT '',
    ADD COLUMN receipt_issued BOOLEAN      NOT NULL DEFAULT FALSE;
