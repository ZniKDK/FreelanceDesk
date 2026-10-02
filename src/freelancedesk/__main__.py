"""Точка входа: python -m freelancedesk."""

import sys

from PyQt6.QtWidgets import QApplication

from freelancedesk.app.main_window import MainWindow
from freelancedesk.core.manager import OrderManager
from freelancedesk.core.storage import InMemoryStorage


def main() -> int:
    app = QApplication(sys.argv)
    # Пока DbStorage не готов, работаем с хранилищем в памяти
    manager = OrderManager(InMemoryStorage())
    window = MainWindow(manager)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
