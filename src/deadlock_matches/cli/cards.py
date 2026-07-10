"""The hero, ability, and item stat cards."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from deadlock_matches import abilities, heroes, history, items

if TYPE_CHECKING:
    import argparse
    from pathlib import Path

UNITS_PER_METER = 39.37


def _as_of_note(when: dt.date | None) -> str:
    """Return a trailing as-of label for a card header, or empty when current."""
    return f"  (as of {when:%Y-%m-%d})" if when is not None else ""


def _hero_asof(hero_id: int, when: dt.date | None) -> heroes.Hero | None:
    """Resolve a hero from the era live at when, or the current snapshot when None."""
    if when is None:
        return heroes.hero_map().get(hero_id)

    return heroes.hero_asof(hero_id, when) or heroes.hero_map().get(hero_id)


def _ability_asof(gun: abilities.Ability | None, when: dt.date | None) -> abilities.Ability | None:
    """Resolve a weapon ability as of when, keeping the current one when None or missing."""
    if gun is None or when is None:
        return gun

    return abilities.ability_asof(gun.class_name, when) or gun


BOON_LABELS = {
    "base_health_from_level": "health",
    "base_bullet_damage_from_level": "bullet damage",
    "base_bullet_damage_from_level_alt_fire": "bullet damage (alt fire)",
    "base_melee_damage_from_level": "melee damage",
    "tech_power": "spirit power",
    "tech_resist": "spirit resist",
    "bullet_armor_damage_resist": "bullet resist",
    "bonus_attack_range": "attack range",
}


def _gun_lines(hero_id: int, bullet_bonus: float, when: dt.date | None = None) -> None:
    """Print bullet damage and dps with a boon bonus applied."""
    gun = _ability_asof(abilities.hero_gun(hero_id), when)

    if not gun or not gun.weapon.get("bullet_damage"):
        return

    base = gun.weapon["bullet_damage"]
    bullet = base + bullet_bonus
    dps = gun.weapon.get("damage_per_second", 0.0) * bullet / base

    if bullet_bonus:
        print(f"  bullet damage    {bullet:>8.1f}  ({gun.name}, {base:g} base)")
    else:
        print(f"  bullet damage    {bullet:>8.1f}  ({gun.name})")

    print(f"  gun dps          {dps:>8.1f}")


def _alt_gun_lines(hero_id: int, when: dt.date | None = None) -> None:
    """Print the alt-fire weapon damage for heroes with a second firing mode."""
    gun = _ability_asof(abilities.hero_alt_gun(hero_id), when)

    if not gun or not gun.weapon.get("bullet_damage"):
        return

    w = gun.weapon
    pellets = w.get("bullets", 1)

    print()
    print("  alt fire")
    print(f"  bullet damage    {w['bullet_damage']:>8.1f}")
    print(f"  gun dps          {w.get('damage_per_second', 0.0):>8.1f}")
    print(f"  bullets per sec  {w.get('bullets_per_second', 0.0) / pellets:>8.2f}")
    print(f"  ammo             {w.get('clip_size', 0):>8}")


def _hero_base_card(hero: heroes.Hero, hero_id: int, when: dt.date | None = None) -> None:
    """Print base stats and what each boon adds."""
    light, heavy = hero.melee_damage(1)

    print(f"{hero.name}{_as_of_note(when)}")
    _gun_lines(hero_id, 0.0, when)
    gun = _ability_asof(abilities.hero_gun(hero_id), when)

    if gun and gun.weapon:
        w = gun.weapon
        pellets = w.get("bullets", 1)

        if pellets > 1:
            print(f"  pellets per shot {pellets:>8}")

        print(f"  ammo             {w.get('clip_size', 0):>8}")
        print(f"  bullets per sec  {w.get('bullets_per_second', 0) / pellets:>8.2f}")
        print(f"  reload time      {w.get('reload_duration', 0):>8.1f}")

        if speed := w.get("bullet_speed"):
            print(f"  bullet velocity  {speed / UNITS_PER_METER:>8.0f}")

    _alt_gun_lines(hero_id, when)

    print()
    print(f"  light melee      {light:>8.1f}")
    print(f"  heavy melee      {heavy:>8.1f}")

    print()
    print(f"  max health       {hero.stats.get('max_health', 0):>8,.0f}")
    print(f"  health regen     {hero.stats.get('base_health_regen', 0):>8.1f}")

    if resist := hero.stats.get("tech_armor_damage_reduction"):
        print(f"  spirit resist    {resist:>7g}%")

    if resist := hero.stats.get("bullet_armor_damage_reduction"):
        print(f"  bullet resist    {resist:>7g}%")

    crit_taken = round((hero.stats.get("crit_damage_received_scale", 1.0) - 1) * 100)

    if crit_taken:
        print(f"  crit taken       {crit_taken:>+7d}%")

    print()
    print(f"  move speed       {hero.stats.get('max_move_speed', 0):>8.1f}")
    print(f"  sprint speed     {hero.stats.get('sprint_speed', 0):>8.1f}")

    dash = hero.stats.get("ground_dash_distance_in_meters", 0.0)
    dash_s = hero.stats.get("ground_dash_duration", 0.0)

    if dash and dash_s:
        print(f"  dash speed       {dash / dash_s:>8.1f}")

    print()
    print(f"  stamina          {hero.stats.get('stamina', 0):>8.0f}")

    if regen := hero.stats.get("stamina_regen_per_second"):
        print(f"  stamina cooldown {1 / regen:>8.1f}")

    names = _ability_names(hero_id)

    if names:
        print("\nabilities")

        for name in names:
            print(f"  {name}")

    if not hero.levels:
        return

    top = hero.levels[-1]
    boons = hero.standard_levels(top.level)
    ratio = heavy / light if light else 0.0

    print(f"\nEach boon adds ({boons} boons to level {top.level} at {top.required_souls:,} souls):")

    for key, per in hero.level_up.items():
        if key == "boon_count":
            continue

        label = BOON_LABELS.get(key, key.replace("_", " "))

        if key == "base_melee_damage_from_level" and ratio:
            print(f"  {label:<16} +{per:g} light / +{per * ratio:.2f} heavy")
        else:
            print(f"  {label:<16} +{per:g}")


def hero_report(args: argparse.Namespace) -> None:
    """Prints boon stats at a soul or level breakpoint, or the base card without one."""
    hero_id = heroes.hero_id_by_name(args.hero)

    if hero_id is None:
        print(f"Unknown hero: {args.hero}")
        return

    if getattr(args, "changes", False):
        print_changes(heroes.hero_name(hero_id), "hero", heroes.HERO_HISTORY_PARQUET, hero_id)
        return

    when = getattr(args, "as_of", None)
    hero = _hero_asof(hero_id, when)

    if hero is None:
        print(f"Unknown hero: {args.hero}")
        return

    if args.souls is None and args.level is None:
        _hero_base_card(hero, hero_id, when)
        return

    level = args.level if args.level is not None else hero.level_for_souls(args.souls)
    stats = hero.boon_stats(level)

    if args.souls is not None:
        print(f"{hero.name} at {args.souls:,} souls: level {level}{_as_of_note(when)}")
    else:
        print(f"{hero.name} at level {level}{_as_of_note(when)}")

    print(f"  max health       {stats['max_health']:>8,.0f}")
    print(f"  spirit power     {stats['spirit_power']:>8.1f}")
    print(f"  ability points   {stats['ability_points']:>8}")
    print(f"  ability unlocks  {stats['ability_unlocks']:>8}")
    print(f"  light melee      {stats['light_melee_damage']:>8.1f}")
    print(f"  heavy melee      {stats['heavy_melee_damage']:>8.1f}")
    _gun_lines(hero_id, stats["bullet_damage_bonus"], when)


def _item_stat_line(item: items.Item, prop: str, indent: str) -> str | None:
    """Formats one item property line (fire rate +22%)."""
    value = item.properties.get(prop)

    if value is None:
        return None

    info = item.labels.get(prop, {})
    label = str(info.get("label") or prop.replace("_", " ")).lower()

    if isinstance(value, str):
        shown = value
    else:
        shown = f"{value:+g}" if info.get("signed") else f"{value:g}"
        shown += str(info.get("postfix", ""))

    return f"{indent}{label:<34} {shown:>10}"


def item_card(item: items.Item, when: dt.date | None = None) -> None:
    """Prints the shop card for an item, innate stats first, then each passive or active section."""
    print(f"{item.name}  ({item.slot} tier {item.tier}, {item.cost:,} souls){_as_of_note(when)}")

    names = [c.name for c in map(items.item_by_class_name, item.components) if c]

    if names:
        print(f"  upgrades from {', '.join(names)}")

    if not item.sections:
        if item.description:
            print(f"  {item.description}")

        print()

        for prop in item.properties:
            if line := _item_stat_line(item, prop, "  "):
                print(line)

        return

    cooldown = item.properties.get("ability_cooldown")
    typed = {sec["section"] for sec in item.sections}
    fallback = "active" if item.is_active and "active" not in typed else "passive"

    for sec in item.sections:
        if sec["section"] == "innate":
            print()

            for prop in sec["properties"]:
                if line := _item_stat_line(item, prop, "  "):
                    print(line)

            continue

        note = ""

        if cooldown:
            note = f"  (cooldown {cooldown:g}s)"
            cooldown = None

        print(f"\n{(sec['section'] or fallback).capitalize()}{note}")

        if sec["text"]:
            print(f"  {sec['text']}")

        for prop in sec["properties"]:
            if line := _item_stat_line(item, prop, "  "):
                print(line)


def _scale_label(stat: str) -> str:
    """Turn tech_power into spirit and other stats into spaced words."""
    if stat == "tech_power":
        return "spirit"

    return stat.removesuffix("_damage").replace("_", " ")


def _upgrade_line(up: dict[str, Any], default_stat: str = "tech_power") -> str:
    """Formats one tier bonus (damage +60, damage +1 x spirit)."""
    name = up["property"].replace("_", " ")

    if up.get("type") in ("add_to_scale", "multiply_scale"):
        return f"{name} {up['bonus']:+g} x {_scale_label(up.get('stat', default_stat))}"

    return f"{name} {up['bonus']:+g}"


def _ability_context(hero: heroes.Hero | None, level: int) -> dict[str, float]:
    """Collects the stats at a level that ability scaling multiplies against."""
    if hero is None:
        return {}

    light, heavy = hero.melee_damage(level)

    return {
        "tech_power": hero.spirit_power(level),
        "light_melee_damage": light,
        "heavy_melee_damage": heavy,
        "level_up_boons": float(hero.standard_levels(level)),
    }


def _resolved_value(
    ability: abilities.Ability, prop: str, tier: int, ctx: dict[str, float]
) -> float:
    """Apply the context stats to the value of a property at a tier."""
    value = ability.stat(prop, tier)

    for stat, scale in ability.scaling_at(prop, tier).items():
        value += ctx.get(stat, 0.0) * scale

    return value


def _tier_changes(ability: abilities.Ability, n: int, ctx: dict[str, float]) -> list[str]:
    """Builds one line per tier bonus, before -> after where the value resolves."""
    out = []
    seen = set()

    for up in tuple(ability.upgrades[n - 1]):
        prop = up["property"]
        name = prop.replace("_", " ")
        scale_up = up.get("type") in ("add_to_scale", "multiply_scale")
        base = ability.scaling.get(prop)
        stat = str(up.get("stat", base["stat"] if base else "tech_power"))

        if not scale_up or ctx.get(stat):
            if prop in seen:
                continue

            seen.add(prop)
            before = _resolved_value(ability, prop, n - 1, ctx)
            after = _resolved_value(ability, prop, n, ctx)

            if before != after:
                out.append(f"{name} {before:.4g} -> {after:.4g}")
            elif not scale_up and prop not in ability.properties and not ability.stat(prop, n - 1):
                out.append(_upgrade_line(up))
        else:
            before = ability.scaling_at(prop, n - 1).get(stat, 0.0)
            after = ability.scaling_at(prop, n).get(stat, 0.0)

            if before != after:
                out.append(f"{name} +{before:g} -> +{after:g} x {_scale_label(stat)}")

    return out


def _ability_names(hero_id: int) -> list[str]:
    """List the four signature abilities for a hero, the names the ability command takes."""
    return [a.name for a in abilities.for_hero(hero_id) if "ability_melee" not in a.class_name]


def ability_report(args: argparse.Namespace) -> None:
    """Prints base values, scaling, and tier upgrades for an ability or gun."""
    hero_id = None

    if args.hero is not None:
        hero_id = heroes.hero_id_by_name(args.hero)

        if hero_id is None:
            print(f"Unknown hero: {args.hero}")
            return

    try:
        ability = abilities.ability_by_name(args.ability, hero_id=hero_id)
    except ValueError as e:
        print(e)
        print("Narrow it with --hero")
        return

    if ability is None:
        print(f"Unknown ability: {args.ability}")
        return

    if getattr(args, "changes", False):
        print_changes(
            ability.name, ability.kind, abilities.ABILITY_HISTORY_PARQUET, ability.class_name
        )
        return

    spirit = getattr(args, "spirit", None)

    if spirit is not None and (args.souls is not None or args.level is not None):
        print("--spirit is the total and already includes boons, drop --souls or --level")
        return

    when = getattr(args, "as_of", None)
    ability = _ability_asof(ability, when) or ability
    hero = _hero_asof(ability.hero, when) if ability.hero else None
    level = 1

    if hero and args.level is not None:
        level = args.level
    elif hero and args.souls is not None:
        level = hero.level_for_souls(args.souls)

    ctx = _ability_context(hero, level)

    if spirit is not None:
        ctx["tech_power"] = spirit

    where = []

    if args.souls is not None or args.level is not None:
        where.append(f"level {level}")

    if ctx.get("tech_power"):
        where.append(f"{ctx['tech_power']:g} spirit")

    owner = f"{heroes.hero_name(ability.hero)} " if ability.hero else ""
    note = f" at {', '.join(where)}" if where and ability.kind == "ability" else ""
    print(f"{ability.name}  ({owner}{ability.kind}{note})")

    if ability.kind == "weapon":
        for stat, value in ability.weapon.items():
            if stat.endswith("range"):
                print(f"  {stat.replace('_', ' '):<34} {value / UNITS_PER_METER:>9.1f}m")
            else:
                print(f"  {stat.replace('_', ' '):<34} {value:>10.6g}")

        return

    if ability.description:
        print(f"  {ability.description}")

    print()

    shown = dict.fromkeys([*ability.properties, *ability.scaling])

    for prop in sorted(shown):
        value = ability.stat(prop)
        scales = ability.scaling_at(prop)
        notes = []

        for stat, scale in list(scales.items()):
            if ctx.get(stat):
                value += ctx[stat] * scale
                notes.append(f"({scale:g} x {_scale_label(stat)})")
                scales.pop(stat)

        if not value and not scales:
            continue

        line = f"  {prop.replace('_', ' '):<34} {value:>10.4g}"

        for stat, scale in scales.items():
            line += f"  +{scale:g} x {_scale_label(stat)}"

        for note in notes:
            line += f"  {note}"

        print(line)

    for n in range(1, len(ability.upgrades) + 1):
        text = ability.tier_descriptions[n - 1] if n <= len(ability.tier_descriptions) else None
        changes = ", ".join(_tier_changes(ability, n, ctx))

        if text:
            print(f"\n  T{n}  {text}")

            if changes:
                print(f"      {changes}")
        else:
            print(f"\n  T{n}  {changes}")


def _flatten(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    """Flatten a nested record into (dotted path, scalar) leaves."""
    if isinstance(value, dict):
        return [pair for k, v in value.items() for pair in _flatten(v, f"{prefix}{k}.")]

    if isinstance(value, list):
        return [pair for i, v in enumerate(value) for pair in _flatten(v, f"{prefix}{i}.")]

    return [(prefix.rstrip("."), value)]


def _fmt(value: Any) -> str:
    """Format one leaf value for a change line, trimming long text."""
    if value is None:
        return "-"

    if isinstance(value, float):
        return f"{value:g}"

    text = str(value)

    return text if len(text) <= 40 else f"{text[:37]}..."


def _record_diff(prev: dict[str, Any], flat: dict[str, Any]) -> list[tuple[str, Any, Any]]:
    """Return the leaves that changed between two flattened records, sorted by path."""
    keys = set(prev) | set(flat)

    return sorted((k, prev.get(k), flat.get(k)) for k in keys if prev.get(k) != flat.get(k))


def print_changes(name: str, kind: str, path: Path, record_id: str | int) -> None:
    """Print the recorded change timeline for one asset, one block per era that changed it."""
    series = history.record_history(path, record_id)

    if not series:
        print(f"No recorded history for {name}")
        return

    print(f"{name}  ({kind} change history, {len(series)} eras tracked)")
    prev: dict[str, Any] | None = None

    for frm, build, rec in series:
        flat = dict(_flatten(rec))

        if prev is None:
            print(f"\n  {frm[:10]}  build {build}  first tracked")
        else:
            changed = _record_diff(prev, flat)

            if not changed:
                continue

            print(f"\n  {frm[:10]}  build {build}")

            for key, old, new in changed:
                print(f"    {key:<34} {_fmt(old)} -> {_fmt(new)}")

        prev = flat
