"""Главное окно: боковое меню слева, экраны справа.

Окно хранит общие для всех экранов вещи (OrderManager, сегодняшнюю
дату, настройки) и предоставляет экранам услуги: run, show_error,
confirm, open_order (см. описание в пакете pages).
"""

from collections.abc import Callable
from datetime import date
from pathlib import Path

from PyQt6.QtCore import QByteArray, QSettings, QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QKeySequence
from PyQt6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QMainWindow, QMenu, QMessageBox,
    QStackedWidget, QVBoxLayout, QWidget,
)

from freelancedesk import __version__
from freelancedesk.app.pages.clients import ClientsPage
from freelancedesk.app.pages.dashboard import DashboardPage
from freelancedesk.app.pages.finance import FinancePage
from freelancedesk.app.pages.orders import OrdersPage
from freelancedesk.app.theme import C, icon
from freelancedesk.app.widgets import button, label
from freelancedesk.core.manager import OrderManager
from freelancedesk.core.sql_storage import DB_ERRORS

# Ошибки, которые показываем пользователю окном, а не падением программы:
# ValueError/KeyError — нарушены правила OrderManager или хранилища,
# DB_ERRORS — проблемы с базой данных (PostgreSQL или SQLite)
USER_ERRORS = (ValueError, KeyError, *DB_ERRORS)

# Пункты бокового меню: (подпись, иконка)
NAVIGATION = [("Главная", "house"), ("Заказы", "briefcase"),
              ("Клиенты", "users"), ("Финансы", "wallet")]
HOME, ORDERS, CLIENTS, FINANCE = range(4)

HOTKEYS_HELP = """\
Ctrl+1…4 — Главная, Заказы, Клиенты, Финансы
Ctrl+N — новый заказ
Ctrl+Shift+N — новый клиент
Ctrl+P — платёж по выбранному заказу
F2 — изменить выбранное
Delete — удалить выбранное
Ctrl+F — поиск
F5 — обновить
Ctrl+Q — выход

Правая кнопка мыши по заказу — статус, платёж, ссылка."""


class MainWindow(QMainWindow):
    """Главное окно приложения.

    today — функция «какое сегодня число» (в тестах — фиксированная дата).
    settings — где хранить размер окна, экран, фильтр и цель; None — нигде.
    data_dir — папка с файлами пользователя (для пункта меню).
    storage_label — где лежат данные (подпись внизу бокового меню).
    """

    def __init__(self, manager: OrderManager,
                 today: Callable[[], date] = date.today,
                 settings: QSettings | None = None,
                 data_dir: Path | None = None,
                 storage_label: str = "") -> None:
        super().__init__()
        self.manager = manager
        self.today = today
        self._settings = settings
        self._data_dir = data_dir
        self._goal = 0
        self.setWindowTitle("FreelanceDesk")
        self.setWindowIcon(icon("briefcase", C["accent"], 32))
        self.resize(1240, 760)
        self.setMinimumSize(1000, 620)

        # Цель нужна экранам при построении — читаем заранее
        if settings is not None:
            self._goal = settings.value("goal", 0, type=int)

        self.stack = QStackedWidget()
        self.dashboard = DashboardPage(self)
        self.orders = OrdersPage(self)
        self.clients = ClientsPage(self)
        self.finance = FinancePage(self)
        self.pages = [self.dashboard, self.orders, self.clients, self.finance]
        for page in self.pages:
            self.stack.addWidget(page)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar(storage_label))
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self._build_menu()
        self._restore_state()
        self.refresh()

    # ------------------------------------------------------------------
    # Боковое меню и верхнее меню
    # ------------------------------------------------------------------

    def _build_sidebar(self, storage_label: str) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 16, 10, 12)
        layout.setSpacing(4)
        title = label("FreelanceDesk")
        title.setObjectName("appTitle")
        layout.addWidget(title)
        layout.addSpacing(10)

        self.nav_group = QButtonGroup(self)
        self.nav_buttons = []
        for index, (text, icon_name) in enumerate(NAVIGATION):
            btn = button(f"  {text}", icon_name)
            btn.setCheckable(True)
            btn.setToolTip(f"Ctrl+{index + 1}")
            btn.clicked.connect(lambda _, i=index: self.show_page(i))
            self.nav_group.addButton(btn)
            self.nav_buttons.append(btn)
            layout.addWidget(btn)
        layout.addStretch(1)

        if storage_label:
            where = label(storage_label, "caption")
            where.setWordWrap(True)
            where.setToolTip(storage_label)
            layout.addWidget(where)
        if self._data_dir is not None:
            folder = button("Папка с данными", "folder-open", "ghost")
            folder.clicked.connect(self.open_data_dir)
            layout.addWidget(folder)
        return sidebar

    def _action(self, menu: QMenu, text: str, slot: Callable,
                shortcut: str | None = None) -> QAction:
        """Пункт меню с (необязательной) горячей клавишей."""
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _build_menu(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&Файл")
        if self._data_dir is not None:
            self._action(file_menu, "Открыть папку с данными",
                         self.open_data_dir)
            file_menu.addSeparator()
        self._action(file_menu, "Выход", self.close, "Ctrl+Q")

        work = bar.addMenu("&Работа")
        self._action(work, "Новый заказ", self.new_order, "Ctrl+N")
        self._action(work, "Новый клиент", self.new_client, "Ctrl+Shift+N")
        self._action(work, "Платёж по заказу", self.new_payment, "Ctrl+P")
        work.addSeparator()
        self._action(work, "Изменить", self.edit_current, "F2")
        self._action(work, "Удалить", self.delete_current, "Delete")
        self._action(work, "Поиск", self.focus_search, "Ctrl+F")
        self._action(work, "Обновить", self.refresh, "F5")

        view = bar.addMenu("&Вид")
        for index, (text, _) in enumerate(NAVIGATION):
            # _=False — сигнал triggered передаёт флажок, он нам не нужен
            self._action(view, text,
                         lambda _=False, i=index: self.show_page(i),
                         f"Ctrl+{index + 1}")

        help_menu = bar.addMenu("&Справка")
        self._action(help_menu, "Горячие клавиши", self.show_hotkeys)
        self._action(help_menu, "О программе", self.show_about)

    # ------------------------------------------------------------------
    # Навигация и обновление
    # ------------------------------------------------------------------

    def show_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)

    def refresh(self) -> None:
        """Перечитать данные на всех экранах."""
        for page in self.pages:
            page.refresh()

    def open_order(self, order_id: int) -> None:
        """Перейти к заказу на экране «Заказы»."""
        self.show_page(ORDERS)
        self.orders.show_order(order_id)

    # --- Команды меню ---

    def new_order(self) -> None:
        self.show_page(ORDERS)
        self.orders.add_order()

    def new_client(self) -> None:
        self.show_page(CLIENTS)
        self.clients.add_client()

    def new_payment(self) -> None:
        self.show_page(ORDERS)
        self.orders.add_payment()

    def edit_current(self) -> None:
        if self.stack.currentIndex() == ORDERS:
            self.orders.edit_order()
        elif self.stack.currentIndex() == CLIENTS:
            self.clients.edit_client()

    def delete_current(self) -> None:
        if self.stack.currentIndex() == ORDERS:
            self.orders.delete_order()
        elif self.stack.currentIndex() == CLIENTS:
            self.clients.delete_client()

    def focus_search(self) -> None:
        """Ctrl+F: поиск клиентов на экране «Клиенты», иначе — заказов."""
        on_clients = self.stack.currentIndex() == CLIENTS
        page = self.clients if on_clients else self.orders
        self.show_page(CLIENTS if on_clients else ORDERS)
        page.search_edit.setFocus()
        page.search_edit.selectAll()

    # ------------------------------------------------------------------
    # Цель на месяц
    # ------------------------------------------------------------------

    def goal(self) -> int:
        return self._goal

    def set_goal(self, value: int) -> None:
        self._goal = value
        if self._settings is not None:
            self._settings.setValue("goal", value)
        self.dashboard.refresh()

    # ------------------------------------------------------------------
    # Услуги для экранов
    # ------------------------------------------------------------------

    def run(self, action: Callable[[], object]) -> bool:
        """Выполнить изменение данных и обновить все экраны.

        Ошибку показываем окном с текстом — программа не падает.
        Возвращает True, если действие прошло успешно.
        """
        try:
            action()
        except USER_ERRORS as exc:
            self.show_error(str(exc))
            return False
        self.refresh()
        return True

    def show_error(self, text: str) -> None:
        QMessageBox.warning(self, "FreelanceDesk", text)

    def confirm(self, text: str) -> bool:
        answer = QMessageBox.question(self, "FreelanceDesk", text)
        return answer == QMessageBox.StandardButton.Yes

    # ------------------------------------------------------------------
    # Справка и служебное
    # ------------------------------------------------------------------

    def open_data_dir(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._data_dir)))

    def show_hotkeys(self) -> None:
        QMessageBox.information(self, "Горячие клавиши", HOTKEYS_HELP)

    def show_about(self) -> None:
        QMessageBox.about(
            self, "О программе",
            f"<b>FreelanceDesk {__version__}</b><br>"
            "Учёт заказов самозанятого фрилансера:<br>"
            "сроки, платежи, доход и налог НПД.<br><br>"
            "Иконки — Lucide (ISC). Лицензия программы — MIT.<br>"
            "<a href='https://github.com/ZniKDK/FreelanceDesk'>GitHub</a>")

    def _restore_state(self) -> None:
        """Вернуть размер окна, экран и фильтр заказов с прошлого запуска."""
        page = 0
        if self._settings is not None:
            geometry = self._settings.value("geometry")
            if isinstance(geometry, QByteArray):
                self.restoreGeometry(geometry)
            # type=int — значения из ini-файла приходят строками
            page = self._settings.value("page", 0, type=int)
            saved_filter = self._settings.value("orders_filter", "")
            for key, chip_btn in self.orders.chips.items():
                # У выборок OrderView сохраняем .value, у «отменённых» — ключ
                if getattr(key, "value", key) == saved_filter:
                    chip_btn.setChecked(True)
        self.show_page(page if 0 <= page < len(self.pages) else 0)

    def closeEvent(self, event) -> None:  # noqa: N802 — имя задано Qt
        """Перед закрытием окна запомнить его состояние."""
        if self._settings is not None:
            self._settings.setValue("geometry", self.saveGeometry())
            self._settings.setValue("page", self.stack.currentIndex())
            key = self.orders.current_filter_key()
            self._settings.setValue("orders_filter",
                                    getattr(key, "value", key))
        super().closeEvent(event)
