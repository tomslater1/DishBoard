"""Shared UI tokens for consistent spacing, surfaces, and control styles."""

from __future__ import annotations

from utils.theme import manager


SPACING = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 24,
    "xxl": 32,
    "page_y": 28,
    "page_x": 32,
    "page_y_compact": 20,
    "page_x_compact": 24,
    "card_padding": 20,
    "section_gap": 24,
    "section_gap_sm": 12,
}

RADIUS = {
    "sm": 8,
    "md": 10,
    "lg": 12,
    "xl": 14,
    "pill": 18,
    "panel": 16,
}

FONT = {
    "display": 30,
    "page": 28,
    "card_title": 16,
    "body": 14,
    "micro": 12,
    "eyebrow": 11,
}

MOTION = {
    "hover": 120,
    "fast": 120,
    "base": 170,
    "section": 170,
    "slow": 240,
    "panel": 240,
}

SIZING = {
    "toolbar_height": 40,
    "control_height": 38,
    "tab_height": 36,
    "chip_height": 28,
}

SURFACE = {
    "base": ("#111317", "#fcf8f2"),
    "raised": ("#171a1f", "#ffffff"),
    "muted": ("#14171b", "#f4efe8"),
    "tint": ("rgba(255,255,255,0.04)", "rgba(0,0,0,0.04)"),
}

BORDER = {
    "soft": ("rgba(255,255,255,0.08)", "#ddd2c5"),
    "default": ("#2b3036", "#ddd2c5"),
    "strong": ("#383d45", "#cfc2b5"),
}

TEXT = {
    "primary": ("#f2eee8", "#181510"),
    "secondary": ("#a39d95", "#71685d"),
    "muted": ("#8c867e", "#8b8176"),
    "tertiary": ("#6f6962", "#9f9488"),
}

ACCENT = {
    "primary": "#ff6b35",
    "success": "#34d399",
    "warning": "#f0a500",
    "danger": "#ef4444",
    "info": "#60a5fa",
}


def page_margins(*, compact: bool = False) -> tuple[int, int, int, int]:
    if compact:
        return (
            SPACING["page_x_compact"],
            SPACING["page_y_compact"],
            SPACING["page_x_compact"],
            SPACING["page_y_compact"],
        )
    return (SPACING["page_x"], SPACING["page_y"], SPACING["page_x"], SPACING["page_y"])


def text_color(level: str = "primary") -> str:
    dark, light = TEXT.get(level, TEXT["primary"])
    return manager.c(dark, light)


def border_color(level: str = "default") -> str:
    dark, light = BORDER.get(level, BORDER["default"])
    return manager.c(dark, light)


def surface_color(level: str = "raised") -> str:
    dark, light = SURFACE.get(level, SURFACE["raised"])
    return manager.c(dark, light)


def secondary_button_style(height: int | None = None) -> str:
    control_height = int(height or SIZING["control_height"])
    return (
        "QPushButton {"
        f"  background-color: {surface_color('muted')};"
        f"  color: {text_color('secondary')};"
        f"  border: 1px solid {border_color('default')}; border-radius: {RADIUS['md']}px;"
        f"  min-height: {control_height}px;"
        "  font-size: 13px; font-weight: 600; padding: 0 14px;"
        "}"
        "QPushButton:hover {"
        f"  background-color: {manager.c('#191d22', '#efe5d8')};"
        "  border-color: rgba(255,107,53,0.26);"
        f"  color: {text_color('primary')};"
        "}"
    )


def primary_button_style(height: int | None = None) -> str:
    control_height = int(height or SIZING["control_height"])
    return (
        "QPushButton {"
        "  background-color: #ff6b35; color: #fff7f1;"
        "  border: 1px solid rgba(255,107,53,0.42); border-radius: 10px;"
        f"  min-height: {control_height}px;"
        "  font-size: 13px; font-weight: 600; padding: 0 14px;"
        "}"
        "QPushButton:hover {"
        "  background-color: #ff7a48; border-color: rgba(255,107,53,0.62);"
        "}"
    )


def subtle_surface_style() -> str:
    return (
        f"background: {surface_color('muted')};"
        f"border: 1px solid {border_color('soft')};"
        f"border-radius: {RADIUS['md']}px;"
    )


def ai_button_style(height: int | None = None) -> str:
    control_height = int(height or SIZING["control_height"])
    return (
        "QPushButton {"
        f"  background-color: {surface_color('muted')}; color: {text_color('secondary')};"
        f"  border: 1px solid {border_color('default')}; border-radius: 10px;"
        f"  min-height: {control_height}px;"
        "  font-size: 13px; font-weight: 600; padding: 0 14px;"
        "}"
        "QPushButton:hover {"
        f"  background-color: {manager.c('#1b2026', '#efe5d8')};"
        "  border-color: rgba(255,107,53,0.26);"
        f"  color: {text_color('primary')};"
        "}"
    )
def empty_state_style() -> str:
    return (
        f"background: {surface_color('muted')};"
        f"border: 1px dashed {border_color('soft')};"
        f"border-radius: {RADIUS['panel']}px;"
    )


def input_style(*, height: int | None = None, radius: int | None = None) -> str:
    control_height = int(height or SIZING["control_height"])
    control_radius = int(radius or RADIUS["md"])
    return (
        "QLineEdit {"
        f" background-color: {surface_color('muted')};"
        f" color: {text_color('primary')};"
        f" border: 1px solid {border_color('default')};"
        f" border-radius: {control_radius}px;"
        f" min-height: {control_height}px;"
        " padding: 0 14px; font-size: 14px;"
        "}"
        "QLineEdit:focus {"
        " border-color: rgba(255,107,53,0.42);"
        f" background-color: {surface_color('raised')};"
        "}"
        "QLineEdit::placeholder {"
        f" color: {text_color('tertiary')};"
        "}"
    )


def chip_style(*, active: bool = False, role: str = "metadata", with_icon: bool = False) -> str:
    padding = "0 10px" if with_icon else "0 12px"
    base = (
        "QPushButton {"
        f" background: {surface_color('muted')};"
        f" color: {text_color('secondary')};"
        f" border: 1px solid {border_color('soft')};"
        f" border-radius: {RADIUS['pill']}px;"
        f" min-height: {SIZING['chip_height']}px;"
        f" padding: {padding}; font-size: 11px; font-weight: 600;"
        "}"
    )
    if active:
        accent = ACCENT["primary"]
        return (
            "QPushButton {"
            " background: rgba(255,107,53,0.12);"
            f" color: {accent};"
            " border: 1px solid rgba(255,107,53,0.26);"
            f" border-radius: {RADIUS['pill']}px;"
            f" min-height: {SIZING['chip_height']}px;"
            f" padding: {padding}; font-size: 11px; font-weight: 700;"
            "}"
        )
    if role == "status":
        return (
            "QPushButton {"
            f" background: {surface_color('raised')};"
            f" color: {text_color('primary')};"
            f" border: 1px solid {border_color('default')};"
            f" border-radius: {RADIUS['pill']}px;"
            f" min-height: {SIZING['chip_height']}px;"
            f" padding: {padding}; font-size: 11px; font-weight: 600;"
            "}"
            "QPushButton:hover {"
            f" background: {manager.c('#1a1f24', '#eee4d8')};"
            " border-color: rgba(255,107,53,0.2);"
            "}"
        )
    return (
        base +
        "QPushButton:hover {"
        f" background: {manager.c('#1a1f24', '#eee4d8')};"
        f" color: {text_color('primary')};"
        " border-color: rgba(255,107,53,0.18);"
        "}"
    )


def checkbox_style() -> str:
    return (
        "QCheckBox {"
        f" color: {text_color('primary')};"
        " font-size: 13px; font-weight: 600;"
        " spacing: 8px;"
        " background: transparent;"
        "}"
        "QCheckBox::indicator {"
        " image: none;"
        " width: 16px; height: 16px;"
        f" border: 1px solid {border_color('strong')};"
        " border-radius: 4px;"
        f" background: {surface_color('base')};"
        "}"
        "QCheckBox::indicator:checked {"
        " image: none;"
        " background: #ff6b35;"
        " border: 1px solid #ff6b35;"
        "}"
    )
