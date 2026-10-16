"""Тесты интерфейса без показа окон (QT_QPA_PLATFORM=offscreen, см. conftest).

Проверяем, что формы правильно собирают объекты, а главное окно
правильно показывает данные. Модальные окна (exec, QMessageBox)
в тестах не открываем — они ждали бы нажатия пользователя.
"""

from datetime import date
from decimal import Decimal

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication

from freelancedesk.app.dialogs import ClientDialog, OrderDialog, to_qdate
from freelancedesk.app.labels import (
    format_date, format_money, format_month, format_short_money,
)
from freelancedesk.app.main_window import (
    DUE_TODAY_COLOR, NO_RECEIPT_COLOR, OVERDUE_COLOR, MainWindow,
)
from freelancedesk.app.widgets import BarChart, SortItem
from freelancedesk.core.manager import OrderManager, OrderView
from freelancedesk.core.models import Client, ClientType, Order, OrderStatus
from freelancedesk.core.storage import InMemoryStorage

TODAY = date(2026, 10, 15)


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Одно QApplication на все тесты — без него виджеты не создать."""
    return QApplication.instance() or QApplication([])


@pytest.fixture
def manager() -> OrderManager:
    """Два клиента и четыре заказа на все случаи подсветки."""
    m = OrderManager(InMemoryStorage())
    ivan = m.add_client(Client(name="Иван", platform="Kwork"))
    firm = m.add_client(Client(name="ООО Ромашка", platform="FL.ru",
                               client_type=ClientType.COMPANY))
    m.add_order(Order(title="Telegram-бот", client_id=ivan.id,
                      amount=Decimal("5000"), deadline=date(2026, 10, 1),
                      description="Запись клиентов к мастеру"))
    m.add_order(Order(title="Правки", client_id=ivan.id,
                      amount=Decimal("900"), deadline=TODAY))
    m.add_order(Order(title="Парсер", client_id=firm.id,
                      amount=Decimal("10000"), status=OrderStatus.PAID,
                      paid_on=date(2026, 10, 5)))
    m.add_order(Order(title="Лендинг", client_id=firm.id,
                      amount=Decimal("8000"), deadline=date(2026, 11, 1)))
    return m


@pytest.fixture
def window(manager) -> MainWindow:
    return MainWindow(manager, today=lambda: TODAY)


def column(table, col: int) -> list[str]:
    """Тексты одной колонки таблицы."""
    return [table.item(row, col).text() for row in range(table.rowCount())]


def select_order(window, title: str) -> None:
    """Выделить в таблице строку заказа с этим названием."""
    window.orders_table.selectRow(column(window.orders_table, 0).index(title))


# --- Форматирование ---

def test_format_money():
    assert format_money(Decimal("1500.5")) == "1 500,50 ₽"
    assert format_money(Decimal("0")) == "0,00 ₽"


def test_format_short_money():
    assert format_short_money(Decimal("12500")) == "12,5к"
    assert format_short_money(Decimal("60000")) == "60к"
    assert format_short_money(Decimal("800")) == "800"


def test_format_dates():
    assert format_date(date(2026, 10, 2)) == "02.10.2026"
    assert format_date(None) == ""
    assert format_month(date(2026, 9, 1)) == "сентябрь 2026"


def test_sort_item_sorts_by_value():
    # По тексту «9 000» > «10 000», по значению — наоборот
    nine = SortItem("9 000,00 ₽", Decimal("9000"))
    ten = SortItem("10 000,00 ₽", Decimal("10000"))
    assert nine < ten


# --- Формы ---

def test_client_dialog_roundtrip():
    original = Client(id=7, name="ООО Ромашка",
                      client_type=ClientType.COMPANY, contact="@romashka",
                      platform="Своя площадка", note="постоянный")
    assert ClientDialog(original).client() == original


def test_order_dialog_roundtrip():
    clients = [Client(id=1, name="Иван"), Client(id=2, name="ООО")]
    original = Order(id=3, title="Бот", client_id=2,
                     amount=Decimal("1500.50"), deadline=date(2026, 10, 20),
                     status=OrderStatus.PAID, paid_on=date(2026, 10, 2),
                     description="ТЗ", link="https://kwork.ru/track/1",
                     receipt_issued=True)
    assert OrderDialog(clients, original, today=TODAY).order() == original


def test_order_dialog_defaults():
    dialog = OrderDialog([Client(id=1, name="Иван")], today=TODAY)
    dialog.title_edit.setText("Бот")
    order = dialog.order()
    assert order.deadline == date(2026, 10, 22)  # через неделю
    assert order.paid_on is None
    # Поля оплаты недоступны, пока статус не «Оплачен»
    assert not dialog.paid_on_edit.isEnabled()
    assert not dialog.receipt_check.isEnabled()


def test_order_dialog_without_deadline():
    dialog = OrderDialog([Client(id=1, name="Иван")], today=TODAY)
    dialog.title_edit.setText("Бот")
    dialog.deadline_check.setChecked(False)
    assert dialog.order().deadline is None
    assert not dialog.deadline_edit.isEnabled()


def test_order_dialog_drops_payment_when_status_changes():
    clients = [Client(id=1, name="Иван")]
    paid = Order(id=1, title="Бот", client_id=1, amount=Decimal("100"),
                 status=OrderStatus.PAID, paid_on=date(2026, 10, 2),
                 receipt_issued=True)
    dialog = OrderDialog(clients, paid, today=TODAY)
    dialog.status_combo.setCurrentIndex(
        dialog.status_combo.findData(OrderStatus.DELIVERED))
    order = dialog.order()
    assert order.paid_on is None and not order.receipt_issued


# --- Главное окно: заказы ---

def test_default_filter_shows_active_orders(window):
    # Оплаченный «Парсер» в активные не входит
    assert sorted(column(window.orders_table, 0)) == [
        "Telegram-бот", "Лендинг", "Правки"]
    assert "13 900,00 ₽" in window.orders_total_label.text()


def test_highlighting(window):
    window.show_view(OrderView.ALL)
    table = window.orders_table
    titles = column(table, 0)

    def background(title, col=0):
        return table.item(titles.index(title), col).background().color()

    assert background("Telegram-бот") == OVERDUE_COLOR
    assert background("Правки") == DUE_TODAY_COLOR
    assert background("Лендинг") not in (OVERDUE_COLOR, DUE_TODAY_COLOR)
    assert background("Парсер", col=6) == NO_RECEIPT_COLOR  # колонка «Чек»


def test_banner_counts_and_navigation(window):
    window.show()  # видимость виджетов проверяется только у показанного окна
    assert window.banner.isVisible()
    assert window.banner.buttons[OrderView.OVERDUE].text() == "Просрочено: 1"

    window.banner.buttons[OrderView.NO_RECEIPT].click()
    assert column(window.orders_table, 0) == ["Парсер"]
    window.close()


def test_status_filter_and_search(window):
    for index in range(window.order_filter.count()):
        if window.order_filter.itemData(index) == ("status",
                                                   OrderStatus.PAID):
            window.order_filter.setCurrentIndex(index)
    assert column(window.orders_table, 0) == ["Парсер"]

    window.show_view(OrderView.ALL)
    window.search_edit.setText("МАСТЕР")  # ищет и в описании
    assert column(window.orders_table, 0) == ["Telegram-бот"]


def test_default_sorting(window):
    # Заказы — по дедлайну (срочные сверху), клиенты — по алфавиту
    assert column(window.orders_table, 0) == [
        "Telegram-бот", "Правки", "Лендинг"]
    assert column(window.clients_table, 0) == ["Иван", "ООО Ромашка"]


def test_sorting_by_amount(window):
    window.orders_table.sortItems(2)  # колонка «Сумма», по возрастанию
    assert column(window.orders_table, 0) == [
        "Правки", "Telegram-бот", "Лендинг"]


def test_context_actions(window):
    window.show_view(OrderView.ALL)
    select_order(window, "Лендинг")
    window.set_status(OrderStatus.PAID)
    lending = next(o for o in window._manager.list_orders()
                   if o.title == "Лендинг")
    assert lending.paid_on == TODAY

    select_order(window, "Лендинг")
    window.toggle_receipt()
    assert window._manager.get_order(lending.id).receipt_issued


def test_receipt_error_is_shown_not_raised(window, monkeypatch):
    shown = []
    monkeypatch.setattr(window, "_show_error", shown.append)
    select_order(window, "Лендинг")  # не оплачен — чек выбить нельзя
    window.toggle_receipt()
    assert "только по оплаченному" in shown[0]


# --- Клиенты ---

def test_clients_table_with_stats(window):
    table = window.clients_table
    names = column(table, 0)
    firm_row = names.index("ООО Ромашка")
    assert table.item(firm_row, 4).text() == "2"               # заказов
    assert table.item(firm_row, 5).text() == "10 000,00 ₽"     # оплачено


def test_run_shows_error_instead_of_crash(window, monkeypatch):
    shown = []
    monkeypatch.setattr(window, "_show_error", shown.append)
    ivan = next(c for c in window._manager.list_clients()
                if c.name == "Иван")

    ok = window._run(lambda: window._manager.delete_client(ivan.id))

    assert not ok
    assert "есть заказы" in shown[0]
    assert window.clients_table.rowCount() == 2  # клиент не удалён


# --- Сводка ---

def test_summary_for_current_month(window):
    # Оплачен только «Парсер» от юрлица: 10 000 ₽, налог 6 %
    assert window.income_label.text() == "10 000,00 ₽"
    assert window.tax_label.text() == "600,00 ₽"
    assert window.net_label.text() == "9 400,00 ₽"
    assert "FL.ru: 10 000,00 ₽" in window.platform_label.text()


def test_quick_periods(window):
    window.set_period("last_month")
    assert window.start_edit.date() == to_qdate(date(2026, 9, 1))
    assert window.end_edit.date() == to_qdate(date(2026, 9, 30))
    assert window.income_label.text() == "0,00 ₽"

    window.set_period("this_year")
    assert window.start_edit.date() == to_qdate(date(2026, 1, 1))


def test_goal_progress(window):
    window.goal_spin.setValue(40_000)
    assert window.goal_bar.value() == 25  # 10 000 из 40 000
    assert "из 40 000,00 ₽" in window.goal_bar.format()


def test_tax_due_text(window, manager):
    ivan = next(c for c in manager.list_clients() if c.name == "Иван")
    manager.add_order(Order(title="Сентябрь", client_id=ivan.id,
                            amount=Decimal("1000"), status=OrderStatus.PAID,
                            paid_on=date(2026, 9, 10)))
    window.refresh()
    text = window.tax_due_label.text()
    assert "сентябрь 2026" in text and "40,00 ₽" in text
    assert "28.10.2026" in text


def test_chart_renders(window):
    # Отрисовка в картинку: проверяем, что paintEvent не падает
    chart = BarChart()
    chart.resize(400, 220)
    chart.set_data([("сен", Decimal("0")), ("окт", Decimal("12500"))])
    chart.render(QPixmap(400, 220))
    chart.set_data([])
    chart.render(QPixmap(400, 220))


# --- Состояние окна ---

def test_state_is_saved_and_restored(manager, tmp_path):
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    first = MainWindow(manager, today=lambda: TODAY, settings=settings)
    first.goal_spin.setValue(60_000)
    first.show_view(OrderView.ALL)  # переключает на «Заказы»...
    first.tabs.setCurrentIndex(2)   # ...поэтому вкладку выбираем после
    first.close()  # closeEvent сохраняет состояние

    second = MainWindow(manager, today=lambda: TODAY, settings=settings)
    assert second.goal_spin.value() == 60_000
    assert second.tabs.currentIndex() == 2
    assert second.order_filter.currentData() == ("view", OrderView.ALL)
