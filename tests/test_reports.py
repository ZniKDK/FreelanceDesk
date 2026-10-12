"""Тесты новых возможностей OrderManager: выборки, чеки, отчёты, налог."""

from datetime import date
from decimal import Decimal

import pytest

from freelancedesk.core.manager import (
    NO_PLATFORM, OrderManager, OrderView, add_months, month_end,
)
from freelancedesk.core.models import Client, ClientType, Order, OrderStatus
from freelancedesk.core.storage import InMemoryStorage

TODAY = date(2026, 10, 15)


@pytest.fixture
def manager() -> OrderManager:
    return OrderManager(InMemoryStorage())


def add(manager, client, title, amount="1000", **fields) -> Order:
    """Короткий способ добавить заказ в тестах."""
    return manager.add_order(
        Order(title=title, client_id=client.id, amount=Decimal(amount),
              **fields),
        today=fields.get("paid_on") or TODAY)


@pytest.fixture
def ivan(manager) -> Client:
    return manager.add_client(Client(name="Иван", platform="Kwork"))


@pytest.fixture
def firm(manager) -> Client:
    return manager.add_client(Client(name="ООО Ромашка", platform="FL.ru",
                                     client_type=ClientType.COMPANY))


# --- Даты ---

def test_add_months_crosses_year():
    assert add_months(date(2026, 11, 1), 3) == date(2027, 2, 1)
    assert add_months(date(2026, 1, 1), -1) == date(2025, 12, 1)


def test_month_end_handles_february():
    assert month_end(date(2028, 2, 1)) == date(2028, 2, 29)  # високосный
    assert month_end(date(2026, 12, 1)) == date(2026, 12, 31)


# --- Выборки и поиск ---

def test_views(manager, ivan):
    add(manager, ivan, "Просрочен", deadline=date(2026, 10, 1))
    add(manager, ivan, "Сегодня", deadline=TODAY)
    add(manager, ivan, "Без чека", status=OrderStatus.PAID)
    add(manager, ivan, "Отменён", status=OrderStatus.CANCELLED)

    def titles(view):
        return [o.title for o in manager.list_orders(view=view, today=TODAY)]

    assert titles(OrderView.ACTIVE) == ["Просрочен", "Сегодня"]
    assert titles(OrderView.OVERDUE) == ["Просрочен"]
    assert titles(OrderView.DUE_TODAY) == ["Сегодня"]
    assert titles(OrderView.NO_RECEIPT) == ["Без чека"]
    assert len(titles(OrderView.ALL)) == 4


def test_search_by_description_and_client(manager, ivan, firm):
    add(manager, ivan, "Бот", description="интеграция с CRM")
    add(manager, firm, "Лендинг")

    def found(text):
        return [o.title for o in manager.list_orders(search=text)]

    assert found("crm") == ["Бот"]
    assert found("ромаш") == ["Лендинг"]


def test_attention_counts(manager, ivan):
    add(manager, ivan, "Просрочен", deadline=date(2026, 10, 1))
    add(manager, ivan, "Сегодня", deadline=TODAY)
    add(manager, ivan, "Без чека", status=OrderStatus.PAID)
    add(manager, ivan, "С чеком", status=OrderStatus.PAID,
        receipt_issued=True)

    attention = manager.attention(TODAY)
    assert (attention.due_today, attention.overdue,
            attention.no_receipt) == (1, 1, 1)
    assert attention.total == 3


# --- Чеки и нормализация ---

def test_set_receipt_only_for_paid(manager, ivan):
    order = add(manager, ivan, "Бот")
    with pytest.raises(ValueError):
        manager.set_receipt(order.id)

    manager.change_status(order.id, OrderStatus.PAID, today=TODAY)
    assert manager.set_receipt(order.id).receipt_issued


def test_unpaying_resets_receipt(manager, ivan):
    order = add(manager, ivan, "Бот", status=OrderStatus.PAID,
                receipt_issued=True)
    changed = manager.change_status(order.id, OrderStatus.DELIVERED)
    assert changed.paid_on is None and not changed.receipt_issued


def test_same_status_keeps_payment_date(manager, ivan):
    order = add(manager, ivan, "Бот", status=OrderStatus.PAID,
                paid_on=date(2026, 10, 2))
    manager.change_status(order.id, OrderStatus.PAID, today=TODAY)
    assert manager.get_order(order.id).paid_on == date(2026, 10, 2)


def test_link_gets_scheme(manager, ivan):
    order = add(manager, ivan, "Бот", link="  kwork.ru/track/1 ")
    assert order.link == "https://kwork.ru/track/1"


def test_clients_sorted_case_insensitive(manager):
    for name in ("яндекс", "Борис", "алина"):
        manager.add_client(Client(name=name))
    assert [c.name for c in manager.list_clients()] == [
        "алина", "Борис", "яндекс"]


def test_client_stats(manager, ivan, firm):
    add(manager, ivan, "Оплачен", "1500", status=OrderStatus.PAID)
    add(manager, ivan, "В работе", "700")
    stats = manager.client_stats()
    assert stats[ivan.id].orders == 2
    assert stats[ivan.id].income == Decimal("1500")
    assert firm.id not in stats  # заказов нет — нет и строки


# --- Отчёты ---

def test_income_by_month(manager, ivan):
    add(manager, ivan, "Сентябрь", "1000", status=OrderStatus.PAID,
        paid_on=date(2026, 9, 30))
    add(manager, ivan, "Октябрь", "500", status=OrderStatus.PAID,
        paid_on=date(2026, 10, 1))
    add(manager, ivan, "Давно", "999", status=OrderStatus.PAID,
        paid_on=date(2025, 1, 1))

    months = manager.income_by_month(TODAY, months=3)

    assert months == [(date(2026, 8, 1), Decimal("0")),
                      (date(2026, 9, 1), Decimal("1000")),
                      (date(2026, 10, 1), Decimal("500"))]


def test_income_by_platform(manager, ivan, firm):
    no_platform = manager.add_client(Client(name="Пётр"))
    add(manager, ivan, "A", "1000", status=OrderStatus.PAID)
    add(manager, firm, "B", "3000", status=OrderStatus.PAID)
    add(manager, no_platform, "C", "500", status=OrderStatus.PAID)

    result = manager.income_by_platform(date(2026, 10, 1), TODAY)

    assert result == [("FL.ru", Decimal("3000")), ("Kwork", Decimal("1000")),
                      (NO_PLATFORM, Decimal("500"))]


def test_tax_due_for_previous_month(manager, ivan, firm):
    add(manager, ivan, "Сентябрь", "1000", status=OrderStatus.PAID,
        paid_on=date(2026, 9, 10))
    add(manager, firm, "Сентябрь", "2000", status=OrderStatus.PAID,
        paid_on=date(2026, 9, 20))
    add(manager, ivan, "Октябрь", "5000", status=OrderStatus.PAID,
        paid_on=date(2026, 10, 5))

    due = manager.tax_due(TODAY)

    assert due.month == date(2026, 9, 1)
    assert due.amount == Decimal("160.00")  # 1000 × 4 % + 2000 × 6 %
    assert due.due_date == date(2026, 10, 28)


def test_tax_due_in_january_is_for_december(manager):
    due = manager.tax_due(date(2027, 1, 10))
    assert due.month == date(2026, 12, 1)
    assert due.due_date == date(2027, 1, 28)
