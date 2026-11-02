"""Тестовые данные: клиенты, заказы и платежи за последний год.

Запуск: python -m freelancedesk.demo
Данные добавляются в базу из настроек (как у программы). Повторный
запуск ничего не дублирует: если демо-клиенты уже есть, команда
завершится без изменений.

Пригодится, чтобы посмотреть программу «в работе» и сделать скриншоты.
"""

from datetime import date, timedelta
from decimal import Decimal

from freelancedesk.core.manager import OrderManager, add_months, month_start
from freelancedesk.core.models import (
    Client, ClientType, ContactMethod, Order, OrderStatus, Payment,
)

# Пометка в заметке, по которой демо-клиентов можно узнать
DEMO_MARK = "[демо]"

CLIENTS = [
    Client("Салон красоты «Лиса»", platform="Kwork", email="lisa@mail.ru",
           phone="+7 915 123-45-67", preferred_contact=ContactMethod.EMAIL,
           note=f"{DEMO_MARK} Постоянный клиент. Заказывает ботов и "
                "лендинги, платит без задержек. Любит созвоны по вечерам."),
    Client("Иван Петров", platform="Kwork", messenger="@ivan_dev",
           messenger_app="Telegram",
           preferred_contact=ContactMethod.MESSENGER,
           note=f"{DEMO_MARK} Стартап, часто меняет ТЗ."),
    Client("ООО «Ромашка»", ClientType.COMPANY, platform="Напрямую",
           email="info@romashka.ru", phone="+7 495 000-00-00",
           messenger="+7 900 000-00-00", messenger_app="WhatsApp",
           preferred_contact=ContactMethod.PHONE,
           note=f"{DEMO_MARK} Платят по счёту, нужен чек на юрлицо (6 %)."),
    Client("Анна Смирнова", platform="FL.ru", email="anna.s@yandex.ru",
           preferred_contact=ContactMethod.EMAIL,
           note=f"{DEMO_MARK} Интернет-магазин одежды."),
    Client("ИП Кузнецов", ClientType.COMPANY, platform="Workzilla",
           phone="+7 926 555-12-12", messenger="@kuznetsov_shop",
           messenger_app="Telegram",
           preferred_contact=ContactMethod.MESSENGER,
           note=f"{DEMO_MARK} Парсеры цен конкурентов, раз в квартал."),
    Client("Студия «Пиксель»", platform="FL.ru", email="hello@pixel.studio",
           messenger="pixel_studio", messenger_app="VK",
           note=f"{DEMO_MARK} Подряд на вёрстку."),
]

# Готовые заказы прошлых месяцев: (клиент, название, цена, месяцев назад)
HISTORY = [
    (0, "Telegram-бот записи клиентов", "15000", 11),
    (3, "Парсер каталога поставщика", "8000", 10),
    (2, "Скрипт выгрузки заказов в Excel", "12000", 9),
    (1, "Лендинг для мобильного приложения", "21000", 8),
    (5, "Вёрстка страницы «О нас»", "9500", 7),
    (4, "Парсер цен конкурентов", "18000", 6),
    (0, "Бот-напоминание о визите", "26000", 5),
    (3, "Автоматизация отчётов в Google Таблицах", "14000", 4),
    (2, "Интеграция сайта с CRM", "31000", 3),
    (1, "Доработка админ-панели", "22000", 2),
    (5, "Вёрстка лендинга акции", "27500", 1),
]


def demo_present(manager: OrderManager) -> bool:
    """Демо-данные уже добавлены?"""
    return any(DEMO_MARK in c.note for c in manager.list_clients())


def seed(manager: OrderManager, today: date | None = None) -> int:
    """Добавить тестовые данные. Возвращает число созданных заказов."""
    today = today or date.today()
    if demo_present(manager):
        return 0
    clients = [manager.add_client(c) for c in CLIENTS]
    created = 0

    def order(client_index: int, title: str, price: str, **fields) -> Order:
        nonlocal created
        created += 1
        return manager.add_order(
            Order(title=title, client_id=clients[client_index].id,
                  amount=Decimal(price), **fields), today=today)

    def pay(target: Order, amount: str, day: date,
            receipt: bool = True) -> None:
        manager.add_payment(Payment(order_id=target.id,
                                    amount=Decimal(amount), paid_on=day,
                                    receipt_issued=receipt))

    # Прошлые месяцы: заказы сданы и оплачены, чеки выбиты
    for client_index, title, price, months_ago in HISTORY:
        month = add_months(month_start(today), -months_ago)
        done = order(client_index, title, price,
                     status=OrderStatus.DELIVERED,
                     deadline=month.replace(day=12),
                     delivered_on=month.replace(day=10))
        if int(price) >= 20000:  # крупные — с предоплатой 50 %
            half = str(Decimal(price) / 2)
            pay(done, half, month.replace(day=2))
            pay(done, half, month.replace(day=11))
        else:
            pay(done, price, month.replace(day=11))

    # Текущие дела: всё, что бывает в жизни
    bot = order(0, "Telegram-бот для записи к мастерам", "15000",
                status=OrderStatus.IN_PROGRESS,
                deadline=today - timedelta(days=2),
                link="https://kwork.ru/track/123456",
                description="Запись к мастерам, напоминания за сутки, "
                            "выгрузка в Google Таблицы.")
    pay(bot, "7500", today - timedelta(days=12))   # предоплата
    order(1, "Правки на лендинге", "2500", status=OrderStatus.IN_PROGRESS,
          deadline=today, description="Поменять тексты и форму заявки.")
    parser = order(2, "Парсер маркетплейса", "12500",
                   status=OrderStatus.DELIVERED,
                   deadline=today - timedelta(days=3),
                   delivered_on=today - timedelta(days=3))
    pay(parser, "12500", today - timedelta(days=1), receipt=False)  # без чека
    order(3, "Сайт-визитка магазина", "20000", status=OrderStatus.DELIVERED,
          deadline=today - timedelta(days=4),
          delivered_on=today - timedelta(days=4))  # ждёт оплаты
    order(2, "Скрипт выгрузки остатков в Excel", "7000",
          deadline=today + timedelta(days=5))
    order(4, "Чат-бот поддержки", "18000", deadline=today + timedelta(days=12),
          description="Ответы на частые вопросы, передача оператору.")
    order(5, "Вёрстка email-рассылки", "4000", status=OrderStatus.CANCELLED,
          description="Клиент передумал.")
    return created


def main() -> None:
    from freelancedesk.__main__ import open_storage
    from freelancedesk.config import app_dir, load_config

    data_dir = app_dir()
    storage, label = open_storage(load_config(data_dir / "config.ini"),
                                  data_dir)
    manager = OrderManager(storage)
    created = seed(manager)
    if hasattr(storage, "close"):  # у хранилища в памяти закрывать нечего
        storage.close()
    if created:
        print(f"Добавлено: {len(CLIENTS)} клиентов, {created} заказов "
              f"({label}).")
    else:
        print("Демо-данные уже есть — ничего не добавлено.")


if __name__ == "__main__":
    main()
