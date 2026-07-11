"""Resolve hero IDs to names and base stats from the assets API data."""

from __future__ import annotations

import datetime as dt
import functools
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from deadlock_matches import history

HEROES_JSON = Path(__file__).parent / "data" / "heroes.json"
HERO_HISTORY_PARQUET = Path(__file__).parent / "data" / "hero_history.parquet"


@dataclass(frozen=True, slots=True)
class CostBonus:
    """One step of the investment bonus curve for a shop category."""

    souls: int
    bonus: float


@dataclass(frozen=True, slots=True)
class LevelInfo:
    """One row of the hero level table."""

    level: int
    required_souls: int
    standard_upgrade: bool
    currencies: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Hero:
    """One Deadlock hero, with the fields useful for match analysis."""

    id: int
    name: str
    class_name: str
    hero_type: str | None
    gun_tag: str | None
    complexity: int | None
    tags: tuple[str, ...]
    player_selectable: bool
    disabled: bool
    stats: dict[str, float] = field(default_factory=dict)
    level_up: dict[str, float] = field(default_factory=dict)
    levels: tuple[LevelInfo, ...] = ()
    purchase_bonuses: dict[str, Any] = field(default_factory=dict)
    cost_bonuses: dict[str, tuple[CostBonus, ...]] = field(default_factory=dict)
    scaling_stats: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_record(cls, rec: dict[str, Any]) -> Hero:
        """Build a Hero from one heroes.json record, ignoring extra keys."""
        return cls(
            id=rec["id"],
            name=rec["name"],
            class_name=rec["class_name"],
            hero_type=rec.get("hero_type"),
            gun_tag=rec.get("gun_tag"),
            complexity=rec.get("complexity"),
            tags=tuple(rec.get("tags") or ()),
            player_selectable=bool(rec.get("player_selectable")),
            disabled=bool(rec.get("disabled")),
            stats=dict(rec.get("stats") or {}),
            level_up=dict(rec.get("level_up") or {}),
            levels=tuple(
                LevelInfo(
                    level=lvl["level"],
                    required_souls=lvl.get("required_souls", 0),
                    standard_upgrade=bool(lvl.get("standard_upgrade")),
                    currencies=tuple(lvl.get("currencies") or ()),
                )
                for lvl in rec.get("levels") or []
            ),
            purchase_bonuses=dict(rec.get("purchase_bonuses") or {}),
            cost_bonuses={
                slot: tuple(CostBonus(souls=b["souls"], bonus=b["bonus"]) for b in bonuses)
                for slot, bonuses in (rec.get("cost_bonuses") or {}).items()
            },
            scaling_stats=dict(rec.get("scaling_stats") or {}),
        )

    def investment_bonus(self, slot: str, spent: int) -> float:
        """Cumulative shop category bonus for souls spent in a slot type.

        slot is a shop category: weapon, vitality or spirit.
        """
        bonus = 0.0

        for step in self.cost_bonuses.get(slot, ()):
            if spent >= step.souls:
                bonus = step.bonus

        return bonus

    def level_for_souls(self, souls: int) -> int:
        """Level reached at a given soul count.

        souls is the total earned, buying items does not reduce it.
        """
        level = 0

        for info in self.levels:
            if souls >= info.required_souls:
                level = info.level

        return level

    def standard_levels(self, level: int) -> int:
        """How many level-ups applied the standard stat boon by this level."""
        return sum(1 for info in self.levels if info.level <= level and info.standard_upgrade)

    def base_health(self, level: int) -> float:
        """Base max health at a level, before items and shop tier bonuses."""
        per_level = self.level_up.get("base_health_from_level", 0.0)

        return self.stats.get("max_health", 0.0) + per_level * self.standard_levels(level)

    def spirit_power(self, level: int) -> float:
        """Spirit power from level boons alone."""
        return self.level_up.get("tech_power", 0.0) * self.standard_levels(level)

    def bullet_damage_bonus(self, level: int) -> float:
        """Extra damage per bullet from level boons."""
        per_level = self.level_up.get("base_bullet_damage_from_level", 0.0)

        return per_level * self.standard_levels(level)

    def melee_damage(self, level: int) -> tuple[float, float]:
        """Light and heavy melee damage at a level.

        The melee boon adds to light, heavy keeps the base heavy/light ratio.
        """
        light = self.stats.get("light_melee_damage", 0.0)
        heavy = self.stats.get("heavy_melee_damage", 0.0)
        bonus = self.level_up.get("base_melee_damage_from_level", 0.0) * self.standard_levels(level)
        ratio = heavy / light if light else 0.0

        return light + bonus, heavy + bonus * ratio

    def ability_points(self, level: int) -> int:
        """Ability points earned by a level."""
        return self._currency("ability_points", level)

    def ability_unlocks(self, level: int) -> int:
        """Ability unlocks earned by a level."""
        return self._currency("ability_unlocks", level)

    def _currency(self, name: str, level: int) -> int:
        """Count one bonus currency over the levels reached."""
        return sum(info.currencies.count(name) for info in self.levels if info.level <= level)

    def boon_stats(self, level: int) -> dict[str, float | int]:
        """Everything the level boons change, at one level."""
        light, heavy = self.melee_damage(level)

        return {
            "level": level,
            "max_health": self.base_health(level),
            "spirit_power": self.spirit_power(level),
            "bullet_damage_bonus": self.bullet_damage_bonus(level),
            "light_melee_damage": light,
            "heavy_melee_damage": heavy,
            "ability_points": self.ability_points(level),
            "ability_unlocks": self.ability_unlocks(level),
        }

    def stats_at(self, souls: int) -> dict[str, float | int]:
        """Boon stats at a soul count."""
        return {"souls": souls, **self.boon_stats(self.level_for_souls(souls))}


@functools.cache
def hero_map(path: Path = HEROES_JSON) -> dict[int, Hero]:
    """Load heroes.json into {hero_id: Hero}, cached per path."""
    records = json.loads(Path(path).read_text(encoding="utf-8"))

    return {rec["id"]: Hero.from_record(rec) for rec in records}


def hero_name(hero_id: int, path: Path = HEROES_JSON) -> str:
    """Name for a hero ID, or "id<N>" when the ID is unknown."""
    hero = hero_map(path).get(hero_id)

    return hero.name if hero else f"id{hero_id}"


def hero_asof(
    hero_id: int, when: dt.datetime | dt.date, path: Path = HERO_HISTORY_PARQUET
) -> Hero | None:
    """Return the hero stats and scaling in effect at the given time.

    - latest era on or before `when`
    - times older than all history get the earliest era
    - no history at all falls back to the bundled current snapshot
    """
    if not history.has_history(path):
        return hero_map().get(hero_id)

    rec = history.record_asof(path, hero_id, when)

    return Hero.from_record(rec) if rec else None


def normalize_name(name: str) -> str:
    """Lowercases a display name and strips everything but letters and digits.

    "Mo & Krill" and "mo krill" both become "mokrill", so names with shell
    characters match without quoting them exactly.
    """
    return re.sub(r"[^a-z0-9]", "", name.lower())


def hero_id_by_name(name: str, path: Path = HEROES_JSON) -> int | None:
    """Look up the hero ID for a display name ("Mirage", "mo krill")."""
    wanted = normalize_name(name)

    for hero in hero_map(path).values():
        if normalize_name(hero.name) == wanted:
            return hero.id

    return None
