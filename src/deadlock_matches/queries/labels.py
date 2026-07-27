"""Current asset labels derived from stable ids and engine class names.

These expressions deliberately live on the read side. Match parquet stores the
wire ids/classes, while display names follow the current asset snapshot without
requiring the archive to be rebuilt after a rename.
"""

from __future__ import annotations

import polars as pl

from deadlock_matches import extract
from deadlock_matches.assets import abilities, accolades, heroes, items


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


def with_damage_source_name(frame: pl.LazyFrame, column: str = "source_class") -> pl.LazyFrame:
    """Add the conventional ``source_name`` display column to a frame."""
    return frame.with_columns(damage_source_name(column).alias("source_name"))


def with_stack_labels(frame: pl.LazyFrame, column: str = "ability_id") -> pl.LazyFrame:
    """Add current ``class_name`` and ``name`` columns to stack rows."""
    return frame.with_columns(
        stack_class_name(column).alias("class_name"),
        stack_name(column).alias("name"),
    )
