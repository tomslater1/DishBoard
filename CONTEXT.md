# DishBoard — Project Context

> This file exists so that Claude Code can read it at the start of each session to understand the full
> picture of what DishBoard is, how it's built, and where it's going.
> **Update this file whenever a significant feature, structural change, or design decision is made.**

---

## What is DishBoard?

A personal recipe manager and meal planner desktop app for macOS, built with Python + PySide6.
Tom Slater is the sole developer. It is currently a dev-only Python app run via `python3 DishBoard.py`.

**Future plans:**
- Package as a proper macOS `.app` via PyInstaller and share with friends
- Eventually a companion iOS app (React Native consuming a thin local or cloud API layer)
- Update distribution via GitHub Releases + in-app version checker

---

## Tech Stack

| Layer | Choice |
|---|---|
| GUI | PySide6 (Qt for Python) |
| Styling | qt_material dark_amber base + custom `theme.qss` + `theme_light.qss` |
| Database | SQLite via sqlite3 (`dishboard.db` in project root) |
| AI | Anthropic Claude (claude-haiku-4-5-20251001 for chat, claude-sonnet-4-6 for tool-use) |
| Web search | Google Custom Search API |
| Async | QThreadPool + custom `Worker`/`run_async` in `utils/workers.py` |
| Icons | qtawesome (Font Awesome 5) |
| Env / keys | python-dotenv — `.env` file in project root |

**Removed APIs (no longer in codebase):** Spoonacular, Nutritionix, USDA FoodData Central, Tesco

---

## Project Structure

```
DishBoard/
├── DishBoard.py                 # Entry point — loads .env, initialises DB, launches QApplication
├── main_window.py               # QMainWindow: sidebar nav + QStackedWidget content area
├── CONTEXT.md                   # ← this file
│
├── views/
│   ├── my_kitchen.py            # My Kitchen (home): stat cards, quick actions, recent recipes, Dishy tip
│   ├── recipes.py               # Recipe browser + create/edit form + detail view (QStackedWidget)
│   ├── meal_planner.py          # Weekly meal planner grid (Mon–Sun × Breakfast/Lunch/Dinner)
│   ├── nutrition.py             # Daily nutrition log + macro rings (custom QPainter widget)
│   ├── shopping_list.py         # Shopping list with check/delete, import from meal plan
│   ├── dishy.py                 # Full-page Dishy AI chat view (sidebar nav item)
│   ├── settings.py              # API keys, theme toggle, dietary prefs, data export/import, nutrition goals
│   └── help.py                  # How-to-use guide
│
├── widgets/
│   ├── dishy_bubble.py          # Floating FAB + chat panel overlay (appears on all views)
│   └── ingredient_row.py        # Nutrition ingredient row with Dishy-powered macro lookup
│
├── api/
│   ├── claude_ai.py             # Anthropic client: chat(), chat_with_tools(), lookup_nutrition()
│   ├── dishy_tools.py           # Tool schemas (TOOLS list) + DishyActions executor
│   ├── google_search.py         # Google Custom Search wrapper for recipe URL discovery
│   └── recipe_scraper.py        # Web scraper: extracts ingredients/instructions from recipe URLs
│
├── auth/
│   ├── supabase_client.py       # Singleton Supabase client + is_online() + is_configured()
│   ├── session_manager.py       # macOS Keychain session persist/restore (keyring)
│   ├── oauth_server.py          # Temporary Flask server for Google OAuth callback
│   ├── cloud_sync.py            # CloudSyncService — bidirectional push/pull engine
│   └── migration_dialog.py      # First sign-in dialog: upload existing local data
│
├── models/
│   └── database.py              # Database class: all SQLite CRUD helpers + sync helpers
│
├── utils/
│   ├── theme.py                 # ThemeManager singleton — Signal + c(dark, light) helper
│   ├── version.py               # APP_VERSION + VERSION_HISTORY — update here on every release
│   ├── workers.py               # Worker (QRunnable) + run_async() + ImageLoader
│   ├── macro_goals.py           # MACRO_SPECS, get/set macro goals (DB), goals_changed Signal broadcaster
│   ├── cloud_sync_service.py    # CloudSyncBackgroundService — QTimer 5min polling + Realtime WebSocket
│   └── image_upload.py          # upload_recipe_image() + is_supabase_url() — no Qt dep
│
└── assets/
    ├── icons/
    │   ├── icon.png             # App icon
    │   └── icon_dock.png        # Square macOS dock icon
    └── styles/
        ├── theme.qss            # Dark mode QSS (applied over qt_material dark_amber)
        └── theme_light.qss      # Light mode QSS (standalone, replaces qt_material)
```

---

## Database Schema (`dishboard.db`)

```sql
recipes            id, source_id, source, title, image_url, summary, servings,
                   ready_mins, data_json, saved_at, is_favourite, cloud_id, updated_at

meal_plans         id, day_of_week, meal_type, recipe_id, custom_name, week_start, notes,
                   cloud_id, updated_at

shopping_items     id, name, quantity, unit, checked, source, added_at, cloud_id, updated_at

settings           key, value   (key-value store: dietary_prefs, dishy_tip, dishy_tip_date,
                   sync_last_push_at, sync_last_pull_at, supabase_url, supabase_anon_key, etc.)

nutrition_logs     id, log_date, food_name, kcal, protein_g, carbs_g, fat_g, fiber_g, sugar_g, logged_at

dishy_chat_history id, session_id, role, content, tool_names, timestamp
                   (local-only — NOT included in JSON export/backup)
```

`data_json` on `recipes` stores the full recipe object as JSON including:
`ingredients` (list[str]), `instructions` (list[str]), `tags` (list[str]), `icon`, `colour`, `image_path`, `nutrition` (dict of macros).

---

## Navigation / View Indices

The `QStackedWidget` in `MainWindow` has views at fixed indices:

| Index | View | Section colour |
|---|---|---|
| 0 | MyKitchenView | #ff6b35 (orange) |
| 1 | RecipesView | #7c6af7 (purple) |
| 2 | MealPlannerView | #4caf8a (teal/green) |
| 3 | NutritionView | #e05c7a (pink) |
| 4 | ShoppingListView | #f0a500 (amber) |
| 5 | DishyView | #34d399 (green) |
| 6 | HelpView | — |
| 7 | SettingsView | — |

Sidebar also has: How to use (→ index 6), Settings (→ index 7) pinned at bottom.

---

## Theme System

- `utils/theme.py` exports a `ThemeManager` singleton as `manager`
- `manager.c(dark_val, light_val)` — returns correct value for current mode (use at widget-creation time)
- `manager.theme_changed` Signal — broadcast from `MainWindow._on_theme_changed()`
- All views/widgets implement `apply_theme(mode: str)` for structural updates on mode switch
- Dark mode: `apply_stylesheet(app, "dark_amber.xml")` + `theme.qss` appended
- Light mode: `theme_light.qss` only (replaces qt_material entirely)

### Colour palette
| Token | Dark | Light |
|---|---|---|
| Background | #090909 | #f5f5f5 |
| Sidebar bg | #050505 | #efefef |
| Card bg | #111111 | #ffffff |
| Text primary | #f0f0f0 | #1a1a1a |
| Text muted | #888888 | #666666 |
| Accent orange | #ff6b35 | #ff6b35 |
| Dishy green | #34d399 | #34d399 |

### Checkbox fix (important)
qt_material dark_amber injects SVG images into checkbox indicators. To override:
- **Must** include `image: none;` on every `::indicator` pseudo-state
- **Must** include full indicator CSS in any inline `setStyleSheet()` on checkboxes (app-level QSS doesn't cascade into widget-level inline styles)
- See `shopping_list.py → ShoppingItem._apply_style()` for the canonical pattern

---

## Dishy AI System

### Two chat surfaces
1. **DishyBubble** (`widgets/dishy_bubble.py`) — floating FAB overlay on all views, context-aware per page
2. **DishyView** (`views/dishy.py`) — full-page chat in sidebar nav (index 5)

Both share the same architecture:
- `ClaudeAI.chat_with_tools()` agentic loop (Sonnet model)
- `TOOLS` list from `api/dishy_tools.py` — Anthropic function-calling schemas
- `DishyActions` executor (`api/dishy_tools.py`) — handles all tool calls, queues `pending_refreshes`
- `MainWindow` wires `DishyActions` to both surfaces and handles `_on_dishy_refresh()`
- Green action confirmation pills shown after tool calls (`ActionConfirmBubble`)

### Available tools (as of v0.37)
`save_recipe`, `set_meal_slot`, `fill_week_meal_plan`, `add_shopping_items`, `shopping_list_from_meal_plan`,
`delete_meal_slot`, `clear_meal_day`, `clear_meal_plan`, `delete_shopping_item`, `clear_shopping_list`,
`delete_recipe`, `clear_recipe_library`, `log_recipe_nutrition`

All delete/clear tools require user confirmation before Dishy will call them.
`clear_meal_day` clears all 3 meal slots for a specific day.
`clear_meal_plan` clears the current week by default; `all_weeks=true` wipes all data.

### Context injection
Every message prepends:
- `[Page context: ...]` — describes current view
- `## Live app context` — dietary prefs, saved recipes, meal plan, shopping list, today's nutrition

### Models
- `ClaudeAI.MODEL = "claude-haiku-4-5-20251001"` — general chat and nutrition lookup
- `ClaudeAI.TOOLS_MODEL = "claude-sonnet-4-6"` — tool-use (more reliable)

---

## Recipes System

`RecipesView` (`views/recipes.py`) has a 4-page internal `QStackedWidget`:
- Page 0: Saved recipes grid (with tag filter bar)
- Page 1: Recipe detail view (with Edit button)
- Page 2: Google search / URL scrape browser
- Page 3: Create/Edit recipe form (`CreateRecipePage`)

### Tag filter bar
- Meal-type chips (Breakfast/Lunch/Dinner/Snack/Dessert) always pinned at left, **teal** `#4caf8a` style
- 1px separator between meal chips and descriptive tags
- Descriptive tags use orange style
- `_meal_chip_style()` and `_tag_chip_style()` methods

### Edit recipe
- Edit button in detail view (pen icon) → calls `_edit_recipe(db_id)`
- Loads `data_json`, calls `CreateRecipePage.load_for_edit(data, edit_id)`
- On save, `_save()` checks `self._edit_id` → UPDATE vs INSERT
- `reset_for_create()` clears form when creating new

---

## Meal Planner

`MealPlannerView` (`views/meal_planner.py`)
- Grid: Mon–Sun columns × Breakfast/Lunch/Dinner rows
- Week navigation (prev/next week)
- Meal slot icons: `fa5s.egg` (breakfast), `fa5s.utensils` (lunch), `fa5s.concierge-bell` (dinner)
- "Fill with Dishy" button triggers Dishy to auto-generate the week's plan

---

## Shopping List

`ShoppingListView` (`views/shopping_list.py`)
- Items loaded from `shopping_items` DB table and grouped by category
- **Collapsible category sections** (`_CategorySection`) — click header to expand/collapse; shows item count badge + X/Y progress
- Stats strip: total, to-get, in-basket, categories count chips
- Slim amber progress bar showing overall completion
- Per-item checkbox (rounded, amber accent) + source badge ("plan" in green for meal_plan source) + delete button
- "Generate from Meal Plan" — extracts ingredients from this week's planned recipes
- "Ask Dishy" — triggers Dishy to build/update the list
- "Export to Notes" — preserves category grouping in exported text
- "Clear checked" button

---

## Nutrition

`NutritionView` (`views/nutrition.py`)
- `MacroRing` — custom `QPainter` widget showing a circular progress ring per macro
- "Today's Intake" card: Calories/Protein/Carbs/Fat/Fiber/Sugar rings with daily goals
- "Today's Food Log" — per-entry rows with delete; running totals
- Food lookup via `ClaudeAI.lookup_nutrition(query)` — natural language, returns JSON macros
- "Ask Dishy" button triggers lookup

### Nutrition across the app (v0.21+)
- Every recipe stores `nutrition_ingredients` (per-item breakdown), `nutrition_total`, `nutrition_per_serving` in `data_json`
- `ClaudeAI.analyze_recipe_nutrition(ingredients, servings)` — single API call returning full nutrition for all ingredients
- Scraped recipes: auto-analyzed after Dishy enrichment completes (`_on_nutrition_analyzed`)
- Dishy-saved recipes: nutrition analyzed inside `_tool_save_recipe` before DB write
- Recipe detail shows per-ingredient macro pills (kcal, protein, fat, carbs) inline
- Nutrition summary card: 6 macros + "Log to Today" button + Dishy badge
- `log_recipe_nutrition` Dishy tool logs a saved recipe to today's nutrition log
- Weekly nutrition summary included in Dishy's live context via `get_nutrition_totals_for_range`

---

## Settings

`SettingsView` (`views/settings.py`)
- API keys: Anthropic, Google Search (saved to DB settings table, loaded into `os.environ`)
- Theme toggle: Dark / Light (calls `MainWindow._on_theme_changed()`)
- Dietary preferences (free-text, saved to DB)
- Data management: export JSON backup, import JSON backup, clear all data
- Version History card: user-friendly changelog, data sourced from `utils/version.py`

---

## Key Patterns

### Async pattern
```python
from utils.workers import run_async
self._worker = run_async(
    some_blocking_fn, arg1, arg2,
    on_result=self._on_result,
    on_error=self._on_error,
)
```
`QueuedConnection` ensures callbacks run on main thread.

### Theme-aware inline colour
```python
from utils.theme import manager as theme_manager
color = theme_manager.c('#c8c8c8', '#333333')  # dark, light
```

### All views use `objectName("view-container")`
### All nav buttons use `objectName("nav-btn")` and are checkable `QPushButton`

---

## Version History

| Version | Summary |
|---|---|
| v0.37 | Smart shopping lists (consolidate, practical units, skip pantry staples, pantry mode teaser); clear_meal_day tool; clear_meal_plan all_weeks support; meal planner wipe fixed |
| v0.36 | Instant cloud sync on every data change; Today's Log reads directly from meal planner (no duplicates); macro rings driven by meal plan; NutritionSyncService removed |
| v0.35 | Supabase auth + cloud sync: login screen, Google OAuth, bidirectional sync, offline-first, sync indicator, Account settings page |
| v0.1 | Initial shell + all core views |
| v0.2 | Settings tab removed, shopping list Notes export, meal planner calendar redesign + Apple Calendar export, Dishy rename, sidebar branding, dock icon |
| v0.3 | USDA nutrition integration (since replaced) |
| v0.4 | Dark/light mode toggle; ThemeManager singleton; theme_light.qss |
| v0.5 | Light mode polish; How to use + Settings sidebar; Dishy theme-aware; Data Portability card |
| v0.6 | Recipe tag filter bar; Dishy meal plan generation; recipe photos; Dishy quick-prompt chips; duplicate recipe detection |
| v0.7 | Canonical section colour palette; nav button per-section checked colours; My Kitchen uses section colours |
| v0.8 | Sidebar Dishy Tip card + Recent Recipes strip; Nutrition: MacroRing widget, Today's Intake, food log; nutrition_logs DB table |
| v0.9 | Nutrition lookup → Dishy (Claude AI) replaces USDA; natural language lookup; note field |
| v0.10 | Full Dishy integration; ingredient_row Dishy-powered; all Dishy buttons green; richer page contexts |
| v0.11 | Dishy tool-use (function calling); dishy_tools.py; ClaudeAI.chat_with_tools(); action pills; per-tab Ask Dishy buttons |
| v0.12 | Full-page DishyView with tool-calling parity; DishyView.setup_actions(); wired in MainWindow |
| v0.13 | Checkbox interior fix (image: none + full indicator in inline QSS); meal planner icons (egg/utensils/concierge-bell); recipe filter by meal type; edit recipe functionality; meal-type tags visually distinct (teal) from descriptive tags |
| v0.14 | New app icon (modern rounded dark design); version history page in Settings; `utils/version.py` as single version source |
| v0.15 | Dashboard renamed to "My Kitchen"; home view fully redesigned with scrollable widgets, unified card style, all views refresh on navigation |
| v0.17 | Create Recipe fully redesigned: two-column card layout, inline macro pills per ingredient, collapsible Appearance card, star fav toggle, enlarged fonts |
| v0.18 | Meal planner calendar redesign: row labels (Breakfast/Lunch/Dinner) in col 0, bigger fonts, wider accent strip, more grid spacing |
| v0.19 | Meal planner recipe access: View Recipe button per slot, edit pencil button, day header date darker in light mode |
| v0.20 | Dishy delete & clear actions: 6 new tools (delete/clear for meal plan, shopping list, recipes); all require user confirmation |
| v0.21 | Nutrition everywhere: per-ingredient macros on recipes, auto-analysis for scraped + Dishy recipes, Log to Today button, log_recipe_nutrition tool, weekly nutrition in Dishy context |
| v0.22 | Nutrition dashboard redesign: full-page non-scrolling dashboard; 6 macro rings; Today's Plan panel with kcal from meal planner; Import meals button; weekly bar chart; 4 stat tiles; Quick Add (Dishy-powered); navigate_to wired in |
| v0.23 | Dishy daily macro tracking: `sync_meal_plan_nutrition` tool; system prompt updated with daily tracking loop; context includes per-meal sync status; proactive syncing behaviour |
| v0.24 | Fully automatic nutrition tracking: `auto_log_meal_nutrition()` DB helper; meal planner auto-logs today's meals on save; Dishy tools auto-log when setting/filling meal slots; removed manual import button; nutrition page auto-refreshes on new meal |
| v0.25 | Guaranteed macro tracking: `_maybe_analyze_and_log()` helper; Dishy save_recipe retries nutrition; UI recipe save triggers background analysis if missing; `showEvent` on NutritionView auto-refreshes on every visit; macros mandatory in system prompt |
| v0.26 | Live nutrition sync engine: `NutritionSyncService` (QTimer, 10 s interval) in `utils/nutrition_sync.py`; instant sync on meal slot save; background Claude analysis for recipes missing macros; Meal Planner + Nutrition page fully linked in real time |
| v0.27 | Recipe-only meal planner: `MealPickerDialog` text input removed; Set Meal disabled until recipe selected; selection highlighted with accent colour; current recipe pre-selected on re-open; Dishy `set_meal_slot` rejects non-library names |
| v0.28 | Deep Dishy integration: system prompt fully rewritten; per-page contexts and greetings overhauled; live context enriched with favourites, category breakdown, missing-nutrition list; tool descriptions sharpened; full cross-app workflow awareness |
| v0.29 | Help page rewrite: all sections updated to cover current features; feature bullet lists per section; Dishy section with all 12 direct actions; Settings section added; "The DishBoard Loop" workflow banner; redesigned card layout |
| v0.34 | Dishy chat overhaul: modern glassy UI, green user bubbles with Dishy avatar, wide bubbles, horizontal chip row, persistent SQLite chat history, history browser dialog, resume-last-session banner |
| v0.33 | Shopping list overhaul: collapsible category sections, stats strip (total/to-get/in-basket/categories), amber progress bar, meal-plan source badges, full dark/light mode support |

| v0.43 | Editable macro goals in Settings → Nutrition Goals; goals saved to DB (cloud synced); goals_changed Signal updates nutrition rings and My Kitchen rings instantly; MACRO_SPECS moved to utils/macro_goals.py |
| v0.42 | Server-side AI proxy (Supabase Edge Function); Supabase Storage for recipe images; Realtime WebSocket sync; "Live" sync indicator state; polling reduced to 5 min |
| v0.41 | Full light mode: Dishy chat, Settings header/nav, login logo all theme-adaptive at runtime; new icon set |

**Current version: v0.43**

> IMPORTANT: Always increment version on every session that makes changes. Do NOT reach v1.0 without explicit user approval.
> When bumping version: (1) update `APP_VERSION` in `utils/version.py`, (2) prepend a new entry to `VERSION_HISTORY` in the same file, (3) update CONTEXT.md and MEMORY.md version tables.

---

## Packaging as macOS .app

```bash
cd /Users/thomasslater/Documents/VSCODE/DishBoard
pyinstaller DishBoard.spec --clean -y
open dist/DishBoard.app
```

- Output: `dist/DishBoard.app` (~160 MB)
- User data (DB, config.json) stored in `~/Library/Application Support/DishBoard/`
- Assets (QSS, icons) bundled read-only inside the .app via `sys._MEIPASS`
- `utils/paths.py` — `get_data_dir()` and `get_resource_path()` handle frozen vs dev paths
- `DishBoard.spec` — includes `mf2py/backcompat-rules` as explicit data (required by recipe_scrapers → extruct → mf2py)
- API keys entered in Settings are saved to DB and loaded into `os.environ` at startup

---

## How to Run

```bash
cd /Users/thomasslater/Documents/VSCODE/DishBoard
python3 DishBoard.py
```

Requires `.env` in project root:
```
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
GOOGLE_CSE_ID=...
```
