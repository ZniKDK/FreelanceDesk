"""Тесты платежей, денег по заказу, отчётов и налога НПД."""

from datetime import date
from decimal import Decimal

import pytest

from freelancedesk.core.manager import (
    NO_PLATFORM, OrderManager, PaymentState, add_months, month_end,
)
from freelancedesk.core.models import (
    Client, ClientType, Order, OrderStatus, Payment,
)
from freelancedesk.core.storage import InMemoryStorage

TODAY = date(2026, 10, 15)


@pytest.fixture
def manager() -> OrderManager:
    return OrderManager(InMemoryStorage())


@pytest.fixture
def ivan(manager) -> Client:
    return manager.add_client(Client(name="Иван", platform="Kwork"))


@pytest.fixture
def firm(manager) -> Client:
    return manager.add_client(Client(name="ООО Ромашка", platform="FL.ru",
                                     client_type=ClientType.COMPANY))


def order_for(manager, client, amount="1000", **fields) -> Order:
    return manager.add_order(Order(title="Заказ", client_id=client.id,
                                   amount=Decimal(amount), **fields),
                             today=TODAY)


def pay(manager, order, amount, paid_on=TODAY, receipt=False) -> Payment:
    return manager.add_payment(Payment(order_id=order.id,
                                       amount=Decimal(amount),
                                       paid_on=paid_on,
                                       receipt_issued=receipt))


# --- Даты ---

def test_add_months_crosses_year():
    assert add_months(date(2026, 11, 1), 3) == date(2027, 2, 1)
    assert add_months(date(2026, 1, 1), -1) == date(2025, 12, 1)


def test_month_end_handles_february():
    assert month_end(date(2028, 2, 1)) == date(2028, 2, 29)  # високосный
    assert month_end(date(2026, 12, 1)) == date(2026, 12, 31)


# --- Платежи ---

def test_payment_must_be_positive(manager, ivan):
    order = order_for(manager, ivan)
    with pytest.raises(ValueError):
        pay(manager, order, "0")


def test_payment_for_missing_order_rejected(manager):
    with pytest.raises(ValueError):
        manager.add_payment(Payment(order_id=99, amount=Decimal("1"),
                                    paid_on=TODAY))


def test_set_receipt(manager, ivan):
    payment = pay(manager, order_for(manager, ivan), "500")
    assert manager.set_receipt(payment.id).receipt_issued
    assert not manager.set_receipt(payment.id, False).receipt_issued


def test_update_and_delete_payment(manager, ivan):
    order = order_for(manager, ivan)
    payment = pay(manager, order, "500")
    payment.amount = Decimal("700")
    manager.update_payment(payment)
    assert manager.money(order.id).received == Decimal("700")

    manager.delete_payment(payment.id)
    assert manager.payments_for(order.id) == []


# --- Деньги по заказу ---

def test_money_unpaid(manager, ivan):
    money = manager.money(order_for(manager, ivan, "15000").id)
    assert money.state == PaymentState.UNPAID
    assert money.remaining == Decimal("15000")
    assert money.progress == 0


def test_money_partial_prepayment(manager, ivan):
    order = order_for(manager, ivan, "15000")
    pay(manager, order, "7500", receipt=True)

    money = manager.money(order.id)

    assert money.state == PaymentState.PARTIAL
    assert money.received == Decimal("7500")
    assert money.remaining == Decimal("7500")
    assert money.tax == Decimal("300.00")      # 7500 × 4 %
    assert money.net == Decimal("7200.00")
    assert money.progress == 0.5
    assert money.without_receipt == 0


def test_money_paid_in_two_parts_company(manager, firm):
    order = order_for(manager, firm, "10000")
    pay(manager, order, "5000", date(2026, 9, 20), receipt=True)
    pay(manager, order, "5000", TODAY)

    money = manager.money(order.id)

    assert money.state == PaymentState.PAID
    assert money.tax == Decimal("600.00")      # 10 000 × 6 %
    assert money.without_receipt == 1


def test_overpayment_is_not_negative_debt(manager, ivan):
    order = order_for(manager, ivan, "1000")
    pay(manager, order, "1200")  # клиент добавил чаевые
    money = manager.money(order.id)
    assert money.remaining == 0 and money.progress == 1.0


def test_payment_tax(manager, ivan, firm):
    assert manager.payment_tax(pay(manager, order_for(manager, ivan),
                                   "333")) == Decimal("13.32")
    assert manager.payment_tax(pay(manager, order_for(manager, firm),
                                   "333")) == Decimal("19.98")


def test_awaiting_payment(manager, ivan):
    delivered = order_for(manager, ivan, "20000",
                          status=OrderStatus.DELIVERED)
    pay(manager, delivered, "5000")
    order_for(manager, ivan, "9000")  # ещё в работе — не считается

    awaiting = manager.awaiting_payment()

    assert awaiting.orders == 1
    assert awaiting.amount == Decimal("15000")


# --- Отчёты ---

def test_summary_counts_payments_by_date(manager, ivan, firm):
    # Налог считается по дате поступления денег, а не по заказу
    september = order_for(manager, ivan, "3000")
    pay(manager, september, "1000", date(2026, 9, 30))
    pay(manager, september, "2000", date(2026, 10, 1))
    pay(manager, order_for(manager, firm), "1000", date(2026, 10, 5))

    result = manager.summary(date(2026, 10, 1), date(2026, 10, 31))

    assert result.income == Decimal("3000")
    assert result.tax == Decimal("140.00")     # 2000 × 4 % + 1000 × 6 %
    assert result.net == Decimal("2860.00")
    assert result.payments == 2


def test_income_by_month(manager, ivan):
    order = order_for(manager, ivan, "5000")
    pay(manager, order, "1000", date(2026, 9, 30))
    pay(manager, order, "500", date(2026, 10, 1))
    pay(manager, order, "999", date(2025, 1, 1))  # вне окна

    assert manager.income_by_month(TODAY, months=3) == [
        (date(2026, 8, 1), Decimal("0")),
        (date(2026, 9, 1), Decimal("1000")),
        (date(2026, 10, 1), Decimal("500")),
    ]


def test_income_by_platform(manager, ivan, firm):
    nobody = manager.add_client(Client(name="Пётр"))
    pay(manager, order_for(manager, ivan), "1000")
    pay(manager, order_for(manager, firm), "3000")
    pay(manager, order_for(manager, nobody), "500")

    assert manager.income_by_platform(date(2026, 10, 1), TODAY) == [
        ("FL.ru", Decimal("3000")), ("Kwork", Decimal("1000")),
        (NO_PLATFORM, Decimal("500"))]


def test_tax_due_for_previous_month(manager, ivan, firm):
    pay(manager, order_for(manager, ivan), "1000", date(2026, 9, 10))
    pay(manager, order_for(manager, firm), "2000", date(2026, 9, 20))
    pay(manager, order_for(manager, ivan), "5000", date(2026, 10, 5))

    due = manager.tax_due(TODAY)

    assert due.month == date(2026, 9, 1)
    assert due.amount == Decimal("160.00")     # 1000 × 4 % + 2000 × 6 %
    assert due.due_date == date(2026, 10, 28)


def test_tax_due_in_january_is_for_december(manager):
    due = manager.tax_due(date(2027, 1, 10))
    assert due.month == date(2026, 12, 1)
    assert due.due_date == date(2027, 1, 28)
