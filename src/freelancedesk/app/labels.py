"""Русские подписи для перечислений и форматирование значений в интерфейсе.

Модели хранят технические значения ('paid', 'person'), а пользователь
видит понятный текст. Подписи собраны в одном месте, чтобы не
дублировать их в разных окнах.
"""

from datetime import date
from decimal import Decimal

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


def format_money(amount: Decimal) -> str:
    """1500.5 -> '1 500,50 ₽' (пробел между тысячами, запятая в копейках)."""
    text = f"{amount:,.2f}"  # '1,500.50' — формат Python по умолчанию
    return text.replace(",", " ").replace(".", ",") + " ₽"


def format_date(value: date | None) -> str:
    """date(2026, 10, 2) -> '02.10.2026'; None -> пустая строка."""
    return value.strftime("%d.%m.%Y") if value else ""
