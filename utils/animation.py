"""UI motion helpers designed for paint stability (no QGraphics effects)."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QAbstractAnimation
from utils.ui_tokens import MOTION


def slide_in_widget(widget, *, offset_px: int = 16, duration_ms: int = 170):
    """Slide the given widget in from the right.

    Uses position animation only (no QGraphicsEffect) to avoid painter warnings.
    Returns the QPropertyAnimation instance.
    """
    if widget is None:
        return None

    try:
        old = getattr(widget, "_dishy_slide_anim", None)
        if old is not None:
            old.stop()
    except Exception:
        pass

    end_pos = widget.pos()
    start_pos = QPoint(end_pos.x() + int(offset_px), end_pos.y())
    widget.move(start_pos)

    anim = QPropertyAnimation(widget, b"pos", widget)
    base = int(MOTION.get("base", 170))
    anim.setDuration(max(80, int(duration_ms or base)))
    anim.setStartValue(start_pos)
    anim.setEndValue(end_pos)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    setattr(widget, "_dishy_slide_anim", anim)

    def _cleanup():
        if getattr(widget, "_dishy_slide_anim", None) is anim:
            setattr(widget, "_dishy_slide_anim", None)

    anim.finished.connect(_cleanup)
    anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim
