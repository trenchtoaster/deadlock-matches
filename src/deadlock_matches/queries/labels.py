"""Labels derived at read time from the stable ids and engine classes in parquet.

These expressions deliberately live on the read side. Match parquet stores the
wire ids/classes, display names come from the current asset snapshot or the
mappings here, so a rename or a mapping fix never requires a rebuild.
"""

from __future__ import annotations

from enum import IntEnum

import polars as pl

from deadlock_matches import extract
from deadlock_matches.assets import abilities, accolades, heroes, items


class GoldSource(IntEnum):
    """Income source IDs in snapshot gold_sources rows (protobuf EGoldSource)."""

    PLAYERS = 1
    LANE_CREEPS = 2
    NEUTRALS = 3
    BOSSES = 4
    TREASURE = 5
    ASSISTS = 6
    DENIES = 7
    TEAM_BONUS = 8
    ABILITY_ASSASSINATE = 9
    ITEM_TROPHY_COLLECTOR = 10
    ITEM_CULTIST_SACRIFICE = 11
    BREAKABLE = 12
    ITEM_GOOSE_EGG = 13


SOUL_SOURCE_NAMES = {
    GoldSource.PLAYERS: "players",
    GoldSource.LANE_CREEPS: "troopers",
    GoldSource.NEUTRALS: "jungle",
    GoldSource.BOSSES: "bosses",
    GoldSource.TREASURE: "treasure",
    GoldSource.ASSISTS: "assists",
    GoldSource.DENIES: "denies",
    GoldSource.TEAM_BONUS: "team_bonus",
    GoldSource.ABILITY_ASSASSINATE: "assassinate",
    GoldSource.ITEM_TROPHY_COLLECTOR: "trophy_collector",
    GoldSource.ITEM_CULTIST_SACRIFICE: "cultist_sacrifice",
    GoldSource.BREAKABLE: "breakables",
    GoldSource.ITEM_GOOSE_EGG: "goose_egg",
}

LANE_NAMES = {1: "yellow", 4: "blue", 6: "green"}

OBJECTIVE_LANES = {1: "yellow", 3: "blue", 4: "green"}

OBJECTIVE_NAMES = {
    0: "Weakened Patron",
    9: "Patron",
    10: "Shrine",
    11: "Shrine",
}
OBJECTIVE_NAMES.update(dict.fromkeys((1, 2, 3, 4), "Guardian"))
OBJECTIVE_NAMES.update({i + 4: "Walker" for i in (1, 2, 3, 4)})
OBJECTIVE_NAMES.update({i + 11: "Base Guardians" for i in (1, 2, 3, 4)})

OBJECTIVE_LANE_IDS = {i: i for i in (1, 2, 3, 4)}
OBJECTIVE_LANE_IDS.update({i + 4: i for i in (1, 2, 3, 4)})
OBJECTIVE_LANE_IDS.update({i + 11: i for i in (1, 2, 3, 4)})

OBJECTIVE_LANE_NAMES = {
    objective_id: OBJECTIVE_LANES.get(lane) for objective_id, lane in OBJECTIVE_LANE_IDS.items()
}


def match_mode_name(column: str = "match_mode") -> pl.Expr:
    """Turn a match mode number into its readable name.

    - the names come from the compiled protobuf enum
    - value 1 reads as Matchmaking because Deadlock has one queue, and the
      protobuf calls it Unranked only as a holdover
    """
    return pl.col(column).replace_strict(extract.MATCH_MODES, default=None, return_dtype=pl.String)


def game_mode_name(column: str = "game_mode") -> pl.Expr:
    """Turn a game mode number into its readable name such as Street Brawl."""
    return pl.col(column).replace_strict(extract.GAME_MODES, default=None, return_dtype=pl.String)


def soul_source_name(column: str = "source") -> pl.Expr:
    """Turn an income source id into its slug such as troopers or jungle.

    - the ids follow the protobuf EGoldSource enum, the slugs follow the
      in game vocabulary
    - an unknown id reads as its number rather than going null
    """
    mapping = {int(source): name for source, name in SOUL_SOURCE_NAMES.items()}
    source = pl.col(column)

    return source.replace_strict(
        mapping,
        default=source.cast(pl.String),
        return_dtype=pl.String,
    )


def lane_name(column: str = "assigned_lane") -> pl.Expr:
    """Turn a starting lane engine id into its color.

    - 1/4/6 are the three lanes on the current map, other ids go null
    """
    return pl.col(column).replace_strict(LANE_NAMES, default=None, return_dtype=pl.String)


def objective_name(column: str = "objective_id") -> pl.Expr:
    """Turn an ECitadelTeamObjective id into the objective it names.

    - tier 1 ids read as Guardian, tier 2 as Walker, barrack bosses as
      Base Guardians, shield generators as Shrine
    - an unknown id goes null
    """
    return pl.col(column).replace_strict(OBJECTIVE_NAMES, default=None, return_dtype=pl.String)


def objective_lane(column: str = "objective_id") -> pl.Expr:
    """Turn an ECitadelTeamObjective id into the color of its lane.

    - laneless objectives such as the patron go null, as does the retired
      fourth lane
    """
    return pl.col(column).replace_strict(OBJECTIVE_LANE_NAMES, default=None, return_dtype=pl.String)


def buff_family(column: str = "type") -> pl.Expr:
    """Pull the buff family out of a pickup engine class name.

    - hp_permanent_pickup_lv2 and hp_powerup_pickup both read as hp
    - an unrecognized class name goes null
    """
    return pl.coalesce(
        pl.col(column).str.extract(r"^(\w+?)_permanent_pickup(?:_lv\d+)?$", 1),
        pl.col(column).str.extract(r"^(\w+?)_powerup_pickup$", 1),
    )


def buff_level(column: str = "type") -> pl.Expr:
    """Pull the statue level out of a pickup engine class name.

    - the unsuffixed statue name is level 1
    - the timed bridge buffs and unrecognized class names go null
    """
    statue = pl.col(column).str.extract(r"^(\w+?)_permanent_pickup(?:_lv\d+)?$", 1)
    level = pl.col(column).str.extract(r"^\w+?_permanent_pickup_lv(\d+)$", 1).cast(pl.Int64)

    return pl.when(statue.is_not_null()).then(level.fill_null(1)).otherwise(None)


def hero_name(column: str = "hero_id") -> pl.Expr:
    """Resolve a hero id to its current display name.

    - an unknown id reads as id<N> rather than going null
    """
    mapping = {hero_id: hero.name for hero_id, hero in heroes.hero_map().items()}
    hero_id = pl.col(column)

    return (
        pl.when(hero_id.is_null())
        .then(pl.lit(None, dtype=pl.String))
        .otherwise(
            hero_id.replace_strict(
                mapping,
                default=pl.concat_str(pl.lit("id"), hero_id),
                return_dtype=pl.String,
            )
        )
    )


def damage_source_name(column: str = "source_class") -> pl.Expr:
    """Resolve an engine damage class to its current display label.

    - unknown engine classes stay readable as their raw class name
    - UnknownAbility reads as Unknown ability, the game emits it for ability
      damage it never resolved to a source class
    - a crit class takes the ``(crit)`` suffix only when its base class has a
      display name of its own, so the ~200 assets whose name is just their class
      name keep the raw ``<class>_crit`` form that abilities.label produced
    """
    mapping: dict[str, str] = {}

    for ability in abilities.ability_map().values():
        mapping[ability.class_name] = ability.name

    for item in items.item_map().values():
        if item.class_name:
            mapping.setdefault(item.class_name, item.name)

    mapping |= {
        f"{class_name}_crit": f"{name} (crit)"
        for class_name, name in mapping.items()
        if name != class_name
    }

    mapping["UnknownAbility"] = "Unknown ability"

    source_class = pl.col(column)

    return source_class.replace_strict(
        mapping,
        default=source_class,
        return_dtype=pl.String,
    )


def imbued_ability_name(column: str = "imbued_ability_id") -> pl.Expr:
    """Resolve an imbued ability id to its current display name."""
    mapping = {ability.id: ability.name for ability in abilities.ability_map().values()}

    return pl.col(column).replace_strict(mapping, default=None, return_dtype=pl.String)


def accolade_name(column: str = "accolade_id") -> pl.Expr:
    """Resolve an accolade id to the current stat class it grades."""
    mapping = {
        accolade_id: accolade.class_name
        for accolade_id, accolade in accolades.accolade_map().items()
    }

    return pl.col(column).replace_strict(mapping, default=None, return_dtype=pl.String)


def stack_class_name(column: str = "ability_id") -> pl.Expr:
    """Resolve a stack counter id to its current item or ability engine class."""
    classes, _ = _stack_labels()

    return pl.col(column).replace_strict(classes, default=None, return_dtype=pl.String)


def stack_name(column: str = "ability_id") -> pl.Expr:
    """Resolve a stack counter id to its current item or ability display name."""
    _, names = _stack_labels()

    return pl.col(column).replace_strict(names, default=None, return_dtype=pl.String)


def _stack_labels() -> tuple[dict[int, str], dict[int, str]]:
    """Build the stack id lookups for engine classes and display names.

    - an item wins over an ability sharing the id, matching what the export did
    """
    classes = {ability.id: ability.class_name for ability in abilities.ability_map().values()}
    names = {ability.id: ability.name for ability in abilities.ability_map().values()}

    for item_id, item in items.item_map().items():
        if item.class_name:
            classes[item_id] = item.class_name
            names[item_id] = item.name

    return classes, names


def with_hero_name(frame: pl.LazyFrame, column: str = "hero_id") -> pl.LazyFrame:
    """Add the conventional ``hero`` display column to a frame."""
    return frame.with_columns(hero_name(column).alias("hero"))


def with_soul_source_name(frame: pl.LazyFrame, column: str = "source") -> pl.LazyFrame:
    """Add the conventional ``source_name`` slug column to soul source rows."""
    return frame.with_columns(soul_source_name(column).alias("source_name"))


def with_lane_name(frame: pl.LazyFrame, column: str = "assigned_lane") -> pl.LazyFrame:
    """Add the conventional ``lane`` color column to player rows."""
    return frame.with_columns(lane_name(column).alias("lane"))


def with_objective_labels(frame: pl.LazyFrame, column: str = "objective_id") -> pl.LazyFrame:
    """Add the ``objective`` and ``lane`` columns to objective rows."""
    return frame.with_columns(
        objective_name(column).alias("objective"),
        objective_lane(column).alias("lane"),
    )


def with_buff_labels(frame: pl.LazyFrame, column: str = "type") -> pl.LazyFrame:
    """Add the ``buff`` and ``level`` columns to buff pickup rows."""
    return frame.with_columns(
        buff_family(column).alias("buff"),
        buff_level(column).alias("level"),
    )


def with_damage_source_name(frame: pl.LazyFrame, column: str = "source_class") -> pl.LazyFrame:
    """Add the conventional ``source_name`` display column to a frame."""
    return frame.with_columns(damage_source_name(column).alias("source_name"))


def with_stack_labels(frame: pl.LazyFrame, column: str = "ability_id") -> pl.LazyFrame:
    """Add current ``class_name`` and ``name`` columns to stack rows."""
    return frame.with_columns(
        stack_class_name(column).alias("class_name"),
        stack_name(column).alias("name"),
    )
