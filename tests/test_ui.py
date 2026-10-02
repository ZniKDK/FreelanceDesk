"""Тесты интерфейса без показа окон (QT_QPA_PLATFORM=offscreen, см. conftest).

Проверяем, что формы правильно собирают объекты, а главное окно
правильно показывает данные. Модальные окна (exec, QMessageBox)
в тестах не открываем — они ждали бы нажатия пользователя.
"""

from datetime import date
from decimal import Decimal

import pytest
from PyQt6.QtWidgets import QApplication

from freelancedesk.app.dialogs import ClientDialog, OrderDialog, to_qdate
from freelancedesk.app.labels import format_date, format_money
from freelancedesk.app.main_window import OVERDUE_COLOR, MainWindow
from freelancedesk.core.manager import OrderManager
from freelancedesk.core.models import Client, ClientType, Order, OrderStatus
from freelancedesk.core.storage import InMemoryStorage

TODAY = date(2026, 10, 15)


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Одно QApplication на все тесты — без него виджеты не создать."""
    return QApplication.instance() or QApplication([])


@pytest.fixture
def manager() -> OrderManager:
    """Менеджер с двумя клиентами и тремя заказами."""
    m = OrderManager(InMemoryStorage())
    ivan = m.add_client(Client(name="Иван"))
    firm = m.add_client(Client(name="ООО Ромашка",
                               client_type=ClientType.COMPANY))
    m.add_order(Order(title="Telegram-бот", client_id=ivan.id,
                      amount=Decimal("5000"), deadline=date(2026, 10, 1)))
    m.add_order(Order(title="Парсер", client_id=firm.id,
                      amount=Decimal("10000"), status=OrderStatus.PAID),
                today=date(2026, 10, 5))
    m.add_order(Order(title="Лендинг", client_id=firm.id,
                      amount=Decimal("8000"), deadline=date(2026, 11, 1)))
    return m


@pytest.fixture
def window(manager) -> MainWindow:
    return MainWindow(manager, today=lambda: TODAY)


# --- Форматирование ---

def test_format_money():
    assert format_money(Decimal("1500.5")) == "1 500,50 ₽"
    assert format_money(Decimal("0")) == "0,00 ₽"


def test_format_date():
    assert format_date(date(2026, 10, 2)) == "02.10.2026"
    assert format_date(None) == ""


# --- Формы ---

def test_client_dialog_roundtrip():
    original = Client(id=7, name="ООО Ромашка",
                      client_type=ClientType.COMPANY, contact="@romashka",
                      platform="Kwork", note="постоянный")
    assert ClientDialog(original).client() == original


def test_order_dialog_roundtrip():
    clients = [Client(id=1, name="Иван"), Client(id=2, name="ООО")]
    original = Order(id=3, title="Бот", client_id=2,
                     amount=Decimal("1500.50"), deadline=date(2026, 10, 20),
                     status=OrderStatus.PAID, paid_on=date(2026, 10, 2))
    assert OrderDialog(clients, original).order() == original


def test_order_dialog_without_deadline():
    dialog = OrderDialog([Client(id=1, name="Иван")])
    dialog.title_edit.setText("Бот")
    dialog.deadline_check.setChecked(False)
    order = dialog.order()
    assert order.deadline is None
    assert order.client_id == 1
    assert not dialog.deadline_edit.isEnabled()


def test_order_dialog_drops_paid_on_when_status_changes():
    clients = [Client(id=1, name="Иван")]
    paid = Order(id=1, title="Бот", client_id=1, amount=Decimal("100"),
                 status=OrderStatus.PAID, paid_on=date(2026, 10, 2))
    dialog = OrderDialog(clients, paid)
    dialog.status_combo.setCurrentIndex(
        dialog.status_combo.findData(OrderStatus.DELIVERED))
    assert dialog.order().paid_on is None


# --- Главное окно ---

def column(table, col: int) -> list[str]:
    """Тексты одной колонки таблицы."""
    return [table.item(row, col).text() for row in range(table.rowCount())]


def test_tables_show_data(window):
    assert window.orders_table.rowCount() == 3
    assert window.clients_table.rowCount() == 2
    assert "10 000,00 ₽" in column(window.orders_table, 2)


def test_overdue_row_is_highlighted(window):
    titles = column(window.orders_table, 0)
    overdue_row = titles.index("Telegram-бот")
    normal_row = titles.index("Лендинг")
    table = window.orders_table
    assert table.item(overdue_row, 0).background().color() == OVERDUE_COLOR
    assert table.item(normal_row, 0).background().color() != OVERDUE_COLOR


def test_status_filter_and_search(window):
    window.status_filter.setCurrentIndex(
        window.status_filter.findData(OrderStatus.PAID))
    assert column(window.orders_table, 0) == ["Парсер"]

    window.status_filter.setCurrentIndex(0)  # «Все статусы»
    window.search_edit.setText("лЕнд")       # поиск без учёта регистра
    assert column(window.orders_table, 0) == ["Лендинг"]


def test_summary_for_current_month(window):
    # Оплачен только «Парсер» от юрлица: 10 000 ₽, налог 6 %
    assert window.income_label.text() == "10 000,00 ₽"
    assert window.tax_label.text() == "600,00 ₽"
    assert window.net_label.text() == "9 400,00 ₽"
    assert window.overdue_label.text() == "1"


def test_summary_for_other_period(window):
    window.start_edit.setDate(to_qdate(date(2026, 9, 1)))
    window.end_edit.setDate(to_qdate(date(2026, 9, 30)))
    window.calculate_summary()
    assert window.income_label.text() == "0,00 ₽"


def test_run_shows_error_instead_of_crash(window, monkeypatch):
    # Подменяем окно ошибки, чтобы перехватить текст и не ждать нажатия
    shown = []
    monkeypatch.setattr(window, "_show_error", shown.append)
    ivan_id = window._manager.list_clients()[0].id

    ok = window._run(lambda: window._manager.delete_client(ivan_id))

    assert not ok
    assert "есть заказы" in shown[0]
    assert window.clients_table.rowCount() == 2  # клиент не удалён


def test_run_refreshes_tables(window):
    window._run(lambda: window._manager.add_client(Client(name="Пётр")))
    assert window.clients_table.rowCount() == 3
