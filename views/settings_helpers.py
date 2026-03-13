"""Shared UI helpers for settings pages."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QPushButton, QWidget

from utils.theme import manager


def make_sep() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(
        f"color: {manager.c('#252535', '#dddddd')};"
        f" background: {manager.c('#252535', '#dddddd')};"
        " border: none; max-height: 1px;"
    )
    return sep


def selector_style(active: bool, size: int = 15) -> str:
    if active:
        return (
            f"QPushButton {{"
            f"  background-color: rgba(255,107,53,0.14);"
            f"  color: #ff6b35;"
            f"  border: 2px solid #ff6b35;"
            f"  border-radius: 10px;"
            f"  font-size: {size}px; font-weight: 700;"
            f"}}"
        )
    bg = manager.c("#0e0e0e", "#f7f7f7")
    fg = manager.c("#606060", "#555555")
    border = manager.c("#2c2c2c", "#cecece")
    hover = manager.c("#161616", "#eeeeee")
    return (
        f"QPushButton {{"
        f"  background-color: {bg}; color: {fg};"
        f"  border: 1px solid {border}; border-radius: 10px;"
        f"  font-size: {size}px; font-weight: 500;"
        f"}}"
        f"QPushButton:hover {{"
        f"  background-color: {hover}; border-color: rgba(255,107,53,0.35);"
        f"  color: {manager.c('#909090', '#333333')};"
        f"}}"
    )


def card_widget() -> QWidget:
    w = QWidget()
    w.setObjectName("card")
    return w

