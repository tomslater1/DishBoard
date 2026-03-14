# DishBoard North Star

This file defines the long-term product direction for DishBoard.

It exists to stop the product from drifting into a collection of individually useful features that do not add up to a strong, distinctive experience.

Read this after [CONTEXT.md](./CONTEXT.md) when making product, UX, navigation, workflow, or interface decisions.

## Core Thesis

DishBoard should feel like a `food operations console`.

That means:
- one connected workspace
- fast movement between related tasks
- visible system state
- clear next actions
- AI that explains itself
- a calmer, sharper interface with stronger hierarchy

DishBoard should not feel like:
- a disconnected set of utility pages
- a basic recipe scrapbook
- an AI novelty layer on top of forms
- a dashboard full of equal-weight cards without operational flow

## Product Promise

A user should be able to open DishBoard and quickly answer:
- What should I cook today?
- What needs using up soon?
- What do I need to buy?
- What is already covered?
- How am I doing nutritionally?
- What should I do next?

The app should increasingly behave like a command panel for food planning and household meal operations.

## Primary Goals

### 1. One Workspace, Not Separate Pages

The app should feel like a single system, not a row of unrelated views.

Recipes, pantry, shopping, planning, nutrition, settings, and Dishy should connect naturally through:
- command palette
- global search
- quick actions
- drawers
- overlays
- linked transitions

Full page switches should be used deliberately, not as the default for every interaction.

### 2. Fast, Confident Interaction

DishBoard should feel quick and decisive.

Users should be able to:
- add things quickly
- jump anywhere with minimal friction
- inspect details without losing place
- understand sync/loading/AI state instantly
- recover from mistakes without confusion

### 3. Show What Matters Now

The app should surface urgency and next steps clearly.

High-value examples:
- ingredients expiring soon
- meals planned today
- shopping gaps
- nutrition progress
- recent changes
- Dishy suggestions

### 4. Make Intelligence Legible

Dishy should be smart, but not opaque.

Users should increasingly be able to see:
- why a recipe was suggested
- why a trust score looks the way it does
- why a shopping item is needed
- why a planner suggestion was chosen
- what confidence the app has in a result

### 5. Build a More Intentional Interface

The UI should feel more like a modern technical product and less like a feature-heavy desktop utility.

That means:
- stronger hierarchy
- tighter spacing discipline
- more contextual actions
- better use of drawers and panels
- fewer equally weighted blocks
- more obvious status and flow

## Experience Principles

### Act Without Leaving Context

Prefer:
- detail drawers
- overlays
- quick editors
- inline actions

Over:
- repeated hard navigation
- multi-step context switching for simple actions

### Bias Toward Next Action

Every major surface should help answer:
- what is happening
- what matters
- what can I do now

### Keep the System Legible

Users should be able to tell:
- what is synced
- what is local
- what is loading
- what Dishy changed
- what the app is confident about

### Reduce Interaction Cost

The best workflows should require fewer clicks, less hunting, and less repeated input.

### Reward Advanced Use

DishBoard should increasingly reward power users through:
- shortcuts
- command palette access
- saved views
- pinned workflows
- templates
- automation

## UI Direction

The product should evolve from:

`section-based desktop app`

toward:

`integrated operational workspace`

That means more use of:
- command entry
- universal search
- side panels
- pinned operational widgets
- live status
- contextual drill-down

The goal is not to make the interface busier.
The goal is to make it more connected, more decisive, and more useful in flow.

## Roadmap

## Phase 1: Foundation

Target window: March to April 2026

### Command Panel

Status: Completed in `v0.69`.

Add `Cmd/Ctrl+K` with actions such as:
- Add pantry item
- Add shopping item
- Search recipes
- Create recipe
- Plan meal
- Log nutrition
- Open My Kitchen
- Open Shopping
- Open Settings
- Ask Dishy

Why it matters:
- immediate modern-product signal
- reduces friction across the whole app
- creates infrastructure for later power workflows

Completed outcome in `v0.69`:
- `Cmd/Ctrl+K` now opens a mixed-result command panel instead of a command-only launcher
- the panel supports commands, recent usage, saved recipe/pantry/shopping/planner/settings/Dishy search hits, and inline quick-add flows
- meal-planning recipe entry now offers typo-tolerant saved-recipe suggestions while typing
- the panel is keyboard-first, dismisses on outside click, and uses the same calmer unboxed UI language as the Phase 1 shell

### Global Search

Status: Completed in `v0.69` through the command panel surface.

Introduce one search surface for:
- recipes
- pantry items
- shopping items
- meal plan entries
- settings
- recent Dishy activity

Why it matters:
- makes the app feel unified
- reduces dependence on page structure
- directly supports the food operations console direction

Completed outcome in `v0.69`:
- global search now lives inside the command panel rather than a separate dedicated search screen
- users can search recipes, pantry items, shopping items, current-week meal-plan entries, settings, and recent Dishy sessions from one overlay

### Quick-Add Layer

Status: Completed in `v0.69` for the first operational set.

Add a consistent quick-add interaction model for:
- pantry items
- shopping items
- recipes
- nutrition logs
- meal slots

Preferred form:
- compact modal
- overlay
- slide-over drawer

Avoid sending users to a full page for simple creation tasks when a lightweight surface will do.

Completed outcome in `v0.69`:
- the command panel now includes inline quick-add flows for pantry items, shopping items, nutrition logging, and meal-slot planning
- each flow confirms explicitly before writing, then routes into the relevant page and refresh/sync path

### UI System Cleanup

Status: Completed in `v0.68` as the first major Phase 1 delivery.

Standardize:
- page headers
- card structure
- spacing rhythm
- chip language
- tooltip behavior
- hover states
- empty states
- loading states
- status indicators

Why it matters:
- the current feel problem is partly interaction design, but also inconsistency
- stronger UI discipline is required before bigger flagship work lands cleanly

Completed outcome in `v0.68`:
- shared page-shell primitives and a calmer spacing system now anchor the core screens
- action density was reduced with clearer primary/secondary/overflow hierarchy
- the app moved toward a restrained warm-neutral visual system with quieter passive chrome
- Recipes was reworked into a search-first experience and support pages were brought into the same system

### System State Visibility

Status: Completed in `v0.70`.

Make these clearer and calmer:
- sync status
- loading status
- AI work in progress
- stale vs fresh data
- recent changes

Completed outcome in `v0.70`:
- a shared visibility service now derives sync/runtime/AI/job state, module freshness, recent changes, and severity from one policy layer
- Monitoring and account sync surfaces now read from that shared visibility model instead of ad hoc status strings
- high-value producers now report scoped work consistently, so background activity and failures are visible without getting stuck
- the attempted persistent shell/banner chrome was intentionally removed after validation because it added noise rather than helping users act faster

Success marker for Phase 1:
- the app feels more coherent, faster, and more keyboard-friendly
- the command panel, mixed search, and first quick-add workflows are shipped rather than still being roadmap items

## Phase 2: Console Structure

Target window: April to June 2026

### Operations Home

Redesign Home into a real operational dashboard.

Suggested blocks:
- Today
- Planned meals
- Use soon
- Shopping gaps
- Pantry risk
- Nutrition progress
- Dishy suggestions
- Recent activity

This should become the central control surface of the app.

### Right-Side Detail Drawer

Introduce a shared detail drawer for:
- recipes
- pantry items
- shopping items
- planner slots
- Dishy explanations

Benefits:
- preserves context
- reduces navigation churn
- makes the app feel more like a workbench

### Pinned Views

Let users pin reusable operational slices, for example:
- Expiring this week
- High-protein dinners
- Meals under 30 min
- Missing ingredients for planned meals
- Batch-cook candidates
- Budget-friendly recipes

These should act like operational lenses, not just temporary filters.

### Cross-Module Linking

Make transitions more immediate:
- recipe -> add to planner
- planner slot -> open recipe
- planner -> generate shopping
- shopping item -> check pantry overlap
- pantry item -> matching recipes
- nutrition log -> source meal

This is critical to making the app feel connected.

### Activity Timeline

Add a compact timeline that records:
- recipe saves
- pantry updates
- shopping changes
- Dishy actions
- sync events
- nutrition logs

Success marker for Phase 2:
- the app starts to feel operational rather than page-based

## Phase 3: Flagship Features

Target window: June to September 2026

### 1. Daily Ops Console

This should be the flagship surface.

One workspace that helps answer:
- what should I cook today
- what needs using up
- what am I missing
- what should I buy
- how am I doing nutritionally
- what should I do next

It should combine:
- planner context
- pantry urgency
- shopping readiness
- nutrition progress
- Dishy guidance

### 2. Dishy Copilot Workspace

Dishy should evolve from a chat surface into a persistent copilot workspace.

Core capabilities:
- explain recommendations
- rebalance a week
- reduce waste
- shift plans to match budget or macros
- generate shopping changes
- explain tradeoffs
- show reasoning for suggestions

Important rule:
meaningful Dishy recommendations should expose a clear `why this` explanation.

### 3. Smart Shopping Mode

Shopping should become a full operational workflow.

Potential capabilities:
- aisle grouping
- pantry overlap detection
- duplicate consolidation
- estimated spend
- meal source traceability
- "what breaks if I skip this" guidance
- live shopping progress

### 4. Scenario Planning

Allow users to create planning scenarios without overwriting the current setup.

Examples:
- Budget week
- Cutting week
- Family visit week
- Use freezer week
- Meal prep week

The system should allow comparison before application.

### 5. Pantry Intelligence

Evolve the pantry into a predictive surface with:
- expiry risk ranking
- recipe match suggestions
- waste prevention prompts
- restock predictions
- storage-aware planning cues

### 6. Personal Performance Layer

Add weekly insight summaries such as:
- most-used ingredients
- money saved through pantry reuse
- waste avoided
- macro consistency
- plan completion rate
- repeat meal patterns

Success marker for Phase 3:
- DishBoard has standout workflows that feel distinct, not just useful

## Flagship Priorities

If only three major experiences are pursued, prioritize:

1. Daily Ops Console
2. Dishy Copilot Workspace
3. Smart Shopping Mode

These three best express the food operations console identity.

## Recommended Delivery Order

Suggested build order:

1. Command palette
2. Global search
3. Quick-add layer
4. Operations Home redesign
5. Right-side detail drawer
6. Dishy Copilot Workspace
7. Smart Shopping Mode
8. Scenario planning

This order builds shared interaction infrastructure before the larger flagship surfaces.

## What To Avoid

Avoid:
- adding isolated features that do not improve flow
- creating more hard-separated sections when overlays or drawers would work
- making AI feel powerful but opaque
- treating every card and panel as equally important
- relying on style alone instead of interaction quality
- adding explanatory text everywhere instead of improving discoverability and structure

## Success Markers

DishBoard is moving in the right direction if users increasingly feel:
- the app is faster to operate
- sections feel connected
- the next step is clearer
- Dishy is useful and understandable
- they stay in flow more often
- the interface feels like a professional product, not just a collection of tools

## Instruction For Future Work

Future implementation should prefer choices that:
- support the food operations console direction
- reduce context switching
- improve workflow continuity
- make system logic easier to understand
- increase speed, clarity, and operational usefulness

Future assistants and future development passes should treat this document as the default product direction unless explicitly replaced.
