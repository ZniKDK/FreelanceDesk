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

import sys

from PyQt6.QtCore import QByteArray, QProcess, QSettings, Qt, QTimer, QUrl
from PyQt6.QtGui import (
    QAction, QActionGroup, QDesktopServices, QIcon, QKeySequence,
)
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QFileDialog, QFrame, QHBoxLayout,
    QMainWindow, QMenu,
    QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from freelancedesk import __version__, backup
from freelancedesk.export import export_excel
from freelancedesk.logs import LOG_NAME, log, log_dir
from freelancedesk.app import animations
from freelancedesk.config import resource_dir
from freelancedesk.app.pages.clients import ClientsPage
from freelancedesk.app.pages.dashboard import DashboardPage
from freelancedesk.app.pages.finance import FinancePage
from freelancedesk.app.pages.orders import OrdersPage
from freelancedesk.app.theme import (
    C, THEME_MODES, apply_theme, icon, is_dark,
)
from freelancedesk.app.table_layout import ColumnLayout
from freelancedesk.app.widgets import Toast, button, label


def apply_ui_effects(enabled: bool) -> None:
    """Встроенные эффекты Qt: плавное появление меню и подсказок."""
    for effect in (Qt.UIEffect.UI_AnimateMenu, Qt.UIEffect.UI_FadeMenu,
                   Qt.UIEffect.UI_AnimateTooltip,
                   Qt.UIEffect.UI_FadeTooltip):
        QApplication.setEffectEnabled(effect, enabled)
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

    def __init__(self, window: "MainWindow") -> None:
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


class EditBar(QFrame):
    """Плашка над экраном в режиме настройки таблиц."""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.setObjectName("editBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 10, 8)
        hint = label("Настройка таблиц: тяните границы столбцов, "
                     "перетаскивайте заголовки, правая кнопка по шапке — "
                     "показать или скрыть столбцы")
        hint.setWordWrap(True)
        reset_btn = button("Сбросить", "rotate-ccw")
        reset_btn.clicked.connect(window.reset_tables)
        done_btn = button("Готово", "check", "primary", "#ffffff")
        done_btn.clicked.connect(lambda: window.set_table_editing(False))
        layout.addWidget(hint, 1)
        layout.addWidget(reset_btn)
        layout.addWidget(done_btn)


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
                 storage_label: str = "",
                 db_path: Path | None = None) -> None:
        super().__init__()
        # Файл SQLite — для резервных копий (None: PostgreSQL или память)
        self._db_path = db_path
        self.manager = manager
        self.today = today
        self._settings = settings
        self._data_dir = data_dir
        self._storage_label = storage_label
        self._goal = 0
        self.theme_mode = "light"
        self.table_layouts: list[ColumnLayout] = []
        self.tables_editing = False
        if settings is not None:
            self._goal = settings.value("goal", 0, type=int)
            self.theme_mode = settings.value("theme", "light")
            animations.set_enabled(settings.value("animations", True,
                                                  type=bool))
        self.setWindowTitle("FreelanceDesk")
        self.resize(1260, 780)
        self.setMinimumSize(1040, 640)

        apply_ui_effects(animations.ENABLED)
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
        # Та же иконка, что у exe-файла (resources/app.png)
        self.setWindowIcon(QIcon(str(resource_dir() / "resources"
                                     / "app.png")))
        self.table_layouts = []  # экраны зарегистрируют свои таблицы
        self.stack = QStackedWidget()
        self.dashboard = DashboardPage(self)
        self.orders = OrdersPage(self)
        self.clients = ClientsPage(self)
        self.finance = FinancePage(self)
        self.pages = [self.dashboard, self.orders, self.clients, self.finance]
        for page in self.pages:
            self.stack.addWidget(page)
        self.sidebar = Sidebar(self)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # Справа: плашка режима настройки (обычно скрыта) и экраны
        self.edit_bar = EditBar(self)
        self.edit_bar.hide()
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        bar_holder = QWidget()
        bar_layout = QVBoxLayout(bar_holder)
        bar_layout.setContentsMargins(24, 12, 24, 0)
        bar_layout.addWidget(self.edit_bar)
        self.bar_holder = bar_holder
        bar_holder.hide()
        right_layout.addWidget(bar_holder)
        right_layout.addWidget(self.stack, 1)
        layout.addWidget(self.sidebar)
        layout.addWidget(right, 1)
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
        # Без иконок: у отмеченного пункта видна галочка
        for mode, text in THEME_MODES:
            action = theme_menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(mode == self.theme_mode)
            action.triggered.connect(lambda _, m=mode: self.set_theme(m))
            group.addAction(action)
        anim_menu = menu.addMenu(icon("sparkles"), "Анимации")
        anim_group = QActionGroup(anim_menu)
        for enabled, text in ((True, "Включены"), (False, "Выключены")):
            action = anim_menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(animations.ENABLED == enabled)
            action.triggered.connect(
                lambda _, on=enabled: self.set_animations(on))
            anim_group.addAction(action)
        menu.addAction(icon("list-checks"), "Настроить таблицы",
                       lambda: self.set_table_editing(True))
        menu.addSeparator()
        data = menu.addMenu(icon("folder-open"), "Данные")
        data.addAction("Экспорт всех данных в Excel…",
                       lambda: self.export_excel())
        data.addSeparator()
        for text, slot in (("Создать резервную копию", self.make_backup),
                           ("Восстановить из копии…", self.restore_backup),
                           ("Открыть папку копий", self.open_backups)):
            action = data.addAction(text, slot)
            if self._db_path is None:
                action.setEnabled(False)
                action.setToolTip("Копии делаются только для SQLite; "
                                  "для PostgreSQL используйте pg_dump")
        if self._data_dir is not None:
            data.addSeparator()
            data.addAction("Открыть папку с данными", self.open_data_dir)
            data.addAction("Открыть журнал ошибок", self.open_log)
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
        apply_ui_effects(enabled)
        if self._settings is not None:
            self._settings.setValue("animations", enabled)
        # Сразу видно, что переключатель сработал
        self.notify("Анимации включены" if enabled else
                    "Анимации выключены — интерфейс без движения")

    # ------------------------------------------------------------------
    # Настройка таблиц
    # ------------------------------------------------------------------

    def register_table(self, table, key: str,
                       weights: list[int]) -> ColumnLayout:
        """Экран сообщает о своей таблице: доли ширины, ключ настроек."""
        layout = ColumnLayout(table, key, weights, self._settings)
        self.table_layouts.append(layout)
        return layout

    def set_table_editing(self, editing: bool) -> None:
        """Включить или выключить режим настройки столбцов."""
        self.tables_editing = editing
        for layout in self.table_layouts:
            layout.set_editing(editing)
        self.bar_holder.setVisible(editing)
        self.edit_bar.setVisible(editing)
        if editing:
            animations.fade_in(self.edit_bar, shift=0)
            # На «Главной» таблиц нет — переходим к клиентам
            if self.stack.currentIndex() == HOME:
                self.show_page(CLIENTS)
        else:
            self.notify("Настройки таблиц сохранены")

    def reset_tables(self) -> None:
        for layout in self.table_layouts:
            layout.reset()
        self.notify("Столбцы возвращены к стандартным")

    def _rebuild(self) -> None:
        """Построить экраны заново, сохранив, где был пользователь."""
        if self.tables_editing:  # сохраняем настройку до пересборки
            self.set_table_editing(False)
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

    # ------------------------------------------------------------------
    # Экспорт и резервные копии
    # ------------------------------------------------------------------

    def export_excel(self, path: Path | None = None) -> None:
        """Все данные — в книгу Excel (заказы, платежи, клиенты)."""
        if path is None:
            suggested = (Path.home() / "Documents" /
                         f"FreelanceDesk_{self.today():%d.%m.%Y}.xlsx")
            chosen, _ = QFileDialog.getSaveFileName(
                self, "Экспорт в Excel", str(suggested), "Excel (*.xlsx)")
            if not chosen:
                return
            path = Path(chosen)
        try:
            export_excel(self.manager, path)
        except OSError as exc:
            self.show_error(f"Не удалось сохранить файл (возможно, он "
                            f"открыт в Excel): {exc}")
            return
        log.info("Экспорт в Excel: %s", path)
        self.notify(f"Сохранено: {path.name}", "Открыть папку",
                    lambda: QDesktopServices.openUrl(
                        QUrl.fromLocalFile(str(path.parent))))

    def _backup_dir(self) -> Path:
        return backup.backup_dir(self._data_dir or self._db_path.parent)

    def make_backup(self) -> Path | None:
        """Сделать резервную копию базы прямо сейчас."""
        try:
            path = backup.create_backup(self._db_path, self._backup_dir())
        except Exception as exc:  # noqa: BLE001 — сообщаем о любой ошибке
            log.exception("Не удалось создать копию")
            self.show_error(f"Не удалось создать копию: {exc}")
            return None
        log.info("Резервная копия: %s", path)
        self.notify("Резервная копия создана", "Открыть папку",
                    self.open_backups)
        return path

    def restore_backup(self) -> None:
        """Заменить базу выбранной копией и перезапустить программу."""
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Восстановить из копии", str(self._backup_dir()),
            "Копии FreelanceDesk (*.db)")
        if not chosen or not self.confirm(
                "Заменить текущие данные выбранной копией?\n"
                "Текущая база перед этим сама сохранится в копию.\n"
                "Программа перезапустится."):
            return
        self.manager.close()
        try:
            backup.restore_backup(Path(chosen), self._db_path,
                                  self._backup_dir())
        except Exception as exc:  # noqa: BLE001
            log.exception("Не удалось восстановить копию")
            self.show_error(f"Не удалось восстановить копию: {exc}\n"
                            "Перезапустите программу.")
            return
        log.info("Восстановлено из копии: %s", chosen)
        # Перезапуск: тот же исполняемый файл с теми же аргументами
        QProcess.startDetached(sys.executable, sys.argv)
        QApplication.quit()

    def open_backups(self) -> None:
        folder = self._backup_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def open_log(self) -> None:
        path = log_dir(self._data_dir) / LOG_NAME
        target = path if path.exists() else path.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

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
            f"Данные: {self._storage_label or 'не сохраняются'}<br><br>"
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
        if self.tables_editing:
            self.set_table_editing(False)
        if self._settings is not None:
            self._settings.setValue("geometry", self.saveGeometry())
            self._settings.setValue("page", self.stack.currentIndex())
            key = self.orders.current_filter_key()
            self._settings.setValue("orders_filter",
                                    getattr(key, "value", key))
        super().closeEvent(event)
