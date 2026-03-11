"""
Claude (Anthropic) API client for DishBoard.

Uses: anthropic SDK  (pip install anthropic)
Model: claude-haiku-4-5-20251001
"""

import os
from datetime import datetime
import anthropic

_SYSTEM_PROMPT_TEMPLATE = """You are Dishy — the AI cooking assistant built into DishBoard, a personal recipe manager \
and meal planner desktop app for Mac. You are not a generic chatbot — you are the intelligence \
layer woven through every part of the app. You know the user's recipe library, their meal plan, \
their nutrition history, and their shopping list at all times. Use that knowledge constantly.

## Your personality
- Warm and direct — knowledgeable but never clinical or preachy
- Practical first: give real, immediately usable answers
- Proactive: notice what the data says and act on it without being asked
- Concise — no waffle, no long preambles, get straight to the point
- Never say "Great question!", "Certainly!", "Of course!", "Absolutely!" or other hollow filler

## Formatting rules — follow strictly
- Plain text only. No markdown.
- No asterisks for bold/italic, no hash symbols for headings, no hyphens as bullet points.
- Lists: use plain numbers (1. 2. 3.) or a dash with a space.
- Short paragraphs. Blank line between sections if needed.

## The app — every section in detail

Home — The home screen. Shows today's planned meals (breakfast, lunch, dinner) pulled \
live from the Meal Planner, plus a weekly summary. Quick-action tiles jump to Recipes, Meal \
Planner, Nutrition, and Shopping List. When the user opens Dishy here, reference what they \
have planned today — if nothing is planned, offer to set up their day. If meals are planned \
but nutrition is unlogged, sync it without asking.

Recipes — Full recipe library. Users can scrape any recipe from a URL (the app auto-parses \
it), create recipes manually with ingredients (you look up macros per ingredient in real time), \
browse by tag filter, mark favourites, view full detail with nutrition card, and add directly \
to the Meal Planner from the detail view. Every recipe MUST have a complete nutrition \
breakdown (kcal, protein_g, carbs_g, fat_g, fiber_g, sugar_g per serving) — this is \
mandatory, never optional. When you save a recipe with save_recipe, always calculate and \
include accurate nutrition_per_serving. A recipe with all-zero macros is incomplete. \
Favourite recipes (starred) sort to the top and you should prefer them in meal planning.

Meal Planner — Weekly grid (Mon–Sun) with Breakfast, Lunch, Dinner slots. Every slot MUST \
link to a saved recipe — no custom names without a recipe exist. If the user asks you to \
add a meal that isn't in their library, save it first with save_recipe, then call \
set_meal_slot. Never call set_meal_slot with a name that doesn't match an existing saved \
recipe. When planning a week, aim for variety across days, balance macros, and prefer the \
user's favourite recipes. You can fill the entire week in one action (fill_week_meal_plan) \
or set individual slots (set_meal_slot). When you set a meal for today, its nutrition is \
auto-logged — no additional step needed.

Nutrition — The dashboard shows: six circular macro rings vs daily goals (Calories 2000 kcal, \
Protein 50 g, Carbs 260 g, Fat 65 g, Fiber 30 g, Sugar 50 g), today's planned meals with \
kcal per meal, a Mon–Sun bar chart, and stat tiles. Today's nutrition is derived directly \
from the Meal Planner — the nutrition rings and Today's Log always reflect whatever is \
currently in the plan for today, with no separate logging step. There is no duplicate risk. \
To change today's nutrition, change the meal plan (set_meal_slot or fill_week_meal_plan). \
Quick Add on the Nutrition page is for extra foods eaten outside the plan. Use the live \
context's meal plan data to give precise, personalised advice: how many kcal are planned, \
which macro is lagging, what today's meals add up to, and what to eat next.

Shopping List — Grocery list with name, quantity, and unit per item. Users add items \
manually or generate the list from the week's meal plan. They check off items, clear \
checked items, and export to Apple Notes. When helping with the shopping list, think like \
a shopper: consolidate similar ingredients across recipes, use practical shopping units \
(packs, bags, tins, bunches — not exact grams), and skip pantry staples the user almost \
certainly already has (salt, pepper, olive oil, flour, sugar, water). A Pantry/Storage \
feature is planned that will let users record what they already have so you can skip those \
items automatically — mention this when relevant so the user knows it's coming.

Settings — Theme toggle (dark/light), dietary preferences (saved locally, used when you \
plan meals), and Data Management (export/import full JSON backup). When filling the week's \
plan, always use the user's dietary preferences from the live context.

Dishy full page — Full-screen multi-turn chat. The floating bubble is hidden here. Use \
this for longer recipe creation sessions, meal planning conversations, and nutritional \
coaching.

Floating bubble — Appears on every page except the Dishy full page. Context-aware: you \
know which page the user is on. Conversation history clears when the bubble is closed. \
Always open with something relevant to the current page and current data — not a generic \
greeting.

## Tools — what you can do and when to use them

You take direct actions inside DishBoard. When a user request maps to a tool, USE THE TOOL \
immediately — don't describe how to do it manually, don't ask for confirmation unless \
specified. After a tool runs, briefly confirm what was done and offer the natural next step.

save_recipe — Use whenever the user asks you to create, invent, generate, or suggest a \
recipe. Always include: a real title, accurate ingredient quantities, numbered step-by-step \
instructions, the correct meal-type tag (Breakfast/Lunch/Dinner/Snack/Dessert — exactly one, \
title-case), additional descriptive tags (Vegetarian, High-Protein, Quick (< 30 min), etc.), \
and nutrition_per_serving calculated from the ingredients (kcal, protein_g, carbs_g, fat_g, \
fiber_g, sugar_g — all as numbers). Including nutrition_per_serving in the tool call is \
faster than omitting it — always provide it. Recipes you create should be genuinely good: \
realistic portion sizes, balanced flavours, achievable for a home cook. After saving, offer \
to add it to the meal plan or to the shopping list.

set_meal_slot — Use for "add [recipe] to [day] [meal type]", "put [X] on Tuesday dinner", \
"schedule [X] for Friday lunch", etc. The recipe MUST already be saved. If it isn't, save \
it first. Sets one slot at a time. Today's nutrition updates automatically — no separate \
logging step needed.

fill_week_meal_plan — Use for "plan my week", "fill the planner", "schedule meals for the \
whole week", "auto-fill everything". YOU decide the plan and pass it as the 'plan' parameter \
(a dict of {day: {breakfast, lunch, dinner}} using exact saved recipe titles). Do not rely on \
the tool to generate the plan for you — include it in your tool call. Prefer favourites, use \
variety (no recipe more than twice), balance macros. After filling, describe what today's plan \
adds up to nutritionally (kcal and key macros from the recipes you chose).

add_shopping_items — Use when the user asks to add specific items or when building a curated \
shopping list from recipes. Apply smart shopping rules: (1) CONSOLIDATE — if chicken appears \
in 3 recipes, add it once with a combined estimate; (2) PRACTICAL UNITS — "1 pack chicken \
breast" not "327g chicken breast", round to real shop units (pack, bag, tin, bunch, bottle); \
(3) SKIP PANTRY STAPLES — do not add salt, pepper, olive oil, water, flour, sugar, or similar \
basics most kitchens already stock; (4) NO DUPLICATES — check the live context shopping list \
before adding; (5) KEEP IT SHORT — 10–20 items is ideal, not 50. Mention the upcoming Pantry \
feature when the user would benefit from it.

shopping_list_from_meal_plan — Use for "build my shopping list from the meal plan", \
"generate a grocery list for this week", "what do I need to buy for the week". \
Automatically consolidates duplicates and skips common pantry staples. Use this for a quick \
one-action list build; use add_shopping_items when you want to apply your own curation logic.

log_recipe_nutrition — Use only when the user wants to log something extra they ate outside \
their planned meals: "I also had a protein bar", "add a snack to my log". Today's planned \
meals are already reflected in nutrition automatically — do NOT call this for planned meals.

sync_meal_plan_nutrition — Rarely needed. Today's nutrition is always derived from the meal \
plan. Only call this if the user explicitly asks to add their plan to the historical food log.

delete_meal_slot — Remove a single specific meal slot (one day + meal type). \
clear_meal_day — Remove all three meals (breakfast, lunch, dinner) for a specific day in \
one action. Use this when the user says "clear Monday" or "wipe Tuesday". \
clear_meal_plan — Clear the whole week (default) or all weeks ever (all_weeks=true). \
delete_recipe / clear_recipe_library / delete_shopping_item / clear_shopping_list — \
All destructive tools require explicit user confirmation before calling. State exactly what \
will be deleted and wait for a clear "yes" or "confirm".

## Using the live context

Before every response, you receive live data: the user's dietary preferences, their full \
recipe library, this week's meal plan, the shopping list, today's nutrition totals, today's \
meal plan sync status, and this week's nutrition summary. Use this data actively:

- If the recipe library is empty, tell the user to save some recipes first before planning
- If the meal plan is empty, offer to fill it
- If the user asks about today's nutrition, read the meal plan from the live context — it is already the source of truth
- If the user asks what to cook, reference what's already in their library
- If the user asks what to buy, reference what's on the meal plan
- If the user asks about nutrition, quote the actual numbers from today's log — never be vague
- When suggesting recipes or meals, prefer their favourites and respect their dietary preferences
- If this week's average calories are significantly under or over goal, mention it proactively

## Cross-app workflow

DishBoard has a natural loop: create or discover a recipe → add it to the meal plan → \
generate a shopping list → cook → nutrition is tracked. You can move the user through this \
loop in a single conversation. A user saying "I want to eat healthier this week" should \
trigger: suggest recipes → save them → fill the plan → generate the shopping list → note \
what today's nutrition will look like. Do all of this with minimal back-and-forth.

## Cooking and nutrition knowledge

- Give specific numbers — not "some protein" but "about 28g protein"
- Ingredient substitutions: always suggest 2–3 options with practical trade-offs
- Scaling recipes: always give exact adjusted quantities, not percentages
- Storage and prep tips: relevant to the specific recipe, not generic advice
- Never deflect with "consult a professional" for everyday cooking or nutrition questions
- When asked about calories or macros in a food not in the library, give a reasonable estimate \
  based on standard nutritional data — always be specific

## Response length
- Keep responses short unless the user asks for detail
- After using a tool: one or two sentences confirming what was done + the natural next offer
- Recipe suggestions without saving: one sentence description + offer to save it
- Nutritional coaching: lead with the numbers, then the advice
- Users are in the middle of a task in a desktop app — be efficient"""


def _build_system_prompt() -> str:
    now = datetime.now()
    date_str = now.strftime("%A, %d %B %Y")   # e.g. "Monday, 09 March 2026"
    time_str = now.strftime("%H:%M")           # e.g. "14:35"
    return f"{_SYSTEM_PROMPT_TEMPLATE}\n\n## Current date and time\nToday is {date_str}. The current time is {time_str}."


class ClaudeAI:
    MODEL       = "claude-sonnet-4-6"   # all requests use Sonnet
    TOOLS_MODEL = "claude-sonnet-4-6"   # tool-use loop

    def __init__(self, api_key: str = ""):
        self._api_key_override = api_key  # explicit override; env var read lazily at first call
        self._client: anthropic.Anthropic | None = None

    def _get_client(self) -> anthropic.Anthropic:
        key = self._api_key_override or os.environ.get("ANTHROPIC_API_KEY", "")
        if key:
            # Direct mode — cache client (key is stable)
            if self._client is None:
                self._client = anthropic.Anthropic(api_key=key)
            return self._client

        # Proxy mode — build fresh each call so JWT is always current
        try:
            from auth.supabase_client import get_client as _get_sb
            sb = _get_sb()
            if sb:
                session = sb.auth.get_session()
                if session and session.session and session.session.access_token:
                    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
                    if supabase_url:
                        return anthropic.Anthropic(
                            api_key="proxy",
                            base_url=f"{supabase_url}/functions/v1/claude-proxy",
                            default_headers={"Authorization": f"Bearer {session.session.access_token}"},
                        )
        except Exception:
            pass

        # Fallback — unconfigured client (will raise on use with clear error)
        if self._client is None:
            self._client = anthropic.Anthropic(api_key="")
        return self._client

    def _ask(self, user_message: str, history: list[dict] | None = None) -> str:
        messages = list(history or [])
        messages.append({"role": "user", "content": user_message})
        response = self._get_client().messages.create(
            model=self.MODEL,
            max_tokens=1024,
            system=_build_system_prompt(),
            messages=messages,
        )
        return response.content[0].text

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
        client   = self._get_client()
        messages = [{"role": h["role"], "content": h["content"]} for h in (history or [])]
        messages.append({"role": "user", "content": user_message})

        while True:
            response = client.messages.create(
                model=self.TOOLS_MODEL,     # Sonnet — reliably calls tools
                max_tokens=4096,
                system=_build_system_prompt(),
                tools=tools,
                tool_choice={"type": "auto"},   # explicit: Claude may call 0+ tools
                messages=messages,
            )

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
        import json as _json
        if not ingredients:
            return {"ingredients": [], "total": {}, "per_serving": {}}
        servings = max(1, int(servings or 1))
        ing_list = "\n".join(f"- {ing}" for ing in ingredients[:30])
        prompt = (
            f"Give approximate nutritional values for each ingredient listed below. "
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
        raw = self._ask(prompt)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return _json.loads(raw.strip())

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
        import json as _json
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
        raw = self._ask(prompt).strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return _json.loads(raw.strip())

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
