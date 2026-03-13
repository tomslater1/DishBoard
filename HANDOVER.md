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

## Highest-Priority Guardrail

DishBoard must continue to run correctly on macOS.

That is not optional.

Future iOS portability is also a real product goal, so platform-specific work should be isolated rather than baked into shared runtime assumptions. Windows support was added with that rule in mind. If a future change helps Windows but risks macOS behaviour or pushes shared code toward Windows-only patterns, stop and redesign it.

Practical interpretation:
- Prefer additive platform handling over changing shared logic for every platform.
- Keep Windows packaging and setup logic in Windows-specific scripts where possible.
- Do not rewrite shared UI, database, auth, sync, or assets around Windows-only path, shell, or filesystem assumptions.
- Before changing startup or packaging again, verify both the Windows path and the macOS path still make sense.

## What This Refactor Was Trying To Achieve

This round of work started as a Windows enablement pass, but the goal was not just "make it run on Windows once." The goal was to improve the codebase in ways that make the app easier to maintain across Windows and macOS without harming future portability.

The main themes were:
- remove fragile startup globals
- move blocking sync connectivity checks off the UI thread
- reduce silent failure paths around auth/session persistence
- externalize large content blobs that did not belong in Python source
- split some of the biggest view files without changing user-facing behaviour
- add smoke tests that protect packaging and basic Qt construction on Windows

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
