"""Русские подписи и форматирование значений для интерфейса.

Модели хранят технические значения ('delivered', 'person'), а пользователь
видит понятный текст. Подписи собраны в одном месте, чтобы не
дублировать их в разных окнах.
"""

from datetime import date
from decimal import Decimal

from freelancedesk.core.manager import OrderView, PaymentState
from freelancedesk.core.models import (
    ClientType, ContactMethod, Order, OrderStatus,
)

STATUS_LABELS = {
    OrderStatus.NEW: "Новый",
    OrderStatus.IN_PROGRESS: "В работе",
    OrderStatus.DELIVERED: "Сдан",
    OrderStatus.CANCELLED: "Отменён",
}

PAYMENT_LABELS = {
    PaymentState.UNPAID: "Не оплачен",
    PaymentState.PARTIAL: "Оплачен частично",
    PaymentState.PAID: "Оплачен",
}

CLIENT_TYPE_LABELS = {
    ClientType.PERSON: "Физлицо (НПД 4 %)",
    ClientType.COMPANY: "Юрлицо / ИП (НПД 6 %)",
}

# Короткие подписи для таблицы клиентов
CLIENT_TYPE_SHORT = {
    ClientType.PERSON: "Физлицо",
    ClientType.COMPANY: "Юрлицо / ИП",
}

CONTACT_LABELS = {
    ContactMethod.EMAIL: "Почта",
    ContactMethod.PHONE: "Телефон",
    ContactMethod.MESSENGER: "Мессенджер",
}

# Подписи фильтров на экране «Заказы» — в порядке показа
VIEW_LABELS = {
    OrderView.ACTIVE: "Активные",
    OrderView.AWAITING_PAYMENT: "Ждут оплаты",
    OrderView.OVERDUE: "Просрочено",
    OrderView.DUE_TODAY: "Сдать сегодня",
    OrderView.NO_RECEIPT: "Без чека",
    OrderView.DONE: "Завершённые",
    OrderView.ALL: "Все",
}

# Площадки для подсказки в форме клиента (можно вписать свою)
PLATFORMS = ["Kwork", "FL.ru", "Workzilla", "YouDo", "Freelance.ru",
             "Напрямую"]

MONTH_NAMES = ["январь", "февраль", "март", "апрель", "май", "июнь",
               "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
# Родительный падеж: «3 октября»
MONTH_GENITIVE = ["января", "февраля", "марта", "апреля", "мая", "июня",
                  "июля", "августа", "сентября", "октября", "ноября",
                  "декабря"]
# Предложный падеж: «в октябре»
MONTH_PREPOSITIONAL = ["январе", "феврале", "марте", "апреле", "мае",
                       "июне", "июле", "августе", "сентябре", "октябре",
                       "ноябре", "декабре"]
MONTH_SHORT = ["янв", "фев", "мар", "апр", "май", "июн",
               "июл", "авг", "сен", "окт", "ноя", "дек"]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница",
            "суббота", "воскресенье"]


def plural(n: int, forms: tuple[str, str, str]) -> str:
    """Слово в нужной форме после числа: 1 день, 2 дня, 5 дней.

    forms — (одна, две, пять): ("день", "дня", "дней").
    """
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return forms[1]
    return forms[2]


DAYS = ("день", "дня", "дней")
ORDERS = ("заказ", "заказа", "заказов")


def format_money(amount: Decimal, kopecks: bool = True) -> str:
    """1500.5 -> '1 500,50 ₽'; без копеек -> '1 501 ₽'."""
    text = f"{amount:,.2f}" if kopecks else f"{amount:,.0f}"
    # Формат Python: '1,500.50' — меняем разделители на русские
    return text.replace(",", " ").replace(".", ",") + " ₽"


def format_short_money(amount: Decimal) -> str:
    """Короткая подпись: 12500 -> '12,5к', 800 -> '800'."""
    if amount >= 1000:
        text = f"{amount / 1000:.1f}".rstrip("0").rstrip(".")
        return text.replace(".", ",") + "к"
    return f"{amount:.0f}"


def format_date(value: date | None) -> str:
    """date(2026, 10, 2) -> '02.10.2026'; None -> пустая строка."""
    return value.strftime("%d.%m.%Y") if value else ""


def format_month(first_day: date) -> str:
    """date(2026, 9, 1) -> 'сентябрь 2026'."""
    return f"{MONTH_NAMES[first_day.month - 1]} {first_day.year}"


def format_long_date(day: date) -> str:
    """date(2026, 10, 3) -> 'суббота, 3 октября'."""
    return (f"{WEEKDAYS[day.weekday()]}, {day.day} "
            f"{MONTH_GENITIVE[day.month - 1]}")


def deadline_text(order: Order, today: date) -> tuple[str, str]:
    """Срок словами и его «тон» для цвета.

    Тон: 'danger' — просрочен, 'warning' — сегодня, '' — обычный.
    """
    if order.status == OrderStatus.CANCELLED:
        return "отменён", ""
    if order.status == OrderStatus.DELIVERED:
        when = order.delivered_on.strftime("%d.%m") if order.delivered_on \
            else ""
        return f"сдан {when}".strip(), ""
    if order.deadline is None:
        return "без срока", ""
    days = (order.deadline - today).days
    if days < 0:
        return f"просрочен на {-days} {plural(days, DAYS)}", "danger"
    if days == 0:
        return "сдать сегодня", "warning"
    if days == 1:
        return "сдать завтра", ""
    return f"через {days} {plural(days, DAYS)}", ""
