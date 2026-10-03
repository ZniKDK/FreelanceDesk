"""Короткие анимации интерфейса.

Все анимации идут через QPropertyAnimation / QVariantAnimation: Qt сам
плавно меняет значение (прозрачность, положение, число) за заданное
время. Длительности маленькие (150–400 мс), чтобы программа ощущалась
плавной, но не медленной.

ENABLED — общий выключатель (настройка «Анимации»). Когда он выключен,
функции сразу ставят конечное значение. В тестах анимации выключены.
"""

from collections.abc import Callable

from PyQt6.QtCore import (
    QEasingCurve, QObject, QPoint, QPropertyAnimation, QRect,
    QVariantAnimation,
)
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QProgressBar, QWidget

ENABLED = True

# Плавное замедление к концу движения — выглядит естественно
EASING = QEasingCurve.Type.OutCubic


def set_enabled(value: bool) -> None:
    global ENABLED
    ENABLED = value


def _keep(owner: QObject, name: str, animation) -> None:
    """Сохранить анимацию в атрибуте владельца.

    Иначе Python удалит объект анимации сразу после выхода из функции,
    и она не успеет проиграться. Новая анимация того же типа
    останавливает предыдущую.
    """
    old = getattr(owner, name, None)
    if old is not None:
        old.stop()
    setattr(owner, name, animation)


def fade_in(widget: QWidget, duration: int = 220, shift: int = 10) -> None:
    """Плавное появление виджета: прозрачность 0 → 1 и сдвиг снизу вверх.

    Эффект прозрачности после анимации снимаем: постоянный эффект
    замедляет отрисовку и мешает вложенным эффектам.
    """
    if not ENABLED:
        return
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)

    opacity = QPropertyAnimation(effect, b"opacity", widget)
    opacity.setDuration(duration)
    opacity.setStartValue(0.0)
    opacity.setEndValue(1.0)
    opacity.setEasingCurve(EASING)
    opacity.finished.connect(lambda: widget.setGraphicsEffect(None))
    _keep(widget, "_fade_animation", opacity)
    opacity.start()

    if shift:
        end = widget.pos()
        move = QPropertyAnimation(widget, b"pos", widget)
        move.setDuration(duration)
        move.setStartValue(end + QPoint(0, shift))
        move.setEndValue(end)
        move.setEasingCurve(EASING)
        _keep(widget, "_move_animation", move)
        move.start()


def animate_value(bar: QProgressBar, value: int, duration: int = 450) -> None:
    """Полоска прогресса плавно доезжает до нового значения."""
    if not ENABLED or bar.value() == value:
        bar.setValue(value)
        return
    animation = QPropertyAnimation(bar, b"value", bar)
    animation.setDuration(duration)
    animation.setStartValue(bar.value())
    animation.setEndValue(value)
    animation.setEasingCurve(EASING)
    _keep(bar, "_value_animation", animation)
    animation.start()


def count_up(owner: QObject, start: float, end: float,
             show: Callable[[float], None], duration: int = 500) -> None:
    """Число плавно «досчитывает» от start до end.

    show(значение) вызывается на каждом кадре и обновляет надпись.
    """
    if not ENABLED or start == end:
        show(end)
        return
    animation = QVariantAnimation(owner)
    animation.setDuration(duration)
    animation.setStartValue(float(start))
    animation.setEndValue(float(end))
    animation.setEasingCurve(EASING)
    animation.valueChanged.connect(show)
    # Последний кадр — точное значение, без ошибок округления float
    animation.finished.connect(lambda: show(end))
    _keep(owner, "_count_animation", animation)
    animation.start()


def slide_to(widget: QWidget, target: QRect, duration: int = 220) -> None:
    """Плавно передвинуть виджет в новые координаты и размер."""
    if not ENABLED or not widget.isVisible():
        widget.setGeometry(target)
        return
    animation = QPropertyAnimation(widget, b"geometry", widget)
    animation.setDuration(duration)
    animation.setStartValue(widget.geometry())
    animation.setEndValue(target)
    animation.setEasingCurve(EASING)
    _keep(widget, "_slide_animation", animation)
    animation.start()


def progress_animation(owner: QObject, on_frame: Callable[[float], None],
                       duration: int = 500) -> None:
    """Значение 0 → 1 за duration мс (например, рост столбцов диаграммы)."""
    if not ENABLED:
        on_frame(1.0)
        return
    animation = QVariantAnimation(owner)
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(EASING)
    animation.valueChanged.connect(on_frame)
    _keep(owner, "_progress_animation", animation)
    animation.start()
