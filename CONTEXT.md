# DishBoard — Project Context

> This file exists so that Claude Code can read it at the start of each session to understand the full
> picture of what DishBoard is, how it's built, and where it's going.
> **Update this file whenever a significant feature, structural change, or design decision is made.**
>
> After reading this file, also read `HANDOVER.md` for the latest implementation-level refactors,
> platform notes, runtime architecture, and verification history.
>
> For product direction, UX priorities, and the long-term roadmap, also read `NORTH_STAR.md`.

---

## What is DishBoard?

A personal recipe manager and meal planner desktop app for macOS and Windows, built with Python + PySide6.
Tom Slater is the sole developer. It is currently a dev-first Python app run from source during development and packaged for desktop release.

**Future plans:**
- Package as polished desktop releases for both macOS and Windows
- Eventually a companion iOS app (React Native consuming a thin local or cloud API layer)
- Update distribution via GitHub Releases + in-app version checker

**Current release snapshot:**
- Current app version is `v0.71`
- Phase 1 system state visibility is now completed through the shared visibility service plus Monitoring/account surfaces, rather than a persistent status bar on every page
- The always-on shell monitoring strip and contextual page banner were removed after testing because they added noise without improving user actionability
- Dishy, recipe nutrition/enrichment, sync/runtime tracking, and Monitoring integrity actions now publish scoped background work through the shared visibility service
- Monitoring now acts as the detailed operational drill-down for severity, attention reasons, freshness, recent changes, and background work state
- The calmer Phase 1 UI system cleanup remains the shared foundation: warmer neutral chrome, reduced action density, and more consistent spacing/toolbars/tabs/cards across the core screens
- The product north star is now documented in `NORTH_STAR.md`: DishBoard should evolve toward a connected food operations console rather than a collection of disconnected utility pages.

## Non-Negotiable Guardrail

- DishBoard must continue to run correctly on both macOS and Windows at all times.
- No code change should be made for one desktop platform that breaks, weakens, or complicates the other.
- Future iOS portability is also a priority, so platform-specific changes should be isolated and should not push the architecture toward Windows-only assumptions.
- When making cross-platform changes, prefer additive or isolated platform handling over altering shared behaviour in a way that could regress macOS or future iOS work.
- Every meaningful implementation change should also be logged in `HANDOVER.md` so work can move cleanly between machines and assistants.

---

## Tech Stack

| Layer | Choice |
|---|---|
| GUI | PySide6 (Qt for Python) |
| Styling | qt_material dark_amber base + custom `theme.qss` + `theme_light.qss` |
| Database | SQLite via sqlite3 (`dishboard.db` in project root) |
| AI | Anthropic Claude (claude-haiku-4-5-20251001 for chat, claude-sonnet-4-6 for tool-use) |
| Web search | Direct scrapeable recipe-site search (BBC Good Food + Delish) |
| Async | QThreadPool + custom `Worker`/`run_async` in `utils/workers.py` |
| Icons | qtawesome (Font Awesome 5) |
| Env / keys | All API keys stored in SQLite settings table, loaded into `os.environ` at startup |

**Removed APIs (no longer in codebase):** Spoonacular, Nutritionix, USDA FoodData Central, Tesco

---

## Project Structure

```
DishBoard/
├── DishBoard.py                 # Thin bootstrap — sets cert env vars, resolves assets, launches ApplicationController
├── main_window.py               # QMainWindow: sidebar nav + QStackedWidget content area
├── CONTEXT.md                   # ← this file
├── NORTH_STAR.md                # product direction: food operations console goals + roadmap
├── HANDOVER.md                  # detailed implementation handover for future humans / AI assistants
│
├── views/
│   ├── my_kitchen.py            # Home (index 0): stat cards, quick actions, recent recipes, macro rings
│   ├── my_kitchen_storage.py    # My Kitchen (index 4): full pantry/fridge/freezer tracker
│   ├── recipes.py               # Recipe browser + create/edit form + detail view (QStackedWidget)
│   ├── recipes_shared.py        # Shared dialogs/helpers extracted from recipes.py
│   ├── meal_planner.py          # Weekly meal planner grid (Mon–Sun × Breakfast/Lunch/Dinner)
│   ├── nutrition.py             # Daily nutrition log + macro rings (custom QPainter widget)
│   ├── shopping_list.py         # Shopping list + Live Shop mode (tick items → auto adds to My Kitchen)
│   ├── dishy.py                 # Full-page Dishy AI chat view (sidebar nav item)
│   ├── settings.py              # API keys, theme toggle, dietary prefs, data export/import, nutrition goals
│   ├── settings_account.py      # Account/sync/session diagnostics page extracted from settings.py
│   └── help.py                  # How-to-use guide
│
├── widgets/
│   ├── dishy_bubble.py          # Floating FAB + chat panel overlay (appears on all views)
│   └── ingredient_row.py        # Nutrition ingredient row with Dishy-powered macro lookup
│
├── api/
│   ├── claude_ai.py             # Anthropic client: chat(), chat_with_tools(), lookup_nutrition()
│   ├── dishy_tools.py           # Tool schemas (TOOLS list) + DishyActions executor
│   ├── google_search.py         # Direct recipe-site search helper for scrapeable recipe URL discovery
│   └── recipe_scraper.py        # Web scraper: extracts ingredients/instructions from recipe URLs
│
├── auth/
│   ├── supabase_client.py       # Singleton Supabase client + is_online() + is_configured()
│   ├── session_manager.py       # keyring-backed session persist/restore + diagnostics visibility
│   ├── oauth_server.py          # Temporary Flask server for Google OAuth callback
│   ├── cloud_sync.py            # CloudSyncService — bidirectional push/pull engine
│   └── migration_dialog.py      # First sign-in dialog: upload existing local data
│
├── models/
│   └── database.py              # Database class: all SQLite CRUD helpers + sync helpers
│
├── utils/
│   ├── app_runtime.py           # ApplicationController + AppContext runtime bootstrap/lifecycle
│   ├── assets.py                # Helpers for loading bundled text/JSON assets
│   ├── theme.py                 # ThemeManager singleton — Signal + c(dark, light) helper
│   ├── version.py               # APP_VERSION + VERSION_HISTORY loaded from bundled JSON metadata
│   ├── workers.py               # Worker (QRunnable) + run_async() + ImageLoader
│   ├── macro_goals.py           # MACRO_SPECS, get/set macro goals (DB), goals_changed Signal broadcaster
│   ├── cloud_sync_service.py    # CloudSyncBackgroundService — QTimer 5min polling + Realtime WebSocket
│   ├── meal_deduction.py        # MealDeductionService — QTimer deducts pantry items when meal times pass
│   ├── image_upload.py          # upload_recipe_image() + is_supabase_url() — no Qt dep
│   └── search_clients.py        # Lazy API client factories to avoid import-time singletons
│
└── assets/
    ├── metadata/
    │   └── version_history.json # Release/version history loaded by utils.version
    ├── icons/
    │   ├── icon.png             # App icon
    │   └── icon_dock.png        # Square macOS dock icon
    ├── prompts/
    │   └── dishy_system_prompt.txt  # Externalised Dishy system prompt
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

pantry_items       id, name, quantity, unit, storage ('Pantry'|'Fridge'|'Freezer'),
                   expiry_date, added_at, cloud_id, updated_at

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
| 0 | MyKitchenView (Home) | #ff6b35 (orange) |
| 1 | RecipesView | #7c6af7 (purple) |
| 2 | MealPlannerView | #4caf8a (teal/green) |
| 3 | NutritionView | #e05c7a (pink) |
| 4 | MyKitchenStorageView (My Kitchen) | #e8924a (warm amber) |
| 5 | ShoppingListView | #f0a500 (amber) |
| 6 | DishyView | #34d399 (green) |
| 7 | HelpView | — |
| 8 | SettingsView | — |

Sidebar also has: How to use (→ index 7), Settings (→ index 8) pinned at bottom.

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
| v0.71 | Cleanup + flow refresh release: removed dead/orphaned code, redesigned onboarding and the app tour to match the current visual system, replaced Shopping List smart-summary text with a cleaner estimated total treatment, removed the noisy planner mode banner text, and clarified the Home page purpose copy |
| v0.70 | Completed Phase 1 system state visibility through the shared visibility service and Monitoring/account surfaces, standardized scoped runtime work tracking, and removed the low-value always-on shell visibility chrome |
| v0.68 | Phase 1 UI system cleanup foundation: restrained warm-neutral redesign across core screens, search-first Recipes rework, calmer Dishy workspace, cleaner Settings/Help prioritisation, and direct scrapeable recipe-site search for working web results |
| v0.67 | Planner intelligence, reusable templates, pantry rescue, leftover/prep metadata, smarter shopping generation, nutrition coaching, and scaled recipe details |
| v0.66 | Windows compatibility milestone: OS-aware app-data paths, cross-platform file-open/export flows, Windows-ready PyInstaller spec/icon/keyring backend, updater asset selection by platform, and Windows build scripts (`build_windows.ps1` / `.bat`) |
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

| v0.45.3 | Dishy fully operational: Supabase Edge Function deployed + ANTHROPIC_API_KEY set as secret; supabase/config.toml added |
| v0.45.2 | Proxy-only Dishy: removed anthropic_api_key from local DB key-loading; all ClaudeAI instantiations use proxy path; app_tour uses proxy client; no local Anthropic key ever loaded |
| v0.45.1 | Bug fixes: Dishy proxy now works correctly without a personal API key (supabase-py v2 session fix); recipe scraper SSL cert passed explicitly so clicking search results works on packaged app |
| v0.45 | Smart macro recalc via Dishy AI on calorie change; Home/My Kitchen sidebar split; recipe search 60 results as instant modern cards; SSL + Dishy proxy fixes for packaged app; instant cloud sync for Settings + Dishy chats; theme colour fixes across all Settings pages and Dishy panel |
| v0.43 | Editable macro goals in Settings → Nutrition Goals; goals saved to DB (cloud synced); goals_changed Signal updates nutrition rings and My Kitchen rings instantly; MACRO_SPECS moved to utils/macro_goals.py |
| v0.42 | Server-side AI proxy (Supabase Edge Function); Supabase Storage for recipe images; Realtime WebSocket sync; "Live" sync indicator state; polling reduced to 5 min |
| v0.41 | Full light mode: Dishy chat, Settings header/nav, login logo all theme-adaptive at runtime; new icon set |
| v0.56 | Themed dialogs: `utils/themed_dialog.py` ThemedMessageBox replaces all QMessageBox calls; UpdateDialog, MigrationDialog, ChatHistoryDialog, AddToCalendarDialog, _AddItemDialog all use FramelessWindowHint + card pattern + drag support; no native OS chrome on any popup |
| v0.60 | Pantry intelligence: expiry alerts banner on home dashboard (items ≤3 days); 'Use it up →' button pre-loads Dishy; expiry context injected into Dishy live context; 'What can I make with what I have?' quick-prompt chip; new `swap_meal_slots` Dishy tool |
| v0.61 | Feature platform release: Monitoring page (data totals, AI usage, jobs, notifications, telemetry), feature flags (global + per-user + optional cloud refresh), in-app notifications + workflow runner, daily AI hard limit (50/day) enforced in app + Supabase Edge proxy, Dishy retrieved-memory context, typo-tolerant weighted local recipe search, optional Sentry/PostHog hooks |
| v0.59 | Home dashboard: Favourites card replaced with live My Kitchen preview; shows all pantry/fridge/freezer items by storage section + category; expiry badges; instant live refresh via pantry_changed Signal from `get_pantry_broadcaster()` in `my_kitchen_storage.py` |
| v0.58 | Dishy bubble UI redesign: avatar on Dishy messages + typing indicator; gradient FAB; card-colour panel bg; themed input field; icon close button; removed tools badge; indented action pills; 16px corner radius; styled scrollbar |
| v0.57 | Responsive scaling: sidebar auto-collapses at <940px window width (re-expands at >1060px); logo icon always visible (30px collapsed / 52px expanded); Dishy's Tip removed from sidebar; window minimum 780×520; meal planner, recipes, shopping list minimum size constraints lowered |

**Current version: v0.71**

> IMPORTANT: Always increment version on every session that makes changes. Do NOT reach v1.0 without explicit user approval.
> When bumping version: (1) prepend a new entry to `assets/metadata/version_history.json`, (2) confirm `utils/version.py` still loads the JSON metadata correctly, and (3) update `CONTEXT.md`, `HANDOVER.md`, and `NORTH_STAR.md` when the change affects release history or product direction.

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

No `.env` file needed. API keys (Anthropic, Google) are entered in Settings and saved to the local DB. This mirrors exactly how the packaged app works.
