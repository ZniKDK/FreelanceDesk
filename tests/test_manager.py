"""Тесты OrderManager на хранилище в памяти."""

from datetime import date
from decimal import Decimal

import pytest

from freelancedesk.core.manager import OrderManager
from freelancedesk.core.models import Client, ClientType, Order, OrderStatus
from freelancedesk.core.storage import InMemoryStorage


@pytest.fixture
def manager() -> OrderManager:
    return OrderManager(InMemoryStorage())


@pytest.fixture
def person(manager) -> Client:
    return manager.add_client(Client(name="Иван"))


@pytest.fixture
def company(manager) -> Client:
    return manager.add_client(
        Client(name="ООО Ромашка", client_type=ClientType.COMPANY))


def test_add_client_assigns_id(person):
    assert person.id == 1


def test_empty_client_name_rejected(manager):
    with pytest.raises(ValueError):
        manager.add_client(Client(name="   "))


def test_order_for_unknown_client_rejected(manager):
    with pytest.raises(ValueError):
        manager.add_order(Order(title="Бот", client_id=99,
                                amount=Decimal("100")))


def test_negative_amount_rejected(manager, person):
    with pytest.raises(ValueError):
        manager.add_order(Order(title="Бот", client_id=person.id,
                                amount=Decimal("-1")))


def test_cannot_delete_client_with_orders(manager, person):
    manager.add_order(Order(title="Бот", client_id=person.id,
                            amount=Decimal("100")))
    with pytest.raises(ValueError):
        manager.delete_client(person.id)


def test_filter_by_status_and_search(manager, person):
    bot = manager.add_order(Order(title="Telegram-бот", client_id=person.id,
                                  amount=Decimal("100")))
    manager.add_order(Order(title="Парсер", client_id=person.id,
                            amount=Decimal("200")))
    manager.change_status(bot.id, OrderStatus.IN_PROGRESS)

    assert [o.title for o in manager.list_orders(
        status=OrderStatus.IN_PROGRESS)] == ["Telegram-бот"]
    assert [o.title for o in manager.list_orders(search="парс")] == ["Парсер"]


def test_paid_status_sets_and_clears_payment_date(manager, person):
    order = manager.add_order(Order(title="Бот", client_id=person.id,
                                    amount=Decimal("100")))
    paid = manager.change_status(order.id, OrderStatus.PAID,
                                 today=date(2026, 10, 2))
    assert paid.paid_on == date(2026, 10, 2)

    reopened = manager.change_status(order.id, OrderStatus.DELIVERED)
    assert reopened.paid_on is None


def test_summary_uses_rate_by_client_type(manager, person, company):
    day = date(2026, 10, 2)
    for client, amount in ((person, "1000"), (company, "2000")):
        order = manager.add_order(Order(title="Заказ", client_id=client.id,
                                        amount=Decimal(amount)))
        manager.change_status(order.id, OrderStatus.PAID, today=day)

    result = manager.summary(date(2026, 10, 1), date(2026, 10, 31))

    assert result.income == Decimal("3000")
    assert result.tax == Decimal("160.00")  # 1000 * 4 % + 2000 * 6 %
    assert result.net == Decimal("2840.00")


def test_summary_ignores_unpaid_and_out_of_period(manager, person):
    manager.add_order(Order(title="Не оплачен", client_id=person.id,
                            amount=Decimal("500")))
    old = manager.add_order(Order(title="Старый", client_id=person.id,
                                  amount=Decimal("700")))
    manager.change_status(old.id, OrderStatus.PAID, today=date(2026, 9, 1))

    result = manager.summary(date(2026, 10, 1), date(2026, 10, 31))

    assert result.income == Decimal("0")
    assert result.tax == Decimal("0.00")


def test_update_order_validates_and_syncs_paid_on(manager, person):
    order = manager.add_order(Order(title="Бот", client_id=person.id,
                                    amount=Decimal("100")))
    # Через форму поставили «Оплачен» — дата оплаты появляется сама
    order.status = OrderStatus.PAID
    manager.update_order(order, today=date(2026, 10, 2))
    assert manager.get_order(order.id).paid_on == date(2026, 10, 2)

    # Повторное сохранение оплаченного заказа не сдвигает дату оплаты
    manager.update_order(order, today=date(2026, 10, 9))
    assert manager.get_order(order.id).paid_on == date(2026, 10, 2)

    order.title = ""
    with pytest.raises(ValueError):
        manager.update_order(order)


def test_add_paid_order_gets_payment_date(manager, person):
    order = manager.add_order(Order(title="Бот", client_id=person.id,
                                    amount=Decimal("100"),
                                    status=OrderStatus.PAID),
                              today=date(2026, 10, 2))
    assert order.paid_on == date(2026, 10, 2)


def test_update_client_validates_name(manager, person):
    person.name = ""
    with pytest.raises(ValueError):
        manager.update_client(person)


def test_delete_order(manager, person):
    order = manager.add_order(Order(title="Бот", client_id=person.id,
                                    amount=Decimal("100")))
    manager.delete_order(order.id)
    assert manager.get_order(order.id) is None
    # После удаления заказов клиента можно удалить
    manager.delete_client(person.id)
    assert manager.list_clients() == []
