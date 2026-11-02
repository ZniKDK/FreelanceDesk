"""Тесты генератора тестовых данных."""

from datetime import date

from freelancedesk.core.manager import OrderManager, OrderView
from freelancedesk.core.storage import InMemoryStorage
from freelancedesk.demo import CLIENTS, HISTORY, seed

TODAY = date(2026, 10, 15)


def test_seed_creates_everyday_situations():
    manager = OrderManager(InMemoryStorage())
    created = seed(manager, TODAY)

    assert created == len(HISTORY) + 7
    assert len(manager.list_clients()) == len(CLIENTS)
    counts = manager.view_counts(TODAY)
    # Есть всё, что показывает программа: просрочка, срок сегодня,
    # оплата без чека, ожидание оплаты
    for view in (OrderView.OVERDUE, OrderView.DUE_TODAY,
                 OrderView.NO_RECEIPT, OrderView.AWAITING_PAYMENT):
        assert counts[view] >= 1
    # Поступления есть в каждом из последних 12 месяцев
    assert all(amount > 0 for _, amount in manager.income_by_month(TODAY))


def test_seed_is_not_duplicated():
    manager = OrderManager(InMemoryStorage())
    seed(manager, TODAY)
    assert seed(manager, TODAY) == 0
    assert len(manager.list_clients()) == len(CLIENTS)
