"""Общие настройки тестов."""

import os

# offscreen — Qt рисует окна в памяти, не показывая их на экране.
# Нужно задать до создания QApplication, поэтому — в самом начале.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
