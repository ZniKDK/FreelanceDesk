-- Оплата отделена от статуса работы (SQLite).
-- Вместо даты оплаты и чека в заказе — таблица платежей:
-- у заказа может быть несколько поступлений (предоплата, остаток).

CREATE TABLE payments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id       INTEGER NOT NULL REFERENCES orders (id),
    amount         TEXT    NOT NULL CHECK (CAST(amount AS REAL) > 0),
    paid_on        TEXT    NOT NULL,   -- ГГГГ-ММ-ДД
    receipt_issued INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_payments_order ON payments (order_id);
CREATE INDEX idx_payments_paid_on ON payments (paid_on);

-- Каждый оплаченный заказ превращается в один платёж на всю сумму
INSERT INTO payments (order_id, amount, paid_on, receipt_issued)
SELECT id, amount, COALESCE(paid_on, date('now')), receipt_issued
FROM orders
WHERE status = 'paid' AND CAST(amount AS REAL) > 0;

-- Дата сдачи работы; у бывших «оплаченных» считаем её датой оплаты
ALTER TABLE orders ADD COLUMN delivered_on TEXT;
UPDATE orders SET delivered_on = paid_on, status = 'delivered'
WHERE status = 'paid';

-- Старые колонки больше не нужны (сначала удаляем индекс на paid_on)
DROP INDEX idx_orders_paid_on;
ALTER TABLE orders DROP COLUMN paid_on;
ALTER TABLE orders DROP COLUMN receipt_issued;
