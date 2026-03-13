-- DishBoard shared household support + household-scoped sync policies

create extension if not exists pgcrypto;

create table if not exists public.households (
    id            uuid primary key default gen_random_uuid(),
    name          text        not null,
    owner_user_id uuid        not null references auth.users(id) on delete cascade,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

create table if not exists public.household_members (
    household_id uuid        not null references public.households(id) on delete cascade,
    user_id      uuid        not null references auth.users(id) on delete cascade,
    role         text        not null default 'member' check (role in ('owner', 'member')),
    joined_at    timestamptz not null default now(),
    primary key (household_id, user_id)
);

create table if not exists public.household_invites (
    invite_code    text primary key,
    household_id   uuid        not null references public.households(id) on delete cascade,
    household_name text        not null default '',
    created_by     uuid        not null references auth.users(id) on delete cascade,
    active         boolean     not null default true,
    created_at     timestamptz not null default now()
);

alter table public.households enable row level security;
alter table public.household_members enable row level security;
alter table public.household_invites enable row level security;

create or replace function public.is_household_member(hid uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.household_members hm
        where hm.household_id = hid
          and hm.user_id = auth.uid()
    );
$$;

grant execute on function public.is_household_member(uuid) to authenticated;

drop policy if exists "households_select" on public.households;
create policy "households_select"
on public.households
for select
using (
    auth.uid() = owner_user_id
    or public.is_household_member(id)
);

drop policy if exists "households_insert" on public.households;
create policy "households_insert"
on public.households
for insert
with check (auth.uid() = owner_user_id);

drop policy if exists "households_update_owner" on public.households;
create policy "households_update_owner"
on public.households
for update
using (auth.uid() = owner_user_id)
with check (auth.uid() = owner_user_id);

drop policy if exists "households_delete_owner" on public.households;
create policy "households_delete_owner"
on public.households
for delete
using (auth.uid() = owner_user_id);

drop policy if exists "household_members_select" on public.household_members;
create policy "household_members_select"
on public.household_members
for select
using (
    auth.uid() = user_id
    or public.is_household_member(household_id)
);

drop policy if exists "household_members_insert" on public.household_members;
create policy "household_members_insert"
on public.household_members
for insert
with check (
    auth.uid() = user_id
    or exists (
        select 1
        from public.household_members hm
        where hm.household_id = household_members.household_id
          and hm.user_id = auth.uid()
          and hm.role = 'owner'
    )
);

drop policy if exists "household_members_delete" on public.household_members;
create policy "household_members_delete"
on public.household_members
for delete
using (
    auth.uid() = user_id
    or exists (
        select 1
        from public.household_members hm
        where hm.household_id = household_members.household_id
          and hm.user_id = auth.uid()
          and hm.role = 'owner'
    )
);

drop policy if exists "household_invites_select" on public.household_invites;
create policy "household_invites_select"
on public.household_invites
for select
using (active = true);

drop policy if exists "household_invites_insert" on public.household_invites;
create policy "household_invites_insert"
on public.household_invites
for insert
with check (auth.uid() = created_by);

drop policy if exists "household_invites_update" on public.household_invites;
create policy "household_invites_update"
on public.household_invites
for update
using (
    auth.uid() = created_by
    or exists (
        select 1
        from public.households h
        where h.id = household_invites.household_id
          and h.owner_user_id = auth.uid()
    )
)
with check (
    auth.uid() = created_by
    or exists (
        select 1
        from public.households h
        where h.id = household_invites.household_id
          and h.owner_user_id = auth.uid()
    )
);

drop policy if exists "household_invites_delete" on public.household_invites;
create policy "household_invites_delete"
on public.household_invites
for delete
using (
    auth.uid() = created_by
    or exists (
        select 1
        from public.households h
        where h.id = household_invites.household_id
          and h.owner_user_id = auth.uid()
    )
);

alter table if exists public.recipes add column if not exists household_id uuid;
alter table if exists public.meal_plans add column if not exists household_id uuid;
alter table if exists public.shopping_items add column if not exists household_id uuid;
alter table if exists public.nutrition_logs add column if not exists household_id uuid;
alter table if exists public.pantry_items add column if not exists household_id uuid;
alter table if exists public.sync_tombstones add column if not exists household_id uuid;

update public.recipes set household_id = user_id where household_id is null;
update public.meal_plans set household_id = user_id where household_id is null;
update public.shopping_items set household_id = user_id where household_id is null;
update public.nutrition_logs set household_id = user_id where household_id is null;
update public.pantry_items set household_id = user_id where household_id is null;
update public.sync_tombstones set household_id = user_id where household_id is null;

create index if not exists idx_recipes_household_id on public.recipes(household_id);
create index if not exists idx_meal_plans_household_id on public.meal_plans(household_id);
create index if not exists idx_shopping_items_household_id on public.shopping_items(household_id);
create index if not exists idx_nutrition_logs_household_id on public.nutrition_logs(household_id);
create index if not exists idx_pantry_items_household_id on public.pantry_items(household_id);
create index if not exists idx_sync_tombstones_household_id on public.sync_tombstones(household_id);

-- Shared-table policies: keep existing own-user policies and add household access.

drop policy if exists "recipes_household_select" on public.recipes;
create policy "recipes_household_select"
on public.recipes
for select
to authenticated
using (
    auth.uid() = user_id
    or (household_id is not null and public.is_household_member(household_id))
);

drop policy if exists "recipes_household_insert" on public.recipes;
create policy "recipes_household_insert"
on public.recipes
for insert
to authenticated
with check (
    auth.uid() = user_id
    and (household_id is null or public.is_household_member(household_id))
);

drop policy if exists "recipes_household_update" on public.recipes;
create policy "recipes_household_update"
on public.recipes
for update
to authenticated
using (
    auth.uid() = user_id
    or (household_id is not null and public.is_household_member(household_id))
)
with check (
    auth.uid() = user_id
    or (household_id is not null and public.is_household_member(household_id))
);

drop policy if exists "recipes_household_delete" on public.recipes;
create policy "recipes_household_delete"
on public.recipes
for delete
to authenticated
using (
    auth.uid() = user_id
    or (household_id is not null and public.is_household_member(household_id))
);

-- Meal plans
drop policy if exists "meal_plans_household_select" on public.meal_plans;
create policy "meal_plans_household_select"
on public.meal_plans
for select
to authenticated
using (
    auth.uid() = user_id
    or (household_id is not null and public.is_household_member(household_id))
);

drop policy if exists "meal_plans_household_insert" on public.meal_plans;
create policy "meal_plans_household_insert"
on public.meal_plans
for insert
to authenticated
with check (
    auth.uid() = user_id
    and (household_id is null or public.is_household_member(household_id))
);

drop policy if exists "meal_plans_household_update" on public.meal_plans;
create policy "meal_plans_household_update"
on public.meal_plans
for update
to authenticated
using (
    auth.uid() = user_id
    or (household_id is not null and public.is_household_member(household_id))
)
with check (
    auth.uid() = user_id
    or (household_id is not null and public.is_household_member(household_id))
);

drop policy if exists "meal_plans_household_delete" on public.meal_plans;
create policy "meal_plans_household_delete"
on public.meal_plans
for delete
to authenticated
using (
    auth.uid() = user_id
    or (household_id is not null and public.is_household_member(household_id))
);

-- Shopping items
drop policy if exists "shopping_items_household_select" on public.shopping_items;
create policy "shopping_items_household_select"
on public.shopping_items
for select
to authenticated
using (
    auth.uid() = user_id
    or (household_id is not null and public.is_household_member(household_id))
);

drop policy if exists "shopping_items_household_insert" on public.shopping_items;
create policy "shopping_items_household_insert"
on public.shopping_items
for insert
to authenticated
with check (
    auth.uid() = user_id
    and (household_id is null or public.is_household_member(household_id))
);

drop policy if exists "shopping_items_household_update" on public.shopping_items;
create policy "shopping_items_household_update"
on public.shopping_items
for update
to authenticated
using (
    auth.uid() = user_id
    or (household_id is not null and public.is_household_member(household_id))
)
with check (
    auth.uid() = user_id
    or (household_id is not null and public.is_household_member(household_id))
);

drop policy if exists "shopping_items_household_delete" on public.shopping_items;
create policy "shopping_items_household_delete"
on public.shopping_items
for delete
to authenticated
using (
    auth.uid() = user_id
    or (household_id is not null and public.is_household_member(household_id))
);

-- Nutrition logs
drop policy if exists "nutrition_logs_household_select" on public.nutrition_logs;
create policy "nutrition_logs_household_select"
on public.nutrition_logs
for select
to authenticated
using (
    auth.uid() = user_id
    or (household_id is not null and public.is_household_member(household_id))
);

drop policy if exists "nutrition_logs_household_insert" on public.nutrition_logs;
create policy "nutrition_logs_household_insert"
on public.nutrition_logs
for insert
to authenticated
with check (
    auth.uid() = user_id
    and (household_id is null or public.is_household_member(household_id))
);

drop policy if exists "nutrition_logs_household_update" on public.nutrition_logs;
create policy "nutrition_logs_household_update"
on public.nutrition_logs
for update
to authenticated
using (
    auth.uid() = user_id
    or (household_id is not null and public.is_household_member(household_id))
)
with check (
    auth.uid() = user_id
    or (household_id is not null and public.is_household_member(household_id))
);

drop policy if exists "nutrition_logs_household_delete" on public.nutrition_logs;
create policy "nutrition_logs_household_delete"
on public.nutrition_logs
for delete
to authenticated
using (
    auth.uid() = user_id
    or (household_id is not null and public.is_household_member(household_id))
);

-- Pantry items
drop policy if exists "pantry_items_household_select" on public.pantry_items;
create policy "pantry_items_household_select"
on public.pantry_items
for select
to authenticated
using (
    auth.uid() = user_id
    or (household_id is not null and public.is_household_member(household_id))
);

drop policy if exists "pantry_items_household_insert" on public.pantry_items;
create policy "pantry_items_household_insert"
on public.pantry_items
for insert
to authenticated
with check (
    auth.uid() = user_id
    and (household_id is null or public.is_household_member(household_id))
);

drop policy if exists "pantry_items_household_update" on public.pantry_items;
create policy "pantry_items_household_update"
on public.pantry_items
for update
to authenticated
using (
    auth.uid() = user_id
    or (household_id is not null and public.is_household_member(household_id))
)
with check (
    auth.uid() = user_id
    or (household_id is not null and public.is_household_member(household_id))
);

drop policy if exists "pantry_items_household_delete" on public.pantry_items;
create policy "pantry_items_household_delete"
on public.pantry_items
for delete
to authenticated
using (
    auth.uid() = user_id
    or (household_id is not null and public.is_household_member(household_id))
);

-- Tombstones
drop policy if exists "sync_tombstones_household_select" on public.sync_tombstones;
create policy "sync_tombstones_household_select"
on public.sync_tombstones
for select
to authenticated
using (
    auth.uid() = user_id
    or (household_id is not null and public.is_household_member(household_id))
);

drop policy if exists "sync_tombstones_household_insert" on public.sync_tombstones;
create policy "sync_tombstones_household_insert"
on public.sync_tombstones
for insert
to authenticated
with check (
    auth.uid() = user_id
    and (household_id is null or public.is_household_member(household_id))
);
