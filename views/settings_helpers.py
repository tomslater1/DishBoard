"""Shared UI helpers for settings pages."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QWidget

from utils.theme import manager


def _sep_style() -> str:
    return (
        f"color: {manager.c('#252535', '#dddddd')};"
        f" background: {manager.c('#252535', '#dddddd')};"
        " border: none; max-height: 1px;"
    )


def _card_style() -> str:
    return (
        f"background: {manager.c('#14191d', '#fffaf3')};"
        "border: none;"
        "border-radius: 14px;"
    )


def make_sep() -> QFrame:
    sep = QFrame()
    sep.setProperty("settingsSep", True)
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(_sep_style())
    return sep


def selector_style(active: bool, size: int = 15) -> str:
    if active:
        return (
            f"QPushButton {{"
            f"  background-color: rgba(255,107,53,0.12);"
            f"  color: {manager.c('#f2ebe3', '#261c14')};"
            f"  border: none;"
            f"  border-radius: 10px;"
            f"  font-size: {size}px; font-weight: 700;"
            f"}}"
        )
    bg = manager.c("#0e0e0e", "#f7f7f7")
    fg = manager.c("#606060", "#555555")
    hover = manager.c("#161616", "#eeeeee")
    return (
        f"QPushButton {{"
        f"  background-color: {bg}; color: {fg};"
        f"  border: none; border-radius: 10px;"
        f"  font-size: {size}px; font-weight: 500;"
        f"}}"
        f"QPushButton:hover {{"
        f"  background-color: {hover};"
        f"  color: {manager.c('#909090', '#333333')};"
        f"}}"
    )


def card_widget() -> QWidget:
    w = QWidget()
    w.setProperty("settingsCard", True)
    w.setStyleSheet(_card_style())
    return w


def refresh_surface_styles(root: QWidget) -> None:
    for widget in root.findChildren(QWidget):
        if widget.property("settingsCard"):
            widget.setStyleSheet(_card_style())
    for sep in root.findChildren(QFrame):
        if sep.property("settingsSep"):
            sep.setStyleSheet(_sep_style())
