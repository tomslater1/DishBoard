from PySide6.QtCore import QObject, Signal

# (key, label, default_value, unit, colour)
MACRO_SPECS = [
    ("kcal",      "Calories",  2000.0, "kcal", "#ff6b35"),
    ("protein_g", "Protein",     50.0, "g",    "#4fc3f7"),
    ("carbs_g",   "Carbs",      260.0, "g",    "#aed581"),
    ("fat_g",     "Fat",         65.0, "g",    "#ffb74d"),
    ("fiber_g",   "Fiber",       30.0, "g",    "#f06292"),
    ("sugar_g",   "Sugar",       50.0, "g",    "#c084fc"),
]

# Short guide shown next to each input in Settings → Nutrition Goals
MACRO_GUIDES = {
    "kcal":      "Most adults need 1,600–2,500 kcal/day. 2,000 is a common starting point.",
    "protein_g": "Aim for 0.8–1.2g per kg of bodyweight. Go higher if building muscle.",
    "carbs_g":   "45–65% of your daily calories. Around 225–325g on a 2,000 kcal diet.",
    "fat_g":     "20–35% of your daily calories. Around 44–78g on a 2,000 kcal diet.",
    "fiber_g":   "Adults should aim for 25–35g per day for good digestive health.",
    "sugar_g":   "Keep added sugars under 50g per day. Under 25g is even better.",
}


class _GoalsBroadcaster(QObject):
    """Singleton broadcaster — emits goals_changed whenever any goal is saved."""
    goals_changed = Signal()


_broadcaster = _GoalsBroadcaster()


def get_broadcaster() -> _GoalsBroadcaster:
    return _broadcaster


def get_macro_goals(db) -> dict[str, float]:
    """Return current macro goals from DB settings, falling back to defaults."""
    goals: dict[str, float] = {}
    for key, _, default, *_ in MACRO_SPECS:
        try:
            val = db.get_setting(f"macro_goal_{key}", None)
            goals[key] = float(val) if val is not None else default
        except Exception:
            goals[key] = default
    return goals


def set_macro_goal(db, key: str, value: float) -> None:
    """Persist a single macro goal and broadcast the change to all listeners."""
    db.set_setting(f"macro_goal_{key}", str(value))
    _broadcaster.goals_changed.emit()
