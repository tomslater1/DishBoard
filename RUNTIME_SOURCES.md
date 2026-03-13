# DishBoard Runtime Source Of Truth

Current runtime data/services are:

- Local state: `models/database.py` (SQLite in app data dir)
- Shared UI DB handle: `utils/data_service.py`
- Cloud sync engine: `auth/cloud_sync.py`
- Background sync/realtime orchestrator: `utils/cloud_sync_service.py`
- AI execution + tool writes: `api/dishy_tools.py` + `api/claude_ai.py`
- Nutrition UI semantics: `views/nutrition.py`
  - Planned intake: meal plan + recipe nutrition
  - Consumed intake: `nutrition_logs`

Legacy path:

- `utils/nutrition_sync.py` is deprecated and not used in startup/runtime wiring.

