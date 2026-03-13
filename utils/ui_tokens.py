"""Shared UI tokens for consistent spacing, radius, and control styles."""

from __future__ import annotations

from utils.theme import manager


SPACING = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 24,
    "xxl": 32,
}

RADIUS = {
    "sm": 8,
    "md": 10,
    "lg": 12,
    "xl": 14,
}

FONT = {
    "display": 30,
    "page": 28,
    "card_title": 16,
    "body": 14,
    "micro": 12,
}

MOTION = {
    "fast": 120,
    "base": 170,
    "slow": 240,
}


def secondary_button_style() -> str:
    return (
        "QPushButton {"
        f"  background-color: {manager.c('rgba(255,255,255,0.04)', 'rgba(0,0,0,0.04)')};"
        f"  color: {manager.c('#888888', '#555555')};"
        f"  border: 1px solid {manager.c('#2c2c2c', '#cccccc')}; border-radius: {RADIUS['md']}px;"
        "  font-size: 13px; font-weight: 600; padding: 0 14px;"
        "}"
        "QPushButton:hover {"
        f"  background-color: {manager.c('rgba(255,255,255,0.08)', 'rgba(0,0,0,0.08)')};"
        "  border-color: rgba(255,107,53,0.4);"
        f"  color: {manager.c('#bbbbbb', '#222222')};"
        "}"
    )


def primary_button_style() -> str:
    return (
        "QPushButton {"
        "  background-color: rgba(255,107,53,0.10); color: #ff6b35;"
        "  border: 1px solid rgba(255,107,53,0.35); border-radius: 10px;"
        "  font-size: 13px; font-weight: 600; padding: 0 14px;"
        "}"
        "QPushButton:hover {"
        "  background-color: rgba(255,107,53,0.20); border-color: rgba(255,107,53,0.60);"
        "}"
    )


def subtle_surface_style() -> str:
    return (
        f"background: {manager.c('rgba(255,255,255,0.03)', 'rgba(0,0,0,0.03)')};"
        f"border: 1px solid {manager.c('rgba(255,255,255,0.08)', '#dddddd')};"
        f"border-radius: {RADIUS['md']}px;"
    )


def checkbox_style() -> str:
    return (
        "QCheckBox {"
        f" color: {manager.c('#e0e0e0', '#1a1a1a')};"
        " font-size: 13px; font-weight: 600;"
        " spacing: 8px;"
        " background: transparent;"
        "}"
        "QCheckBox::indicator {"
        " image: none;"
        " width: 16px; height: 16px;"
        f" border: 1px solid {manager.c('#3a3a3a', '#bdbdbd')};"
        " border-radius: 4px;"
        f" background: {manager.c('#141414', '#ffffff')};"
        "}"
        "QCheckBox::indicator:checked {"
        " image: none;"
        " background: #ff6b35;"
        " border: 1px solid #ff6b35;"
        "}"
    )
