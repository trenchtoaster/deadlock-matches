"""The data model for the parquet tables, a dtype and description per column.

- one class per table, one Column attribute per column
- export conforms every table to this before writing, so a new column
  without an entry here fails loudly instead of shipping undocumented
- `deadlock schema` prints it as a data dictionary
"""

from __future__ import annotations

from dataclasses import dataclass
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


class Table:
    """Base for table models, where spec() collects the Column attributes in order."""

    @classmethod
    def spec(cls) -> dict[str, Column]:
        """The table's columns as {name: Column}, in declaration order."""
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
        "Shop price in souls from the assets snapshot in effect at match time (see assets_date)",
    )
    slot = Column(pl.String, "Shop slot: weapon/vitality/spirit")
    tier = Column(pl.Int64, "Item tier 1-4")
    sold_time_s = Column(pl.Int64, "When it left the inventory (sold or consumed), 0 if kept")
    flags = Column(pl.Int64, "1 = consumed as a component of an upgrade, NOT a sell, 0 = normal")
    attribution = Column(
        pl.String,
        "How the item's value shows up in damage: 'proc' = has its own damage rows (Scourge, Escalating Exposure), 'stat' = value hides inside other rows (Boundless Spirit, Echo Shard)",
    )
    assets_date = Column(
        pl.Date,
        "Date of the dated assets snapshot that priced this row, null = bundled current snapshot (no history yet covered this match)",
    )


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
    """One row per objective: guardians, walkers, base guardians, shrines, and the patron."""

    match_id = MATCH_ID
    team = Column(pl.Int64, "Team the objective belonged to")
    objective_id = Column(pl.Int64, "Raw ECitadelTeamObjective id")
    objective = Column(
        pl.String, "Guardian, Walker, Base Guardians, Shrine, Patron, or Weakened Patron"
    )
    lane = Column(pl.String, "Color of its lane")
    destroyed_time_s = Column(pl.Int64, "Game time in seconds when it was destroyed")
    first_damage_time_s = Column(pl.Int64, "Game time in seconds when it first took damage")
    player_damage = Column(pl.Int64, "Damage dealt to it by players")
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
    time_to_kill_s = Column(pl.Float64, "How long the killing burst took, in seconds")
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


TABLES: dict[str, dict[str, Column]] = {
    "matches": Matches.spec(),
    "players": Players.spec(),
    "stats": Stats.spec(),
    "soul_sources": SoulSources.spec(),
    "item_events": ItemEvents.spec(),
    "damage": Damage.spec(),
    "damage_sources": DamageSources.spec(),
    "mid_boss": MidBoss.spec(),
    "objectives": Objectives.spec(),
    "movement": Movement.spec(),
    "deaths": Deaths.spec(),
    "downloads": Downloads.spec(),
}


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
