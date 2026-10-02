"""Главное окно приложения."""

from PyQt6.QtWidgets import QLabel, QMainWindow, QTabWidget

from freelancedesk.core.manager import OrderManager


class MainWindow(QMainWindow):
    """Главное окно: вкладки «Заказы», «Клиенты», «Сводка».

    Заготовка: таблицы и кнопки появятся на следующем этапе.
    """

    def __init__(self, manager: OrderManager) -> None:
        super().__init__()
        self._manager = manager
        self.setWindowTitle("FreelanceDesk — учёт заказов")
        self.resize(900, 600)

        tabs = QTabWidget()
        tabs.addTab(QLabel("Список заказов"), "Заказы")
        tabs.addTab(QLabel("Список клиентов"), "Клиенты")
        tabs.addTab(QLabel("Доход и налог за период"), "Сводка")
        self.setCentralWidget(tabs)
