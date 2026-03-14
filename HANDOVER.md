# DishBoard Handover

This file is the detailed handover for future work on DishBoard.

Read this file when:
- a new human developer starts working on the repo
- an AI assistant joins mid-project
- conversation memory has been compressed and the assistant needs the latest structural context
- you want the fastest route to understanding what changed, why it changed, and what must not be broken

How to use this file:
- Read [CONTEXT.md](./CONTEXT.md) first for the product-level picture and non-negotiable platform guardrails.
- Read this file second for the implementation-level state of the repo after the Windows enablement and cross-platform cleanup work.
- Treat this file as a living log of major architectural or workflow changes.
- Update this file whenever a future change materially affects startup, packaging, sync, auth, testing, or project structure.

## Ongoing Project Rules

These rules apply to every future change:

- Every meaningful code or file change must be reflected in [HANDOVER.md](./HANDOVER.md) before the work is considered complete.
- DishBoard must continue to run correctly on both Windows and macOS after every change.
- Do not use single-platform wording for cross-platform features in code comments, release notes, helper text, or handover notes.
- If a feature is genuinely platform-specific, label it explicitly and document the fallback behaviour for the other platform.

## Highest-Priority Guardrail

DishBoard must continue to run correctly on both macOS and Windows.

That is not optional.

Future iOS portability is also a real product goal, so platform-specific work should be isolated rather than baked into shared runtime assumptions. Windows support was added with that rule in mind. If a future change helps one desktop platform but risks the other or pushes shared code toward OS-specific assumptions, stop and redesign it.

Practical interpretation:
- Prefer additive platform handling over changing shared logic for every platform.
- Keep platform packaging and setup logic in platform-specific scripts where possible.
- Do not rewrite shared UI, database, auth, sync, or assets around Windows-only or macOS-only path, shell, or filesystem assumptions.
- Before changing startup, packaging, or release notes again, verify both the Windows path and the macOS path still make sense.

## What This Refactor Was Trying To Achieve

This round of work started as a Windows enablement pass, but the goal was not just "make it run on Windows once." The goal was to improve the codebase in ways that make the app easier to maintain across Windows and macOS without harming future portability.

The main themes were:
- remove fragile startup globals
- move blocking sync connectivity checks off the UI thread
- reduce silent failure paths around auth/session persistence
- externalize large content blobs that did not belong in Python source
- split some of the biggest view files without changing user-facing behaviour
- add smoke tests that protect packaging and basic Qt construction on Windows

## Latest Update

This handover was updated again for the `v0.71` onboarding/cleanup/shopping polish pass.

Recent changes recorded here:
- `v0.71` packages the cleanup and first-run flow refresh that followed the visibility release. Dead/orphaned modules and stale helpers were removed across the runtime, onboarding in [views/onboarding.py](./views/onboarding.py) was rebuilt as a guided selection flow with no freeform text boxes, and the tour in [views/app_tour.py](./views/app_tour.py) was rewritten as a curated theme-aligned walkthrough with corrected page order and more reliable readable copy. Shopping List in [views/shopping_list.py](./views/shopping_list.py) now surfaces a much quieter estimated-total treatment instead of the old smart-summary sentence, [views/meal_planner.py](./views/meal_planner.py) no longer carries the noisy planning-mode banner text, and Home copy in [views/my_kitchen.py](./views/my_kitchen.py) was updated so the page describes itself as the live operational overview it actually is. Coverage for this release was exercised through [tests/test_gui_smoke.py](./tests/test_gui_smoke.py), the existing grocery consolidation tests, and the full suite.
- `v0.70` finishes the Phase 1 system visibility work without forcing permanent chrome into every page. [utils/system_visibility.py](./utils/system_visibility.py) now holds the shared severity/freshness/digest/action policy, [views/settings.py](./views/settings.py) and [views/settings_account.py](./views/settings_account.py) consume that shared model for Monitoring/account sync language, and high-value producers in [views/dishy.py](./views/dishy.py), [widgets/dishy_bubble.py](./widgets/dishy_bubble.py), [views/recipes.py](./views/recipes.py), and Monitoring integrity actions now use scoped visibility work handles so active/failing background work cannot get stuck. The attempted shell strip and page banner were removed from [main_window.py](./main_window.py) after validation because they added noise without enough user value, so Monitoring remains the detailed operational drill-down rather than the app carrying permanent status chrome on every page. Coverage for the current visibility state lives in [tests/test_system_visibility.py](./tests/test_system_visibility.py), [tests/test_system_visibility_gui.py](./tests/test_system_visibility_gui.py), and [tests/test_gui_smoke.py](./tests/test_gui_smoke.py).
- `v0.69` closes the first major command workflow milestone. The old command-only launcher is now a mixed-result command panel: [widgets/command_palette.py](./widgets/command_palette.py) renders the `Cmd/Ctrl+K` overlay, [main_window.py](./main_window.py) owns result gathering/execution/recent persistence, and the core views expose palette-safe highlight/open/save APIs so the panel can navigate and act without private-widget reach-ins. The shipped surface now includes commands, recent usage, saved recipe/pantry/shopping/planner/settings/Dishy search results, inline quick-add flows, outside-click dismissal, themed selectors, and typo-tolerant saved-recipe suggestions while typing. Coverage for this release sits in [tests/test_command_palette.py](./tests/test_command_palette.py) and [tests/test_gui_smoke.py](./tests/test_gui_smoke.py).
- The first Phase 1 command palette was expanded into a mixed-result command panel. [widgets/command_palette.py](./widgets/command_palette.py) now renders a flat, unboxed `Cmd/Ctrl+K` overlay with grouped commands, recent usage, saved recipe/pantry/shopping/planner/settings/Dishy search hits, and inline quick-add forms for pantry, shopping, nutrition, and meal-slot planning. The overlay now dismisses on outside click, recipe-search form fields surface typo-tolerant saved-recipe suggestions only after the user starts typing, those suggestions render as a quieter dropdown-like list instead of bright inline rows, and selector popups are explicitly themed instead of falling back to native highlight colours. [main_window.py](./main_window.py) now owns the mixed result providers, recent-item persistence in `settings`, inline recipe suggestion logic, and close-then-dispatch execution flow, while [views/meal_planner.py](./views/meal_planner.py), [views/my_kitchen_storage.py](./views/my_kitchen_storage.py), [views/shopping_list.py](./views/shopping_list.py), [views/nutrition.py](./views/nutrition.py), [views/dishy.py](./views/dishy.py), and [views/settings.py](./views/settings.py) expose palette-safe highlight/open/save APIs. Panel actions now also sync their recent-usage persistence back through the cloud path so the command panel state is not left as local-only metadata. Coverage for mixed search, quick-add, autocomplete suggestions, recents, exact-section/session routing, modal blocking, outside-click dismissal, and the no-box styling contract lives in [tests/test_command_palette.py](./tests/test_command_palette.py) alongside the main-window smoke assertion in [tests/test_gui_smoke.py](./tests/test_gui_smoke.py).
- `v0.68` bundles the first major Phase 1 "food operations console" UI foundation release. The shared shell is now materially established rather than experimental: calmer page chrome, stronger spacing discipline, restrained accents, overflow-based action reduction, and warmer neutral surfaces now shape the core product screens.
- The restrained redesign now reaches the busiest user-facing views. [views/recipes.py](./views/recipes.py) was reworked into a search-first workspace, [views/meal_planner.py](./views/meal_planner.py) and [views/nutrition.py](./views/nutrition.py) were flattened to reduce colour clutter, [views/shopping_list.py](./views/shopping_list.py) and [views/my_kitchen_storage.py](./views/my_kitchen_storage.py) keep section-aware guidance but with quieter chrome, and [views/help.py](./views/help.py) plus [views/settings.py](./views/settings.py) now read as calmer support pages instead of dense utility panels.
- Dishy is still a flagship destination and is now visually aligned with the rest of the app rather than standing apart as a green-heavy sub-product. [views/dishy.py](./views/dishy.py), [widgets/dishy_bubble.py](./widgets/dishy_bubble.py), and the loading dialog in [views/recipes_shared.py](./views/recipes_shared.py) now share the same warm neutral/orange language.
- Recipe web search no longer relies on the older unreliable search path. [api/google_search.py](./api/google_search.py) now pulls direct scrapeable recipe URLs from recipe sites, which fixed the "single result / cannot open result" failure path in the Recipes search UI.
- Settings information hierarchy was intentionally reprioritised in [views/settings.py](./views/settings.py) so everyday user controls come first and lower-frequency account/data/monitoring/version surfaces are visually demoted.
- Version metadata for the latest shipped release now lives at the top of [assets/metadata/version_history.json](./assets/metadata/version_history.json) as `v0.71`.
- Added [NORTH_STAR.md](./NORTH_STAR.md) as the product-direction document. It defines the "food operations console" north star, the primary UX goals, the experience principles, and the phased roadmap with flagship features. Future product/UI work should read it alongside [CONTEXT.md](./CONTEXT.md) instead of relying on chat-only planning.
- Phase 1 UI system cleanup started landing across the shared shell. [utils/ui_tokens.py](./utils/ui_tokens.py) now exposes semantic spacing/surface/border/motion tokens, [widgets/page_scaffold.py](./widgets/page_scaffold.py) adds shared page primitives (`PageScaffold`, `PageToolbar`, `StatStrip`, `SegmentedTabs`, `StatusBanner`, `EmptyStateCard`), and both [assets/styles/theme.qss](./assets/styles/theme.qss) and [assets/styles/theme_light.qss](./assets/styles/theme_light.qss) style those object names directly.
- Core screens were moved onto the new shell primitives instead of bespoke top chrome: [views/shopping_list.py](./views/shopping_list.py), [views/my_kitchen_storage.py](./views/my_kitchen_storage.py), [views/meal_planner.py](./views/meal_planner.py), [views/nutrition.py](./views/nutrition.py), and [views/help.py](./views/help.py) now share the same page rhythm for headers, toolbar rows, banners, tab pills, and stat strips. This is the first real step toward the "food operations console" north star.
- The next modernity pass reduced visible action density instead of only restyling it. [widgets/page_scaffold.py](./widgets/page_scaffold.py) now includes `OverflowActionMenu` plus semantic toolbar grouping (`primary`, `secondary`, `overflow`), and the dark/light QSS files style that quieter control language. Core page chrome was simplified in [views/shopping_list.py](./views/shopping_list.py), [views/my_kitchen_storage.py](./views/my_kitchen_storage.py), [views/meal_planner.py](./views/meal_planner.py), [views/nutrition.py](./views/nutrition.py), [views/recipes.py](./views/recipes.py), and [views/my_kitchen.py](./views/my_kitchen.py): fewer visible buttons, more overflow, and less persistent Dishy promotion.
- Dishy remains a flagship destination and was explicitly not removed. [views/dishy.py](./views/dishy.py) was rebalanced toward a calmer dedicated workspace: quieter header chrome, fewer visible quick prompts, less prominent utility controls, and a stronger focus on the conversation canvas and input area.
- GUI smoke coverage was expanded in [tests/test_gui_smoke.py](./tests/test_gui_smoke.py), and [tests/test_design_system_smoke.py](./tests/test_design_system_smoke.py) was added to instantiate the shared page-shell primitives in both dark and light theme modes.
- SQLite connections now enable WAL mode plus a 30 second busy timeout in [models/database.py](./models/database.py) to reduce transient multi-connection lock failures during startup sync.
- Cloud sync now treats SQLite lock errors as retryable cycle failures instead of logging long per-row cascades in [auth/cloud_sync.py](./auth/cloud_sync.py).
- The documentation rule is now explicit: every meaningful future change must also update [HANDOVER.md](./HANDOVER.md).
- Cross-platform support is now a standing release rule for both Windows and macOS, and handover or user-facing text should not imply a single-platform app unless a feature is genuinely platform-specific.
- `v0.67` added planner intelligence in [views/meal_planner.py](./views/meal_planner.py), [utils/meal_optimizer.py](./utils/meal_optimizer.py), and [utils/planner_intelligence.py](./utils/planner_intelligence.py): planning modes, reusable templates, pantry rescue, prep metadata, and leftover routing now sit on top of `meal_plans.notes` plus synced settings rather than introducing a separate planner store.
- Shopping optimisation was extended in [views/shopping_list.py](./views/shopping_list.py) and [utils/grocery_consolidation.py](./utils/grocery_consolidation.py): planner-generated lists now skip pantry overlaps, consolidate before insertion, and show a smarter summary for spend/aisle overlap.
- Nutrition coaching was added in [views/nutrition.py](./views/nutrition.py) and [utils/nutrition_coach.py](./utils/nutrition_coach.py), giving the Nutrition page a weekly coaching card without requiring extra cloud services.
- Recipe scaling and more visible quality surfacing were added in [views/recipes.py](./views/recipes.py) and [utils/recipe_scaling.py](./utils/recipe_scaling.py).
- Monitoring now exposes Dishy memory source summaries and a chat-memory clear action via [views/settings.py](./views/settings.py) and [utils/ai_memory.py](./utils/ai_memory.py).
- A post-merge boot crash was fixed in [utils/ai_memory.py](./utils/ai_memory.py): memory summary/corpus building now converts `sqlite3.Row` objects to plain dicts before using `.get(...)`, which keeps Monitoring and Dishy memory safe at startup.
- SQLite connection mode was hardened again in [models/database.py](./models/database.py): the shared connection now opens with `isolation_level=None` (autocommit) alongside WAL + 30s busy timeout. Reason: multiple in-process timers/workers can otherwise leave deferred write transactions open long enough to block Supabase sync with fresh `database is locked` errors.
- All new work in this pass was kept cross-platform. Future changes must preserve Windows compatibility as a hard requirement, not as a packaging afterthought.

## Current Runtime Architecture

The startup path is now intentionally simpler:

1. `DishBoard.py` is a thin bootstrap.
2. `DishBoard.py` sets certificate env vars and resolves resource paths.
3. `DishBoard.py` constructs `ApplicationController` from [utils/app_runtime.py](./utils/app_runtime.py).
4. `ApplicationController` creates the `QApplication`, loads theme/font/runtime defaults, opens the shared database, builds the top-level views, restores session state, starts runtime services, and launches the app.

The important architectural shift is that the app no longer depends on a large set of startup module globals in `DishBoard.py`.

The new central types are:
- `AppContext` in [utils/app_runtime.py](./utils/app_runtime.py)
- `ApplicationController` in [utils/app_runtime.py](./utils/app_runtime.py)

`AppContext` holds the live application objects:
- `app`
- `db`
- `root_stack`
- `login_view`
- `main_window`
- `onboarding_view`
- `sync_service`
- `workflow_engine`
- `app_tour`

`ApplicationController` now owns:
- startup defaults
- loading Supabase credentials from settings into env vars
- theme application
- view construction and signal wiring
- post-login service startup
- cloud sync service startup
- onboarding and app-tour routing
- session restore handling
- update check scheduling
- shutdown cleanup

This makes startup logic easier to reason about, easier to test, and less dependent on import order.

## Major Code Changes Made In This Refactor

### 1. Startup globals were replaced with an explicit runtime controller

Files:
- [DishBoard.py](./DishBoard.py)
- [utils/app_runtime.py](./utils/app_runtime.py)
- [main_window.py](./main_window.py)
- [utils/data_service.py](./utils/data_service.py)

What changed:
- `DishBoard.py` was reduced to a small bootstrap.
- Shared runtime state moved into `ApplicationController`.
- `MainWindow` now accepts an optional `db` argument so it can use the shared database instance explicitly.
- `utils.data_service` gained `set_db(db)` so the runtime can bind the shared database instance during bootstrap.

Why this matters:
- Fewer hidden dependencies.
- Cleaner lifecycle management.
- Less risk from import-time behaviour.
- Better future foundation for cross-platform work.

### 2. Database path resolution was made lazy instead of import-time

File:
- [models/database.py](./models/database.py)

What changed:
- Default database path resolution moved into `default_db_path()`.
- `Database.__init__` now accepts `path: str | None = None` and resolves lazily.

Why this matters:
- Importing the module no longer performs path resolution side effects.
- Test setup is cleaner.
- Packaging and startup are a little safer across platforms.

### 3. Large prompt text and version history were moved out of code

Files:
- [utils/assets.py](./utils/assets.py)
- [api/claude_ai.py](./api/claude_ai.py)
- [utils/version.py](./utils/version.py)
- [assets/prompts/dishy_system_prompt.txt](./assets/prompts/dishy_system_prompt.txt)
- [assets/metadata/version_history.json](./assets/metadata/version_history.json)

What changed:
- Added asset loaders for bundled text and JSON.
- Dishy's system prompt now lives in a text asset.
- Version history now lives in JSON instead of a huge Python constant file.

Why this matters:
- Easier to review and edit content separately from code.
- Smaller Python modules.
- Less merge pain.
- Cleaner packaging story because assets are explicit.

### 4. Sync connectivity checks no longer block the Qt thread

File:
- [utils/cloud_sync_service.py](./utils/cloud_sync_service.py)

What changed:
- The sync service used to run `is_online()` before dispatching background work.
- That check used a blocking network call and could happen on the UI thread.
- The connectivity preflight was moved into the worker functions used by sync and realtime pull.

Why this matters:
- Reduces UI hitching on slow or unstable networks.
- Especially helpful on Windows laptops and flaky Wi-Fi.
- Keeps the UI thread focused on UI work.

Important note:
- This was done by moving the connectivity check, not by changing sync semantics.
- If offline, the worker still fails quickly and the resilience/backoff logic still handles it.

### 5. Session persistence failures are now observable instead of mostly silent

Files:
- [auth/session_manager.py](./auth/session_manager.py)
- [views/settings_account.py](./views/settings_account.py)
- [views/settings.py](./views/settings.py)

What changed:
- `auth.session_manager` now logs warnings instead of silently swallowing most keyring failures.
- Session persistence now maintains a simple diagnostics snapshot via `get_session_diagnostics()`.
- The Account section in Settings now shows a session persistence status message via `_session_store_lbl`.

Why this matters:
- Keyring issues are common across platforms.
- Silent failure makes users think sync or login is random.
- There is now a visible signal when session restore/persistence is degraded.

Diagnostics states currently used:
- `available`
- `degraded`
- `network_unavailable`
- `invalid`
- `unknown`

### 6. Supabase client failures are logged more clearly

File:
- [auth/supabase_client.py](./auth/supabase_client.py)

What changed:
- Client construction and reachability failures now log warnings instead of disappearing.

Why this matters:
- Makes startup/auth/cloud-sync debugging more realistic on real machines.

### 7. Import-time singleton side effects were reduced

Files:
- [utils/search_clients.py](./utils/search_clients.py)
- [views/recipes.py](./views/recipes.py)
- [views/recipes_shared.py](./views/recipes_shared.py)

What changed:
- The recipe search UI no longer creates a module-level `GoogleSearchAPI()` instance during import.
- A lazy factory now lives in `utils.search_clients`.

Why this matters:
- Reduces work at import time.
- Keeps module imports lighter and more test-friendly.
- Makes it easier to reason about when network-capable clients are created.

### 8. Two very large UI files were partially split

Files:
- [views/settings.py](./views/settings.py)
- [views/settings_account.py](./views/settings_account.py)
- [views/recipes.py](./views/recipes.py)
- [views/recipes_shared.py](./views/recipes_shared.py)

What changed:
- The Account page section was extracted from `views/settings.py` into `views/settings_account.py`.
- Shared recipe helpers and dialogs were extracted from `views/recipes.py` into `views/recipes_shared.py`.

Why this matters:
- Safer future refactoring.
- Smaller files.
- Less cognitive load when editing settings/account behaviour or recipe helper UI.

Important note:
- These files were split conservatively to avoid behavioural changes.
- There is still more work to do if you want fully modular views later.

### 9. Windows packaging and local setup were hardened

Files:
- [build_windows.ps1](./build_windows.ps1)
- [scripts/pre_release_checks.py](./scripts/pre_release_checks.py)
- [tests/test_packaging_smoke.py](./tests/test_packaging_smoke.py)
- [.vscode/settings.json](./.vscode/settings.json)
- [.vscode/extensions.json](./.vscode/extensions.json)

What changed:
- The Windows build script now uses the project venv explicitly.
- It runs PyInstaller via `python -m PyInstaller`.
- The pre-release check output is ASCII-safe for Windows terminals.
- VS Code workspace settings recommend and point at the project interpreter.
- Packaging smoke tests verify the expected Windows build script behaviour and PyInstaller spec assets.

Why this matters:
- Better out-of-the-box behaviour on a fresh Windows machine.
- Less reliance on PATH state.
- Easier onboarding for the repo owner.

### 10. Minor shared safety fixes

Files:
- [api/dishy_tools.py](./api/dishy_tools.py)
- [utils/paths.py](./utils/paths.py)

What changed:
- Tool-level DB connections are closed more reliably in `api.dishy_tools`.
- `utils.paths` is a little more tolerant of a permission edge case seen in tests.

Why this matters:
- Slightly safer runtime behaviour.
- No intentional platform-specific behaviour change.

## New Files Added

These files were added in this refactor:

- [HANDOVER.md](./HANDOVER.md)
- [utils/app_runtime.py](./utils/app_runtime.py)
- [utils/assets.py](./utils/assets.py)
- [utils/search_clients.py](./utils/search_clients.py)
- [views/settings_account.py](./views/settings_account.py)
- [views/recipes_shared.py](./views/recipes_shared.py)
- [assets/prompts/dishy_system_prompt.txt](./assets/prompts/dishy_system_prompt.txt)
- [assets/metadata/version_history.json](./assets/metadata/version_history.json)
- [tests/test_gui_smoke.py](./tests/test_gui_smoke.py)
- [tests/test_packaging_smoke.py](./tests/test_packaging_smoke.py)

## Files That Future Assistants Should Read First

If you are an AI assistant or a new contributor, this is the fastest useful reading order:

1. [CONTEXT.md](./CONTEXT.md)
2. [HANDOVER.md](./HANDOVER.md)
3. [DishBoard.py](./DishBoard.py)
4. [utils/app_runtime.py](./utils/app_runtime.py)
5. [main_window.py](./main_window.py)
6. [models/database.py](./models/database.py)
7. [utils/cloud_sync_service.py](./utils/cloud_sync_service.py)
8. [auth/session_manager.py](./auth/session_manager.py)
9. [auth/supabase_client.py](./auth/supabase_client.py)
10. [views/settings.py](./views/settings.py)
11. [views/settings_account.py](./views/settings_account.py)
12. [views/recipes.py](./views/recipes.py)
13. [views/recipes_shared.py](./views/recipes_shared.py)

That order gives a future assistant the product context, the latest architectural context, the runtime entrypoint, the main window, the database shape, the sync/auth layers, and then the largest UI surfaces.

## How To Run The App

### Windows development

Run from the project root:

```powershell
.\.venv\Scripts\python.exe DishBoard.py
```

### Windows tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

### Windows pre-release checks

```powershell
.\.venv\Scripts\python.exe scripts\pre_release_checks.py
```

### Windows packaged build

```powershell
powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
```

### macOS development

```bash
python3 DishBoard.py
```

### macOS pre-release checks

```bash
./scripts/pre_release_checks.sh
```

### macOS packaged build

```bash
./build.sh
```

## Verification Completed During This Refactor

The following checks were run successfully on Windows after the refactor:

- full unittest suite
- GUI smoke tests
- packaging smoke tests
- `scripts/pre_release_checks.py`
- `build_windows.ps1`

At the end of this refactor, the test suite passed with 47 tests.

The Windows package build produced:
- `dist/DishBoard/`
- `dist/DishBoard-v0.66-windows.zip`

## Important Behavioural Notes

### The shared DB instance is now passed more explicitly

The runtime now creates the shared database earlier and binds it through `set_db(db)`. `MainWindow` can also accept the db directly. When adding new high-level services or windows, prefer explicit dependency flow over importing globals.

### Prompt and version edits are now asset edits, not code edits

If you want to change Dishy's system prompt, edit:
- [assets/prompts/dishy_system_prompt.txt](./assets/prompts/dishy_system_prompt.txt)

If you want to change release history or version metadata, edit:
- [assets/metadata/version_history.json](./assets/metadata/version_history.json)

Be careful to keep the packaging spec aligned with any new asset folders that must be bundled.

### Settings account UI now includes session persistence visibility

If a future assistant changes login, logout, session restore, or keyring behaviour, they should also check the Account page UI in Settings so the visible diagnostics still make sense.

### The sync service still uses the same resilience/backoff model

The threading change only moved the network preflight into the worker path. It did not redesign sync or realtime architecture. If future sync work is done, preserve the main-thread safety that this refactor introduced.

## Known Limitations And Suggested Next Steps

This refactor intentionally stopped short of a few larger jobs:

- `views/recipes.py` is still large even after extracting shared helpers.
- `views/settings.py` is still large even after extracting the account page.
- `models/database.py` still contains a lot of responsibility and would benefit from repository-style splitting later.
- `ApplicationController` is much better than the old globals, but it could eventually be broken into smaller services if the startup flow keeps growing.
- Some extracted modules may still carry broader imports than strictly necessary because the split prioritised safety over cleanup.

If more cleanup is planned, the safest order is:

1. continue splitting `views/recipes.py`
2. continue splitting `views/settings.py`
3. separate database repositories by domain
4. add more targeted controller or sync tests if architecture changes again

## Guidance For Future AI Assistants

If you are Codex, Claude Code, or another AI assistant:

- Read [CONTEXT.md](./CONTEXT.md) and then this file before proposing major structural changes.
- Do not undo the runtime-controller refactor unless you have a strong reason.
- Do not move blocking network checks back onto the UI thread.
- Do not re-inline the Dishy system prompt or version history into Python source.
- Preserve the macOS path and future iOS portability when making Windows improvements.
- When editing packaging, check both `build_windows.ps1` and `build.sh`.
- When editing assets, confirm PyInstaller still bundles what is needed.
- When editing auth/session restore, check both logs and the Settings Account diagnostics label.
- When editing top-level startup, test both app launch and at least the smoke suite.

If memory is compressed and you need a short mental model, use this:

DishBoard is a PySide6 desktop app with SQLite, Supabase auth/sync, Dishy AI integrations, and GitHub-release style packaging. Startup is now controlled by `ApplicationController`, large content blobs moved to assets, session persistence now exposes diagnostics, sync preflight checks run in background workers, and partial file splits were done to lower maintenance risk without changing product behaviour.

## Guidance For Future Human Developers

If you are continuing development manually:

- Prefer changing one area at a time and re-running the test suite after structural work.
- Keep cross-platform logic in Python and packaging logic in per-platform scripts.
- If a future feature requires OS-specific APIs, isolate that behind a helper or adapter.
- Update both [CONTEXT.md](./CONTEXT.md) and [HANDOVER.md](./HANDOVER.md) after meaningful architectural changes.

## Summary

This refactor did two things at once:
- it made DishBoard run cleanly on Windows
- it improved the shared codebase in ways that should help, not hurt, macOS and future iOS work

The most important long-term improvement is the move away from fragile startup globals toward an explicit runtime controller. The most important safety rule is still the same: do not break macOS in the name of Windows support.
