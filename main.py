"""Запуск из IDE (PyCharm): Run 'main'.

Добавляет src/ в путь поиска модулей, чтобы пакет freelancedesk
находился без установки через pip.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from freelancedesk.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
