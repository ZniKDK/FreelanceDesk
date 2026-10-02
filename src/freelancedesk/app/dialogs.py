"""Диалоги добавления и редактирования клиентов и заказов."""

from PyQt6.QtWidgets import QDialog


class ClientDialog(QDialog):
    """Форма клиента. Заготовка."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Клиент")


class OrderDialog(QDialog):
    """Форма заказа. Заготовка."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Заказ")
