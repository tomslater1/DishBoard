"""
Claude (Anthropic) API client for DishBoard.

Uses: anthropic SDK  (pip install anthropic)
Model: claude-haiku-4-5-20251001
"""

import os
import logging
import json
from datetime import datetime
import anthropic

from utils.assets import load_text_asset

_SYSTEM_PROMPT_TEMPLATE = load_text_asset("assets/prompts/dishy_system_prompt.txt")


def _build_system_prompt() -> str:
    now = datetime.now()
    date_str = now.strftime("%A, %d %B %Y")   # e.g. "Monday, 09 March 2026"
    time_str = now.strftime("%H:%M")           # e.g. "14:35"
    return f"{_SYSTEM_PROMPT_TEMPLATE}\n\n## Current date and time\nToday is {date_str}. The current time is {time_str}."


class ClaudeAI:
    MODEL       = "claude-sonnet-4-6"   # all requests use Sonnet
    TOOLS_MODEL = "claude-sonnet-4-6"   # tool-use loop

    def __init__(self):
        self._client: anthropic.Anthropic | None = None
        self._log = logging.getLogger("dishboard.ai")
        self._nutrition_cache: dict[str, dict] = {}

    @staticmethod
    def _current_user_id() -> str:
        try:
            from auth.supabase_client import get_client as _get_sb

            sb = _get_sb()
            if not sb:
                return ""
            session = sb.auth.get_session()
            user = getattr(session, "user", None)
            if user and getattr(user, "id", None):
                return str(user.id)
            # Fallback for supabase-py response shapes
            s = getattr(session, "session", None)
            u2 = getattr(s, "user", None) if s else None
            if u2 and getattr(u2, "id", None):
                return str(u2.id)
        except Exception:
            pass
        return ""

    def _enforce_daily_limit(self) -> tuple[str, int]:
        """Check and increment local daily usage meter (hard block at configured limit)."""
        user_id = self._current_user_id()
        if not user_id:
            return "", 0

        db = None
        try:
            from models.database import Database
            from utils.ai_limits import can_make_request, record_attempt, record_block, utc_day_str
            from utils.feature_flags import FeatureFlagService
            from utils.telemetry import track_event

            db = Database()
            db.connect()

            flags = FeatureFlagService(db, user_id)
            if not flags.is_enabled("ai_daily_hard_limit", default=True):
                usage = record_attempt(db, user_id, blocked=False)
                return user_id, int(usage.get("request_count", 0) or 0)

            allowed, remaining, limit = can_make_request(db, user_id)
            if not allowed:
                record_block(db, user_id, day=utc_day_str())
                track_event(
                    "ai.request_blocked",
                    {"user_id": user_id, "daily_limit": limit, "remaining": 0},
                    user_id=user_id,
                )
                raise RuntimeError(
                    f"dishy_rate_limited: Daily AI request limit reached ({limit}/day)."
                )

            usage = record_attempt(db, user_id, blocked=False)
            track_event(
                "ai.request_started",
                {
                    "user_id": user_id,
                    "daily_limit": limit,
                    "remaining_after_start": max(0, remaining - 1),
                },
                user_id=user_id,
            )
            return user_id, int(usage.get("request_count", 0) or 0)
        except Exception:
            # Never fail user requests because metering telemetry had an issue.
            return user_id, 0
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass

    def _get_client(self) -> anthropic.Anthropic:
        # Always use the Supabase server-side proxy — no local API key ever used.
        # Proxy mode — build fresh each call so JWT is always current
        access_token: str | None = None

        # 1. Try gotrue in-memory session (handles auto-refresh)
        try:
            from auth.supabase_client import get_client as _get_sb
            sb = _get_sb()
            if sb:
                session = sb.auth.get_session()
                access_token = getattr(session, "access_token", None) or None
                if not access_token:
                    nested = getattr(session, "session", None)
                    access_token = getattr(nested, "access_token", None) if nested else None
        except Exception:
            pass

        # 2. Keychain fallback — gotrue may lose its in-memory state between
        #    app restarts or after a session refresh failure.  The keychain
        #    always holds the last-known tokens; we pass them to set_session()
        #    so gotrue can refresh if needed, then read back the (possibly new)
        #    access token.
        if not access_token:
            try:
                from auth.session_manager import load_session
                from auth.supabase_client import get_client as _get_sb2
                stored = load_session()
                if stored:
                    sb2 = _get_sb2()
                    if sb2:
                        resp = sb2.auth.set_session(
                            stored.get("access_token", ""),
                            stored.get("refresh_token", ""),
                        )
                        if resp and resp.session:
                            access_token = resp.session.access_token
                        elif stored.get("access_token"):
                            access_token = stored["access_token"]
            except Exception:
                pass

        if access_token:
            supabase_url = (os.environ.get("SUPABASE_URL", "") or "https://ixddtfprarxsgscwytro.supabase.co").rstrip("/")
            return anthropic.Anthropic(
                api_key="proxy",
                base_url=f"{supabase_url}/functions/v1/claude-proxy/",
                default_headers={"Authorization": f"Bearer {access_token}"},
            )

        # No session available — raise a clear, user-friendly error
        raise RuntimeError(
            "dishy_not_signed_in: Dishy couldn't connect. Please sign out and sign in again."
        )

    def _ask(self, user_message: str, history: list[dict] | None = None) -> str:
        user_id, _ = self._enforce_daily_limit()
        messages = list(history or [])
        messages.append({"role": "user", "content": user_message})
        try:
            response = self._get_client().messages.create(
                model=self.MODEL,
                max_tokens=1024,
                system=_build_system_prompt(),
                messages=messages,
            )
            try:
                from utils.telemetry import track_event

                track_event(
                    "ai.request_succeeded",
                    {"model": self.MODEL, "surface": "single_turn"},
                    user_id=user_id,
                )
            except Exception:
                pass
            return response.content[0].text
        except Exception as exc:
            try:
                from utils.telemetry import capture_exception, track_event

                track_event(
                    "ai.request_failed",
                    {"model": self.MODEL, "surface": "single_turn", "error": str(exc)[:200]},
                    user_id=user_id,
                )
                capture_exception(exc, context={"model": self.MODEL, "surface": "single_turn"}, user_id=user_id)
            except Exception:
                pass
            raise

    def _ask_fast_json(self, system_prompt: str, user_message: str, *, max_tokens: int = 700) -> str:
        """Low-latency JSON call with a tiny system prompt for structured tasks."""
        user_id, _ = self._enforce_daily_limit()
        try:
            response = self._get_client().messages.create(
                model=self.MODEL,
                max_tokens=max_tokens,
                temperature=0,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            try:
                from utils.telemetry import track_event

                track_event(
                    "ai.request_succeeded",
                    {"model": self.MODEL, "surface": "fast_json"},
                    user_id=user_id,
                )
            except Exception:
                pass

            chunks: list[str] = []
            for block in response.content:
                if hasattr(block, "type") and block.type == "text":
                    chunks.append(block.text)
            return "\n".join(chunks).strip()
        except Exception as exc:
            try:
                from utils.telemetry import capture_exception, track_event

                track_event(
                    "ai.request_failed",
                    {"model": self.MODEL, "surface": "fast_json", "error": str(exc)[:200]},
                    user_id=user_id,
                )
                capture_exception(exc, context={"model": self.MODEL, "surface": "fast_json"}, user_id=user_id)
            except Exception:
                pass
            raise

    def plan_week_structured(
        self,
        saved_recipes: list[str],
        dietary_prefs: str = "",
        week_label: str = "",
    ) -> dict:
        """Return a structured 7-day meal plan as a dict keyed by day name.

        Each value is a dict with keys "breakfast", "lunch", "dinner" mapping
        to a meal name string.  Prefers names from *saved_recipes* where sensible
        but may suggest new ideas too.

        Returns: {"Monday": {"breakfast": "...", "lunch": "...", "dinner": "..."}, ...}
        """
        recipe_list = ", ".join(saved_recipes) if saved_recipes else "none saved yet"
        prefs_str   = f" Dietary preferences: {dietary_prefs}." if dietary_prefs else ""
        week_str    = f" This is for the week of {week_label}." if week_label else ""

        prompt = (
            f"Create a balanced 7-day meal plan for Monday through Sunday.{week_str}{prefs_str}\n"
            f"The user has these saved recipes they could use: {recipe_list}.\n"
            "Reuse saved recipes where they fit naturally, but you can also suggest new ideas.\n"
            "Keep meals realistic, varied, and balanced across the week.\n\n"
            "Respond with ONLY a valid JSON object — no markdown, no prose, no code fences.\n"
            "Format:\n"
            '{"Monday":{"breakfast":"...","lunch":"...","dinner":"..."},'
            '"Tuesday":{"breakfast":"...","lunch":"...","dinner":"..."},'
            '"Wednesday":{"breakfast":"...","lunch":"...","dinner":"..."},'
            '"Thursday":{"breakfast":"...","lunch":"...","dinner":"..."},'
            '"Friday":{"breakfast":"...","lunch":"...","dinner":"..."},'
            '"Saturday":{"breakfast":"...","lunch":"...","dinner":"..."},'
            '"Sunday":{"breakfast":"...","lunch":"...","dinner":"..."}}'
        )
        import json as _json
        raw = self._ask(prompt)
        # Strip any accidental markdown fences
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return _json.loads(raw.strip())

    def chat(self, message: str, history: list[dict] | None = None) -> str:
        """Send a free-form message."""
        return self._ask(message, history)

    def chat_with_tools(
        self,
        user_message: str,
        tools: list,
        tool_handler,           # callable(name: str, input: dict) -> str
        history: list[dict] | None = None,
    ) -> str:
        """
        Agentic chat loop with Anthropic tool-use support.

        Uses TOOLS_MODEL (Sonnet) rather than the default Haiku — Haiku often
        ignores tools and responds in text instead of calling them.

        Sends user_message (with optional history) and runs the tool-use loop
        until Claude returns end_turn.  For each tool_use block Claude emits,
        tool_handler(name, input) is called synchronously and the result is
        fed back.  Returns the final plain-text assistant response.
        """
        user_id, _ = self._enforce_daily_limit()
        client   = self._get_client()
        messages = [{"role": h["role"], "content": h["content"]} for h in (history or [])]
        messages.append({"role": "user", "content": user_message})

        while True:
            try:
                response = client.messages.create(
                    model=self.TOOLS_MODEL,     # Sonnet — reliably calls tools
                    max_tokens=4096,
                    system=_build_system_prompt(),
                    tools=tools,
                    tool_choice={"type": "auto"},   # explicit: Claude may call 0+ tools
                    messages=messages,
                )
            except Exception as exc:
                try:
                    from utils.telemetry import capture_exception, track_event

                    track_event(
                        "ai.request_failed",
                        {"model": self.TOOLS_MODEL, "surface": "tools_turn", "error": str(exc)[:200]},
                        user_id=user_id,
                    )
                    capture_exception(
                        exc,
                        context={"model": self.TOOLS_MODEL, "surface": "tools_turn"},
                        user_id=user_id,
                    )
                except Exception:
                    pass
                raise

            text_parts: list[str] = []
            tool_calls:  list     = []
            for block in response.content:
                if not hasattr(block, "type"):
                    continue
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_calls.append(block)

            # Serialise the assistant turn back to plain dicts so the next
            # messages.create() call accepts them correctly.
            assistant_content = []
            for block in response.content:
                if not hasattr(block, "type"):
                    continue
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type":  "tool_use",
                        "id":    block.id,
                        "name":  block.name,
                        "input": block.input,
                    })
            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason == "end_turn" or not tool_calls:
                try:
                    from utils.telemetry import track_event

                    track_event(
                        "ai.request_succeeded",
                        {"model": self.TOOLS_MODEL, "surface": "tools_turn", "tool_calls": len(tool_calls)},
                        user_id=user_id,
                    )
                except Exception:
                    pass
                return "\n".join(text_parts)

            # Execute each tool and send results back
            tool_results = []
            for tc in tool_calls:
                result = tool_handler(tc.name, tc.input)
                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": tc.id,
                    "content":     str(result),
                })
            messages.append({"role": "user", "content": tool_results})

    def enrich_scraped_recipe(self, recipe: dict) -> dict:
        """Add DishBoard UI metadata to a raw scraped recipe.

        Returns a dict with keys: description, tags (list), icon, colour, servings (int).
        The caller should merge this into the recipe dict and add the 'Online' tag.
        """
        import json as _json
        title      = recipe.get("title", "Untitled")
        host       = recipe.get("host", "the web")
        total_time = recipe.get("total_time", 0)
        yields     = recipe.get("yields", "")
        ingredients = recipe.get("ingredients", [])
        instructions = recipe.get("instructions", [])

        ings_str  = "\n".join(f"- {i}" for i in ingredients[:20]) or "Not listed"
        inst_preview = instructions[0] if instructions else "Not available"

        prompt = (
            f"You are enriching a recipe scraped from {host} for DishBoard, a personal recipe manager app.\n\n"
            f"Title: {title}\n"
            f"Cook time: {total_time} minutes\n"
            f"Yield: {yields}\n"
            f"Ingredients:\n{ings_str}\n"
            f"First instruction: {inst_preview}\n\n"
            "Return ONLY valid JSON, no markdown, no code fences:\n"
            '{"description":"...","tags":["Dinner"],"icon":"fa5s.utensils","colour":"#ff6b35","servings":4}\n\n'
            "Rules:\n"
            "- description: 2–3 engaging sentences on taste, texture, and occasion. No waffle.\n"
            "- tags: exactly ONE meal type from [Breakfast, Lunch, Dinner, Snack, Dessert], "
            "plus up to 3 from: Vegetarian, Vegan, Gluten-Free, Dairy-Free, High-Protein, "
            "Low-Carb, Keto, Quick (< 30 min), One-Pot, Meal-Prep, Spicy, Healthy, "
            "Comfort Food, Budget-Friendly, Date Night, Kid-Friendly, BBQ, Baking\n"
            "- icon: pick the single best fit from: fa5s.utensils, fa5s.pizza-slice, fa5s.fish, "
            "fa5s.drumstick-bite, fa5s.hamburger, fa5s.leaf, fa5s.egg, fa5s.birthday-cake, "
            "fa5s.cookie, fa5s.fire, fa5s.pepper-hot, fa5s.bread-slice, fa5s.ice-cream, "
            "fa5s.blender, fa5s.lemon, fa5s.cheese, fa5s.bacon, fa5s.seedling, fa5s.carrot\n"
            "- colour: pick one hex from: #ff6b35, #ef4444, #f59e0b, #fbbf24, #34d399, "
            "#10b981, #4fc3f7, #60a5fa, #a78bfa, #f472b6, #fb7185\n"
            "- servings: integer estimate"
        )
        raw = self._ask(prompt)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return _json.loads(raw.strip())

    def daily_tip(self) -> str:
        """Return one short cooking or nutrition tip for today."""
        return self._ask(
            "Give me one short, practical cooking or nutrition tip. "
            "One or two sentences max. No bullet points, no intro phrase. "
            "Start with an action verb."
        )

    def analyze_recipe_nutrition(self, ingredients: list[str], servings: int = 1) -> dict:
        """Analyze nutrition for every ingredient in a recipe in a single API call.

        Takes a list of ingredient strings (with quantities, e.g. '200g chicken breast')
        and returns a breakdown per ingredient plus total and per-serving summaries.

        Returns:
            {
                "ingredients": [
                    {"name": str, "kcal": float, "protein_g": float,
                     "carbs_g": float, "fat_g": float, "fiber_g": float, "sugar_g": float},
                    ...
                ],
                "total":      {"kcal": float, "protein_g": float, ...},
                "per_serving": {"kcal": float, "protein_g": float, ...},
            }
        """
        if not ingredients:
            return {"ingredients": [], "total": {}, "per_serving": {}}
        servings = max(1, int(servings or 1))
        normalized = [" ".join(str(i or "").strip().split()) for i in ingredients if str(i or "").strip()]
        if not normalized:
            return {"ingredients": [], "total": {}, "per_serving": {}}

        cache_key = json.dumps({"ingredients": normalized, "servings": servings}, sort_keys=True)
        if cache_key in self._nutrition_cache:
            return json.loads(json.dumps(self._nutrition_cache[cache_key]))

        ing_list = "\n".join(f"- {ing}" for ing in normalized[:24])
        system = (
            "You are a nutrition estimation engine. Respond only with valid JSON. "
            "Never include markdown or extra prose."
        )
        prompt = (
            f"Recipe serving count: {servings}\n"
            f"Ingredients:\n{ing_list}\n\n"
            "Estimate macros for each ingredient using the stated quantity. "
            "Then compute TOTAL and PER_SERVING values.\n"
            "Output JSON exactly in this shape:\n"
            '{"ingredients":[{"name":"","kcal":0,"protein_g":0,"carbs_g":0,"fat_g":0,"fiber_g":0,"sugar_g":0}],'
            '"total":{"kcal":0,"protein_g":0,"carbs_g":0,"fat_g":0,"fiber_g":0,"sugar_g":0},'
            '"per_serving":{"kcal":0,"protein_g":0,"carbs_g":0,"fat_g":0,"fiber_g":0,"sugar_g":0}}'
        )
        fallback_prompt = (
            "Give approximate nutritional values for each ingredient listed below. "
            f"This recipe makes {servings} serving{'s' if servings != 1 else ''}.\n\n"
            f"Ingredients:\n{ing_list}\n\n"
            "Use the quantity stated in each ingredient string. "
            "Sum all ingredients for TOTAL values. "
            "Divide totals by the serving count for PER_SERVING values.\n\n"
            "Respond ONLY with valid JSON — no markdown, no code fences, no prose:\n"
            '{"ingredients":['
            '{"name":"...","kcal":0.0,"protein_g":0.0,"carbs_g":0.0,"fat_g":0.0,"fiber_g":0.0,"sugar_g":0.0}'
            '],'
            '"total":{"kcal":0.0,"protein_g":0.0,"carbs_g":0.0,"fat_g":0.0,"fiber_g":0.0,"sugar_g":0.0},'
            '"per_serving":{"kcal":0.0,"protein_g":0.0,"carbs_g":0.0,"fat_g":0.0,"fiber_g":0.0,"sugar_g":0.0}}'
        )

        def _extract_json_payload(raw: str) -> dict:
            def _is_payload_shape(obj: object) -> bool:
                if not isinstance(obj, dict):
                    return False
                return any(
                    key in obj
                    for key in ("ingredients", "total", "totals", "per_serving", "perServing")
                )

            txt = (raw or "").strip()
            if txt.startswith("```"):
                parts = txt.split("```")
                if len(parts) >= 2:
                    txt = parts[1]
                    if txt.startswith("json"):
                        txt = txt[4:]
                    txt = txt.strip()
            try:
                obj = json.loads(txt)
                if _is_payload_shape(obj):
                    return obj
            except Exception:
                pass

            # Fallback: scan mixed output and decode the first valid JSON object.
            decoder = json.JSONDecoder()
            for idx, ch in enumerate(txt):
                if ch != "{":
                    continue
                try:
                    obj, _end = decoder.raw_decode(txt[idx:])
                except Exception:
                    continue
                if _is_payload_shape(obj):
                    return obj
            raise ValueError("No valid JSON object in AI response")

        def _repair_json_payload(raw: str) -> dict:
            repair_system = (
                "You repair malformed JSON. Return only one valid JSON object. "
                "No markdown, no code fences, no explanation."
            )
            repair_prompt = (
                "The JSON below may be malformed. Fix it so it is valid JSON with this exact shape:\n"
                '{"ingredients":[{"name":"","kcal":0,"protein_g":0,"carbs_g":0,"fat_g":0,"fiber_g":0,"sugar_g":0}],'
                '"total":{"kcal":0,"protein_g":0,"carbs_g":0,"fat_g":0,"fiber_g":0,"sugar_g":0},'
                '"per_serving":{"kcal":0,"protein_g":0,"carbs_g":0,"fat_g":0,"fiber_g":0,"sugar_g":0}}\n\n'
                "Malformed JSON:\n"
                f"{(raw or '')[:10000]}"
            )
            repaired = self._ask_fast_json(repair_system, repair_prompt, max_tokens=1200)
            return _extract_json_payload(repaired)

        def _to_float(v) -> float:
            try:
                return float(v or 0)
            except Exception:
                return 0.0

        def _normalise_payload(data: dict) -> dict:
            ingredients_rows = data.get("ingredients", [])
            if not isinstance(ingredients_rows, list):
                ingredients_rows = []
            norm_rows = []
            for idx, row in enumerate(ingredients_rows):
                if not isinstance(row, dict):
                    continue
                norm_rows.append({
                    "name": str(row.get("name") or normalized[idx] if idx < len(normalized) else "Ingredient"),
                    "kcal": _to_float(row.get("kcal")),
                    "protein_g": _to_float(row.get("protein_g", row.get("protein"))),
                    "carbs_g": _to_float(row.get("carbs_g", row.get("carbs"))),
                    "fat_g": _to_float(row.get("fat_g", row.get("fat"))),
                    "fiber_g": _to_float(row.get("fiber_g", row.get("fiber"))),
                    "sugar_g": _to_float(row.get("sugar_g", row.get("sugar"))),
                })

            total_raw = data.get("total") or data.get("totals") or {}
            per_raw = data.get("per_serving") or data.get("perServing") or {}
            if not isinstance(total_raw, dict):
                total_raw = {}
            if not isinstance(per_raw, dict):
                per_raw = {}

            total = {
                "kcal": _to_float(total_raw.get("kcal")),
                "protein_g": _to_float(total_raw.get("protein_g", total_raw.get("protein"))),
                "carbs_g": _to_float(total_raw.get("carbs_g", total_raw.get("carbs"))),
                "fat_g": _to_float(total_raw.get("fat_g", total_raw.get("fat"))),
                "fiber_g": _to_float(total_raw.get("fiber_g", total_raw.get("fiber"))),
                "sugar_g": _to_float(total_raw.get("sugar_g", total_raw.get("sugar"))),
            }
            if not total["kcal"] and norm_rows:
                for row in norm_rows:
                    total["kcal"] += row["kcal"]
                    total["protein_g"] += row["protein_g"]
                    total["carbs_g"] += row["carbs_g"]
                    total["fat_g"] += row["fat_g"]
                    total["fiber_g"] += row["fiber_g"]
                    total["sugar_g"] += row["sugar_g"]

            per_serving = {
                "kcal": _to_float(per_raw.get("kcal")),
                "protein_g": _to_float(per_raw.get("protein_g", per_raw.get("protein"))),
                "carbs_g": _to_float(per_raw.get("carbs_g", per_raw.get("carbs"))),
                "fat_g": _to_float(per_raw.get("fat_g", per_raw.get("fat"))),
                "fiber_g": _to_float(per_raw.get("fiber_g", per_raw.get("fiber"))),
                "sugar_g": _to_float(per_raw.get("sugar_g", per_raw.get("sugar"))),
            }
            if not per_serving["kcal"]:
                per_serving = {
                    "kcal": total["kcal"] / max(1, servings),
                    "protein_g": total["protein_g"] / max(1, servings),
                    "carbs_g": total["carbs_g"] / max(1, servings),
                    "fat_g": total["fat_g"] / max(1, servings),
                    "fiber_g": total["fiber_g"] / max(1, servings),
                    "sugar_g": total["sugar_g"] / max(1, servings),
                }

            return {
                "ingredients": norm_rows,
                "total": total,
                "per_serving": per_serving,
            }

        parsed: dict | None = None
        raw_candidates: list[str] = []

        try:
            raw_primary = self._ask_fast_json(system, prompt, max_tokens=900)
            raw_candidates.append(raw_primary)
            parsed = _extract_json_payload(raw_primary)
        except Exception:
            parsed = None

        if parsed is None:
            try:
                raw_fallback = self._ask(fallback_prompt)
                raw_candidates.append(raw_fallback)
                parsed = _extract_json_payload(raw_fallback)
            except Exception:
                parsed = None

        if parsed is None:
            for candidate in reversed(raw_candidates):
                if not candidate:
                    continue
                try:
                    parsed = _repair_json_payload(candidate)
                    break
                except Exception:
                    continue

        if parsed is None:
            raise RuntimeError(
                "Dishy returned invalid nutrition JSON multiple times. Please retry."
            )

        data = _normalise_payload(parsed)
        self._nutrition_cache[cache_key] = data
        return json.loads(json.dumps(data))

    def calculate_macros_from_calories(self, calories: float, dietary_prefs: str = "") -> dict:
        """Return protein_g, carbs_g, fat_g that sum to the given calorie target.

        Adjusts standard ratios (25/50/25) based on dietary preferences
        (e.g. 'high protein', 'keto', 'vegan'). Fiber and sugar are independent
        health targets and are NOT included in this calculation.

        Returns:
            {
                "protein_g": float,
                "carbs_g":   float,
                "fat_g":     float,
                "note":      str,   # explains the ratios used
            }
        """
        prefs_str = f" Dietary preferences: {dietary_prefs}." if dietary_prefs.strip() else ""
        prompt = (
            f"A person has set a daily calorie goal of {calories:.0f} kcal.{prefs_str}\n\n"
            "Calculate appropriate daily macro targets (protein, carbs, fat) that add up to "
            "this calorie goal. Use these standard ratios as your starting point:\n"
            "- Protein: 25% of calories (4 kcal per gram)\n"
            "- Carbs:   50% of calories (4 kcal per gram)\n"
            "- Fat:     25% of calories (9 kcal per gram)\n\n"
            "Adjust the ratios if dietary preferences suggest otherwise "
            "(e.g. high-protein → 35% protein; keto → 70% fat, 25% protein, 5% carbs; "
            "low-carb → 40% fat, 30% protein, 30% carbs). "
            "The gram values must mathematically sum to the calorie target. Round to whole grams.\n\n"
            "Respond with ONLY valid JSON — no markdown, no code fences, no prose:\n"
            '{"protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0, "note": "..."}'
        )
        try:
            raw = self._ask_fast_json(
                "Return valid JSON only. No markdown.",
                prompt,
                max_tokens=350,
            )
        except Exception:
            raw = self._ask(prompt)
        data = self._parse_json_dict(raw)
        return {
            "protein_g": max(1.0, float(data.get("protein_g", 1.0) or 1.0)),
            "carbs_g": max(1.0, float(data.get("carbs_g", 1.0) or 1.0)),
            "fat_g": max(1.0, float(data.get("fat_g", 1.0) or 1.0)),
            "note": str(data.get("note", "") or ""),
        }

    @staticmethod
    def _parse_json_dict(raw: str) -> dict:
        """Best-effort extraction of a JSON object from model output."""
        txt = (raw or "").strip()
        if txt.startswith("```"):
            parts = txt.split("```")
            if len(parts) >= 2:
                txt = parts[1]
                if txt.startswith("json"):
                    txt = txt[4:]
                txt = txt.strip()
        try:
            parsed = json.loads(txt)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        decoder = json.JSONDecoder()
        for idx, ch in enumerate(txt):
            if ch != "{":
                continue
            try:
                parsed, _end = decoder.raw_decode(txt[idx:])
            except Exception:
                continue
            if isinstance(parsed, dict):
                return parsed
        raise ValueError("No valid JSON object in AI response")

    def recalculate_macro_goals(
        self,
        anchor_key: str,
        anchor_value: float,
        current_goals: dict | None = None,
        dietary_prefs: str = "",
    ) -> dict:
        """Dishy-powered rebalance of kcal/protein/carbs/fat from any single anchor value."""
        allowed = {"kcal", "protein_g", "carbs_g", "fat_g"}
        anchor = str(anchor_key or "").strip().lower()
        if anchor not in allowed:
            raise ValueError(f"Unsupported macro anchor: {anchor_key}")

        goals = dict(current_goals or {})
        try:
            anchor_val = max(1.0, float(anchor_value or 1.0))
        except Exception:
            anchor_val = 1.0
        goals[anchor] = anchor_val

        prefs_str = f" Dietary preferences: {dietary_prefs}." if str(dietary_prefs or "").strip() else ""
        prompt = (
            f"A user is editing nutrition goals in DishBoard.{prefs_str}\n\n"
            f"Current goals: kcal={float(goals.get('kcal', 2000) or 2000):.0f}, "
            f"protein_g={float(goals.get('protein_g', 50) or 50):.0f}, "
            f"carbs_g={float(goals.get('carbs_g', 260) or 260):.0f}, "
            f"fat_g={float(goals.get('fat_g', 65) or 65):.0f}.\n\n"
            f"Anchor goal: {anchor}={anchor_val:.0f}. Keep this anchor exact.\n\n"
            "Rebalance ALL goals (kcal, protein_g, carbs_g, fat_g) around that anchor with practical, "
            "healthy targets for the given preferences.\n"
            "Rules:\n"
            "- Keep the anchor value unchanged.\n"
            "- Return numeric values only.\n"
            "- Keep protein/carbs/fat above 0.\n"
            "- kcal should approximately match macro calories (4*protein + 4*carbs + 9*fat).\n\n"
            "Respond with ONLY valid JSON:\n"
            '{"kcal":0.0,"protein_g":0.0,"carbs_g":0.0,"fat_g":0.0,"note":"..."}'
        )
        try:
            raw = self._ask_fast_json(
                "You are a macro-goal calculator. Return valid JSON only.",
                prompt,
                max_tokens=380,
            )
        except Exception:
            raw = self._ask(prompt)

        data = self._parse_json_dict(raw)
        protein = max(1.0, float(data.get("protein_g", goals.get("protein_g", 50)) or 1.0))
        carbs = max(1.0, float(data.get("carbs_g", goals.get("carbs_g", 260)) or 1.0))
        fat = max(1.0, float(data.get("fat_g", goals.get("fat_g", 65)) or 1.0))
        kcal = max(1.0, float(data.get("kcal", goals.get("kcal", 2000)) or 1.0))

        # Enforce the user's edited anchor value exactly.
        if anchor == "protein_g":
            protein = anchor_val
        elif anchor == "carbs_g":
            carbs = anchor_val
        elif anchor == "fat_g":
            fat = anchor_val
        elif anchor == "kcal":
            kcal = anchor_val

        macro_kcal = (protein * 4.0) + (carbs * 4.0) + (fat * 9.0)
        if anchor != "kcal":
            kcal = macro_kcal
        elif macro_kcal > 0:
            # Keep kcal fixed; gently scale carbs/fat/protein to close energy gap.
            scale = kcal / macro_kcal
            protein = max(1.0, protein * scale)
            carbs = max(1.0, carbs * scale)
            fat = max(1.0, fat * scale)

        return {
            "kcal": kcal,
            "protein_g": protein,
            "carbs_g": carbs,
            "fat_g": fat,
            "note": str(data.get("note", "") or ""),
        }

    @staticmethod
    def _fallback_goals_from_body_metrics(
        height_cm: float,
        weight_kg: float,
        dietary_prefs: str = "",
    ) -> dict:
        """Deterministic fallback when AI output is unavailable."""
        h = max(120.0, min(230.0, float(height_cm or 170.0)))
        w = max(35.0, min(260.0, float(weight_kg or 70.0)))
        prefs = str(dietary_prefs or "").lower()

        bmi = w / ((h / 100.0) ** 2)
        if bmi >= 30:
            kcal_factor = 24.0
        elif bmi >= 27:
            kcal_factor = 26.0
        elif bmi >= 23:
            kcal_factor = 28.0
        else:
            kcal_factor = 30.0
        kcal = max(1400.0, min(4200.0, w * kcal_factor))

        protein_per_kg = 1.2
        if "muscle" in prefs or "high protein" in prefs or "high-protein" in prefs:
            protein_per_kg = 1.6
        protein_g = max(60.0, min(260.0, w * protein_per_kg))

        if "keto" in prefs:
            fat_ratio = 0.68
            carb_ratio = 0.07
        elif "low carb" in prefs or "low-carb" in prefs:
            fat_ratio = 0.40
            carb_ratio = 0.30
        else:
            fat_ratio = 0.28
            carb_ratio = 0.46

        fat_g = max(35.0, (kcal * fat_ratio) / 9.0)
        carbs_g = max(50.0, (kcal * carb_ratio) / 4.0)

        # Bring calories back in line with chosen macros.
        kcal = (protein_g * 4.0) + (carbs_g * 4.0) + (fat_g * 9.0)
        fiber_g = max(25.0, (kcal / 1000.0) * 14.0)
        sugar_g = min(55.0, max(20.0, (kcal * 0.10) / 4.0))

        return {
            "kcal": kcal,
            "protein_g": protein_g,
            "carbs_g": carbs_g,
            "fat_g": fat_g,
            "fiber_g": fiber_g,
            "sugar_g": sugar_g,
            "note": "Calculated from height, weight, and dietary preferences.",
        }

    def recommend_goals_from_body_metrics(
        self,
        *,
        primary_height_cm: float,
        primary_weight_kg: float,
        dietary_prefs: str = "",
        secondary_profile: dict | None = None,
    ) -> dict:
        """Recommend daily goals from body metrics. Supports a shared 2-person target."""
        p_h = max(120.0, min(230.0, float(primary_height_cm or 0.0)))
        p_w = max(35.0, min(260.0, float(primary_weight_kg or 0.0)))
        prefs = str(dietary_prefs or "").strip()
        secondary = dict(secondary_profile or {})

        fallback_primary = self._fallback_goals_from_body_metrics(p_h, p_w, prefs)

        has_secondary = bool(
            secondary
            and secondary.get("height_cm")
            and secondary.get("weight_kg")
        )
        fallback_secondary = None
        if has_secondary:
            s_h = max(120.0, min(230.0, float(secondary.get("height_cm") or 0.0)))
            s_w = max(35.0, min(260.0, float(secondary.get("weight_kg") or 0.0)))
            fallback_secondary = self._fallback_goals_from_body_metrics(s_h, s_w, prefs)

        if has_secondary and fallback_secondary:
            fallback_result = {
                "kcal": (fallback_primary["kcal"] + fallback_secondary["kcal"]) / 2.0,
                "protein_g": (fallback_primary["protein_g"] + fallback_secondary["protein_g"]) / 2.0,
                "carbs_g": (fallback_primary["carbs_g"] + fallback_secondary["carbs_g"]) / 2.0,
                "fat_g": (fallback_primary["fat_g"] + fallback_secondary["fat_g"]) / 2.0,
                "fiber_g": (fallback_primary["fiber_g"] + fallback_secondary["fiber_g"]) / 2.0,
                "sugar_g": (fallback_primary["sugar_g"] + fallback_secondary["sugar_g"]) / 2.0,
                "note": "Shared target averaged from both users' body metrics.",
            }
        else:
            fallback_result = dict(fallback_primary)

        prefs_str = f"Dietary preferences: {prefs}." if prefs else "Dietary preferences: none specified."
        if has_secondary:
            s_name = str(secondary.get("name") or "User 2").strip() or "User 2"
            prompt = (
                "You are setting nutrition goals for a shared household with two people.\n"
                f"{prefs_str}\n\n"
                f"User 1: height={p_h:.0f} cm, weight={p_w:.1f} kg.\n"
                f"{s_name}: height={float(secondary.get('height_cm')):.0f} cm, "
                f"weight={float(secondary.get('weight_kg')):.1f} kg.\n\n"
                "Return ONE shared daily target both users can reasonably follow together. "
                "Use a practical middle ground between both users.\n"
                "Output ONLY valid JSON:\n"
                '{"kcal":0.0,"protein_g":0.0,"carbs_g":0.0,"fat_g":0.0,"fiber_g":0.0,"sugar_g":0.0,"note":"..."}'
            )
        else:
            prompt = (
                "You are setting nutrition goals for one person.\n"
                f"{prefs_str}\n\n"
                f"User: height={p_h:.0f} cm, weight={p_w:.1f} kg.\n\n"
                "Return practical daily targets for calories, protein, carbs, fat, fiber, and sugar.\n"
                "Output ONLY valid JSON:\n"
                '{"kcal":0.0,"protein_g":0.0,"carbs_g":0.0,"fat_g":0.0,"fiber_g":0.0,"sugar_g":0.0,"note":"..."}'
            )

        try:
            raw = self._ask_fast_json(
                "You are a nutrition goal calculator. Return valid JSON only.",
                prompt,
                max_tokens=420,
            )
            data = self._parse_json_dict(raw)
            result = {
                "kcal": max(1.0, float(data.get("kcal", fallback_result["kcal"]) or fallback_result["kcal"])),
                "protein_g": max(1.0, float(data.get("protein_g", fallback_result["protein_g"]) or fallback_result["protein_g"])),
                "carbs_g": max(1.0, float(data.get("carbs_g", fallback_result["carbs_g"]) or fallback_result["carbs_g"])),
                "fat_g": max(1.0, float(data.get("fat_g", fallback_result["fat_g"]) or fallback_result["fat_g"])),
                "fiber_g": max(1.0, float(data.get("fiber_g", fallback_result["fiber_g"]) or fallback_result["fiber_g"])),
                "sugar_g": max(1.0, float(data.get("sugar_g", fallback_result["sugar_g"]) or fallback_result["sugar_g"])),
                "note": str(data.get("note", "") or fallback_result.get("note", "")),
            }
            return result
        except Exception:
            return fallback_result

    def lookup_nutrition(self, query: str) -> dict:
        """Return macro estimates for any food query as a dict.

        The query can be a food name, ingredient, dish, or quantity
        (e.g. "100g chicken breast", "a bowl of oats", "banana").

        Returns:
            {
                "food_name": str,      # tidy display name
                "serving":   str,      # e.g. "100 g" or "1 medium"
                "kcal":      float,
                "protein_g": float,
                "carbs_g":   float,
                "fat_g":     float,
                "fiber_g":   float,
                "sugar_g":   float,
                "note":      str,      # optional caveat / source note
            }
        """
        import json as _json
        prompt = (
            f"Give me the approximate nutritional values for: {query}\n\n"
            "Use your best knowledge — real-world averages or USDA-style values are fine.\n"
            "If a quantity is not specified, assume a typical single serving.\n\n"
            "Respond with ONLY a valid JSON object — no markdown, no code fences, no prose.\n"
            "Format exactly:\n"
            '{"food_name":"...","serving":"...","kcal":0.0,"protein_g":0.0,'
            '"carbs_g":0.0,"fat_g":0.0,"fiber_g":0.0,"sugar_g":0.0,"note":"..."}'
        )
        raw = self._ask(prompt)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return _json.loads(raw.strip())
