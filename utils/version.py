APP_VERSION = "v0.45.3"

# ── Version history ───────────────────────────────────────────────────────────
# Add a new entry here every time a version is released.
# Each entry: {"version": str, "title": str, "changes": list[str]}
VERSION_HISTORY = [
    {
        "version": "v0.45.3",
        "title": "Dishy is fully working",
        "changes": [
            "Dishy AI is now working on all devices — the server-side proxy has been deployed and connected",
            "No API key is needed on your device — all AI requests are handled securely server-side",
        ],
    },
    {
        "version": "v0.45.2",
        "title": "Dishy proxy fix — works on all installs",
        "changes": [
            "Fixed Dishy not working on packaged app installs — the app no longer tries to load an Anthropic API key from local storage, so the Supabase proxy is always used correctly",
            "Fixed the app tour narrator failing on DMG builds — it now uses the same proxy connection as the rest of Dishy",
            "Removed all code paths that expected an Anthropic API key to be stored on the device",
        ],
    },
    {
        "version": "v0.45.1",
        "title": "Bug fixes for packaged app",
        "changes": [
            "Fixed Dishy not working on Macs without a personal Anthropic API key — the Supabase proxy now connects correctly",
            "Fixed clicking a recipe search result doing nothing — SSL certificates are now passed explicitly to the recipe scraper",
        ],
    },
    {
        "version": "v0.45",
        "title": "Smart macros, My Kitchen tab, recipe search overhaul & bug fixes",
        "changes": [
            "Changing your Calorie goal in Settings → Nutrition Goals now automatically recalculates Protein, Carbs & Fat using Dishy AI",
            "Dishy adjusts the macro split based on your dietary preferences — high protein, keto, vegan, etc.",
            "Home: the first sidebar tab has been renamed from 'My Kitchen' to 'Home'",
            "My Kitchen: a new sidebar tab for the upcoming pantry & ingredient storage tracker",
            "Up to 60 recipe results per search (was 26) — results appear instantly as modern cards with title, source, description, and a Dishy macros badge",
            "Fixed recipe search returning no results on the packaged app — SSL certificates are now correctly bundled",
            "Fixed Dishy not working on fresh installs — Supabase credentials are now always available at startup",
            "Settings and Dishy chats now sync to the cloud instantly on every change",
            "Theme fixes: all Settings pages and the Dishy panel now correctly update colours when switching between dark and light mode",
        ],
    },
    {
        "version": "v0.44",
        "title": "First public release",
        "changes": [
            "App ready to run on any Mac — no Python or developer tools required",
            "Automatic update checker: DishBoard notifies you when a new version is available on GitHub",
            "Supabase auth works out of the box on fresh installs — no manual configuration needed",
            "Build system improvements: version numbers auto-sync, clean DMG produced by build.sh",
        ],
    },
    {
        "version": "v0.43",
        "title": "Set your own nutrition goals",
        "changes": [
            "New 'Nutrition Goals' section in Settings — set your own daily targets for calories, protein, carbs, fat, fibre, and sugar",
            "Each goal has a plain-English guide so you know what a sensible number looks like",
            "The progress rings on both the Nutrition page and My Kitchen update the moment you save a new goal",
            "A 'Reset to defaults' button puts everything back if you change your mind",
        ],
    },
    {
        "version": "v0.42",
        "title": "Dishy works out of the box, real-time sync & permanent recipe images",
        "changes": [
            "Dishy now works the moment you sign in — no API key needed",
            "Recipe photos are saved permanently and show up on all your devices",
            "Changes you make sync to other devices in seconds, not minutes",
            "A 'Live' indicator in the sidebar shows when sync is active",
        ],
    },
    {
        "version": "v0.41",
        "title": "Full light mode & new app icons",
        "changes": [
            "Dishy chat, Settings, and the login screen now all switch correctly between dark and light mode",
            "New app icons throughout — cleaner and more polished",
        ],
    },
    {
        "version": "v0.40",
        "title": "Guided app tour for new users",
        "changes": [
            "New users get a guided tour of DishBoard narrated by Dishy",
            "Each step highlights the relevant part of the screen so you know exactly where to look",
            "The tour is personalised using your name and cooking preferences",
            "Works even without an internet connection",
        ],
    },
    {
        "version": "v0.39",
        "title": "Dishy chat visual refresh",
        "changes": [
            "Chat bubbles are smaller and cleaner — easier to read at a glance",
            "User and assistant bubbles have a softer, more polished glass-style look",
            "Quick-prompt chips are more compact with a 'Try asking' label and a shuffle button",
            "Input bar has a clear button when you've typed something",
        ],
    },
    {
        "version": "v0.38",
        "title": "Scrollable pages & layout fixes",
        "changes": [
            "My Kitchen and Nutrition now scroll at smaller window sizes instead of squishing everything",
            "Meal Planner stays readable at narrow window widths",
            "Today's Plan shows the correct breakfast, lunch, and dinner icons with colour strips",
            "Shopping List groups items by category with coloured headers and checkboxes",
        ],
    },
    {
        "version": "v0.37",
        "title": "Smarter shopping lists & more Dishy meal planner controls",
        "changes": [
            "Shopping lists are smarter — ingredients from multiple recipes are combined, converted to shop-friendly quantities, and common staples like salt and oil are skipped",
            "Dishy can now clear a single day's meals in one go — just ask it to 'clear Monday'",
            "Dishy can wipe the entire meal plan across all weeks",
        ],
    },
    {
        "version": "v0.36",
        "title": "Instant sync & nutrition straight from your meal plan",
        "changes": [
            "Changes save to the cloud instantly — no more waiting",
            "Nutrition now pulls directly from your meal plan — no separate logging needed",
            "Macro rings update the moment you change a meal",
            "Removing a meal from Today's Log removes it from the planner too",
        ],
    },
    {
        "version": "v0.35",
        "title": "Accounts & cloud sync",
        "changes": [
            "Sign in with email or Google to back up your data and access it on any device",
            "The app works fully offline — syncing happens quietly in the background",
            "Everything syncs: recipes, meal plans, shopping list, nutrition, and chat history",
            "A sync status indicator in the sidebar shows Synced, Syncing, or Offline at a glance",
            "Your API keys never leave your device — they're excluded from sync",
        ],
    },
    {
        "version": "v0.34",
        "title": "Dishy chat redesign",
        "changes": [
            "Dishy chat has a fresh new look — glassy bubbles, Dishy avatar on every reply, and a cleaner input bar",
            "Every conversation is saved so you can pick up where you left off",
            "A banner offers to resume your last chat when you reopen the app",
            "Browse and reopen any past conversation from the chat history panel",
        ],
    },
    {
        "version": "v0.33",
        "title": "Shopping List redesign",
        "changes": [
            "Shopping list now groups items by category with collapsible sections",
            "A progress bar at the top tracks how much of your list is done",
            "Items from the meal plan are badged so you know where they came from",
            "Exported lists keep the category grouping",
        ],
    },
    {
        "version": "v0.32",
        "title": "Nutrition dashboard upgrade",
        "changes": [
            "Today's Plan uses the same breakfast/lunch/dinner colours as the Meal Planner",
            "Food log entries are larger and show full macro details on every row",
            "Weekly chart is taller, shows dates, and highlights days where you hit your goal",
            "New 'Recently Logged' card lets you re-add recent foods in one tap",
        ],
    },
    {
        "version": "v0.31",
        "title": "Nutrition stays in sync when you change meals",
        "changes": [
            "Removing or replacing a meal in the planner instantly updates your nutrition totals",
            "No stale numbers left behind — everything updates right away",
        ],
    },
    {
        "version": "v0.30",
        "title": "Settings clear buttons now work properly",
        "changes": [
            "Clearing your meal plan, shopping list, or recipes in Settings instantly refreshes the relevant page",
            "No restart needed — the empty state shows up right away",
        ],
    },
    {
        "version": "v0.29",
        "title": "Help page rewrite",
        "changes": [
            "Help page completely rewritten to cover everything in the app",
            "Each section has a short summary plus a feature-by-feature list",
            "New Dishy section shows all the actions Dishy can take for you",
            "Bottom banner explains the full Recipe → Plan → Shopping → Nutrition flow",
        ],
    },
    {
        "version": "v0.28",
        "title": "Dishy knows your app inside out",
        "changes": [
            "Dishy now has detailed knowledge of every section and can guide you through the whole app",
            "Responses reference your actual recipes, favourites, and meal plan — not generic advice",
            "Dishy can now handle the full workflow — find a recipe, plan it, build the shopping list, and track nutrition — all in one conversation",
        ],
    },
    {
        "version": "v0.27",
        "title": "Meal planner only uses saved recipes",
        "changes": [
            "Meals can only be added from your saved recipe library — no more free-text names",
            "The meal picker highlights your selection and remembers it when you reopen a slot",
            "Dishy follows the same rule — it will save a recipe first before adding it to the plan",
        ],
    },
    {
        "version": "v0.26",
        "title": "Nutrition updates live as you plan meals",
        "changes": [
            "Adding or changing a meal instantly updates your nutrition totals — no refresh needed",
            "Recipes without nutrition data are analysed automatically in the background",
            "Meal Planner and Nutrition are now fully linked and always in sync",
        ],
    },
    {
        "version": "v0.25",
        "title": "Nutrition data is always complete",
        "changes": [
            "Every recipe is guaranteed to have macros — Dishy fills them in automatically on save",
            "If macros are missing when a recipe is added to the plan, they're fetched on the spot",
            "The Nutrition page always shows the latest data when you open it",
        ],
    },
    {
        "version": "v0.24",
        "title": "Nutrition tracks itself automatically",
        "changes": [
            "Add a recipe to today's meal plan and its macros appear in Nutrition instantly — nothing to tap",
            "Dishy logs meals automatically when it sets a slot or fills the week",
            "Removed the manual import button — it all happens in the background now",
        ],
    },
    {
        "version": "v0.23",
        "title": "Dishy tracks your daily nutrition",
        "changes": [
            "Ask Dishy 'log today's meals' or 'how am I doing?' and it handles everything",
            "Dishy knows which planned meals are already logged and which still need to be — it'll offer to fill in the gaps",
            "After planning the week, Dishy will offer to sync today's nutrition straight away",
        ],
    },
    {
        "version": "v0.22",
        "title": "Nutrition dashboard redesign",
        "changes": [
            "Nutrition page rebuilt as a full-page dashboard — no scrolling",
            "Six macro rings show today's progress at a glance (calories, protein, carbs, fat, fibre, sugar)",
            "Today's Plan pulls meals directly from the meal planner",
            "Weekly bar chart with daily calorie totals",
            "Quick Add — describe any food and Dishy logs the macros for you",
        ],
    },
    {
        "version": "v0.21",
        "title": "Nutrition on every recipe, powered by Dishy",
        "changes": [
            "Every recipe now shows a full nutrition breakdown — per ingredient and in total",
            "Web-scraped recipes are automatically analysed when you import them",
            "Macro pills (kcal, protein, fat, carbs) appear next to each ingredient in the detail view",
            "'Log to Today' button on every recipe — one tap to add it to your daily nutrition",
        ],
    },
    {
        "version": "v0.20",
        "title": "Dishy can delete & clear things",
        "changes": [
            "Dishy can now remove a specific meal, clear the whole week's plan, delete shopping items, or remove recipes",
            "All deletions ask for confirmation before anything is removed",
        ],
    },
    {
        "version": "v0.19",
        "title": "Jump to recipes from the meal planner",
        "changes": [
            "Meal slots now show a 'View Recipe' button when a recipe is linked — tap to go straight to it",
            "A small edit button lets you update a meal without clicking the whole slot",
            "Empty slots still open the meal picker with a single click",
        ],
    },
    {
        "version": "v0.18",
        "title": "Meal planner calendar redesign",
        "changes": [
            "Clearer layout with better separation between days and meal times",
            "Row labels show Breakfast, Lunch, Dinner with icons and a colour band",
            "Meal names are larger and easier to read at a glance",
        ],
    },
    {
        "version": "v0.17",
        "title": "Create Recipe overhaul",
        "changes": [
            "Create Recipe form completely redesigned — two-column layout with clearly labelled sections",
            "Ingredient rows show macro pills inline so you can see nutrition as you build",
            "Icon and colour pickers tucked into a collapsible section so they're out of the way",
            "Favourite star at the top for quick access",
        ],
    },
    {
        "version": "v0.16",
        "title": "Recipe card grid",
        "changes": [
            "Recipes now display as cards in a 3-column grid — see more at once",
            "Each card shows a photo, title, description, tags, cook time, and servings",
            "Cards have a hover highlight for clear selection feedback",
        ],
    },
    {
        "version": "v0.15",
        "title": "My Kitchen & home redesign",
        "changes": [
            "Dashboard renamed to 'My Kitchen'",
            "Redesigned home screen with scrollable shopping and favourites widgets",
            "All home cards share the same consistent style and spacing",
        ],
    },
    {
        "version": "v0.14",
        "title": "New icon & version history",
        "changes": [
            "Brand-new app icon — modern rounded design",
            "Version history page added to Settings (you're looking at it!)",
        ],
    },
    {
        "version": "v0.13",
        "title": "Recipe editing & meal planner polish",
        "changes": [
            "Recipes can now be edited after saving — tap the pen icon in any recipe detail view",
            "Meal planner slots now show icons for breakfast, lunch, and dinner",
            "Meal-type tags (Breakfast, Lunch, etc.) are now teal to stand out from other tags",
        ],
    },
    {
        "version": "v0.12",
        "title": "Dishy actions work from the full page too",
        "changes": [
            "Dishy can now save recipes, plan meals, and update your shopping list from both the sidebar page and the pop-up bubble",
        ],
    },
    {
        "version": "v0.11",
        "title": "Dishy can take actions",
        "changes": [
            "Dishy can now actually do things — not just chat",
            "Supported actions: save a recipe, add meals to your plan, update the shopping list",
            "A green confirmation pill appears after Dishy completes an action",
        ],
    },
    {
        "version": "v0.10",
        "title": "Dishy everywhere",
        "changes": [
            "Dishy is now woven into every section with smarter, context-aware responses",
            "Ingredient rows in recipe creation auto-look up nutrition via Dishy",
            "All Dishy buttons are now green across the whole app",
        ],
    },
    {
        "version": "v0.9",
        "title": "AI-powered nutrition lookup",
        "changes": [
            "Nutrition search is now powered by Dishy instead of a database",
            "Just type naturally — '200g chicken breast' or 'a bowl of oats' both work",
        ],
    },
    {
        "version": "v0.8",
        "title": "Macro rings & daily food log",
        "changes": [
            "Nutrition page shows circular macro rings for your daily progress",
            "Log food to today and see your running totals update live",
            "Sidebar shows a daily cooking tip from Dishy and your three most recent recipes",
        ],
    },
    {
        "version": "v0.7",
        "title": "Section colour coding",
        "changes": [
            "Every section has its own colour — orange, purple, teal, pink, amber, green",
            "Nav buttons highlight in each section's colour when active",
        ],
    },
    {
        "version": "v0.6",
        "title": "Recipe photos, tag filters & Dishy meal plans",
        "changes": [
            "Add photos to recipes — shown as a banner in the detail view",
            "Filter your saved recipes by tag using the chip bar at the top",
            "'Fill with Dishy' in Meal Planner — Dishy plans your whole week automatically",
            "Duplicate recipe detection stops you saving the same recipe twice",
        ],
    },
    {
        "version": "v0.5",
        "title": "Light mode polish & expanded Settings",
        "changes": [
            "Light mode thoroughly polished with stronger contrast and updated colours",
            "Settings now has a Preferences card: name, dietary filters, week start day, default servings",
            "Export all your data to a backup file, or import a previous one",
        ],
    },
    {
        "version": "v0.4",
        "title": "Dark & light mode",
        "changes": [
            "Switch between dark and light mode in Settings — changes apply instantly",
        ],
    },
    {
        "version": "v0.3",
        "title": "Nutrition & macro tracking",
        "changes": [
            "Nutrition section with ingredient search and live results",
            "Per-ingredient macro breakdown (calories, protein, carbs, fat)",
            "Running macro total shown while building a recipe",
        ],
    },
    {
        "version": "v0.2",
        "title": "Dishy, meal planner redesign & shopping improvements",
        "changes": [
            "Dishy AI assistant introduced — floating chat bubble available on every page",
            "Meal planner redesigned with a proper weekly calendar view",
            "Apple Calendar export for your meal plan",
            "Shopping list now supports notes and text export",
        ],
    },
    {
        "version": "v0.1",
        "title": "First launch",
        "changes": [
            "DishBoard is born — My Kitchen, Recipes, Meal Planner, Nutrition, Shopping List, and Settings all up and running",
        ],
    },
]
