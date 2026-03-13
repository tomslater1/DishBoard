"""
Dishy tool definitions (Anthropic tool-use schema).

TOOLS — list of Anthropic tool schemas used by Dishy tool-calling chat.
Separated from the executor to keep api/dishy_tools.py focused on runtime logic.
"""

from __future__ import annotations

TOOLS: list[dict] = [
    {
        "name": "save_recipe",
        "description": (
            "Save a fully-formed recipe to the user's DishBoard recipe library. "
            "Use whenever the user asks you to create, invent, generate, or save a recipe — "
            "including when you need to save a recipe before setting a meal slot. "
            "Always provide: a real title, accurate ingredient quantities (e.g. '200 g chicken breast'), "
            "numbered step-by-step instructions (one action per step), and exactly one meal-type tag "
            "from this exact list (title-case): 'Breakfast', 'Lunch', 'Dinner', 'Snack', 'Dessert'. "
            "Add descriptive tags too (e.g. 'Vegetarian', 'High-Protein', 'Quick (< 30 min)', 'Spicy'). "
            "After saving, offer to add it to the meal plan or generate a shopping list for it. "
            "CRITICAL: You MUST calculate and include accurate nutrition_per_serving (kcal, protein_g, "
            "carbs_g, fat_g, fiber_g, sugar_g). Never omit nutrition. Never leave all macros as zero."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Recipe title",
                },
                "summary": {
                    "type": "string",
                    "description": "One-sentence description of the dish",
                },
                "servings": {
                    "type": "integer",
                    "description": "Number of servings",
                },
                "ready_mins": {
                    "type": "integer",
                    "description": "Total time in minutes (prep + cook)",
                },
                "ingredients": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Ingredient lines with quantities, "
                        "e.g. ['200 g chicken breast', '2 cloves garlic, minced']"
                    ),
                },
                "instructions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered step-by-step instructions (one step per item)",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Category tags for this recipe. MUST include exactly one meal-type tag "
                        "from this exact list (title-case): 'Breakfast', 'Lunch', 'Dinner', "
                        "'Snack', 'Dessert'. Then add any relevant descriptive tags such as "
                        "'Vegetarian', 'High-Protein', 'Quick (< 30 min)', 'Spicy', etc. "
                        "Example: ['Dinner', 'High-Protein', 'Spicy']"
                    ),
                },
                "nutrition_per_serving": {
                    "type": "object",
                    "description": (
                        "Nutritional values per serving. REQUIRED — calculate from ingredients. "
                        "Providing this avoids a slow re-analysis step after saving. "
                        "All values are numbers (floats). "
                        "Example: {\"kcal\": 520, \"protein_g\": 38, \"carbs_g\": 45, "
                        "\"fat_g\": 18, \"fiber_g\": 6, \"sugar_g\": 8}"
                    ),
                    "properties": {
                        "kcal":      {"type": "number"},
                        "protein_g": {"type": "number"},
                        "carbs_g":   {"type": "number"},
                        "fat_g":     {"type": "number"},
                        "fiber_g":   {"type": "number"},
                        "sugar_g":   {"type": "number"},
                    },
                },
            },
            "required": ["title", "ingredients", "instructions", "tags"],
        },
    },
    {
        "name": "set_meal_slot",
        "description": (
            "Assign a meal to a specific day and meal type in the current week's meal planner. "
            "Use for single-slot requests such as 'add pasta to Tuesday dinner' or "
            "'put avocado toast on Wednesday breakfast'. "
            "If a saved recipe name matches, it will be linked automatically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "day": {
                    "type": "string",
                    "enum": [
                        "Monday", "Tuesday", "Wednesday",
                        "Thursday", "Friday", "Saturday", "Sunday",
                    ],
                },
                "meal_type": {
                    "type": "string",
                    "enum": ["breakfast", "lunch", "dinner", "snack"],
                },
                "meal_name": {
                    "type": "string",
                    "description": "Name of the meal or recipe to place in this slot",
                },
            },
            "required": ["day", "meal_type", "meal_name"],
        },
    },
    {
        "name": "fill_week_meal_plan",
        "description": (
            "Fill an entire week's meal plan — Monday through Sunday, "
            "breakfast, lunch, dinner, and optionally snack for each day. "
            "Use when the user asks to plan the whole week, auto-fill the planner, "
            "fill everything, or schedule meals for the week. "
            "YOU must decide the plan and pass it via the 'plan' parameter — do not leave it empty. "
            "Use only recipes that exist in the live context recipe library. "
            "Prioritise the user's favourite recipes. Aim for variety — avoid repeating the same "
            "recipe more than twice. Balance macros across the week where possible. "
            "Today's meals are automatically logged to nutrition after filling — mention this in your reply."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "plan": {
                    "type": "object",
                    "description": (
                        "The full 7-day meal plan you have decided on. "
                        "Keys are day names (Monday–Sunday), values are objects with keys "
                        "'breakfast', 'lunch', 'dinner', and optionally 'snack' mapping to recipe title strings. "
                        "Only use recipe titles that exist in the user's saved recipe library. "
                        "Example: {\"Monday\": {\"breakfast\": \"Overnight Oats\", "
                        "\"lunch\": \"Caesar Salad\", \"dinner\": \"Pasta Bolognese\", "
                        "\"snack\": \"Protein Balls\"}, ...}"
                    ),
                },
                "preferences": {
                    "type": "string",
                    "description": (
                        "Dietary restrictions or preferences applied when choosing meals, "
                        "e.g. 'vegetarian', 'high-protein', 'no dairy'."
                    ),
                },
            },
            "required": ["plan"],
        },
    },
    {
        "name": "add_shopping_items",
        "description": (
            "Add one or more grocery items to the user's shopping list. "
            "Use when the user asks to add specific ingredients or products to their list: "
            "'add milk', 'I need eggs and butter', 'add the ingredients for pasta bolognese'. "
            "Always include quantity and unit when the user specifies them. "
            "After adding, offer to build the full week's shopping list if relevant.\n\n"
            "SHOPPING LIST RULES — think like a shopper, not a recipe parser:\n"
            "1. CONSOLIDATE: if multiple recipes need the same ingredient (e.g. chicken breast "
            "appears in 3 recipes), add it ONCE with a combined or estimated total quantity.\n"
            "2. PRACTICAL UNITS: use real shopping units — '1 pack chicken breast', "
            "'1 dozen eggs', '1 bag spinach', '1 tin chopped tomatoes'. "
            "Never add '183g chicken breast' — no one buys that. Round to the nearest "
            "practical shop unit (pack, bag, bunch, tin, bottle, jar, dozen, etc.).\n"
            "3. SKIP PANTRY STAPLES: do NOT add salt, black pepper, olive oil, water, "
            "sugar, plain flour, butter (unless a large amount), or other basics that "
            "virtually every kitchen already has — unless the user explicitly requests them.\n"
            "4. SKIP DUPLICATES: never add an item already on the shopping list.\n"
            "5. KEEP IT MANAGEABLE: a good shopping list has 10–20 items, not 50. "
            "Combine similar items, trim the obvious, focus on what needs buying.\n"
            "NOTE: A Pantry/Storage feature is coming soon — it will let you see exactly "
            "what the user already has and automatically skip those items. Until then, "
            "use common sense to avoid adding things most kitchens stock."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name":     {"type": "string", "description": "Item name (practical shopping name, not recipe verbatim)"},
                            "quantity": {"type": "string", "description": "Amount in practical units, e.g. '2', '1'"},
                            "unit":     {"type": "string", "description": "Shopping unit, e.g. 'pack', 'bag', 'tin', 'bunch', 'bottle'"},
                        },
                        "required": ["name"],
                    },
                    "description": "Grocery items to add — consolidated, practical, no pantry staples",
                },
            },
            "required": ["items"],
        },
    },
    # ── Destructive / delete tools ────────────────────────────────────────────
    {
        "name": "delete_meal_slot",
        "description": (
            "Remove a single meal from a specific day and meal type in the current week's plan. "
            "Use when the user asks to clear, remove, or delete a specific meal (e.g. 'remove Tuesday dinner'). "
            "⚠️ CONFIRMATION REQUIRED: Before calling this tool you MUST ask the user to confirm "
            "which slot they want to remove and receive a clear 'yes' or 'confirm'. "
            "If their most recent message already clearly confirms the deletion, proceed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "day": {
                    "type": "string",
                    "enum": [
                        "Monday", "Tuesday", "Wednesday",
                        "Thursday", "Friday", "Saturday", "Sunday",
                    ],
                },
                "meal_type": {
                    "type": "string",
                    "enum": ["breakfast", "lunch", "dinner", "snack"],
                },
            },
            "required": ["day", "meal_type"],
        },
    },
    {
        "name": "swap_meal_slots",
        "description": (
            "Swap two meal slots in the meal planner — moves the meals from each slot into the other. "
            "Use when the user asks to swap, move, or rearrange meals between days or meal types — "
            "e.g. 'swap Monday dinner and Wednesday dinner', 'move Tuesday lunch to Thursday'. "
            "Works within the current week. Both slots are updated atomically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "day1": {
                    "type": "string",
                    "enum": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                    "description": "First day",
                },
                "meal_type1": {
                    "type": "string",
                    "enum": ["breakfast", "lunch", "dinner", "snack"],
                    "description": "Meal type for the first slot",
                },
                "day2": {
                    "type": "string",
                    "enum": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                    "description": "Second day",
                },
                "meal_type2": {
                    "type": "string",
                    "enum": ["breakfast", "lunch", "dinner", "snack"],
                    "description": "Meal type for the second slot",
                },
            },
            "required": ["day1", "meal_type1", "day2", "meal_type2"],
        },
    },
    {
        "name": "clear_meal_day",
        "description": (
            "Clear all meal slots (breakfast, lunch, and dinner) for a specific day. "
            "Use when the user asks to wipe, clear, or remove all meals for a particular day — "
            "e.g. 'clear Monday', 'wipe everything on Friday', 'remove all of Tuesday's meals'. "
            "This removes all three meal types for that day in one action. "
            "⚠️ CONFIRMATION REQUIRED: Before calling, confirm which day will be cleared "
            "and receive a clear 'yes' or 'confirm' from the user."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "day": {
                    "type": "string",
                    "enum": [
                        "Monday", "Tuesday", "Wednesday",
                        "Thursday", "Friday", "Saturday", "Sunday",
                    ],
                    "description": "The day whose meals should all be cleared",
                },
            },
            "required": ["day"],
        },
    },
    {
        "name": "clear_meal_plan",
        "description": (
            "Clear meal plan entries — either just this week, or the entire meal plan history. "
            "⚠️ DESTRUCTIVE — CANNOT BE UNDONE. "
            "Use all_weeks=true only if the user explicitly asks to wipe everything / all weeks. "
            "NEVER call this tool without first explicitly telling the user exactly what will be deleted "
            "and receiving a clear 'yes', 'confirm', or equivalent confirmation. "
            "If you are unsure they have confirmed, ask again."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "all_weeks": {
                    "type": "boolean",
                    "description": (
                        "If true, clears ALL meal plan data across every week (full wipe). "
                        "If false or omitted, only the current week is cleared (default)."
                    ),
                },
            },
        },
    },
    {
        "name": "delete_shopping_item",
        "description": (
            "Remove a specific item from the shopping list by name. "
            "⚠️ CONFIRMATION REQUIRED: Before calling this tool you MUST confirm with the user "
            "which item to remove and receive a clear 'yes' or 'confirm'. "
            "If their most recent message already clearly confirms the deletion, proceed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_name": {
                    "type": "string",
                    "description": "The name of the shopping item to remove (case-insensitive match)",
                },
            },
            "required": ["item_name"],
        },
    },
    {
        "name": "clear_shopping_list",
        "description": (
            "Clear the entire shopping list — removes ALL items. "
            "⚠️ DESTRUCTIVE — CANNOT BE UNDONE. "
            "NEVER call this tool without first explicitly telling the user exactly what will be deleted "
            "and receiving a clear 'yes', 'confirm', or equivalent confirmation. "
            "If you are unsure they have confirmed, ask again."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "delete_recipe",
        "description": (
            "Permanently delete a single saved recipe from the recipe library by its title. "
            "⚠️ CONFIRMATION REQUIRED: Before calling this tool you MUST confirm with the user "
            "which recipe to delete and receive a clear 'yes' or 'confirm'. "
            "If their most recent message already clearly confirms the deletion, proceed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "The exact title of the recipe to delete",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "clear_recipe_library",
        "description": (
            "Delete ALL saved recipes from the recipe library — every single recipe is permanently removed. "
            "⚠️ EXTREMELY DESTRUCTIVE — CANNOT BE UNDONE. "
            "NEVER call this tool without first explicitly warning the user that ALL their recipes will be "
            "permanently deleted and receiving a clear, unambiguous 'yes' or 'confirm'. "
            "If there is any doubt, ask the user to type 'confirm' before proceeding."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "log_recipe_nutrition",
        "description": (
            "Log a saved recipe's nutritional values to today's food log in the Nutrition tracker. "
            "Use when the user says they ate, cooked, or want to track a specific recipe — "
            "e.g. 'I just had the chicken pasta', 'log my dinner', 'track what I ate'. "
            "Looks up the recipe's stored nutrition data and adds it to today's log automatically. "
            "Always confirm with the exact kcal and macro breakdown after logging."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "recipe_title": {
                    "type": "string",
                    "description": "The title of the saved recipe to log (exact or close match)",
                },
                "servings_eaten": {
                    "type": "number",
                    "description": "How many servings the user ate (default: 1)",
                },
            },
            "required": ["recipe_title"],
        },
    },
    {
        "name": "sync_meal_plan_nutrition",
        "description": (
            "Sync a day's planned meals from the Meal Planner into the Nutrition log. "
            "Reads each recipe linked to a meal slot for the specified day, takes its stored "
            "per-serving nutrition data, and adds it to the day's food log. "
            "Skips meals already logged for that date (unless overwrite=true). "
            "Use when: the user asks to log their planned meals, track their day, sync their plan, "
            "or asks how they're doing nutritionally and unlogged meals exist. "
            "Also use proactively after filling the week's meal plan if the user asks about today's nutrition. "
            "Meals without stored nutrition data are reported back so the user knows."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "day": {
                    "type": "string",
                    "description": (
                        "Day to sync — a day name ('Monday', 'Tuesday', etc.) or 'today'. "
                        "Defaults to today if omitted."
                    ),
                },
                "overwrite": {
                    "type": "boolean",
                    "description": (
                        "If true, re-log meals even if they are already in today's log "
                        "(useful if the user says they want a fresh sync). Default: false."
                    ),
                },
            },
        },
    },
    {
        "name": "shopping_list_from_meal_plan",
        "description": (
            "Extract ingredients from this week's saved meal plan and add them to the shopping list. "
            "Use when the user asks to generate, populate, or build their shopping list from the meal planner. "
            "The tool automatically consolidates duplicate ingredients across recipes and skips common "
            "pantry staples (salt, pepper, oil, water, flour, sugar, butter). "
            "Items are added with practical shopping names, not raw recipe strings. "
            "Check My Kitchen in the live context first — skip items already in stock."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    # ── My Kitchen (pantry/fridge/freezer) tools ──────────────────────────────
    {
        "name": "add_pantry_item",
        "description": (
            "Add an ingredient to the user's pantry, fridge, or freezer in My Kitchen. "
            "Use when the user says they have an ingredient at home or just bought something. "
            "Also use when the user asks you to 'remember' that they have something stocked."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The ingredient or item name",
                },
                "quantity": {
                    "type": "string",
                    "description": "Amount as a number string, e.g. '500', '2'",
                },
                "unit": {
                    "type": "string",
                    "description": "Unit of measurement, e.g. 'g', 'kg', 'pack', 'bottle'",
                },
                "storage": {
                    "type": "string",
                    "enum": ["Pantry", "Fridge", "Freezer"],
                    "description": "Where the item is stored. Default: Pantry",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "remove_pantry_item",
        "description": (
            "Remove an item from My Kitchen (pantry, fridge, or freezer). "
            "Requires user confirmation — state the item name before calling. "
            "If the user has clearly named the item to remove, proceed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The name of the item to remove (fuzzy match)",
                },
                "storage": {
                    "type": "string",
                    "description": "Storage section to search in (optional — searches all if omitted)",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "clear_pantry_section",
        "description": (
            "Clear all items from one storage section or from all of My Kitchen. "
            "⚠️ DESTRUCTIVE — CANNOT BE UNDONE. "
            "NEVER call without first telling the user exactly what will be deleted "
            "and receiving a clear 'yes' or 'confirm'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "storage": {
                    "type": "string",
                    "enum": ["Pantry", "Fridge", "Freezer", "all"],
                    "description": "Which section to clear. Use 'all' to wipe everything.",
                },
            },
            "required": ["storage"],
        },
    },
]

