"""Общие настройки тестов."""

import os

# offscreen — Qt рисует окна в памяти, не показывая их на экране.
# Нужно задать до создания QApplication, поэтому — в самом начале.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


import pytest  # noqa: E402 — после настройки окружения Qt


@pytest.fixture(autouse=True)
def no_animations():
    """Анимации в тестах выключены: значения ставятся сразу."""
    from freelancedesk.app import animations
    animations.set_enabled(False)
    yield
    animations.set_enabled(False)
