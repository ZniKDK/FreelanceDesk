"""Русские подписи для перечислений и форматирование значений в интерфейсе.

Модели хранят технические значения ('paid', 'person'), а пользователь
видит понятный текст. Подписи собраны в одном месте, чтобы не
дублировать их в разных окнах.
"""

from datetime import date
from decimal import Decimal

from freelancedesk.core.manager import OrderView
from freelancedesk.core.models import ClientType, OrderStatus

STATUS_LABELS = {
    OrderStatus.NEW: "Новый",
    OrderStatus.IN_PROGRESS: "В работе",
    OrderStatus.DELIVERED: "Сдан",
    OrderStatus.PAID: "Оплачен",
    OrderStatus.CANCELLED: "Отменён",
}

CLIENT_TYPE_LABELS = {
    ClientType.PERSON: "Физлицо (НПД 4 %)",
    ClientType.COMPANY: "Юрлицо / ИП (НПД 6 %)",
}

VIEW_LABELS = {
    OrderView.ACTIVE: "Активные",
    OrderView.ALL: "Все заказы",
    OrderView.OVERDUE: "Просроченные",
    OrderView.DUE_TODAY: "Сдать сегодня",
    OrderView.NO_RECEIPT: "Оплачены без чека",
}

# Площадки для подсказки в форме клиента (можно вписать свою)
PLATFORMS = ["Kwork", "FL.ru", "Workzilla", "YouDo", "Freelance.ru",
             "Напрямую"]

MONTH_NAMES = ["январь", "февраль", "март", "апрель", "май", "июнь",
               "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
MONTH_SHORT = ["янв", "фев", "мар", "апр", "май", "июн",
               "июл", "авг", "сен", "окт", "ноя", "дек"]


def format_money(amount: Decimal) -> str:
    """1500.5 -> '1 500,50 ₽' (пробел между тысячами, запятая в копейках)."""
    text = f"{amount:,.2f}"  # '1,500.50' — формат Python по умолчанию
    return text.replace(",", " ").replace(".", ",") + " ₽"


def format_short_money(amount: Decimal) -> str:
    """Короткая подпись для диаграммы: 12500 -> '12,5к', 800 -> '800'."""
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
