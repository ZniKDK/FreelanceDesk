-- Оплата отделена от статуса работы (PostgreSQL).
-- Вместо даты оплаты и чека в заказе — таблица платежей:
-- у заказа может быть несколько поступлений (предоплата, остаток).

CREATE TABLE payments (
    id             SERIAL PRIMARY KEY,
    order_id       INTEGER        NOT NULL REFERENCES orders (id),
    amount         NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    paid_on        DATE           NOT NULL,
    receipt_issued BOOLEAN        NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_payments_order ON payments (order_id);
CREATE INDEX idx_payments_paid_on ON payments (paid_on);

-- Каждый оплаченный заказ превращается в один платёж на всю сумму
INSERT INTO payments (order_id, amount, paid_on, receipt_issued)
SELECT id, amount, COALESCE(paid_on, CURRENT_DATE), receipt_issued
FROM orders
WHERE status = 'paid' AND amount > 0;

-- Дата сдачи работы; у бывших «оплаченных» считаем её датой оплаты
ALTER TABLE orders ADD COLUMN delivered_on DATE;
UPDATE orders SET delivered_on = paid_on, status = 'delivered'
WHERE status = 'paid';

-- Статуса «оплачен» у работы больше нет
ALTER TABLE orders DROP CONSTRAINT orders_status_check;
ALTER TABLE orders ADD CONSTRAINT orders_status_check
    CHECK (status IN ('new', 'in_progress', 'delivered', 'cancelled'));

-- Старые колонки больше не нужны (индекс на paid_on удалится сам)
ALTER TABLE orders DROP COLUMN paid_on, DROP COLUMN receipt_issued;
