"""The data model for the parquet tables, a dtype and description per column.

- one class per table, one Column attribute per column
- export conforms every table to this before writing, so a new column
  without an entry here fails loudly instead of shipping undocumented
- `deadlock schema` prints it as a data dictionary
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from deadlock_matches import extract


@dataclass(frozen=True)
class Column:
    """One table column, its polars dtype and what it means."""

    dtype: pl.DataType | type[pl.DataType]
    description: str


def souls(field_name: str) -> str:
    """Rename a protobuf gold_* field to souls_* (the game calls the currency souls)."""
    if field_name.startswith("gold"):
        return "souls" + field_name.removeprefix("gold")

    return field_name


def _stat_field_names() -> tuple[str, ...]:
    """Scalar PlayerStats field names, read off the protobuf descriptor."""
    desc: Any = extract.pb.CMsgMatchMetaDataContents.Players.DESCRIPTOR
    stats_desc = desc.fields_by_name["stats"].message_type

    return tuple(
        f.name for f in stats_desc.fields if f.type != f.TYPE_MESSAGE and not f.is_repeated
    )


STAT_FIELDS = _stat_field_names()

MATCH_ID = Column(pl.Int64, "Valve match id, increasing over time")
ACCOUNT_ID = Column(pl.Int64, "Steam32 account ID of the player")

ERA_FROM = Column(
    pl.Datetime("us", "UTC"), "Release time of the client build that started this era"
)
CLIENT_VERSION = Column(pl.Int64, "Steam client build id the era began at (the patch version)")

WEAPON_HISTORY_FIELDS = (
    "bullet_damage",
    "bullets",
    "clip_size",
    "cycle_time",
    "reload_duration",
    "bullets_per_second",
    "damage_per_second",
    "bullet_speed",
    "crit_bonus_start",
    "crit_bonus_end",
    "crit_bonus_start_range",
    "crit_bonus_end_range",
    "damage_falloff_start_range",
    "damage_falloff_end_range",
    "damage_falloff_end_scale",
    "range",
)

WEAPON_FIELD_DESCRIPTIONS = {
    "bullet_damage": "Damage per bullet",
    "bullets": "Bullets fired per shot",
    "clip_size": "Rounds in a full clip",
    "cycle_time": "Seconds between shots",
    "reload_duration": "Reload time in seconds",
    "bullets_per_second": "Bullets fired per second",
    "damage_per_second": "Sustained damage per second",
    "bullet_speed": "Bullet travel speed in units per second",
    "crit_bonus_start": "Headshot damage bonus at close range",
    "crit_bonus_end": "Headshot damage bonus at long range",
    "crit_bonus_start_range": "Range where the headshot bonus starts falling off",
    "crit_bonus_end_range": "Range where the headshot bonus reaches its far value",
    "damage_falloff_start_range": "Range where bullet damage starts falling off",
    "damage_falloff_end_range": "Range where bullet damage reaches its floor",
    "damage_falloff_end_scale": "Damage multiplier at the falloff floor",
    "range": "Maximum useful bullet range",
}


class Table:
    """Base for table models, where spec() collects the Column attributes in order."""

    @classmethod
    def spec(cls) -> dict[str, Column]:
        """Collect the table columns as {name: Column}, in declaration order."""
        return {name: v for name, v in vars(cls).items() if isinstance(v, Column)}


class Matches(Table):
    """One row per match."""

    match_id = MATCH_ID
    start_time = Column(pl.Datetime("us", "UTC"), "When the match started (UTC)")
    duration_s = Column(pl.Int64, "Match length in seconds")
    winning_team = Column(
        pl.Int64, "0 = The Hidden King (Amber internally), 1 = The Archmother (Sapphire)"
    )
    match_mode = Column(pl.Int64, "1 = ranked")
    game_mode = Column(pl.Int64, "Protobuf ECitadelGameMode value (1 = normal)")
    average_badge_team0 = Column(
        pl.Int64,
        "Average skill rating of team 0 as a badge level, tier * 10 + level "
        "(95 = Phantom 5, queries.skill_rating maps it), null if unset",
    )
    average_badge_team1 = Column(
        pl.Int64,
        "Average skill rating of team 1 as a badge level, tier * 10 + level "
        "(112 = Eternus 2, queries.skill_rating maps it), null if unset",
    )
    not_scored = Column(
        pl.Boolean,
        "Valve flagged the match as not scored (usually a safe-to-leave after "
        "an early abandon), winning_team is still set and match history still "
        "shows the result",
    )


class Players(Table):
    """One row per player per match with final scoreboard numbers."""

    match_id = MATCH_ID
    account_id = ACCOUNT_ID
    hero_id = Column(pl.Int64, "Numeric hero id (heroes.py maps to names)")
    hero = Column(pl.String, "Hero display name")
    team = Column(pl.Int64, "0 = The Hidden King (Amber internally), 1 = The Archmother (Sapphire)")
    player_slot = Column(pl.Int64, "Slot within the match, joins to damage target/dealer")
    assigned_lane = Column(pl.Int64, "Starting lane, raw engine id (1/4/6 on the three-lane map)")
    lane = Column(pl.String, "Color of the starting lane")
    won = Column(pl.Boolean, "Whether this player's team won")
    kills = Column(pl.Int64, "Final kills")
    deaths = Column(pl.Int64, "Final deaths")
    assists = Column(pl.Int64, "Final assists")
    net_worth = Column(pl.Int64, "Final net worth in souls")
    last_hits = Column(pl.Int64, "Final last hits")
    denies = Column(pl.Int64, "Final denies")
    mvp_rank = Column(
        pl.Int64,
        "The match awards: 1 = MVP (always a winner), 2 and 3 = Key Player "
        "(3 is usually the best loser), 0 = no award",
    )
    party = Column(
        pl.Int64,
        "Party id within the match, 0 = queued solo, players sharing a nonzero "
        "id queued together, null after 2026-03-11 (Valve removed the field)",
    )
    abandon_time_s = Column(
        pl.Int64, "Game time in seconds when the player abandoned, null if they stayed"
    )


class Stats(Table):
    """Cumulative snapshots taken every minute, with columns from the protobuf descriptor.

    Declare a Column attribute here to describe a field. Anything not declared
    gets a generic description. spec() fills in the full protobuf field list.
    """

    match_id = MATCH_ID
    account_id = ACCOUNT_ID
    time_stamp_s = Column(
        pl.Int64,
        "Snapshot game time in seconds, the other stats columns are cumulative as of this time",
    )
    net_worth = Column(pl.Int64, "Total souls earned so far (the scoreboard number)")
    souls_player = Column(pl.Int64, "Souls from hero kills and assists")
    souls_denied = Column(pl.Int64, "Souls earned by denying enemy orbs")
    souls_death_loss = Column(pl.Int64, "Souls lost to deaths")
    shots_hit = Column(pl.Int64, "Gun shots that hit anything")
    shots_missed = Column(pl.Int64, "Gun shots that missed")
    hero_bullets_hit = Column(pl.Int64, "Bullets that hit enemy heroes, body shots only")
    hero_bullets_hit_crit = Column(pl.Int64, "Bullets that hit enemy heroes as headshots")
    heal_prevented = Column(pl.Int64, "Enemy healing this player suppressed (Healbane and similar)")
    heal_lost = Column(pl.Int64, "Own healing lost to enemy anti-heal")
    player_damage = Column(pl.Int64, "Damage dealt to enemy heroes")
    player_damage_taken = Column(pl.Int64, "Damage taken from enemy heroes")
    possible_creeps = Column(pl.Int64, "Lane creeps this player could have last-hit")

    @classmethod
    def spec(cls) -> dict[str, Column]:
        """Builds the full column list from the protobuf descriptor, using the declared Columns where they exist."""
        declared = super().spec()
        cols = {"match_id": MATCH_ID, "account_id": ACCOUNT_ID}

        for field in STAT_FIELDS:
            name = souls(field)
            col = declared.get(name, Column(pl.Int64, f"Cumulative {name.replace('_', ' ')}"))

            if name != field:
                col = Column(col.dtype, f"{col.description} (protobuf {field})")

            cols[name] = col

        unknown = set(declared) - set(cols)
        if unknown:
            msg = f"Stats describes columns the protobuf doesn't have: {sorted(unknown)}"
            raise ValueError(msg)

        return cols


class SoulSources(Table):
    """Souls per income source per snapshot."""

    match_id = MATCH_ID
    account_id = ACCOUNT_ID
    time_stamp_s = Column(pl.Int64, "Snapshot time in seconds, souls are cumulative")
    source = Column(pl.Int64, "Income source enum id")
    source_name = Column(
        pl.String, "Income source: players/troopers/jungle/bosses/treasure/breakables/..."
    )
    souls = Column(pl.Int64, "Cumulative souls from this source")
    souls_orbs = Column(pl.Int64, "The orb-confirm portion of souls (protobuf gold_orbs)")


class ItemEvents(Table):
    """One row per item bought."""

    match_id = MATCH_ID
    account_id = ACCOUNT_ID
    game_time_s = Column(pl.Int64, "When the item was bought, seconds from match start")
    item_id = Column(pl.Int64, "Numeric item id")
    item = Column(pl.String, "Item display name, null for unknown/removed items")
    cost = Column(
        pl.Int64,
        "Shop price in souls from the committed item history era live at match time",
    )
    slot = Column(pl.String, "Shop slot: weapon/vitality/spirit")
    tier = Column(pl.Int64, "Item tier 1-4")
    sold_time_s = Column(pl.Int64, "When it left the inventory (sold or consumed), 0 if kept")
    flags = Column(pl.Int64, "1 = consumed as a component of an upgrade, NOT a sell, 0 = normal")
    imbued_ability_id = Column(pl.Int64, "Ability the item was imbued into, null when not imbued")
    imbued_ability = Column(pl.String, "Display name of the imbued ability, null when not imbued")


class Accolades(Table):
    """End of match stat awards, one row per accolade per player."""

    match_id = MATCH_ID
    account_id = ACCOUNT_ID
    accolade_id = Column(pl.Int64, "Numeric accolade id")
    accolade = Column(
        pl.String, "Stat the accolade grades (kills, headshot_damage, ...), null for unknown ids"
    )
    value = Column(pl.Int64, "The player's number for that stat this match")
    threshold = Column(pl.Int64, "Highest star threshold reached, 0-based, -1 = none reached")


class Damage(Table):
    """Final damage matrix numbers for each dealer, source, and target."""

    match_id = MATCH_ID
    dealer_account_id = Column(pl.Int64, "Who dealt it, null for non-player slots")
    target_account_id = Column(
        pl.Int64, "Who received it, null for non-player targets (objectives, creeps)"
    )
    target_player_slot = Column(pl.Int64, "Raw target slot, kept for non-player targets")
    source_name = Column(
        pl.String, "Current display name (Dust Devil, 'Promises Kept (crit)' for headshots)"
    )
    source_class = Column(
        pl.String, "Engine class_name, stable across patches unlike display names"
    )
    category = Column(
        pl.String,
        "Row type, 'total' = the summary rows on the match screen (Bullet, Ability, ...), which just add up the gun/ability/item detail rows",
    )
    delivery = Column(
        pl.String,
        "How a detail row was delivered: gun, gun_proc (items that proc on hit, like Mystic Shot), ability, spirit_proc. Null on total rows",
    )
    stat = Column(
        pl.String, "Which figure this row carries: damage/healing/mitigated/... (EStatType)"
    )
    damage = Column(pl.Int64, "Final cumulative value at match end for this row")


class DamageSources(Table):
    """Cumulative damage per dealer and source over time, summed over targets."""

    match_id = MATCH_ID
    dealer_account_id = Column(pl.Int64, "Who dealt it, null for non-player slots")
    source_name = Column(
        pl.String, "Current display name (Dust Devil, 'Promises Kept (crit)' for headshots)"
    )
    source_class = Column(
        pl.String, "Engine class_name, stable across patches unlike display names"
    )
    category = Column(
        pl.String,
        "Row type, 'total' = the summary rows on the match screen (Bullet, Ability, ...), which just add up the gun/ability/item detail rows",
    )
    delivery = Column(
        pl.String,
        "How a detail row was delivered: gun, gun_proc (items that proc on hit, like Mystic Shot), ability, spirit_proc. Null on total rows",
    )
    stat = Column(
        pl.String, "Which figure this row carries: damage/healing/mitigated/... (EStatType)"
    )
    vs_heroes = Column(
        pl.Boolean,
        "True = summed over hero targets, False = summed over non-player targets (creeps, objectives)",
    )
    time_stamp_s = Column(
        pl.Int64,
        "Sample game time in seconds, damage is cumulative; samples are sparse (about every three minutes plus match end)",
    )
    damage = Column(pl.Int64, "Cumulative value at this sample for this row's group of targets")


class MidBoss(Table):
    """One row per midboss (Rejuvenator) kill."""

    match_id = MATCH_ID
    destroyed_time_s = Column(pl.Int64, "When the midboss died, seconds from match start")
    team_killed = Column(pl.Int64, "Team that landed the killing blow on the midboss")
    team_claimed = Column(
        pl.Int64,
        "Team that secured the dropped Rejuvenator, can differ from team_killed when stolen",
    )


class Objectives(Table):
    """One row per objective, covering guardians, walkers, base guardians, shrines, and the patron."""

    match_id = MATCH_ID
    team = Column(pl.Int64, "Team the objective belonged to")
    objective_id = Column(pl.Int64, "Raw ECitadelTeamObjective id")
    objective = Column(
        pl.String, "Guardian, Walker, Base Guardians, Shrine, Patron, or Weakened Patron"
    )
    lane = Column(pl.String, "Color of its lane")
    destroyed_time_s = Column(pl.Int64, "Game time in seconds when it was destroyed")
    first_damage_time_s = Column(pl.Int64, "Game time in seconds when it first took damage")
    player_damage = Column(pl.Int64, "Damage dealt to it by players (gun and spirit combined)")
    player_spirit_damage = Column(pl.Int64, "The spirit portion of player_damage")
    creep_damage = Column(pl.Int64, "Damage dealt to it by troopers")


class Movement(Table):
    """One row per player per second with position, health, and movement state."""

    match_id = MATCH_ID
    account_id = ACCOUNT_ID
    game_time_s = Column(pl.Int64, "Seconds from match start, one row per second")
    x = Column(pl.Float64, "Map x position in world units")
    y = Column(pl.Float64, "Map y position in world units")
    health_percent = Column(pl.Int64, "Health as a percent of max health, 0 while dead")
    combat_type = Column(
        pl.String,
        "What they were fighting that second: out (no combat), player, enemy_npc, neutral",
    )
    move_type = Column(
        pl.String,
        "Movement state: normal, ability, ability_debuff, ground_dash, slide, rope_climbing, ziplining, in_air, air_dash",
    )


class Deaths(Table):
    """One row per death, with position, killer, and respawn time."""

    match_id = MATCH_ID
    account_id = ACCOUNT_ID
    game_time_s = Column(pl.Int64, "When the death happened, seconds from match start")
    time_to_kill_s = Column(
        pl.Float64,
        "How long the fight that ended in this death lasted, in seconds. It spans "
        "the whole engagement including partial recoveries, not just the final burst",
    )
    death_duration_s = Column(pl.Int64, "Respawn timer in seconds")
    killer_account_id = Column(pl.Int64, "Who got the kill, null when the killer was not a player")
    x = Column(pl.Float64, "Death x position in world units")
    y = Column(pl.Float64, "Death y position in world units")
    z = Column(pl.Float64, "Death z position (height) in world units")
    killer_x = Column(pl.Float64, "Killer x position in world units")
    killer_y = Column(pl.Float64, "Killer y position in world units")
    killer_z = Column(pl.Float64, "Killer z position (height) in world units")


class Downloads(Table):
    """One row per (downloaded match, tracked player), showing why each match is in the players tables.

    This table only exists in the players parquet directory. The eight match tables there share
    the schemas above.
    """

    match_id = MATCH_ID
    account_id = Column(
        pl.Int64,
        "Steam32 account ID of the tracked player whose match history brought this match in",
    )
    player = Column(pl.String, "Tracked player's name at download time (leaderboard or config)")
    hero_id = Column(pl.Int64, "Hero the player was tracked for")
    rank = Column(
        pl.Int64, "Leaderboard rank at download time, null for players selected in config"
    )
    region = Column(
        pl.String, "Leaderboard region at download time, null for players selected in config"
    )
    downloaded_at = Column(
        pl.Datetime("us", "UTC"),
        "When this match's metadata was first downloaded (patch-era marker for the whole match)",
    )


class ItemHistory(Table):
    """One row per item per era."""

    item_id = Column(pl.Int64, "Numeric item id")
    name = Column(pl.String, "Item display name")
    class_name = Column(pl.String, "Engine class name, stable across patches")
    cost = Column(pl.Int64, "Shop price in souls")
    slot = Column(pl.String, "Shop slot: weapon/vitality/spirit")
    tier = Column(pl.Int64, "Item tier 1-4")
    is_active = Column(pl.Boolean, "Whether the item has an active use")
    description = Column(pl.String, "Cleaned shop description text")
    era_from = ERA_FROM
    client_version = CLIENT_VERSION


class ItemComponentHistory(Table):
    """One row per component an item builds from, per era."""

    item_id = Column(pl.Int64, "Numeric id of the upgrade item")
    position = Column(pl.Int64, "Component order in the build, starting at 0")
    component_class_name = Column(pl.String, "Engine class name of the component item")
    era_from = ERA_FROM
    client_version = CLIENT_VERSION


class HeroHistory(Table):
    """One row per hero per era."""

    hero_id = Column(pl.Int64, "Numeric hero id")
    name = Column(pl.String, "Hero display name")
    class_name = Column(pl.String, "Engine class name, stable across patches")
    hero_type = Column(pl.String, "Hero type tag from the assets API")
    gun_tag = Column(pl.String, "Weapon archetype tag")
    complexity = Column(pl.Int64, "Complexity rating shown in hero select")
    player_selectable = Column(pl.Boolean, "Whether players can pick the hero")
    disabled = Column(pl.Boolean, "Whether the hero is disabled")
    era_from = ERA_FROM
    client_version = CLIENT_VERSION


class HeroLevelHistory(Table):
    """One row per hero level per era."""

    hero_id = Column(pl.Int64, "Numeric hero id")
    level = Column(pl.Int64, "Hero level, starting at 1")
    required_souls = Column(pl.Int64, "Total souls earned to reach this level")
    standard_upgrade = Column(pl.Boolean, "Whether this level applies the standard stat boon")
    era_from = ERA_FROM
    client_version = CLIENT_VERSION


class HeroStatHistory(Table):
    """One row per hero starting stat per era."""

    hero_id = Column(pl.Int64, "Numeric hero id")
    stat = Column(pl.String, "Starting stat name (max_health, light_melee_damage, ...)")
    value = Column(pl.Float64, "Starting value of the stat")
    era_from = ERA_FROM
    client_version = CLIENT_VERSION


class HeroLevelUpHistory(Table):
    """One row per hero boon stat per era."""

    hero_id = Column(pl.Int64, "Numeric hero id")
    stat = Column(
        pl.String, "Stat that grows each standard level (base_health_from_level, tech_power, ...)"
    )
    per_level_value = Column(pl.Float64, "Amount the stat gains per standard level")
    era_from = ERA_FROM
    client_version = CLIENT_VERSION


class AbilityHistory(Table):
    """One row per ability or gun per era."""

    ability_class = Column(pl.String, "Engine class name of the ability or gun")
    id = Column(pl.Int64, "Numeric ability id")
    name = Column(pl.String, "Ability display name")
    hero = Column(pl.Int64, "Numeric id of the hero that owns it, null for shared guns")
    kind = Column(pl.String, "ability or weapon")
    description = Column(pl.String, "Cleaned ability card text")
    era_from = ERA_FROM
    client_version = CLIENT_VERSION


class AbilityPropertyHistory(Table):
    """One row per ability property per era, base value merged with scaling."""

    ability_class = Column(pl.String, "Engine class name of the ability or gun")
    property = Column(pl.String, "Property name (impact_damage, ability_cooldown, ...)")
    value = Column(pl.Float64, "Base value of the property, null when it only scales")
    scale_stat = Column(pl.String, "Stat the property scales with, null when it does not scale")
    scale = Column(pl.Float64, "Scale factor applied to scale_stat")
    era_from = ERA_FROM
    client_version = CLIENT_VERSION


class AbilityUpgradeHistory(Table):
    """One row per tier upgrade entry per era."""

    ability_class = Column(pl.String, "Engine class name of the ability or gun")
    tier = Column(pl.Int64, "Upgrade tier 1-3")
    property = Column(pl.String, "Property the upgrade changes")
    bonus = Column(pl.Float64, "Amount the upgrade adds or multiplies")
    type = Column(
        pl.String,
        "How the bonus applies (add_to_base, multiply_base, add_to_scale, ...), null for add_to_base",
    )
    stat = Column(pl.String, "Stat a scale upgrade targets, null when it uses the property default")
    era_from = ERA_FROM
    client_version = CLIENT_VERSION


class AbilityWeaponHistory(Table):
    """One row per gun per era with the full weapon stat block."""

    ability_class = Column(pl.String, "Engine class name of the gun")
    era_from = ERA_FROM
    client_version = CLIENT_VERSION

    @classmethod
    def spec(cls) -> dict[str, Column]:
        """Slot the weapon stat columns between the class name and the era grain."""
        base = super().spec()
        weapon = {
            f: Column(pl.Float64, WEAPON_FIELD_DESCRIPTIONS[f]) for f in WEAPON_HISTORY_FIELDS
        }

        return {
            "ability_class": base["ability_class"],
            **weapon,
            "era_from": base["era_from"],
            "client_version": base["client_version"],
        }


class RankHistory(Table):
    """One row per badge tier per era."""

    tier = Column(pl.Int64, "Badge tier number")
    name = Column(pl.String, "Rank name (Initiate, Eternus, ...)")
    era_from = ERA_FROM
    client_version = CLIENT_VERSION


TABLES: dict[str, dict[str, Column]] = {
    "matches": Matches.spec(),
    "players": Players.spec(),
    "stats": Stats.spec(),
    "soul_sources": SoulSources.spec(),
    "item_events": ItemEvents.spec(),
    "accolades": Accolades.spec(),
    "damage": Damage.spec(),
    "damage_sources": DamageSources.spec(),
    "mid_boss": MidBoss.spec(),
    "objectives": Objectives.spec(),
    "movement": Movement.spec(),
    "deaths": Deaths.spec(),
    "downloads": Downloads.spec(),
    "item_history": ItemHistory.spec(),
    "item_component_history": ItemComponentHistory.spec(),
    "hero_history": HeroHistory.spec(),
    "hero_level_history": HeroLevelHistory.spec(),
    "hero_stat_history": HeroStatHistory.spec(),
    "hero_level_up_history": HeroLevelUpHistory.spec(),
    "ability_history": AbilityHistory.spec(),
    "ability_property_history": AbilityPropertyHistory.spec(),
    "ability_upgrade_history": AbilityUpgradeHistory.spec(),
    "ability_weapon_history": AbilityWeaponHistory.spec(),
    "rank_history": RankHistory.spec(),
}

ASSET_TABLES = frozenset(
    {
        "item_history",
        "item_component_history",
        "hero_history",
        "hero_level_history",
        "hero_stat_history",
        "hero_level_up_history",
        "ability_history",
        "ability_property_history",
        "ability_upgrade_history",
        "ability_weapon_history",
        "rank_history",
    }
)


PARTITIONED = frozenset(TABLES) - ASSET_TABLES - {"downloads"}


IDENTITY: dict[str, tuple[str, ...]] = {
    "matches": ("match_id",),
    "players": ("match_id", "account_id"),
    "stats": ("match_id", "account_id", "time_stamp_s"),
    "soul_sources": ("match_id", "account_id", "time_stamp_s", "source"),
    "item_events": ("match_id", "account_id", "game_time_s", "item_id"),
    "accolades": ("match_id", "account_id", "accolade_id"),
    "damage": ("match_id", "dealer_account_id", "target_player_slot", "source_class", "stat"),
    "damage_sources": (
        "match_id",
        "dealer_account_id",
        "source_class",
        "stat",
        "vs_heroes",
        "time_stamp_s",
    ),
    "mid_boss": ("match_id", "destroyed_time_s"),
    "objectives": ("match_id", "team", "objective_id"),
    "movement": ("match_id", "account_id", "game_time_s"),
    "deaths": ("match_id", "account_id", "game_time_s"),
}


def is_partitioned(table: str) -> bool:
    """Whether a table is stored as a directory of month files rather than a single parquet."""
    return table in PARTITIONED


def partition_dir(table: str, parquet_dir: str | Path) -> Path:
    """Directory that holds a partitioned table's per-month parquet files."""
    return Path(parquet_dir) / table


def table_path(table: str, parquet_dir: str | Path) -> Path:
    """Path to a single-file table parquet (asset tables live under the assets subfolder).

    Partitioned tables live in a directory instead. Callers that need to read them
    go through queries.scan, which tolerates both layouts.
    """
    parquet_dir = Path(parquet_dir)

    if table in ASSET_TABLES:
        return parquet_dir / "assets" / f"{table}.parquet"

    return parquet_dir / f"{table}.parquet"


def conform(name: str, rows: list[dict] | pl.DataFrame) -> pl.DataFrame:
    """Build one table from rows or a prebuilt frame, enforcing the declared columns and dtypes."""
    spec = TABLES[name]
    got = set(rows.columns) if isinstance(rows, pl.DataFrame) else set(rows[0]) if rows else None

    if got is not None:
        missing = sorted(set(spec) - got)
        extra = sorted(got - set(spec))

        if missing or extra:
            msg = f"{name} drifted from schemas.py: missing={missing} extra={extra}"
            raise ValueError(msg)

    if isinstance(rows, pl.DataFrame):
        return rows.select(pl.col(c).cast(col.dtype) for c, col in spec.items())

    return pl.DataFrame(rows, schema={c: col.dtype for c, col in spec.items()})


def describe(table: str | None = None) -> str:
    """Data dictionary as text, one table or all of them when table is None."""
    if table is not None and table not in TABLES:
        known = ", ".join(TABLES)
        msg = f"Unknown table {table!r}, tables: {known}"
        raise ValueError(msg)

    names = [table] if table else list(TABLES)
    lines = []

    for n in names:
        lines.append(n)
        width = max(len(c) for c in TABLES[n])

        for c, col in TABLES[n].items():
            d = col.dtype
            dtype = (
                f"Datetime[{d.time_unit}, {d.time_zone}]" if isinstance(d, pl.Datetime) else str(d)
            )
            lines.append(f"  {c:<{width}}  {dtype:<18} {col.description}")

        lines.append("")

    return "\n".join(lines).rstrip()
