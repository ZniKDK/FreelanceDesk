"""Главное окно: боковое меню слева, экраны справа.

Окно хранит общие для всех экранов вещи (OrderManager, сегодняшнюю
дату, настройки) и предоставляет экранам услуги: run, notify,
show_error, confirm, open_order (см. описание в пакете pages).

Верхнего меню нет: команды — в боковом меню («Настройки», «Справка»),
горячие клавиши работают через действия окна (QAction).
"""

from collections.abc import Callable
from datetime import date
from pathlib import Path

from PyQt6.QtCore import QByteArray, QSettings, Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QActionGroup, QDesktopServices, QKeySequence
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QMainWindow, QMenu,
    QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from freelancedesk import __version__
from freelancedesk.app import animations
from freelancedesk.app.pages.clients import ClientsPage
from freelancedesk.app.pages.dashboard import DashboardPage
from freelancedesk.app.pages.finance import FinancePage
from freelancedesk.app.pages.orders import OrdersPage
from freelancedesk.app.theme import (
    C, THEME_MODES, apply_theme, icon, is_dark,
)
from freelancedesk.app.widgets import Toast, button, label
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
Ctrl+T — светлая / тёмная тема
F5 — обновить
Ctrl+Q — выход

Правая кнопка мыши по заказу — статус, платёж, ссылка."""


class Sidebar(QFrame):
    """Боковое меню с плавно переезжающей подсветкой выбранного пункта."""

    def __init__(self, window: "MainWindow", storage_label: str) -> None:
        super().__init__()
        self.setObjectName("sidebar")
        self.setFixedWidth(210)
        # Подсветка — отдельная плашка под кнопками; её и двигаем
        self.indicator = QFrame(self)
        self.indicator.setObjectName("navIndicator")
        self.indicator.lower()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 16, 10, 12)
        layout.setSpacing(4)
        title = label("FreelanceDesk")
        title.setObjectName("appTitle")
        layout.addWidget(title)
        layout.addSpacing(10)

        self.group = QButtonGroup(self)
        self.buttons: list[QPushButton] = []
        for index, (text, icon_name) in enumerate(NAVIGATION):
            btn = button(f"  {text}", icon_name)
            btn.setCheckable(True)
            btn.setToolTip(f"Ctrl+{index + 1}")
            btn.clicked.connect(lambda _, i=index: window.show_page(i))
            self.group.addButton(btn)
            self.buttons.append(btn)
            layout.addWidget(btn)
        layout.addStretch(1)

        if storage_label:
            where = label(storage_label, "caption")
            where.setWordWrap(True)
            where.setToolTip(storage_label)
            layout.addWidget(where)
            layout.addSpacing(6)
        self.settings_btn = button("  Настройки", "settings")
        self.settings_btn.setMenu(window.build_settings_menu())
        self.help_btn = button("  Справка", "circle-help")
        self.help_btn.setMenu(window.build_help_menu())
        layout.addWidget(self.settings_btn)
        layout.addWidget(self.help_btn)

    def select(self, index: int, animate: bool = True) -> None:
        """Отметить пункт и передвинуть к нему подсветку."""
        btn = self.buttons[index]
        btn.setChecked(True)
        if animate:
            animations.slide_to(self.indicator, btn.geometry())
        else:
            self.indicator.setGeometry(btn.geometry())

    def _sync_indicator(self) -> None:
        checked = self.group.checkedButton()
        if checked is not None:
            self.indicator.setGeometry(checked.geometry())

    def resizeEvent(self, event) -> None:  # noqa: N802 — имя задано Qt
        super().resizeEvent(event)
        self._sync_indicator()

    def showEvent(self, event) -> None:  # noqa: N802 — имя задано Qt
        super().showEvent(event)
        # Кнопки получают координаты после раскладки — ставим подсветку
        # чуть позже, когда Qt её закончит
        QTimer.singleShot(0, self._sync_indicator)


class MainWindow(QMainWindow):
    """Главное окно приложения.

    today — функция «какое сегодня число» (в тестах — фиксированная дата).
    settings — где хранить окно, экран, фильтр, цель, тему; None — нигде.
    data_dir — папка с файлами пользователя.
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
        self._storage_label = storage_label
        self._goal = 0
        self.theme_mode = "light"
        if settings is not None:
            self._goal = settings.value("goal", 0, type=int)
            self.theme_mode = settings.value("theme", "light")
            animations.set_enabled(settings.value("animations", True,
                                                  type=bool))
        self.setWindowTitle("FreelanceDesk")
        self.resize(1260, 780)
        self.setMinimumSize(1040, 640)

        self._build_shortcuts()
        self.toast = Toast(self)
        self._build_ui()
        self._restore_state()
        self.refresh()

        # «Как в системе»: следим за переключением темы Windows
        app = QApplication.instance()
        app.styleHints().colorSchemeChanged.connect(self._system_theme_changed)

    # ------------------------------------------------------------------
    # Построение интерфейса (повторяется при смене темы)
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowIcon(icon("briefcase", C["accent"], 32))
        self.stack = QStackedWidget()
        self.dashboard = DashboardPage(self)
        self.orders = OrdersPage(self)
        self.clients = ClientsPage(self)
        self.finance = FinancePage(self)
        self.pages = [self.dashboard, self.orders, self.clients, self.finance]
        for page in self.pages:
            self.stack.addWidget(page)
        self.sidebar = Sidebar(self, self._storage_label)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, 1)
        # Старое содержимое окна Qt удалит сам
        self.setCentralWidget(central)
        self.toast.left_margin = self.sidebar.width()
        self.toast.raise_()

    def _build_shortcuts(self) -> None:
        """Горячие клавиши — действия окна без видимого меню."""
        shortcuts = [
            ("Ctrl+N", self.new_order), ("Ctrl+Shift+N", self.new_client),
            ("Ctrl+P", self.new_payment), ("F2", self.edit_current),
            ("Delete", self.delete_current), ("Ctrl+F", self.focus_search),
            ("F5", self.refresh), ("Ctrl+Q", self.close),
            ("Ctrl+T", self.toggle_theme),
        ]
        for index in range(len(NAVIGATION)):
            shortcuts.append((f"Ctrl+{index + 1}",
                              lambda i=index: self.show_page(i)))
        for keys, slot in shortcuts:
            action = QAction(self)
            action.setShortcut(QKeySequence(keys))
            # _=False — сигнал triggered передаёт флажок, он не нужен
            action.triggered.connect(lambda _=False, slot=slot: slot())
            self.addAction(action)

    def build_settings_menu(self) -> QMenu:
        menu = QMenu(self)
        theme_menu = menu.addMenu(icon("sun"), "Тема")
        group = QActionGroup(theme_menu)  # выбор только одного варианта
        theme_icons = {"light": "sun", "dark": "moon", "system": "monitor"}
        for mode, text in THEME_MODES:
            action = theme_menu.addAction(icon(theme_icons[mode]), text)
            action.setCheckable(True)
            action.setChecked(mode == self.theme_mode)
            action.triggered.connect(lambda _, m=mode: self.set_theme(m))
            group.addAction(action)
        anim = menu.addAction(icon("sparkles"), "Анимации")
        anim.setCheckable(True)
        anim.setChecked(animations.ENABLED)
        anim.toggled.connect(self.set_animations)
        if self._data_dir is not None:
            menu.addSeparator()
            menu.addAction(icon("folder-open"), "Открыть папку с данными",
                           self.open_data_dir)
        return menu

    def build_help_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.addAction(icon("keyboard"), "Горячие клавиши", self.show_hotkeys)
        menu.addAction(icon("info"), "О программе", self.show_about)
        return menu

    # ------------------------------------------------------------------
    # Тема и анимации
    # ------------------------------------------------------------------

    def set_theme(self, mode: str) -> None:
        """Сменить тему на лету: пересобрать стили и экраны."""
        self.theme_mode = mode
        if self._settings is not None:
            self._settings.setValue("theme", mode)
        apply_theme(QApplication.instance(), mode)
        self._rebuild()

    def toggle_theme(self) -> None:
        """Ctrl+T: светлая ↔ тёмная."""
        self.set_theme("light" if is_dark() else "dark")

    def _system_theme_changed(self) -> None:
        if self.theme_mode == "system":
            self.set_theme("system")

    def set_animations(self, enabled: bool) -> None:
        animations.set_enabled(enabled)
        if self._settings is not None:
            self._settings.setValue("animations", enabled)

    def _rebuild(self) -> None:
        """Построить экраны заново, сохранив, где был пользователь."""
        page = self.stack.currentIndex()
        orders_filter = self.orders.current_filter_key()
        order_id = self.orders.selected_order_id()
        self._build_ui()
        self.orders.chips[orders_filter].setChecked(True)
        self.refresh()
        self.show_page(page, animate=False)
        if order_id is not None:
            self.orders.select_order(order_id)

    # ------------------------------------------------------------------
    # Навигация и обновление
    # ------------------------------------------------------------------

    def show_page(self, index: int, animate: bool = True) -> None:
        changed = index != self.stack.currentIndex()
        self.stack.setCurrentIndex(index)
        self.sidebar.select(index, animate=animate and changed)
        if changed and animate:
            animations.fade_in(self.stack.currentWidget())
            if index == FINANCE:
                self.finance.chart.replay()

    def refresh(self) -> None:
        """Перечитать данные на всех экранах."""
        for page in self.pages:
            page.refresh()

    def open_order(self, order_id: int) -> None:
        """Перейти к заказу на экране «Заказы»."""
        self.show_page(ORDERS)
        self.orders.show_order(order_id)

    # --- Команды горячих клавиш ---

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

        Пока действие выполняется, курсор — «часики» (заметно, только
        если база отвечает медленно, например PostgreSQL по сети).
        Ошибку показываем окном с текстом — программа не падает.
        Возвращает True, если действие прошло успешно.
        """
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            action()
        except USER_ERRORS as exc:
            QApplication.restoreOverrideCursor()
            self.show_error(str(exc))
            return False
        try:
            self.refresh()
        finally:
            QApplication.restoreOverrideCursor()
        return True

    def notify(self, text: str, action_text: str = "",
               callback: Callable[[], None] | None = None) -> None:
        """Короткое уведомление внизу окна (с необязательной кнопкой)."""
        self.toast.show_message(text, action_text, callback)

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

    def resizeEvent(self, event) -> None:  # noqa: N802 — имя задано Qt
        super().resizeEvent(event)
        self.toast.reposition()

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
        self.show_page(page if 0 <= page < len(self.pages) else 0,
                       animate=False)

    def closeEvent(self, event) -> None:  # noqa: N802 — имя задано Qt
        """Перед закрытием окна запомнить его состояние."""
        if self._settings is not None:
            self._settings.setValue("geometry", self.saveGeometry())
            self._settings.setValue("page", self.stack.currentIndex())
            key = self.orders.current_filter_key()
            self._settings.setValue("orders_filter",
                                    getattr(key, "value", key))
        super().closeEvent(event)
