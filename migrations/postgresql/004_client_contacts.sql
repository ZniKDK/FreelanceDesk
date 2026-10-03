-- Контакты клиента по отдельности (PostgreSQL): почта, телефон,
-- мессенджер и предпочтительный способ связи. Старое поле contact
-- раскладывается по новым полям по виду значения.

ALTER TABLE clients
    ADD COLUMN email             VARCHAR(200) NOT NULL DEFAULT '',
    ADD COLUMN phone             VARCHAR(50)  NOT NULL DEFAULT '',
    ADD COLUMN messenger         VARCHAR(200) NOT NULL DEFAULT '',
    ADD COLUMN messenger_app     VARCHAR(50)  NOT NULL DEFAULT '',
    ADD COLUMN preferred_contact VARCHAR(20)  NOT NULL DEFAULT ''
        CHECK (preferred_contact IN ('', 'email', 'phone', 'messenger'));

-- Похоже на почту: «что-то@что-то.что-то» без пробелов
UPDATE clients
SET email = trim(contact), preferred_contact = 'email'
WHERE trim(contact) ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$';

-- Похоже на телефон: только цифры, пробелы и знаки + ( ) -
UPDATE clients
SET phone = trim(contact), preferred_contact = 'phone'
WHERE email = '' AND trim(contact) ~ '^[0-9+() -]+$'
  AND trim(contact) ~ '[0-9]';

-- Остальное — мессенджер; ник с «@» или ссылка t.me — это Telegram
UPDATE clients
SET messenger = trim(contact), preferred_contact = 'messenger',
    messenger_app = CASE
        WHEN trim(contact) LIKE '@%' OR contact LIKE '%t.me/%'
        THEN 'Telegram' ELSE '' END
WHERE email = '' AND phone = '' AND trim(contact) <> '';

ALTER TABLE clients DROP COLUMN contact;
