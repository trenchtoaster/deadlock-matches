"""Redownload the bundled data snapshots from the assets API."""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import TYPE_CHECKING, Any

from deadlock_matches import abilities, api, heroes, items, paths, skill_rating

if TYPE_CHECKING:
    from pathlib import Path

HERO_FIELDS = (
    "id",
    "name",
    "class_name",
    "hero_type",
    "gun_tag",
    "complexity",
    "tags",
    "player_selectable",
    "disabled",
)

TAG_RE = re.compile(r"<[^>]*>")
CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

WEAPON_FIELDS = (
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


def _clean_text(markup: str | None) -> str | None:
    """Strip the html/svg markup the API embeds in descriptions, keep the text."""
    if not markup:
        return None

    text = re.sub(r"\s+", " ", TAG_RE.sub(" ", markup)).strip()

    return re.sub(r" ([,.!?;:])", r"\1", text) or None


def _stat_key(value_type: str) -> str:
    """Turns MODIFIER_VALUE_TECH_POWER into tech_power."""
    return value_type.removeprefix("MODIFIER_VALUE_").lower()


def _enum_key(name: str) -> str:
    """Turns EAbilityPoints into ability_points."""
    return CAMEL_RE.sub("_", name.removeprefix("E")).lower()


def _number(val: Any) -> Any:
    """Parse numbers the API sends as strings, leaving unit strings ('1m') alone."""
    try:
        f = float(val)
    except TypeError, ValueError:
        return val

    return int(f) if f.is_integer() else f


def _measure(val: Any) -> Any:
    """Convert unit strings to numbers ('20m', '0.2s')."""
    if isinstance(val, str) and val.endswith(("m", "s")):
        try:
            f = float(val[:-1])
        except ValueError:
            return _number(val)

        return int(f) if f.is_integer() else f

    return _number(val)


def _trim_properties(props: dict[str, Any] | None) -> dict[str, Any]:
    """Reduce properties to {name: value}, dropping zeros and disabled values."""
    out = {}

    for name, prop in (props or {}).items():
        if not isinstance(prop, dict):
            continue

        val = _number(prop.get("value"))
        if val in (None, "", 0) or val == _number(prop.get("disable_value")):
            continue

        out[CAMEL_RE.sub("_", name).lower()] = val

    return out


def _trim_hero(rec: dict[str, Any]) -> dict[str, Any]:
    """Keep the hero fields the package uses, flattening starting_stats to {name: value}."""
    out = {k: rec.get(k) for k in HERO_FIELDS}
    stats = rec.get("starting_stats") or {}
    out["stats"] = {k: v.get("value") for k, v in stats.items() if isinstance(v, dict)}
    upgrades = rec.get("standard_level_up_upgrades") or {}
    out["level_up"] = {_stat_key(k): v for k, v in upgrades.items() if v}
    out["levels"] = [
        {
            "level": int(lvl),
            "required_souls": info.get("required_gold", 0),
            "standard_upgrade": bool(info.get("use_standard_upgrade")),
            "currencies": [_enum_key(c) for c in info.get("bonus_currencies") or []],
        }
        for lvl, info in sorted((rec.get("level_info") or {}).items(), key=lambda kv: int(kv[0]))
    ]
    out["purchase_bonuses"] = {
        slot: [
            {"tier": b["tier"], "stat": _stat_key(b["value_type"]), "value": float(b["value"])}
            for b in bonuses
        ]
        for slot, bonuses in (rec.get("purchase_bonuses") or {}).items()
    }
    out["cost_bonuses"] = {
        slot: [{"souls": b["gold_threshold"], "bonus": b["bonus"]} for b in bonuses]
        for slot, bonuses in (rec.get("cost_bonuses") or {}).items()
    }
    out["scaling_stats"] = {
        _enum_key(k): {"stat": _enum_key(v["scaling_stat"]), "scale": v["scale"]}
        for k, v in (rec.get("scaling_stats") or {}).items()
    }

    return out


def _property_labels(props: dict[str, Any] | None, kept: dict[str, Any]) -> dict[str, Any]:
    """Collect the shop display label, unit postfix, and sign hint for each kept property."""
    out = {}

    for name, prop in (props or {}).items():
        key = CAMEL_RE.sub("_", name).lower()

        if key not in kept or not isinstance(prop, dict) or not prop.get("label"):
            continue

        entry: dict[str, Any] = {"label": prop["label"]}

        if prop.get("postfix"):
            entry["postfix"] = prop["postfix"]

        if "sign" in (prop.get("prefix") or ""):
            entry["signed"] = True

        out[key] = entry

    return out


def _card_sections(sections: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Flatten tooltip sections into the groups an item card prints.

    - section is the type the shop shows (innate/passive/active), None on unlabeled blocks
    - text is the cleaned section description
    - properties are the property names in display order, important ones first
    """
    out = []

    for sec in sections or []:
        for attr in sec.get("section_attributes") or []:
            names = [
                CAMEL_RE.sub("_", n).lower()
                for key in ("important_properties", "elevated_properties", "properties")
                for n in attr.get(key) or []
            ]
            entry = {
                "section": sec.get("section_type"),
                "text": _clean_text(attr.get("loc_string")),
                "properties": names,
            }

            if entry["text"] or names:
                out.append(entry)

    return out


def _trim_item(rec: dict[str, Any]) -> dict[str, Any]:
    """Map an API upgrade record to the snapshot shape (the API uses longer field names)."""
    desc = rec.get("description")
    props = _trim_properties(rec.get("properties"))

    return {
        "id": rec["id"],
        "name": rec["name"],
        "class_name": rec.get("class_name"),
        "cost": rec.get("cost"),
        "slot": rec.get("item_slot_type"),
        "tier": rec.get("item_tier"),
        "is_active": bool(rec.get("is_active_item")),
        "description": _clean_text(desc.get("desc") if isinstance(desc, dict) else desc),
        "components": rec.get("component_items") or [],
        "properties": props,
        "labels": _property_labels(rec.get("properties"), props),
        "sections": _card_sections(rec.get("tooltip_sections")),
    }


def _trim_ability_properties(props: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split ability properties into base values and stat scaling."""
    values = {}
    scaling = {}

    for name, prop in (props or {}).items():
        if not isinstance(prop, dict):
            continue

        key = CAMEL_RE.sub("_", name).lower()
        fn = prop.get("scale_function")

        has_scale = isinstance(fn, dict) and fn.get("stat_scale") is not None

        if has_scale and fn.get("specific_stat_scale_type"):
            scaling[key] = {
                "stat": _enum_key(fn["specific_stat_scale_type"]),
                "scale": _number(fn["stat_scale"]),
            }

        val = _measure(prop.get("value"))

        if not isinstance(val, int | float) or val == 0:
            continue

        if val == _measure(prop.get("disable_value")):
            continue

        values[key] = val

    return values, scaling


def _trim_upgrades(tiers: list[dict[str, Any]] | None) -> list[list[dict[str, Any]]]:
    """Reduce tier upgrades to [{property, bonus}] lists, one list per tier."""
    out = []

    for tier in tiers or []:
        entries = []

        for up in tier.get("property_upgrades") or []:
            bonus = _measure(up.get("bonus"))

            if not isinstance(bonus, int | float):
                continue

            if bonus == 0 and up.get("upgrade_type") in (None, "EAddToBase", "EAddToScale"):
                continue

            entry: dict[str, Any] = {
                "property": CAMEL_RE.sub("_", up["name"]).lower(),
                "bonus": bonus,
            }

            if up.get("upgrade_type"):
                entry["type"] = _enum_key(up["upgrade_type"])

            if up.get("scale_stat_filter"):
                entry["stat"] = _enum_key(up["scale_stat_filter"])

            entries.append(entry)

        out.append(entries)

    return out


def _trim_ability(rec: dict[str, Any], kind: str) -> dict[str, Any]:
    """Keep the fields that name a damage source, plus gun stats and ability numbers."""
    out = {
        "id": rec["id"],
        "name": rec["name"],
        "class_name": rec.get("class_name"),
        "hero": rec.get("hero"),
        "kind": kind,
    }

    if kind == "weapon":
        info = rec.get("weapon_info") or {}
        out["weapon"] = {k: info[k] for k in WEAPON_FIELDS if info.get(k) is not None}

    if kind == "ability":
        desc = rec.get("description")
        desc = desc if isinstance(desc, dict) else {"desc": desc}
        out["description"] = _clean_text(desc.get("desc"))
        out["properties"], out["scaling"] = _trim_ability_properties(rec.get("properties"))
        out["upgrades"] = _trim_upgrades(rec.get("upgrades"))
        out["tier_descriptions"] = [
            _clean_text(desc.get(f"t{n}_desc")) for n in range(1, len(out["upgrades"]) + 1)
        ]

    return out


def archive_snapshots(history_dir: Path | None = None, on: dt.date | None = None) -> Path:
    """Copy the bundled snapshots into a dated history folder so old prices stay recoverable.

    history_dir defaults to the standard data directory, and on (the folder date)
    defaults to today.
    """
    history_dir = paths.assets_history_dir() if history_dir is None else history_dir
    on = dt.date.today() if on is None else on
    dest = history_dir / on.isoformat()
    dest.mkdir(parents=True, exist_ok=True)

    for src in (heroes.HEROES_JSON, items.ITEMS_JSON, abilities.ABILITIES_JSON):
        (dest / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    return dest


def refresh_abilities(path: Path | None = None) -> int:
    """Redownload abilities.json (hero abilities + guns) and clear the lookup cache.

    path defaults to the bundled snapshot.
    """
    path = abilities.ABILITIES_JSON if path is None else path
    records = [
        _trim_ability(r, kind)
        for kind in ("ability", "weapon")
        for r in api.get_json(f"v1/assets/items/by-type/{kind}", use_cache=False)
        if r.get("class_name") and r.get("name")
    ]

    path.write_text(json.dumps(records), encoding="utf-8")
    abilities.ability_map.cache_clear()

    return len(records)


def refresh_heroes(path: Path | None = None) -> int:
    """Redownload heroes.json and clear the lookup cache.

    path defaults to the bundled snapshot.
    """
    path = heroes.HEROES_JSON if path is None else path
    records = api.get_json("v1/assets/heroes", use_cache=False)

    path.write_text(json.dumps([_trim_hero(r) for r in records]), encoding="utf-8")
    heroes.hero_map.cache_clear()

    return len(records)


def refresh_skill_rating(path: Path | None = None) -> int:
    """Redownload skill_rating.json (badge tier names) and clear the lookup cache.

    path defaults to the bundled snapshot.
    """
    path = skill_rating.SKILL_RATING_JSON if path is None else path
    records = api.get_json("v1/assets/ranks", use_cache=False)

    path.write_text(
        json.dumps([{"tier": r["tier"], "name": r["name"]} for r in records]), encoding="utf-8"
    )
    skill_rating.tier_map.cache_clear()

    return len(records)


def refresh_items(path: Path | None = None) -> int:
    """Redownload items.json (upgrade items only) and clear the lookup caches.

    path defaults to the bundled snapshot.
    """
    path = items.ITEMS_JSON if path is None else path
    records = api.get_json("v1/assets/items/by-type/upgrade", use_cache=False)

    path.write_text(json.dumps([_trim_item(r) for r in records]), encoding="utf-8")
    items.item_map.cache_clear()
    items.item_by_name.cache_clear()
    items.item_by_class_name.cache_clear()

    return len(records)
