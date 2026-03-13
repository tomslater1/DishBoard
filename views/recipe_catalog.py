"""Recipe editor/library palettes and enums."""

from __future__ import annotations

RECIPE_ICONS: list[tuple[str, str]] = [
    ("fa5s.utensils",       "General"),
    ("fa5s.pizza-slice",    "Pizza"),
    ("fa5s.fish",           "Seafood"),
    ("fa5s.drumstick-bite", "Chicken"),
    ("fa5s.hamburger",      "Burger"),
    ("fa5s.leaf",           "Veg"),
    ("fa5s.seedling",       "Plant"),
    ("fa5s.carrot",         "Veg"),
    ("fa5s.apple-alt",      "Healthy"),
    ("fa5s.bacon",          "Breakfast"),
    ("fa5s.egg",            "Eggs"),
    ("fa5s.coffee",         "Coffee"),
    ("fa5s.birthday-cake",  "Baking"),
    ("fa5s.cookie",         "Snacks"),
    ("fa5s.fire",           "BBQ"),
    ("fa5s.pepper-hot",     "Spicy"),
    ("fa5s.mortar-pestle",  "Spices"),
    ("fa5s.bread-slice",    "Bread"),
    ("fa5s.ice-cream",      "Dessert"),
    ("fa5s.blender",        "Smoothie"),
    ("fa5s.lemon",          "Citrus"),
    ("fa5s.cheese",         "Dairy"),
    ("fa5s.hotdog",         "Fast Food"),
    ("fa5s.mug-hot",        "Hot Drink"),
    ("fa5s.snowflake",      "Cold"),
    ("fa5s.wine-glass-alt", "Drinks"),
    ("fa5s.star",           "Special"),
    ("fa5s.heart",          "Favourite"),
    ("fa5s.sun",            "Lunch"),
    ("fa5s.moon",           "Dinner"),
]

RECIPE_COLOURS: list[tuple[str, str]] = [
    ("#ff6b35", "Orange"),
    ("#ef4444", "Red"),
    ("#f59e0b", "Amber"),
    ("#fbbf24", "Yellow"),
    ("#34d399", "Green"),
    ("#10b981", "Emerald"),
    ("#4fc3f7", "Sky"),
    ("#60a5fa", "Blue"),
    ("#a78bfa", "Purple"),
    ("#f472b6", "Pink"),
    ("#fb7185", "Rose"),
    ("#94a3b8", "Slate"),
]

RECIPE_TAGS: list[str] = [
    "Vegetarian", "Vegan", "Gluten-Free", "Dairy-Free",
    "High-Protein", "Low-Carb", "Keto", "Paleo",
    "Quick (< 30 min)", "One-Pot", "Meal-Prep", "Batch Cook",
    "Spicy", "Healthy", "Comfort Food", "Budget-Friendly",
    "Date Night", "Kid-Friendly", "BBQ", "Breakfast",
    "Lunch", "Dinner", "Snack", "Dessert", "Baking",
]

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MEAL_TYPES = ["breakfast", "lunch", "dinner"]

