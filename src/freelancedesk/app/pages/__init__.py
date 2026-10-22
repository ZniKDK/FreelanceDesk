"""Экраны приложения: Главная, Заказы, Клиенты, Финансы.

Каждый экран получает ссылку на главное окно (app) и пользуется его
общими услугами:
    app.manager      — OrderManager, вся работа с данными;
    app.today()      — сегодняшняя дата (в тестах — фиксированная);
    app.run(action)  — выполнить изменение данных, показать ошибку окном
                       и обновить все экраны;
    app.open_order(id) — перейти к заказу на экране «Заказы».
"""

from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from freelancedesk.app.widgets import label


class Page(QWidget):
    """Основа экрана: заголовок сверху, содержимое ниже."""

    def __init__(self, app, title: str) -> None:
        super().__init__()
        self.app = app
        self.setObjectName("page")
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(24, 20, 24, 20)
        self.layout_.setSpacing(14)
        # Строка заголовка: название слева, кнопки экрана справа
        self.header = QHBoxLayout()
        self.title_label = label(title)
        self.title_label.setObjectName("pageTitle")
        self.header.addWidget(self.title_label)
        self.header.addStretch(1)
        self.layout_.addLayout(self.header)

    def refresh(self) -> None:
        """Перечитать данные и перерисовать экран."""
