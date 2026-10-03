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
    Client, ClientType, ContactMethod, Order, OrderStatus, Payment,
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
                      client_type=ClientType.COMPANY, email="hi@romashka.ru",
                      phone="+7 900 000-00-00", messenger="@romashka",
                      messenger_app="Telegram",
                      preferred_contact=ContactMethod.PHONE,
                      platform="Своя площадка", note="постоянный")
    assert ClientDialog(original).client() == original


def test_client_dialog_without_messenger():
    dialog = ClientDialog()
    dialog.name_edit.setText("Иван")
    client = dialog.client()
    # Мессенджер не указан — и название приложения не сохраняется
    assert (client.messenger, client.messenger_app) == ("", "")
    assert client.preferred_contact is None


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
    assert table.item(1, 6).text() == "2"                 # заказов
    assert table.item(1, 7).text() == "10 000,00 ₽"       # получено

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


# --- Тема ---

def test_dark_theme_rebuilds_and_keeps_place(window, manager):
    from freelancedesk.app.theme import C, DARK, LIGHT
    order_id = find(manager, "Telegram-бот").id
    window.open_order(order_id)
    window.orders.set_filter(OrderView.ALL)
    window.orders.select_order(order_id)

    window.set_theme("dark")
    try:
        assert C["bg"] == DARK["bg"]
        # Экраны построены заново, но пользователь там же, где был
        assert window.stack.currentIndex() == ORDERS
        assert window.orders.current_filter_key() == OrderView.ALL
        assert window.orders.selected_order_id() == order_id
        # Палитра Qt тоже тёмная — для выпадающих списков и форм
        base = QApplication.instance().palette().base().color().name()
        assert base == DARK["surface"]
    finally:
        window.set_theme("light")
    assert C["bg"] == LIGHT["bg"]


def test_toggle_theme_and_saved_choice(manager, tmp_path):
    from freelancedesk.app.theme import is_dark
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    first = MainWindow(manager, today=lambda: TODAY, settings=settings)
    first.toggle_theme()
    try:
        assert is_dark()
        assert settings.value("theme") == "dark"
    finally:
        first.set_theme("light")


# --- «Липкий» заказ и уведомления ---

def test_sticky_order_stays_after_leaving_filter(window, manager,
                                                 no_dialogs):
    order_id = find(manager, "Правки").id
    window.open_order(order_id)  # фильтр «Активные»
    window.orders.set_status(OrderStatus.CANCELLED)

    # Заказ ушёл из «Активных», но остался в списке и в карточке
    assert "Правки" in order_titles(window)
    assert window.orders.selected_order_id() == order_id
    lst = window.orders.list
    row = next(lst.itemWidget(lst.item(i)) for i in range(lst.count())
               if lst.itemWidget(lst.item(i)).title.text() == "Правки")
    assert "перешёл в «Отменённые»" in row.subtitle.text()
    # Уведомление предлагает перейти к заказу
    # isVisibleTo — видимость внутри окна (само окно в тестах не показано)
    assert window.toast.isVisibleTo(window)
    assert window.toast.action.text() == "Показать"

    window.toast.action.click()
    assert window.orders.current_filter_key() == CANCELLED_KEY
    assert window.orders.selected_order_id() == order_id


def test_sticky_order_released_by_filter_change(window, manager,
                                                no_dialogs):
    window.open_order(find(manager, "Правки").id)
    window.orders.set_status(OrderStatus.CANCELLED)
    window.orders.set_filter(OrderView.ACTIVE)
    assert "Правки" not in order_titles(window)


def test_status_change_inside_filter_just_notifies(window, manager,
                                                   no_dialogs):
    window.open_order(find(manager, "Правки").id)
    window.orders.set_status(OrderStatus.DELIVERED)  # «Ждёт оплаты» ⊂ активных
    assert window.toast.text.text() == "Статус: Сдан"
    assert not window.toast.action.isVisibleTo(window)


def test_no_stray_windows_after_refresh(window, manager, no_dialogs):
    """Регрессия: строки платежей не должны становиться отдельными окнами."""
    window.show()
    window.open_order(find(manager, "Telegram-бот").id)
    window.orders.set_status(OrderStatus.DELIVERED)
    stray = [w for w in QApplication.topLevelWidgets()
             if w.isVisible() and w is not window
             and w.__class__.__name__ in ("QFrame", "QLabel", "QWidget")]
    window.close()
    assert stray == []


# --- Мелочи интерфейса ---

def test_filter_chips_fit_text(window):
    for chip_btn in window.orders.chips.values():
        needed = chip_btn.fontMetrics().horizontalAdvance(chip_btn.text())
        assert chip_btn.minimumWidth() > needed


def test_animations_run_without_errors(window, manager):
    from freelancedesk.app import animations
    animations.set_enabled(True)
    window.show()
    window.show_page(FINANCE)                # появление экрана, рост диаграммы
    window.open_order(find(manager, "Парсер").id)   # карточка, полоска
    window.set_goal(50_000)                  # досчитывающие суммы
    window.notify("Проверка")                # уведомление
    QApplication.processEvents()
    window.close()


# --- Лента фильтров, прокрутка, подсказки ---

def _narrow_strip(window):
    """Сузить окно, чтобы фильтры не помещались и ленту можно было крутить."""
    window.resize(1040, 700)
    window.show()
    window.show_page(ORDERS)
    strip = window.orders.chip_strip
    strip.setFixedWidth(300)
    QApplication.processEvents()
    return strip


def test_filter_strip_equal_spacing(window):
    window.show()
    window.show_page(ORDERS)  # раскладка считается только у видимого экрана
    window.resize(1040, 700)  # узкое окно: фильтры не помещаются целиком
    QApplication.processEvents()
    buttons = list(window.orders.chips.values())
    gaps = {b2.x() - (b1.x() + b1.width())
            for b1, b2 in zip(buttons, buttons[1:])}
    window.close()
    assert gaps == {6}  # одинаковый шаг, без наложений


def test_filter_strip_swipe_scrolls_without_click(window):
    from PyQt6.QtCore import QPoint
    from PyQt6.QtTest import QTest
    strip = _narrow_strip(window)
    bar = strip.horizontalScrollBar()
    assert bar.maximum() > 0
    target = window.orders.chips[OrderView.AWAITING_PAYMENT]
    before = window.orders.current_filter_key()

    # Тянем ленту влево мышью, начав прямо на кнопке
    QTest.mousePress(target, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
    for x in (0, -20, -60, -120):
        QTest.mouseMove(target, QPoint(10 + x, 10))
    QTest.mouseRelease(target, Qt.MouseButton.LeftButton,
                       pos=QPoint(-110, 10))

    assert bar.value() > 0
    # Свайп — это не щелчок: фильтр не переключился
    assert window.orders.current_filter_key() == before
    window.close()


def test_filter_strip_wheel_scrolls_horizontally(window):
    from PyQt6.QtCore import QPoint, QPointF
    from PyQt6.QtGui import QWheelEvent
    strip = _narrow_strip(window)
    bar = strip.horizontalScrollBar()
    viewport = strip.viewport()
    event = QWheelEvent(QPointF(10, 10), QPointF(viewport.mapToGlobal(
        QPoint(10, 10))), QPoint(0, 0), QPoint(0, -120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(viewport, event)
    assert bar.value() > 0  # обычное колесо крутит ленту вбок
    window.close()


def test_empty_list_hint(window):
    window.orders.set_filter(CANCELLED_KEY)
    assert window.orders.list.count() == 0
    assert window.orders.list.empty_hint[0] == "Здесь пусто"
    window.orders.search_edit.setText("нет такого заказа")
    assert window.orders.list.empty_hint[0] == "Ничего не нашлось"
    window.orders.list.grab()  # подсказка рисуется без ошибок


def test_sidebar_has_no_storage_path(manager):
    secret = r"SQLite — C:\Users\someone\AppData\freelancedesk.db"
    win = MainWindow(manager, today=lambda: TODAY, storage_label=secret)
    from PyQt6.QtWidgets import QLabel
    texts = [w.text() for w in win.sidebar.findChildren(QLabel)]
    assert all(secret not in t for t in texts)


def test_animations_toggle_notifies(window):
    window.set_animations(False)
    assert window.toast.text.text().startswith("Анимации выключены")
    window.set_animations(True)
    assert window.toast.text.text() == "Анимации включены"
    window.set_animations(False)


def test_animated_combo_popup(window):
    from freelancedesk.app import animations
    animations.set_enabled(True)
    window.show()
    combo = window.orders.sort_combo
    combo.showPopup()
    QApplication.processEvents()
    combo.hidePopup()
    window.close()


# --- Таблицы: столбцы, выравнивание, режим настройки ---

def _shown_clients(window, width=1200):
    window.resize(width, 760)
    window.show()
    window.show_page(CLIENTS)
    QApplication.processEvents()
    return window.clients.table


def _ratios(table) -> list[float]:
    header = table.horizontalHeader()
    total = sum(header.sectionSize(c) for c in range(table.columnCount()))
    return [round(header.sectionSize(c) / total, 2)
            for c in range(table.columnCount())]


def test_columns_keep_proportions_on_resize(window):
    """Регрессия: после «развернуть — свернуть» столбец «Имя» не раздувается."""
    table = _shown_clients(window, 1100)
    before = _ratios(table)
    window.resize(1800, 900)   # как «на весь экран»
    QApplication.processEvents()
    window.resize(1100, 760)   # и обратно
    QApplication.processEvents()
    # Доли те же (±1 % на округление пикселей)
    assert all(abs(a - b) <= 0.01 for a, b in zip(_ratios(table), before))
    # Столбцы занимают ровно ширину таблицы — без щели справа
    header = table.horizontalHeader()
    used = sum(header.sectionSize(c) for c in range(table.columnCount()))
    assert used == table.viewport().width()
    window.close()


def test_cells_are_centered(window):
    table = window.clients.table
    centered = Qt.AlignmentFlag.AlignCenter
    for col in range(table.columnCount()):
        assert table.item(0, col).textAlignment() == centered
    header_align = table.horizontalHeader().defaultAlignment()
    assert header_align & Qt.AlignmentFlag.AlignHCenter


def test_preferred_contact_is_bold(window, manager):
    lisa = manager.add_client(Client(name="Алиса", email="a@mail.ru",
                                     phone="+7 900 000-00-00",
                                     preferred_contact=ContactMethod.PHONE))
    window.refresh()
    table = window.clients.table
    row = [table.item(r, 0).text() for r in range(table.rowCount())].index(
        lisa.name)
    assert table.item(row, 4).font().bold()        # телефон — жирным
    assert not table.item(row, 3).font().bold()    # почта — обычным


def test_column_editing_saved_and_reset(manager, tmp_path):
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    first = MainWindow(manager, today=lambda: TODAY, settings=settings)
    table = _shown_clients(first)
    columns = first.clients.columns

    first.set_table_editing(True)
    assert first.edit_bar.isVisibleTo(first)
    header = table.horizontalHeader()
    header.resizeSection(0, 400)             # шире «Имя»
    header.moveSection(header.visualIndex(4), 1)   # «Телефон» вторым
    columns.set_hidden(8, True)              # спрятать «Заметку»
    first.set_table_editing(False)           # «Готово» — сохраняем
    name_share = columns.weights[0]
    first.close()

    second = MainWindow(manager, today=lambda: TODAY, settings=settings)
    table2 = _shown_clients(second)
    restored = second.clients.columns
    assert round(restored.weights[0], 2) == round(name_share, 2)
    assert table2.horizontalHeader().logicalIndex(1) == 4
    assert table2.horizontalHeader().isSectionHidden(8)

    second.set_table_editing(True)
    second.reset_tables()                    # «Сбросить»
    assert restored.weights == restored.defaults
    assert not table2.horizontalHeader().isSectionHidden(8)
    assert table2.horizontalHeader().logicalIndex(1) == 1
    second.set_table_editing(False)
    second.close()


def test_columns_fixed_outside_editing(window):
    from PyQt6.QtWidgets import QHeaderView
    header = window.clients.table.horizontalHeader()
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Fixed
    window.set_table_editing(True)
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Interactive
    assert header.sectionsMovable()
    window.set_table_editing(False)
    assert not header.sectionsMovable()


def test_last_visible_column_cannot_be_hidden(window):
    columns = window.clients.columns
    for col in range(columns.count):
        columns.set_hidden(col, True)
    assert len(columns.visible_columns()) == 1


def test_animations_submenu(window):
    menu = window.sidebar.settings_btn.menu()
    anim_menu = next(a.menu() for a in menu.actions()
                     if a.text() == "Анимации")
    texts = [a.text() for a in anim_menu.actions()]
    assert texts == ["Включены", "Выключены"]
    anim_menu.actions()[1].trigger()
    assert window.toast.text.text().startswith("Анимации выключены")


# --- v0.5.1: карточка клиента и границы столбцов ---

def test_client_details_show_full_note(window, manager):
    long_note = "Очень длинная заметка о клиенте. " * 10
    client = manager.add_client(Client(name="Алиса", note=long_note.strip(),
                                       email="a@mail.ru",
                                       preferred_contact=ContactMethod.EMAIL))
    window.refresh()
    table = window.clients.table
    assert window.clients.details.isHidden()   # ничего не выбрано
    row = [table.item(r, 0).text() for r in range(table.rowCount())].index(
        client.name)
    table.selectRow(row)
    assert not window.clients.details.isHidden()
    assert window.clients.details_note.text() == long_note.strip()
    assert "a@mail.ru ★" in window.clients.details_contacts.text()
    # Подсказка заметки — с переносом строк (HTML)
    assert table.item(row, 8).toolTip().startswith("<p")


def test_column_cannot_grow_past_table(window):
    table = _shown_clients(window, 1200)
    header = table.horizontalHeader()
    window.set_table_editing(True)
    header.resizeSection(0, 5000)  # тянем «Имя» далеко за край
    used = sum(header.sectionSize(c) for c in range(table.columnCount()))
    assert used == table.viewport().width()
    # Соседи сжались не меньше минимума
    from freelancedesk.app.table_layout import MIN_WIDTH
    assert min(header.sectionSize(c) for c in range(1, 9)) >= MIN_WIDTH
    window.set_table_editing(False)
    window.close()


def test_shrinking_column_leaves_no_gap(window):
    table = _shown_clients(window, 1200)
    header = table.horizontalHeader()
    window.set_table_editing(True)
    header.resizeSection(0, 70)  # сужаем «Имя»
    used = sum(header.sectionSize(c) for c in range(table.columnCount()))
    assert used == table.viewport().width()  # справа нет пустой полосы
    window.set_table_editing(False)
    window.close()


# --- Этап 2: экспорт и резервные копии из интерфейса ---

def test_data_menu(window):
    menu = window.sidebar.settings_btn.menu()
    data = next(a.menu() for a in menu.actions() if a.text() == "Данные")
    texts = [a.text() for a in data.actions() if a.text()]
    assert "Экспорт всех данных в Excel…" in texts
    backup_action = next(a for a in data.actions()
                         if a.text() == "Создать резервную копию")
    assert not backup_action.isEnabled()  # в тестах база в памяти


def test_export_excel_from_window(window, tmp_path):
    path = tmp_path / "export.xlsx"
    window.export_excel(path)
    assert path.exists()
    assert window.toast.text.text() == "Сохранено: export.xlsx"


def test_export_csv_from_finance(window, tmp_path):
    path = tmp_path / "payments.csv"
    window.finance.export_csv(path)
    assert path.read_text(encoding="utf-8-sig").startswith("Дата;")


def test_backup_from_window(manager, tmp_path):
    import sqlite3
    db = tmp_path / "app.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE t (v INTEGER)")
    win = MainWindow(manager, today=lambda: TODAY, data_dir=tmp_path,
                     db_path=db)
    path = win.make_backup()
    assert path.exists() and path.parent == tmp_path / "backups"
    assert win.toast.text.text() == "Резервная копия создана"
