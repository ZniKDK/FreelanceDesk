-- Описание, ссылка и отметка о чеке для заказов (SQLite).
-- SQLite добавляет только по одной колонке за команду.

ALTER TABLE orders ADD COLUMN description TEXT NOT NULL DEFAULT '';
ALTER TABLE orders ADD COLUMN link TEXT NOT NULL DEFAULT '';
-- В SQLite нет BOOLEAN: 0 — нет, 1 — да
ALTER TABLE orders ADD COLUMN receipt_issued INTEGER NOT NULL DEFAULT 0;
