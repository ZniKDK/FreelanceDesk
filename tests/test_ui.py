"""Тесты интерфейса без показа окон (QT_QPA_PLATFORM=offscreen, см. conftest).

Проверяем, что формы правильно собирают объекты, а экраны правильно
показывают данные и выполняют действия. Модальные окна (exec,
QMessageBox) в тестах не открываем — они ждали бы нажатия пользователя,
поэтому подтверждения и ошибки подменяются через monkeypatch.
"""

from datetime import date
from decimal import Decimal

import pytest
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication

from freelancedesk.app.dialogs import (
    ClientDialog, OrderDialog, PaymentDialog, to_qdate,
)
from freelancedesk.app.labels import (
    deadline_text, format_date, format_long_date, format_money, format_month,
    format_short_money, plural,
)
from freelancedesk.app.main_window import CLIENTS, FINANCE, ORDERS, MainWindow
from freelancedesk.app.pages.orders import CANCELLED_KEY
from freelancedesk.app.theme import apply_theme, icon
from freelancedesk.app.widgets import BarChart, SortItem
from freelancedesk.core.manager import OrderManager, OrderView
from freelancedesk.core.models import (
    Client, ClientType, Order, OrderStatus, Payment,
)
from freelancedesk.core.storage import InMemoryStorage

TODAY = date(2026, 10, 15)


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Одно QApplication на все тесты — без него виджеты не создать."""
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    return app


@pytest.fixture
def manager() -> OrderManager:
    """Два клиента и заказы на все случаи жизни."""
    m = OrderManager(InMemoryStorage())
    ivan = m.add_client(Client(name="Иван", platform="Kwork"))
    firm = m.add_client(Client(name="ООО Ромашка", platform="FL.ru",
                               client_type=ClientType.COMPANY))
    bot = m.add_order(Order(title="Telegram-бот", client_id=ivan.id,
                            amount=Decimal("15000"),
                            deadline=date(2026, 10, 1),
                            status=OrderStatus.IN_PROGRESS,
                            description="Запись клиентов к мастеру"))
    m.add_payment(Payment(order_id=bot.id, amount=Decimal("7500"),
                          paid_on=date(2026, 9, 28), receipt_issued=True))
    m.add_order(Order(title="Правки", client_id=ivan.id,
                      amount=Decimal("900"), deadline=TODAY))
    parser = m.add_order(Order(title="Парсер", client_id=firm.id,
                               amount=Decimal("10000"),
                               status=OrderStatus.DELIVERED),
                         today=date(2026, 10, 4))
    m.add_payment(Payment(order_id=parser.id, amount=Decimal("10000"),
                          paid_on=date(2026, 10, 5)))
    m.add_order(Order(title="Лендинг", client_id=firm.id,
                      amount=Decimal("8000"), status=OrderStatus.DELIVERED),
                today=date(2026, 10, 10))
    return m


@pytest.fixture
def window(manager) -> MainWindow:
    return MainWindow(manager, today=lambda: TODAY)


@pytest.fixture
def no_dialogs(window, monkeypatch):
    """Подтверждения отвечают «да», ошибки собираются в список."""
    errors = []
    monkeypatch.setattr(window, "confirm", lambda text: True)
    monkeypatch.setattr(window, "show_error", errors.append)
    return errors


def order_titles(window) -> list[str]:
    """Названия заказов в списке на экране «Заказы» (сверху вниз)."""
    lst = window.orders.list
    return [lst.itemWidget(lst.item(i)).title.text()
            for i in range(lst.count()) if lst.itemWidget(lst.item(i))]


def find(manager, title) -> Order:
    return next(o for o in manager.list_orders() if o.title == title)


# --- Подписи и форматирование ---

def test_format_money():
    assert format_money(Decimal("1500.5")) == "1 500,50 ₽"
    assert format_money(Decimal("1500.5"), kopecks=False) == "1 500 ₽"


def test_format_short_money():
    assert format_short_money(Decimal("12500")) == "12,5к"
    assert format_short_money(Decimal("60000")) == "60к"
    assert format_short_money(Decimal("800")) == "800"


def test_format_dates():
    assert format_date(date(2026, 10, 2)) == "02.10.2026"
    assert format_date(None) == ""
    assert format_month(date(2026, 9, 1)) == "сентябрь 2026"
    assert format_long_date(date(2026, 10, 3)) == "суббота, 3 октября"


@pytest.mark.parametrize("n, word", [(1, "день"), (2, "дня"), (5, "дней"),
                                     (11, "дней"), (21, "день"), (22, "дня"),
                                     (112, "дней")])
def test_plural(n, word):
    assert plural(n, ("день", "дня", "дней")) == word


def test_deadline_text():
    def text(**fields):
        order = Order(title="x", client_id=1, amount=Decimal("1"), **fields)
        return deadline_text(order, TODAY)

    assert text(deadline=date(2026, 10, 13)) == ("просрочен на 2 дня",
                                                 "danger")
    assert text(deadline=TODAY) == ("сдать сегодня", "warning")
    assert text(deadline=date(2026, 10, 16))[0] == "сдать завтра"
    assert text(deadline=date(2026, 10, 20))[0] == "через 5 дней"
    assert text()[0] == "без срока"
    assert text(status=OrderStatus.DELIVERED,
                delivered_on=date(2026, 10, 1))[0] == "сдан 01.10"


def test_sort_item_sorts_by_value():
    # По тексту «9 000» > «10 000», по значению — наоборот
    assert SortItem("9 000,00 ₽", Decimal("9000")) < \
        SortItem("10 000,00 ₽", Decimal("10000"))


def test_icons_load():
    assert not icon("briefcase").isNull()


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
                     status=OrderStatus.DELIVERED,
                     delivered_on=date(2026, 10, 18), description="ТЗ",
                     link="https://kwork.ru/track/1")
    assert OrderDialog(clients, original, today=TODAY).order() == original


def test_order_dialog_defaults_and_no_deadline():
    dialog = OrderDialog([Client(id=1, name="Иван")], today=TODAY)
    dialog.title_edit.setText("Бот")
    assert dialog.order().deadline == date(2026, 10, 22)  # через неделю
    dialog.deadline_check.setChecked(False)
    assert dialog.order().deadline is None
    assert not dialog.deadline_edit.isEnabled()


def test_order_dialog_drops_delivery_date_when_reopened():
    delivered = Order(id=1, title="Бот", client_id=1, amount=Decimal("1"),
                      status=OrderStatus.DELIVERED,
                      delivered_on=date(2026, 10, 1))
    dialog = OrderDialog([Client(id=1, name="Иван")], delivered,
                         today=TODAY)
    dialog.status_combo.setCurrentIndex(
        dialog.status_combo.findData(OrderStatus.IN_PROGRESS))
    assert dialog.order().delivered_on is None


def test_payment_dialog_suggests_remaining():
    dialog = PaymentDialog(5, Decimal("7500"), today=TODAY)
    payment = dialog.payment()
    assert payment == Payment(order_id=5, amount=Decimal("7500.00"),
                              paid_on=TODAY)


def test_payment_dialog_roundtrip():
    original = Payment(id=2, order_id=5, amount=Decimal("300.50"),
                       paid_on=date(2026, 10, 1), receipt_issued=True)
    assert PaymentDialog(5, payment=original,
                         today=TODAY).payment() == original


# --- Заказы: список и фильтры ---

def test_active_filter_and_sorting(window):
    window.show_page(ORDERS)
    # Активные: несданные (срочные сверху) и сданный без оплаты
    assert order_titles(window) == ["Telegram-бот", "Правки", "Лендинг"]


def test_filter_chips_show_counts(window):
    chips = window.orders.chips
    assert chips[OrderView.ACTIVE].text() == "Активные 3"
    assert chips[OrderView.AWAITING_PAYMENT].text() == "Ждут оплаты 1"
    assert chips[OrderView.NO_RECEIPT].text() == "Без чека 1"
    assert chips[CANCELLED_KEY].text() == "Отменённые 0"


def test_filters_and_search(window):
    page = window.orders
    page.set_filter(OrderView.DONE)
    assert order_titles(window) == ["Парсер"]

    page.set_filter(OrderView.ALL)
    page.search_edit.setText("МАСТЕР")  # ищет и в описании
    assert order_titles(window) == ["Telegram-бот"]


def test_sort_by_amount(window):
    page = window.orders
    page.set_filter(OrderView.ALL)
    page.sort_combo.setCurrentIndex(page.sort_combo.findData("amount"))
    assert order_titles(window) == ["Telegram-бот", "Парсер", "Лендинг",
                                    "Правки"]


def test_row_shows_payment_progress(window):
    window.orders.set_filter(OrderView.ALL)
    lst = window.orders.list
    rows = {lst.itemWidget(lst.item(i)).title.text():
            lst.itemWidget(lst.item(i)) for i in range(lst.count())}
    assert rows["Telegram-бот"].money_label.text() == "7,5к / 15к"
    assert rows["Лендинг"].money_label.text() == "ждёт 8к"
    assert rows["Парсер"].money_label.text() == "оплачен"
    assert "просрочен" in rows["Telegram-бот"].subtitle.text()


# --- Заказы: карточка ---

def test_panel_shows_money(window, manager):
    window.open_order(find(manager, "Telegram-бот").id)
    panel = window.orders.panel
    assert panel.received_label.text() == "7 500 ₽ из 15 000 ₽"
    assert panel.tax_label.text() == "300,00 ₽"
    assert panel.net_label.text() == "7 200,00 ₽"
    assert panel.remaining_label.text() == "7 500,00 ₽"
    assert panel.status_buttons[OrderStatus.IN_PROGRESS].isChecked()
    assert panel.money_bar.value() == 50


def test_open_order_hidden_by_filter(window, manager):
    # «Парсер» завершён и не виден в «Активных» — фильтр переключится
    window.open_order(find(manager, "Парсер").id)
    assert window.orders.current_filter_key() == OrderView.ALL
    assert window.orders.selected_order_id() == find(manager, "Парсер").id


def test_status_segments(window, manager, no_dialogs):
    order_id = find(manager, "Правки").id
    window.open_order(order_id)
    window.orders.panel.status_buttons[OrderStatus.DELIVERED].click()

    order = manager.get_order(order_id)
    assert order.status == OrderStatus.DELIVERED
    assert order.delivered_on == TODAY
    # Карточка осталась на том же заказе и показывает новый статус
    assert window.orders.selected_order_id() == order_id
    assert window.orders.panel.status_buttons[
        OrderStatus.DELIVERED].isChecked()


def test_cancel_and_restore(window, manager, no_dialogs):
    order_id = find(manager, "Правки").id
    window.open_order(order_id)
    window.orders.toggle_cancel()
    assert manager.get_order(order_id).status == OrderStatus.CANCELLED

    window.open_order(order_id)
    assert window.orders.panel.cancel_btn.text() == "Вернуть в работу"
    window.orders.toggle_cancel()
    assert manager.get_order(order_id).status == OrderStatus.IN_PROGRESS


def test_receipt_toggle_and_delete_payment(window, manager, no_dialogs):
    order_id = find(manager, "Парсер").id
    payment = manager.payments_for(order_id)[0]
    window.open_order(order_id)

    window.orders.toggle_receipt(payment.id)
    assert manager.get_payment(payment.id).receipt_issued
    assert window.orders.chips[OrderView.NO_RECEIPT].text() == "Без чека 0"

    window.orders.delete_payment(payment.id)
    assert manager.payments_for(order_id) == []


def test_delete_order(window, manager, no_dialogs):
    order_id = find(manager, "Telegram-бот").id
    window.open_order(order_id)
    window.orders.delete_order()
    assert manager.get_order(order_id) is None
    assert window.orders.panel.order is None


def test_actions_without_selection_show_error(window, no_dialogs):
    window.orders.list.setCurrentItem(None)
    window.orders.add_payment()
    assert no_dialogs == ["Выберите заказ в списке."]


def test_run_shows_error_instead_of_crash(window, manager, no_dialogs):
    ivan = next(c for c in manager.list_clients() if c.name == "Иван")
    assert not window.run(lambda: manager.delete_client(ivan.id))
    assert "есть заказы" in no_dialogs[0]


# --- Главная ---

def test_dashboard_cards(window):
    page = window.dashboard
    assert page.income_card.value.text() == "10 000 ₽"   # платёж 05.10
    assert page.income_card.caption.text() == "Получено в октябре"
    assert page.awaiting_card.value.text() == "8 000 ₽"  # «Лендинг»
    # Налог за сентябрь: 7 500 × 4 % = 300 ₽, срок — 28.10
    assert page.tax_card.value.text() == "300,00 ₽"
    assert "28.10.2026" in page.tax_card.hint.text()
    assert page.net_card.value.text() == "9 400 ₽"       # 10 000 − 6 %


def test_dashboard_goal(window):
    window.set_goal(40_000)
    assert window.dashboard.goal_bar.value() == 25
    assert "цель 40 000 ₽ · 25 %" in window.dashboard.income_card.hint.text()


def test_dashboard_hot_list_opens_order(window, manager):
    hot = window.dashboard.hot_list
    texts = [hot.item(i).text() for i in range(hot.count())]
    assert any("Telegram-бот" in t and "просрочен" in t for t in texts)
    assert any("Парсер" in t and "без чека" in t for t in texts)

    window.dashboard._open_item(hot.item(0))
    assert window.stack.currentIndex() == ORDERS
    assert window.orders.selected_order_id() == hot.item(0).data(
        Qt.ItemDataRole.UserRole)


def test_dashboard_upcoming(window):
    upcoming = window.dashboard.upcoming_list
    assert upcoming.count() == 2
    assert "Telegram-бот" in upcoming.item(0).text()


# --- Клиенты ---

def test_clients_table(window):
    table = window.clients.table
    names = [table.item(r, 0).text() for r in range(table.rowCount())]
    assert names == ["Иван", "ООО Ромашка"]
    assert table.item(1, 4).text() == "2"                 # заказов
    assert table.item(1, 5).text() == "10 000,00 ₽"       # получено

    window.clients.search_edit.setText("fl.ru")
    assert window.clients.table.rowCount() == 1


# --- Финансы ---

def test_finance_this_month(window):
    page = window.finance
    assert page.income_card.value.text() == "10 000 ₽"
    assert page.tax_card.value.text() == "600,00 ₽"
    assert page.table.rowCount() == 1
    assert page.table.item(0, 5).text() == "не выбит"


def test_finance_last_month_and_receipt(window, manager, no_dialogs):
    page = window.finance
    page.set_period("last_month")
    assert page.income_card.value.text() == "7 500 ₽"

    page.set_period("this_month")
    page.table.selectRow(0)
    page.toggle_receipt()
    assert all(p.receipt_issued for p in manager.payments_in_period(
        date(2026, 10, 1), TODAY))


def test_finance_open_order_from_journal(window, manager):
    window.show_page(FINANCE)
    window.finance.table.selectRow(0)
    window.finance.open_selected_order()
    assert window.orders.selected_order_id() == find(manager, "Парсер").id


def test_chart_renders():
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
    first.set_goal(60_000)
    first.orders.set_filter(OrderView.DONE)
    first.show_page(CLIENTS)
    first.close()  # closeEvent сохраняет состояние

    second = MainWindow(manager, today=lambda: TODAY, settings=settings)
    assert second.goal() == 60_000
    assert second.stack.currentIndex() == CLIENTS
    assert second.orders.current_filter_key() == OrderView.DONE
