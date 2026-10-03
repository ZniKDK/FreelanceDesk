-- Контакты клиента по отдельности (SQLite): почта, телефон, мессенджер
-- и предпочтительный способ связи. Старое поле contact раскладывается
-- по новым полям по виду значения.

ALTER TABLE clients ADD COLUMN email TEXT NOT NULL DEFAULT '';
ALTER TABLE clients ADD COLUMN phone TEXT NOT NULL DEFAULT '';
ALTER TABLE clients ADD COLUMN messenger TEXT NOT NULL DEFAULT '';
ALTER TABLE clients ADD COLUMN messenger_app TEXT NOT NULL DEFAULT '';
-- '' — не выбран, иначе 'email', 'phone' или 'messenger'
ALTER TABLE clients ADD COLUMN preferred_contact TEXT NOT NULL DEFAULT '';

-- Похоже на почту: есть «@» в середине и точка после него, нет пробелов
UPDATE clients
SET email = trim(contact), preferred_contact = 'email'
WHERE trim(contact) LIKE '_%@_%._%'
  AND trim(contact) NOT LIKE '@%'
  AND trim(contact) NOT LIKE '% %';

-- Похоже на телефон: только цифры, пробелы и знаки + ( ) -
UPDATE clients
SET phone = trim(contact), preferred_contact = 'phone'
WHERE email = '' AND trim(contact) GLOB '*[0-9]*'
  AND trim(contact) NOT GLOB '*[^0-9+() -]*';

-- Остальное — мессенджер; ник с «@» или ссылка t.me — это Telegram
UPDATE clients
SET messenger = trim(contact), preferred_contact = 'messenger',
    messenger_app = CASE
        WHEN trim(contact) LIKE '@%' OR contact LIKE '%t.me/%'
        THEN 'Telegram' ELSE '' END
WHERE email = '' AND phone = '' AND trim(contact) <> '';

ALTER TABLE clients DROP COLUMN contact;
