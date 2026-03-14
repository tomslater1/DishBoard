"""
Smart ingredient input row with Dishy-powered nutrition lookup.
User types an ingredient name and presses Enter; Dishy returns macros per 100 g
which are then scaled by the chosen amount and unit.
"""

from __future__ import annotations
import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox,
)
from PySide6.QtCore import Qt, QSize, QTimer, Signal

from api.claude_ai import ClaudeAI
from utils.workers import run_async
from utils.theme import manager as theme_manager

_claude = ClaudeAI()

UNITS = ["g", "kg", "oz", "lb", "ml", "cup", "tbsp", "tsp", "piece"]
UNIT_TO_G = {
    "g": 1.0, "kg": 1000.0, "oz": 28.35, "lb": 453.6,
    "ml": 1.0, "cup": 240.0, "tbsp": 15.0, "tsp": 5.0, "piece": 100.0,
}


# ── Single ingredient row ──────────────────────────────────────────────────────

class IngredientRow(QWidget):
    changed = Signal()

    def __init__(self, on_remove, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._food_per100g: dict | None = None
        self._on_remove = on_remove
        self._lookup_timer: QTimer | None = None
        self._lookup_step: int = 0
        self._build_ui()

    # ─── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 6)
        self._outer.setSpacing(5)

        # ── Row 1: food search/chip + amount + unit + remove ──────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        # Food search input
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Type ingredient, press ↵ to look up macros…")
        self._search_input.setFixedHeight(44)
        self._search_input.setMinimumWidth(220)
        self._search_input.returnPressed.connect(self._do_lookup)

        # Selected food chip (shown after successful lookup)
        self._food_chip = QWidget()
        self._food_chip.setFixedHeight(44)
        self._food_chip.setMinimumWidth(220)
        self._food_chip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._food_chip.setStyleSheet(
            "background: rgba(52,211,153,0.1); border-radius: 9px;"
            " border: 1px solid rgba(52,211,153,0.25);"
        )
        chip_hl = QHBoxLayout(self._food_chip)
        chip_hl.setContentsMargins(12, 0, 8, 0)
        chip_hl.setSpacing(8)
        self._food_name_lbl = QLabel("")
        self._food_name_lbl.setStyleSheet(
            f"color: {theme_manager.c('#e0e0e0', '#1a1a1a')}; font-size: 14px;"
            " font-weight: 500; background: transparent; border: none;"
        )
        chip_clear = QPushButton("×")
        chip_clear.setFixedSize(26, 26)
        chip_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        chip_clear.setStyleSheet(
            "QPushButton { color: #666; font-size: 18px; background: transparent;"
            " border: none; border-radius: 13px; }"
            "QPushButton:hover { color: #34d399; background: rgba(52,211,153,0.15); }"
        )
        chip_clear.clicked.connect(self._clear_food)
        chip_hl.addWidget(self._food_name_lbl, 1)
        chip_hl.addWidget(chip_clear)
        self._food_chip.setVisible(False)

        # Amount input
        self._amount_input = QLineEdit("100")
        self._amount_input.setFixedWidth(76)
        self._amount_input.setFixedHeight(44)
        self._amount_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._amount_input.textChanged.connect(self._on_amount_changed)

        # Unit combo
        self._unit_combo = QComboBox()
        self._unit_combo.addItems(UNITS)
        self._unit_combo.setFixedWidth(82)
        self._unit_combo.setFixedHeight(44)
        self._unit_combo.currentTextChanged.connect(self._on_amount_changed)

        # Remove button
        self._rm_btn = QPushButton()
        self._rm_btn.setFixedSize(36, 36)
        self._rm_btn.setIcon(qta.icon("fa5s.times", color=theme_manager.c("#555555", "#888888")))
        self._rm_btn.setIconSize(QSize(12, 12))
        self._rm_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; border-radius: 18px; }"
            "QPushButton:hover { background: rgba(239,68,68,0.12); }"
        )
        self._rm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rm_btn.clicked.connect(self._on_remove)
        self._rm_btn.enterEvent = lambda _: self._rm_btn.setIcon(
            qta.icon("fa5s.times", color="#ef4444"))
        self._rm_btn.leaveEvent = lambda _: self._rm_btn.setIcon(
            qta.icon("fa5s.times", color=theme_manager.c("#555555", "#888888")))

        row1.addWidget(self._search_input)
        row1.addWidget(self._food_chip)
        row1.addWidget(self._amount_input)
        row1.addWidget(self._unit_combo)
        row1.addWidget(self._rm_btn)
        self._outer.addLayout(row1)

        # ── Row 2: macro pills (hidden until lookup) ──────────────────────────
        self._pills_widget = QWidget()
        self._pills_widget.setStyleSheet("background: transparent;")
        pw = QHBoxLayout(self._pills_widget)
        pw.setContentsMargins(2, 0, 0, 0)
        pw.setSpacing(6)

        self._loading_lbl = QLabel("Looking up macros ·")
        self._loading_lbl.setStyleSheet(
            "color: #34d399; font-size: 12px; font-style: italic; background: transparent;"
        )
        self._loading_lbl.setVisible(False)
        pw.addWidget(self._loading_lbl)

        self._macro_pills: dict[str, tuple[QWidget, QLabel]] = {}
        for key, icon_name, colour, bg, unit_str in [
            ("kcal",    "fa5s.fire",        "#ff6b35", "rgba(255,107,53,0.12)",  "kcal"),
            ("protein", "fa5s.dumbbell",    "#34d399", "rgba(52,211,153,0.12)",  "g prot"),
            ("fat",     "fa5s.tint",        "#f0a500", "rgba(240,165,0,0.12)",   "g fat"),
            ("carbs",   "fa5s.bread-slice", "#a78bfa", "rgba(124,106,247,0.12)", "g carbs"),
        ]:
            pill = QWidget()
            pill.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            pill.setStyleSheet(f"background: {bg}; border-radius: 6px;")
            pl = QHBoxLayout(pill)
            pl.setContentsMargins(8, 3, 8, 3)
            pl.setSpacing(4)
            ic = QLabel()
            ic.setPixmap(qta.icon(icon_name, color=colour).pixmap(QSize(10, 10)))
            ic.setStyleSheet("background: transparent;")
            val_lbl = QLabel("—")
            val_lbl.setStyleSheet(
                f"color: {colour}; font-size: 12px; font-weight: 700; background: transparent;"
            )
            unit_lbl = QLabel(unit_str)
            unit_lbl.setStyleSheet(
                f"color: {theme_manager.c('#606060', '#999999')}; font-size: 11px; background: transparent;"
            )
            pl.addWidget(ic)
            pl.addWidget(val_lbl)
            pl.addWidget(unit_lbl)
            pill.setVisible(False)
            self._macro_pills[key] = (pill, val_lbl)
            pw.addWidget(pill)

        pw.addStretch()
        self._pills_widget.setVisible(False)
        self._outer.addWidget(self._pills_widget)

    # ─── Dishy animation ───────────────────────────────────────────────────────

    def _start_lookup_animation(self):
        self._lookup_step = 0
        for pill, _ in self._macro_pills.values():
            pill.setVisible(False)
        self._loading_lbl.setText("Looking up macros ·")
        self._loading_lbl.setStyleSheet(
            "color: #34d399; font-size: 12px; font-style: italic; background: transparent;"
        )
        self._loading_lbl.setVisible(True)
        self._pills_widget.setVisible(True)
        if self._lookup_timer is None:
            self._lookup_timer = QTimer(self)
            self._lookup_timer.timeout.connect(self._tick_lookup)
        self._lookup_timer.start(380)

    def _tick_lookup(self):
        self._lookup_step = (self._lookup_step + 1) % 3
        dots = ("·", "· ·", "· · ·")[self._lookup_step]
        self._loading_lbl.setText(f"Looking up macros  {dots}")

    def _stop_lookup_animation(self):
        if self._lookup_timer is not None:
            self._lookup_timer.stop()

    # ─── Dishy lookup ──────────────────────────────────────────────────────────

    def _do_lookup(self):
        query = self._search_input.text().strip()
        if not query:
            return
        self._start_lookup_animation()
        run_async(
            _claude.lookup_nutrition, f"100g {query}",
            on_result=self._on_lookup_result,
            on_error=self._on_lookup_error,
        )

    def _on_lookup_result(self, data: dict):
        self._stop_lookup_animation()
        self._food_per100g = {
            "name":    data.get("food_name", self._search_input.text().strip()),
            "kcal":    float(data.get("kcal",      0)),
            "protein": float(data.get("protein_g", 0)),
            "fat":     float(data.get("fat_g",     0)),
            "carbs":   float(data.get("carbs_g",   0)),
            "fiber":   float(data.get("fiber_g",   0)),
            "sugar":   float(data.get("sugar_g",   0)),
        }
        name  = self._food_per100g["name"]
        short = name[:34] + ("…" if len(name) > 34 else "")
        self._food_name_lbl.setText(short)
        self._food_chip.setVisible(True)
        self._search_input.setVisible(False)
        self._loading_lbl.setVisible(False)
        self._update_macros()

    def _on_lookup_error(self, err: str):
        self._stop_lookup_animation()
        err_lower = err.lower()
        if "credit balance" in err_lower or "too low" in err_lower:
            msg = "Credits out — check billing"
        elif "authentication" in err_lower or "401" in err_lower:
            msg = "Invalid API key — check Settings"
        else:
            msg = "Lookup failed — try again"
        self._loading_lbl.setText(f"⚠  {msg}")
        self._loading_lbl.setStyleSheet(
            "color: #ef4444; font-size: 12px; background: transparent;"
        )
        self._pills_widget.setVisible(True)

    def _clear_food(self):
        self._food_per100g = None
        self._food_chip.setVisible(False)
        self._search_input.setVisible(True)
        self._search_input.clear()
        self._search_input.setFocus()
        self._pills_widget.setVisible(False)
        self.changed.emit()

    def _on_amount_changed(self):
        if self._food_per100g:
            self._update_macros()

    def _update_macros(self):
        if not self._food_per100g:
            self._pills_widget.setVisible(False)
            return
        amount_g = self._amount_in_grams()
        factor   = amount_g / 100.0
        data = {
            "kcal":    self._food_per100g["kcal"]    * factor,
            "protein": self._food_per100g["protein"] * factor,
            "fat":     self._food_per100g["fat"]     * factor,
            "carbs":   self._food_per100g["carbs"]   * factor,
        }
        for key, (pill, val_lbl) in self._macro_pills.items():
            v = data[key]
            val_lbl.setText(str(round(v)) if key == "kcal" else str(round(v, 1)))
            pill.setVisible(True)
        self._loading_lbl.setVisible(False)
        self._pills_widget.setVisible(True)
        self.changed.emit()

    def _amount_in_grams(self) -> float:
        try:
            amount = float(self._amount_input.text() or "100")
        except ValueError:
            amount = 100.0
        unit = self._unit_combo.currentText()
        return amount * UNIT_TO_G.get(unit, 1.0)

    # ─── public API ───────────────────────────────────────────────────────────

    def get_text(self) -> str:
        if self._food_per100g:
            amount = self._amount_input.text() or "100"
            unit   = self._unit_combo.currentText()
            return f"{amount}{unit} {self._food_per100g['name']}"
        return self._search_input.text().strip()

    def get_nutrition(self) -> dict | None:
        if not self._food_per100g:
            return None
        amount_g = self._amount_in_grams()
        factor   = amount_g / 100.0
        return {
            "name":     self._food_per100g["name"],
            "amount":   float(self._amount_input.text() or "100"),
            "unit":     self._unit_combo.currentText(),
            "amount_g": round(amount_g, 1),
            "kcal":     round(self._food_per100g["kcal"]    * factor, 1),
            "protein":  round(self._food_per100g["protein"] * factor, 1),
            "fat":      round(self._food_per100g["fat"]     * factor, 1),
            "carbs":    round(self._food_per100g["carbs"]   * factor, 1),
        }

    def apply_theme(self, _mode=None):
        col = theme_manager.c("#555555", "#888888")
        self._rm_btn.setIcon(qta.icon("fa5s.times", color=col))
        name_col = theme_manager.c("#e0e0e0", "#1a1a1a")
        self._food_name_lbl.setStyleSheet(
            f"color: {name_col}; font-size: 14px;"
            " font-weight: 500; background: transparent; border: none;"
        )


# ── Nutrition ingredient list ──────────────────────────────────────────────────

class NutritionIngredientList(QWidget):
    """
    Drop-in replacement for _DynamicList for the INGREDIENTS section.
    """

    def __init__(self, servings_getter=None, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._servings_getter = servings_getter or (lambda: "1")
        self._rows: list[IngredientRow] = []

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)

        # Rows container
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(4)
        self._outer.addLayout(self._rows_layout)

        # Add button
        self._add_btn = QPushButton("  + Add ingredient")
        self._add_btn.setObjectName("ghost-btn")
        self._add_btn.setFixedHeight(42)
        self._add_btn.clicked.connect(self._add_row)
        self._outer.addWidget(self._add_btn)

        # Nutrition total card
        self._total_card = self._build_total_card()
        self._total_card.setVisible(False)
        self._outer.addWidget(self._total_card)

        # Start with one empty row
        self._add_row()

    def _build_total_card(self) -> QWidget:
        card = QWidget()
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(
            f"background: {theme_manager.c('#0d0d0d', '#f8f8f8')};"
            f" border-radius: 10px; border: 1px solid {theme_manager.c('#1e1e1e', '#e0e0e0')};"
        )
        vl = QVBoxLayout(card)
        vl.setContentsMargins(18, 14, 18, 16)
        vl.setSpacing(12)

        # Header
        header_row = QHBoxLayout()
        hdr_icon = QLabel()
        hdr_icon.setPixmap(qta.icon("fa5s.chart-bar", color="#34d399").pixmap(QSize(13, 13)))
        hdr_icon.setStyleSheet("background: transparent; border: none;")
        self._total_label = QLabel("NUTRITION TOTALS  ·  per serving")
        self._total_label.setStyleSheet(
            f"background: transparent; border: none; color: {theme_manager.c('#888888', '#777777')};"
            " font-size: 11px; font-weight: 700; letter-spacing: 1.5px;"
        )
        header_row.addWidget(hdr_icon)
        header_row.addSpacing(6)
        header_row.addWidget(self._total_label)
        header_row.addStretch()
        vl.addLayout(header_row)

        # Macro pills row
        self._macro_row = QHBoxLayout()
        self._macro_row.setSpacing(10)
        self._macro_pills: dict[str, QLabel] = {}
        for key, icon_name, colour, unit_str in [
            ("kcal",    "fa5s.fire",        "#ff6b35", "kcal"),
            ("protein", "fa5s.dumbbell",    "#34d399", "g protein"),
            ("fat",     "fa5s.tint",        "#f0a500", "g fat"),
            ("carbs",   "fa5s.bread-slice", "#a78bfa", "g carbs"),
        ]:
            pill = QWidget()
            pill.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            pill.setStyleSheet(
                f"background: {theme_manager.c('rgba(255,255,255,0.03)', 'rgba(0,0,0,0.03)')};"
                f" border-radius: 10px; border: 1px solid {theme_manager.c('#1e1e1e', '#e0e0e0')};"
            )
            pl = QVBoxLayout(pill)
            pl.setContentsMargins(14, 10, 14, 10)
            pl.setSpacing(3)
            ic_row = QHBoxLayout()
            ic_row.setSpacing(5)
            ic = QLabel()
            ic.setPixmap(qta.icon(icon_name, color=colour).pixmap(QSize(12, 12)))
            ic.setStyleSheet("background: transparent; border: none;")
            val_lbl = QLabel("—")
            val_lbl.setStyleSheet(
                f"color: {colour}; font-size: 18px; font-weight: 700;"
                " background: transparent; border: none;"
            )
            ic_row.addWidget(ic)
            ic_row.addStretch()
            pl.addLayout(ic_row)
            pl.addWidget(val_lbl)
            unit_lbl = QLabel(unit_str)
            unit_lbl.setStyleSheet(
                f"color: {theme_manager.c('#555555', '#888888')}; font-size: 11px;"
                " background: transparent; border: none;"
            )
            pl.addWidget(unit_lbl)
            self._macro_pills[key] = val_lbl
            self._macro_row.addWidget(pill)
        self._macro_row.addStretch()
        vl.addLayout(self._macro_row)

        return card

    def _add_row(self, text: str = ""):
        def _remove():
            if len(self._rows) <= 1:
                return
            row.setVisible(False)
            self._rows.remove(row)
            self._rows_layout.removeWidget(row)
            row.deleteLater()
            self._update_totals()

        row = IngredientRow(on_remove=_remove)
        row.changed.connect(self._update_totals)
        if text:
            row._search_input.setText(text)
        self._rows.append(row)
        self._rows_layout.addWidget(row)

    def _update_totals(self):
        totals = {"kcal": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}
        has_any = False
        for row in self._rows:
            n = row.get_nutrition()
            if n:
                has_any = True
                for k in totals:
                    totals[k] += n[k]

        if not has_any:
            self._total_card.setVisible(False)
            return

        try:
            servings = max(1, int(self._servings_getter() or "1"))
        except (ValueError, TypeError):
            servings = 1

        per = {k: v / servings for k, v in totals.items()}
        self._total_label.setText(
            f"NUTRITION TOTALS  ·  per serving  (÷ {servings})" if servings > 1
            else "NUTRITION TOTALS  ·  whole recipe"
        )
        self._macro_pills["kcal"].setText(str(round(per["kcal"])))
        self._macro_pills["protein"].setText(str(round(per["protein"], 1)))
        self._macro_pills["fat"].setText(str(round(per["fat"], 1)))
        self._macro_pills["carbs"].setText(str(round(per["carbs"], 1)))
        self._total_card.setVisible(True)

    # ─── public API ────────────────────────────────────────────────────────────

    def values(self) -> list[str]:
        return [r.get_text() for r in self._rows if r.get_text()]

    def set_values(self, items: list[str]):
        while len(self._rows) > 1:
            row = self._rows.pop()
            self._rows_layout.removeWidget(row)
            row.deleteLater()
        if self._rows:
            self._rows[0]._search_input.clear()
        for i, text in enumerate(items):
            if i == 0 and self._rows:
                self._rows[0]._search_input.setText(text)
            else:
                self._add_row(text=text)
        if not items and not self._rows:
            self._add_row()

    def apply_theme(self, mode: str = "dark"):
        for row in self._rows:
            row.apply_theme(mode)
        # Rebuild total card with current theme colors
        old = self._total_card
        was_visible = old.isVisible()
        self._total_card = self._build_total_card()
        self._total_card.setVisible(was_visible)
        self._outer.replaceWidget(old, self._total_card)
        old.deleteLater()

    def nutrition_data(self) -> dict:
        items = [r.get_nutrition() for r in self._rows]
        items = [i for i in items if i]
        total = {"kcal": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}
        for i in items:
            for k in total:
                total[k] += i[k]
        try:
            servings = max(1, int(self._servings_getter() or "1"))
        except (ValueError, TypeError):
            servings = 1
        per_serving = {k: round(v / servings, 1) for k, v in total.items()}
        total = {k: round(v, 1) for k, v in total.items()}
        return {"ingredients": items, "total": total, "per_serving": per_serving,
                "servings": servings}
