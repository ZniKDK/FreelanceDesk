"""Тесты моделей."""

from datetime import date
from decimal import Decimal

from freelancedesk.core.models import Order, OrderStatus

TODAY = date(2026, 10, 2)


def make_order(**kwargs) -> Order:
    defaults = {"title": "Бот", "client_id": 1, "amount": Decimal("1000")}
    defaults.update(kwargs)
    return Order(**defaults)


def test_order_without_deadline_is_not_overdue():
    assert not make_order().is_overdue(TODAY)


def test_open_order_after_deadline_is_overdue():
    order = make_order(deadline=date(2026, 10, 1))
    assert order.is_overdue(TODAY)


def test_delivered_order_is_not_overdue():
    order = make_order(deadline=date(2026, 10, 1),
                       status=OrderStatus.DELIVERED)
    assert not order.is_overdue(TODAY)


def test_deadline_today_is_not_overdue():
    assert not make_order(deadline=TODAY).is_overdue(TODAY)


def test_due_today_only_for_open_orders():
    assert make_order(deadline=TODAY).is_due_on(TODAY)
    assert not make_order(deadline=TODAY,
                          status=OrderStatus.DELIVERED).is_due_on(TODAY)


def test_needs_receipt_only_when_paid_without_receipt():
    assert make_order(status=OrderStatus.PAID).needs_receipt()
    assert not make_order(status=OrderStatus.PAID,
                          receipt_issued=True).needs_receipt()
    assert not make_order(status=OrderStatus.DELIVERED).needs_receipt()
