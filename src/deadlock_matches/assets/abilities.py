"""Resolve ability and weapon class names to display names and base numbers from the assets API data."""

from __future__ import annotations

import datetime as dt
import functools
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

from deadlock_matches.assets import heroes, history, items

ABILITIES_JSON = Path(__file__).parent / "data" / "abilities.json"
ABILITY_HISTORY_PARQUET = Path(__file__).parent / "data" / "ability_history.parquet"


@dataclass(frozen=True, slots=True)
class Ability:
    """One hero ability or gun.

    - properties: base numbers ({damage: 65, ability_cooldown: 36})
    - scaling: which stat a property scales with ({damage: {stat: tech_power, scale: 0.3}})
    - upgrades: bonus entries per tier, type add_to_scale means it changes scaling not the base
    - tier_descriptions: the tier texts the game shows, aligned with upgrades
    """

    id: int
    name: str
    class_name: str
    hero: int | None
    kind: str
    description: str | None = None
    weapon: dict[str, Any] = field(default_factory=dict)
    ability_type: str | None = None
    boss_damage_scale: float | None = None
    behaviours: tuple[str, ...] = ()
    properties: dict[str, Any] = field(default_factory=dict)
    scaling: dict[str, Any] = field(default_factory=dict)
    damage_types: dict[str, str] = field(default_factory=dict)
    scale_types: dict[str, str] = field(default_factory=dict)
    negatives: tuple[str, ...] = ()
    conditionals: dict[str, str] = field(default_factory=dict)
    upgrades: tuple[tuple[dict[str, Any], ...], ...] = ()
    tier_descriptions: tuple[str | None, ...] = ()

    @classmethod
    def from_record(cls, rec: dict[str, Any]) -> Ability:
        """Build an Ability from one abilities.json record."""
        return cls(
            id=rec["id"],
            name=rec["name"],
            class_name=rec["class_name"],
            hero=rec.get("hero"),
            kind=rec.get("kind") or "ability",
            description=rec.get("description"),
            weapon=dict(rec.get("weapon") or {}),
            ability_type=rec.get("ability_type"),
            boss_damage_scale=rec.get("boss_damage_scale"),
            behaviours=tuple(rec.get("behaviours") or ()),
            properties=dict(rec.get("properties") or {}),
            scaling=dict(rec.get("scaling") or {}),
            damage_types=dict(rec.get("damage_types") or {}),
            scale_types=dict(rec.get("scale_types") or {}),
            negatives=tuple(rec.get("negatives") or ()),
            conditionals=dict(rec.get("conditionals") or {}),
            upgrades=tuple(tuple(dict(up) for up in tier) for tier in rec.get("upgrades") or []),
            tier_descriptions=tuple(rec.get("tier_descriptions") or ()),
        )

    def stat(self, name: str, tier: int = 0) -> float:
        """Apply flat upgrade bonuses to the base value of a property through a tier."""
        value = float(self.properties.get(name, 0.0))

        for up in self._tier_upgrades(tier):
            if up["property"] != name:
                continue

            kind = up.get("type", "add_to_base")

            if kind == "add_to_base":
                value += up["bonus"]
            elif kind == "multiply_base":
                value *= up["bonus"]

        return value

    def scaling_at(self, name: str, tier: int = 0) -> dict[str, float]:
        """Apply scale upgrades to the scaling of a property ({tech_power: 0.3}) through a tier.

        An upgrade with no stat of its own applies to the scaling stat of the
        property, tech_power when it has none.
        """
        info = self.scaling.get(name)
        default_stat = info["stat"] if info else "tech_power"
        out = {info["stat"]: float(info["scale"])} if info else {}

        for up in self._tier_upgrades(tier):
            if up["property"] != name:
                continue

            kind = up.get("type")
            stat = up.get("stat", default_stat)

            if kind == "add_to_scale":
                out[stat] = out.get(stat, 0.0) + up["bonus"]
            elif kind == "multiply_scale":
                out[stat] = out.get(stat, 0.0) * up["bonus"]

        return {stat: scale for stat, scale in out.items() if scale}

    def spirit_scale(self, name: str, tier: int = 0) -> float:
        """Reads the spirit power multiplier on a property at an upgrade tier."""
        return self.scaling_at(name, tier).get("tech_power", 0.0)

    def _tier_upgrades(self, tier: int) -> Iterator[dict[str, Any]]:
        """Iterate the upgrade entries through a tier."""
        for entries in self.upgrades[:tier]:
            yield from entries


@functools.cache
def ability_map(path: Path = ABILITIES_JSON) -> dict[str, Ability]:
    """Load abilities.json into {class_name: Ability}, cached per path."""
    records = json.loads(Path(path).read_text(encoding="utf-8"))

    return {rec["class_name"]: Ability.from_record(rec) for rec in records}


def ability_asof(
    class_name: str, when: dt.datetime | dt.date, path: Path = ABILITY_HISTORY_PARQUET
) -> Ability | None:
    """Return the ability tuning in effect at the given time.

    - latest era on or before `when`
    - times older than all history get the earliest era
    - no history at all falls back to the bundled current snapshot
    """
    if not history.has_history(path):
        return ability_map().get(class_name)

    rec = history.record_asof(path, class_name, when)

    return Ability.from_record(rec) if rec else None


def ability_by_name(
    name: str, hero_id: int | None = None, path: Path = ABILITIES_JSON
) -> Ability | None:
    """Look up an ability or gun by display name ("Dust Devil", "djinns mark").

    Pass hero_id when the name exists on several heroes, without it an
    ambiguous name raises ValueError.
    """
    wanted = heroes.normalize_name(name)
    matches = [
        a
        for a in ability_map(path).values()
        if heroes.normalize_name(a.name) == wanted and (hero_id is None or a.hero == hero_id)
    ]
    owners = sorted({heroes.hero_name(a.hero) for a in matches if a.hero})

    if len(owners) > 1:
        shown = ", ".join(owners[:8]) + (f" (+{len(owners) - 8} more)" if len(owners) > 8 else "")
        msg = f"{name!r} is on several heroes: {shown}"
        raise ValueError(msg)

    return matches[0] if matches else None


def for_hero(hero_id: int, path: Path = ABILITIES_JSON) -> tuple[Ability, ...]:
    """List the abilities for a hero."""
    return tuple(a for a in ability_map(path).values() if a.hero == hero_id and a.kind == "ability")


def hero_gun(hero_id: int, path: Path = ABILITIES_JSON) -> Ability | None:
    """Look up the gun and weapon stats for a hero."""
    for ability in ability_map(path).values():
        if ability.hero == hero_id and ability.kind == "weapon":
            return ability

    return None


def hero_alt_gun(hero_id: int, path: Path = ABILITIES_JSON) -> Ability | None:
    """Look up the alt-fire weapon for a hero with a second firing mode.

    The alt record shares the primary display name or has none, so it
    cannot be reached by name.
    """
    for ability in ability_map(path).values():
        if (
            ability.hero == hero_id
            and ability.kind == "weapon"
            and ability.class_name.endswith(("_alt", "_set_2"))
        ):
            return ability

    return None


def string_token(name: str) -> int:
    """Hash a class name the way the engine makes string tokens.

    MurmurHash2 with seed 0x31415926 — ability ids on the wire and asset
    ids are both this hash of the engine class name.
    """
    m = 0x5BD1E995
    h = (0x31415926 ^ len(name)) & 0xFFFFFFFF
    data = name.encode()

    while len(data) >= 4:
        k = (int.from_bytes(data[:4], "little") * m) & 0xFFFFFFFF
        k ^= k >> 24
        h = (((h * m) & 0xFFFFFFFF) ^ ((k * m) & 0xFFFFFFFF)) & 0xFFFFFFFF
        data = data[4:]

    if len(data) == 3:
        h ^= data[2] << 16

    if len(data) >= 2:
        h ^= data[1] << 8

    if len(data) >= 1:
        h = ((h ^ data[0]) * m) & 0xFFFFFFFF

    h ^= h >> 13
    h = (h * m) & 0xFFFFFFFF

    return h ^ h >> 15


@functools.cache
def _token_map(path: Path = ABILITIES_JSON) -> dict[int, str]:
    """Map string tokens back to the ability class names they hash from."""
    return {string_token(name): name for name in ability_map(path)}


def class_by_token(token: int, path: Path = ABILITIES_JSON) -> str | None:
    """Reverse a string token to an ability class name, None when unknown."""
    return _token_map(path).get(token)


def label(class_name: str, path: Path = ABILITIES_JSON) -> str:
    """Display name for a damage source class_name, whether ability, gun, or item.

    Gun headshot damage comes in as <gun class>_crit and resolves to
    "<gun name> (crit)". Falls back to the raw class_name for engine
    sources like "Bullet".
    """
    if class_name.endswith("_crit"):
        base = label(class_name.removesuffix("_crit"), path)

        if base != class_name.removesuffix("_crit"):
            return f"{base} (crit)"

        return class_name

    ability = ability_map(path).get(class_name)
    if ability:
        return ability.name

    item = items.item_by_class_name(class_name)
    if item:
        return item.name

    return class_name
