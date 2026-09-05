---
status: active
scope: the `item_events` table of buys, sells, and component consumption
first_seen: 2026-07-08
last_confirmed: 2026-08-10
---

# Item events

## Why this page exists

`item_events` holds every buy with names, cost, tier, and slot. The value of an item shows up in the damage tables in two different ways, and prices change by patch. `item_buys`, `item_games`, and `item_events_effective` apply the rules below.

## Attribution

First seen 2026-07-08.

`attribution` marks how an item's value shows up. `proc` means the item has its own damage rows, for example Scourge and Escalating Exposure. `stat` means the item never appears as a source and its value hides inside other rows, for example Boundless Spirit and Echo Shard.

## Historical pricing

First seen 2026-07-08.

`cost`, `tier`, and `slot` resolve as-of match time from dated asset snapshots. `assets_date` says which snapshot. Null means no history covered that match yet. A balance patch therefore does not reprice history.

`effective_cost` on `item_events_effective` is the marginal souls a buy cost. It is the era price minus the era prices of the component buys that the upgrade consumed. The consumed components are the `flags=1` rows that leave the inventory at the buy time. `item_component_history` pairs them for the same era. A component buy keeps its own price, so effective costs sum to the actual soul outlay. A plain sell keeps full cost, because the refund is income and not a discount. Two same-second upgrades that list one consumed component credit the lower `item_id` only. The column needs the committed asset history tables.

Recheck when the asset history gains a new era.

## Component consumption is not a sell

First seen 2026-07-08.

In `player.items`, `flags=1` means the item was consumed as a component of an upgrade. It is not a sell. Cross-check with `Item.components`. Ability upgrades also appear in the items list as if they were items. Filter by cost or known item ids when you read builds.

## Ownership windows

First seen 2026-07-08.

An ownership window runs from buy time to sell or consume time, or to match end when the item was kept. `owned_s` on `item_games` sums the windows, and a sold buy's window ends at the sell time. `per_min_owned` on the damage views divides item proc rows by owned minutes, so a late buy reads as true uptime damage per second.

## Tiers

First seen 2026-07-08.

`item_tier` is a real assets label, 1:1 with the costs 800, 1600, 3200, and 6400. No 4800 tier exists. 4800 is only the incremental outlay when a 1600 component upgrades into a 6400 item. The buy row lands at upgrade time at full cost.
