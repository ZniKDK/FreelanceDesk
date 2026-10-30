"""Тесты OrderManager: клиенты, заказы, статусы работы, выборки."""

from datetime import date
from decimal import Decimal

import pytest

from freelancedesk.core.manager import OrderManager, OrderView
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


def add(manager, client, title, amount="1000", **fields) -> Order:
    """Короткий способ добавить заказ в тестах."""
    return manager.add_order(
        Order(title=title, client_id=client.id, amount=Decimal(amount),
              **fields), today=TODAY)


def pay(manager, order, amount, paid_on=TODAY, receipt=False) -> Payment:
    return manager.add_payment(Payment(order_id=order.id,
                                       amount=Decimal(amount),
                                       paid_on=paid_on,
                                       receipt_issued=receipt))


# --- Клиенты ---

def test_add_client_assigns_id(ivan):
    assert ivan.id == 1


def test_empty_client_name_rejected(manager):
    with pytest.raises(ValueError):
        manager.add_client(Client(name="   "))


def test_update_client_validates_name(manager, ivan):
    ivan.name = ""
    with pytest.raises(ValueError):
        manager.update_client(ivan)


def test_clients_sorted_case_insensitive(manager):
    for name in ("яндекс", "Борис", "алина"):
        manager.add_client(Client(name=name))
    assert [c.name for c in manager.list_clients()] == [
        "алина", "Борис", "яндекс"]


def test_cannot_delete_client_with_orders(manager, ivan):
    order = add(manager, ivan, "Бот")
    with pytest.raises(ValueError):
        manager.delete_client(ivan.id)
    manager.delete_order(order.id)
    manager.delete_client(ivan.id)
    assert manager.list_clients() == []


def test_client_stats(manager, ivan, firm):
    paid = add(manager, ivan, "Оплачен", "1500")
    pay(manager, paid, "1500")
    add(manager, ivan, "В работе", "700")
    stats = manager.client_stats()
    assert stats[ivan.id].orders == 2
    assert stats[ivan.id].income == Decimal("1500")
    assert firm.id not in stats  # заказов нет — нет и строки


# --- Заказы ---

def test_order_for_unknown_client_rejected(manager):
    with pytest.raises(ValueError):
        manager.add_order(Order(title="Бот", client_id=99,
                                amount=Decimal("100")))


def test_negative_amount_rejected(manager, ivan):
    with pytest.raises(ValueError):
        add(manager, ivan, "Бот", "-1")


def test_empty_title_rejected_on_update(manager, ivan):
    order = add(manager, ivan, "Бот")
    order.title = ""
    with pytest.raises(ValueError):
        manager.update_order(order)


def test_link_gets_scheme(manager, ivan):
    order = add(manager, ivan, "Бот", link="  kwork.ru/track/1 ")
    assert order.link == "https://kwork.ru/track/1"


def test_delete_order_removes_payments(manager, ivan):
    order = add(manager, ivan, "Бот")
    pay(manager, order, "500")
    manager.delete_order(order.id)
    assert manager.get_order(order.id) is None
    assert manager.payments_in_period(date(2000, 1, 1), TODAY) == []


# --- Статус работы ---

def test_delivering_sets_and_reopening_clears_date(manager, ivan):
    order = add(manager, ivan, "Бот")
    delivered = manager.change_status(order.id, OrderStatus.DELIVERED,
                                      today=TODAY)
    assert delivered.delivered_on == TODAY

    reopened = manager.change_status(order.id, OrderStatus.IN_PROGRESS)
    assert reopened.delivered_on is None


def test_same_status_keeps_delivery_date(manager, ivan):
    order = add(manager, ivan, "Бот", status=OrderStatus.DELIVERED,
                delivered_on=date(2026, 10, 2))
    manager.change_status(order.id, OrderStatus.DELIVERED, today=TODAY)
    assert manager.get_order(order.id).delivered_on == date(2026, 10, 2)


def test_status_does_not_depend_on_payment(manager, ivan):
    # Предоплата за заказ, который ещё в работе — так бывает на Kwork
    order = add(manager, ivan, "Бот", status=OrderStatus.IN_PROGRESS)
    pay(manager, order, "1000")
    assert manager.get_order(order.id).status == OrderStatus.IN_PROGRESS


# --- Выборки и поиск ---

@pytest.fixture
def board(manager, ivan):
    """Набор заказов на все выборки."""
    add(manager, ivan, "Просрочен", deadline=date(2026, 10, 1))
    add(manager, ivan, "Сегодня", deadline=TODAY)
    waiting = add(manager, ivan, "Ждёт оплаты", status=OrderStatus.DELIVERED)
    pay(manager, waiting, "400", receipt=True)
    done = add(manager, ivan, "Закрыт", status=OrderStatus.DELIVERED)
    pay(manager, done, "1000")  # без чека
    add(manager, ivan, "Отменён", status=OrderStatus.CANCELLED)
    return manager


def titles(manager, view, **kwargs):
    return sorted(o.title for o in manager.list_orders(view=view, today=TODAY,
                                                       **kwargs))


def test_views(board):
    assert titles(board, OrderView.ACTIVE) == [
        "Ждёт оплаты", "Просрочен", "Сегодня"]
    assert titles(board, OrderView.AWAITING_PAYMENT) == ["Ждёт оплаты"]
    assert titles(board, OrderView.OVERDUE) == ["Просрочен"]
    assert titles(board, OrderView.DUE_TODAY) == ["Сегодня"]
    assert titles(board, OrderView.NO_RECEIPT) == ["Закрыт"]
    assert titles(board, OrderView.DONE) == ["Закрыт"]
    assert len(titles(board, OrderView.ALL)) == 5


def test_view_counts_and_attention(board):
    counts = board.view_counts(TODAY)
    assert counts[OrderView.ACTIVE] == 3
    attention = board.attention(TODAY)
    assert (attention.overdue, attention.due_today,
            attention.no_receipt) == (1, 1, 1)
    assert attention.total == 3


def test_status_filter(board):
    assert titles(board, OrderView.ALL,
                  status=OrderStatus.CANCELLED) == ["Отменён"]


def test_search_by_description_and_client(manager, ivan, firm):
    add(manager, ivan, "Бот", description="интеграция с CRM")
    add(manager, firm, "Лендинг")

    def found(text):
        return [o.title for o in manager.list_orders(search=text)]

    assert found("crm") == ["Бот"]
    assert found("ромаш") == ["Лендинг"]


def test_upcoming_starts_with_overdue(manager, ivan):
    add(manager, ivan, "Поздно", deadline=date(2026, 11, 1))
    add(manager, ivan, "Просрочен", deadline=date(2026, 10, 1))
    add(manager, ivan, "Без срока")
    add(manager, ivan, "Сдан", deadline=date(2026, 10, 2),
        status=OrderStatus.DELIVERED)
    assert [o.title for o in manager.upcoming(TODAY)] == ["Просрочен",
                                                          "Поздно"]


# --- Контакты клиента ---

from freelancedesk.core.manager import contact_url  # noqa: E402
from freelancedesk.core.models import ContactMethod  # noqa: E402


@pytest.mark.parametrize("email", ["lisa@mail.ru", "a.b-c@sub.domain.org"])
def test_valid_email_accepted(manager, email):
    assert manager.add_client(Client(name="Лиса", email=email)).email == email


@pytest.mark.parametrize("email", ["lisa", "lisa@mail", "@mail.ru",
                                   "li sa@mail.ru"])
def test_bad_email_rejected(manager, email):
    with pytest.raises(ValueError, match="Почта"):
        manager.add_client(Client(name="Лиса", email=email))


@pytest.mark.parametrize("phone", ["+7 900 000-00-00", "8 (900) 0000000",
                                   "79000000000"])
def test_valid_phone_accepted(manager, phone):
    assert manager.add_client(Client(name="Лиса", phone=phone)).phone == phone


@pytest.mark.parametrize("phone", ["12345", "+7 900 abc", "8-800"])
def test_bad_phone_rejected(manager, phone):
    with pytest.raises(ValueError, match="Телефон"):
        manager.add_client(Client(name="Лиса", phone=phone))


def test_telegram_handle_gets_at(manager):
    client = manager.add_client(Client(name="Иван", messenger="ivan",
                                       messenger_app="Telegram"))
    assert client.messenger == "@ivan"


def test_preferred_contact_must_be_filled(manager):
    with pytest.raises(ValueError, match="способ связи"):
        manager.add_client(Client(name="Иван",
                                  preferred_contact=ContactMethod.EMAIL))


def test_contact_urls():
    client = Client(name="Лиса", email="lisa@mail.ru",
                    phone="+7 (900) 000-00-00", messenger="@lisa",
                    messenger_app="Telegram")
    assert contact_url(client, ContactMethod.EMAIL) == "mailto:lisa@mail.ru"
    assert contact_url(client, ContactMethod.PHONE) == "tel:+79000000000"
    assert contact_url(client, ContactMethod.MESSENGER) == \
        "https://t.me/lisa"
    client.messenger, client.messenger_app = "+7 900 000-00-00", "WhatsApp"
    assert contact_url(client, ContactMethod.MESSENGER) == \
        "https://wa.me/79000000000"
    client.messenger_app = "MAX"  # у MAX нет публичных ссылок
    assert contact_url(client, ContactMethod.MESSENGER) is None
    assert contact_url(Client(name="Пусто"), ContactMethod.EMAIL) is None
