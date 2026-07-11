"""Redownload the bundled data snapshots from the assets API."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import time
import urllib.error
from typing import TYPE_CHECKING, Any

from deadlock_matches import (
    abilities,
    accolades,
    api,
    heroes,
    history,
    items,
    skill_rating,
    statues,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

HISTORY_START = "2026-01-01"

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
    """Parse numbers the API sends as strings, leaving unit strings ("1m") alone."""
    try:
        f = float(val)
    except (TypeError, ValueError):
        return val

    return int(f) if f.is_integer() else f


def _measure(val: Any) -> Any:
    """Convert unit strings to numbers ("20m", "0.2s")."""
    if isinstance(val, str) and val.endswith(("m", "s")):
        try:
            f = float(val[:-1])
        except ValueError:
            return _number(val)

        return int(f) if f.is_integer() else f

    return _number(val)


def _property_values(props: dict[str, Any] | None) -> dict[str, Any]:
    """Flatten properties to {name: value}, dropping zeros and disabled values."""
    out = {}

    for name, prop in (props or {}).items():
        if not isinstance(prop, dict):
            continue

        val = _number(prop.get("value"))
        if val in (None, "", 0) or val == _number(prop.get("disable_value")):
            continue

        out[CAMEL_RE.sub("_", name).lower()] = val

    return out


def _hero_snapshot(rec: dict[str, Any]) -> dict[str, Any]:
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

        prefix = prop.get("prefix") or ""

        if "sign" in prefix:
            entry["signed"] = True
        elif prefix in ("+", "-"):
            entry["prefix"] = prefix

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


def _item_snapshot(rec: dict[str, Any]) -> dict[str, Any]:
    """Convert an API upgrade record to the snapshot shape (the API uses longer field names)."""
    desc = rec.get("description")
    props = _property_values(rec.get("properties"))
    derived = _derive_properties(rec.get("properties"), set(props))

    return {
        "id": rec["id"],
        "name": rec["name"],
        "class_name": rec.get("class_name"),
        "cost": rec.get("cost"),
        "slot": rec.get("item_slot_type"),
        "tier": rec.get("item_tier"),
        "is_active": bool(rec.get("is_active_item")),
        "activation": rec.get("activation"),
        "shopable": bool(rec.get("shopable")),
        "disabled": bool(rec.get("disabled")),
        "imbue": rec.get("imbue"),
        "description": _clean_text(desc.get("desc") if isinstance(desc, dict) else desc),
        "components": rec.get("component_items") or [],
        "upgrades": _tier_bonuses(rec.get("upgrades")),
        "properties": props,
        **derived,
        "labels": _property_labels(rec.get("properties"), props),
        "sections": _card_sections(rec.get("tooltip_sections")),
    }


NONLINEAR_SCALE_FUNCTIONS = {
    "scale_function_kinetic_carbine_damage",
    "scale_function_nanotech_rounds_damage",
}


def _damage_stat(css_class: str | None) -> str | None:
    """Return the stat a spirit damage line scales with when the API omits the scale type.

    Weapon damage has no single scaling stat (Carbine and the base-weapon-damage
    abilities each use their own function), so weapon lines get no fallback.
    """
    if css_class == "tech_damage":
        return "tech_power"

    return None


def _damage_line(key: str, css: str | None, scale_class: str | None) -> str | None:
    """Return the damage type of a real damage line, None for stat grants.

    css only sets the color, so fire rate and slow stats share the damage
    colors. A real damage line either scales through a *_damage function or
    names itself *_damage, which keeps stat grants like weapon damage percent
    out.
    """
    if css not in ("tech_damage", "bullet_damage"):
        return None

    scales_damage = bool(scale_class) and scale_class.endswith("_damage")

    if not scales_damage and not key.endswith("_damage"):
        return None

    return "spirit" if css == "tech_damage" else "weapon"


def _derive_properties(
    props: dict[str, Any] | None,
    kept: set[str],
) -> dict[str, Any]:
    """Pull the derived per-property views a card reads.

    - scaling keeps the stat and coefficient for anything that scales by one,
      falling back to the css damage stat when the API leaves out the scale type
    - damage_types marks the type of each real damage line
    - scale_types buckets a value into the reduction family it belongs to, such
      as item cooldown, ability cooldown, duration, range, or healing
    - negatives lists the properties an item counts as a downside
    - conditionals gives the case a value only applies in
    - the kept-only views stay limited to properties that survived filtering
    """
    scaling = {}
    damage_types = {}
    scale_types = {}
    negatives = []
    conditionals = {}

    for name, prop in (props or {}).items():
        if not isinstance(prop, dict):
            continue

        key = CAMEL_RE.sub("_", name).lower()
        css = prop.get("css_class")
        fn = prop.get("scale_function") if isinstance(prop.get("scale_function"), dict) else None
        scale_class = fn.get("class_name") if fn else None
        stat_type = fn.get("specific_stat_scale_type") if fn else None
        scale = _number(fn.get("stat_scale")) if fn else None
        has_coeff = isinstance(scale, int | float)

        if key in kept:
            dtype = _damage_line(key, css, scale_class)

            if dtype:
                damage_types[key] = dtype

            if prop.get("negative_attribute"):
                negatives.append(key)

            if prop.get("conditional"):
                conditionals[key] = prop["conditional"]

            if stat_type and not has_coeff:
                scale_types[key] = _enum_key(stat_type)

        if has_coeff:
            stat = _enum_key(stat_type) if stat_type else _damage_stat(css)

            if stat:
                entry: dict[str, Any] = {"stat": stat, "scale": scale}

                if scale_class in NONLINEAR_SCALE_FUNCTIONS:
                    entry["linear"] = False

                scaling[key] = entry

    return {
        "scaling": scaling,
        "damage_types": damage_types,
        "scale_types": scale_types,
        "negatives": negatives,
        "conditionals": conditionals,
    }


def _split_ability_properties(
    props: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split ability properties into base values and the derived per-property views."""
    values = {}

    for name, prop in (props or {}).items():
        if not isinstance(prop, dict):
            continue

        key = CAMEL_RE.sub("_", name).lower()
        val = _measure(prop.get("value"))

        if not isinstance(val, int | float) or val == 0:
            continue

        if val == _measure(prop.get("disable_value")):
            continue

        values[key] = val

    return values, _derive_properties(props, set(values))


def _tier_bonuses(tiers: list[dict[str, Any]] | None) -> list[list[dict[str, Any]]]:
    """Flatten tier upgrades to [{property, bonus}] lists, one list per tier."""
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


def _ability_snapshot(rec: dict[str, Any], kind: str) -> dict[str, Any]:
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
        out["ability_type"] = rec.get("ability_type")
        out["boss_damage_scale"] = rec.get("boss_damage_scale")
        out["behaviours"] = rec.get("behaviours") or []
        values, derived = _split_ability_properties(rec.get("properties"))
        out["properties"] = values
        out.update(derived)
        out["upgrades"] = _tier_bonuses(rec.get("upgrades"))
        out["tier_descriptions"] = [
            _clean_text(desc.get(f"t{n}_desc")) for n in range(1, len(out["upgrades"]) + 1)
        ]

    return out


def _statue_snapshot(rec: dict[str, Any]) -> dict[str, Any]:
    """Keep the permanent stat one statue pickup grants.

    Statues grant a single stat, so this keeps the first script value.
    """
    subclass = (rec.get("modifier") or {}).get("subclass") or {}
    values = subclass.get("script_values") or [{}]
    first = values[0]
    stat = first.get("value_type")

    return {
        "id": rec["id"],
        "class_name": rec["class_name"],
        "stat": _stat_key(stat) if stat else None,
        "value": _number(first.get("value")),
    }


def client_version_dates(max_age: float = api.DAY) -> dict[int, str]:
    """Return the release datetime for each Steam client build."""
    records = api.get_json("v1/assets/steam-info/all", max_age=max_age)

    return {r["client_version"]: r["version_datetime"] for r in records}


def _versioned(endpoint: str, build: int) -> list[dict[str, Any]]:
    """Return the records from one assets endpoint at a client build."""
    return api.get_json(f"{endpoint}?client_version={build}", permanent=True)


def _load_build(
    build: int,
    cache: dict[int, dict | None],
    load: Callable[[int], dict[str, Any]],
    tries: int = 4,
) -> dict | None:
    """Return the projected records at one client build, retrying transient failures.

    - a 404 means the API never extracted assets for the build, skipped without retrying
    - a build that keeps failing is also skipped so one broken build on the API side
      cannot abort a whole backfill
    - a skipped build never substitutes a neighbor, its records are just absent
    """
    if build in cache:
        return cache[build]

    for k in range(tries):
        try:
            cache[build] = load(build)
            return cache[build]

        except urllib.error.HTTPError as exc:
            if exc.code == 404 or k == tries - 1:
                break

            time.sleep(0.4 * (k + 1))

        except OSError:
            if k == tries - 1:
                break

            time.sleep(0.4 * (k + 1))

    cache[build] = None

    return None


def _digest(records: dict[str, Any]) -> str:
    """Return a stable hash of the projected records of one build."""
    return hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()


def build_asset_history(
    load: Callable[[int], dict[str, Any]],
    path: Path,
    start_date: str = HISTORY_START,
    progress: Callable[[int, int, list[int]], None] | None = None,
    *,
    full: bool = False,
) -> int:
    """Build a committed asset history by scanning client builds for change points.

    - load(build) returns the {id: record} map at a client build
    - one era per patch that changed any stored record
    - resumes from the last committed era, scanning only builds newer than it, so a
      run right after a patch appends the new era instead of rehashing every build
    - full rescans every build from start_date, needed when the API corrects an old
      build or start_date moves earlier
    - walks every scanned build so a value that changes and reverts between two builds
      is still captured, which a bisection over the endpoints would miss
    - builds the API has no data for are skipped, the scan continues from the next one
    - refuses to write when a fresh table would be empty, so an unreachable endpoint
      cannot blank a committed table
    - progress(done, total, skipped_builds) is called after every scanned build
    """
    dates = client_version_dates()
    builds = sorted(b for b, d in dates.items() if d >= start_date)

    if not builds:
        msg = f"no client builds on or after {start_date}"
        raise ValueError(msg)

    existing = [] if full else history.read_states(path)

    if existing and existing[-1]["build"] in set(builds):
        prev: str | None = _digest(existing[-1]["records"])
        pending = [b for b in builds if b > existing[-1]["build"]]
    else:
        existing = []
        prev = None
        pending = builds

    cache: dict[int, dict | None] = {}
    states: list[dict[str, Any]] = []
    skipped: list[int] = []

    for done, build in enumerate(pending, start=1):
        records = _load_build(build, cache, load)

        if records is None:
            skipped.append(build)
        else:
            digest = _digest(records)

            if digest != prev:
                states.append({"from": dates[build], "build": build, "records": records})
                prev = digest

        if progress is not None:
            progress(done, len(pending), skipped)

    combined = existing + states

    if not combined:
        msg = f"no client build since {start_date} could be loaded, refusing to overwrite {path}"
        raise RuntimeError(msg)

    if states or not existing:
        history.write(path, combined)

    return len(combined)


def _by_id(record: dict[str, Any]) -> str:
    """Return the record id as a string."""
    return str(record["id"])


def _endpoint_load(
    endpoint: str,
    project: Callable[[dict[str, Any]], dict[str, Any]],
    key: Callable[[dict[str, Any]], str],
) -> Callable[[int], dict[str, Any]]:
    """Return a loader mapping each record from one endpoint through project, keyed by key."""

    def load(build: int) -> dict[str, Any]:
        return {key(r): project(r) for r in _versioned(endpoint, build)}

    return load


def build_item_history(
    start_date: str = HISTORY_START,
    path: Path | None = None,
    progress: Callable[[int, int, list[int]], None] | None = None,
    *,
    full: bool = False,
) -> int:
    """Build the committed item history from the assets API.

    - one era per patch that changed any item field
    - path defaults to the committed history table
    """
    path = items.ITEM_HISTORY_PARQUET if path is None else path
    load = _endpoint_load("v1/assets/items/by-type/upgrade", _item_snapshot, _by_id)

    return build_asset_history(load, path, start_date, progress, full=full)


def build_hero_history(
    start_date: str = HISTORY_START,
    path: Path | None = None,
    progress: Callable[[int, int, list[int]], None] | None = None,
    *,
    full: bool = False,
) -> int:
    """Build the committed hero history from the assets API.

    - one era per patch that changed any hero field
    - path defaults to the committed history table
    """
    path = heroes.HERO_HISTORY_PARQUET if path is None else path
    load = _endpoint_load("v1/assets/heroes", _hero_snapshot, _by_id)

    return build_asset_history(load, path, start_date, progress, full=full)


def _ability_load(build: int) -> dict[str, Any]:
    """Return the {class_name: ability record} map at a build, from the ability and weapon endpoints."""
    out = {}

    for kind in ("ability", "weapon"):
        for r in _versioned(f"v1/assets/items/by-type/{kind}", build):
            if r.get("class_name") and r.get("name"):
                out[r["class_name"]] = _ability_snapshot(r, kind)

    return out


def build_ability_history(
    start_date: str = HISTORY_START,
    path: Path | None = None,
    progress: Callable[[int, int, list[int]], None] | None = None,
    *,
    full: bool = False,
) -> int:
    """Build the committed ability history from the assets API.

    - one era per patch that changed any ability or gun field
    - path defaults to the committed history table
    """
    path = abilities.ABILITY_HISTORY_PARQUET if path is None else path

    return build_asset_history(_ability_load, path, start_date, progress, full=full)


def _rank_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return the tier and name for one rank record."""
    return {"tier": record["tier"], "name": record["name"]}


def _by_tier(record: dict[str, Any]) -> str:
    """Return the rank tier as a string."""
    return str(record["tier"])


def build_rank_history(
    start_date: str = HISTORY_START,
    path: Path | None = None,
    progress: Callable[[int, int, list[int]], None] | None = None,
    *,
    full: bool = False,
) -> int:
    """Build the committed rank history from the assets API.

    - one era per patch that renamed or added a rank tier
    - path defaults to the committed history table
    """
    path = skill_rating.RANK_HISTORY_PARQUET if path is None else path
    load = _endpoint_load("v1/assets/ranks", _rank_record, _by_tier)

    return build_asset_history(load, path, start_date, progress, full=full)


def _statue_load(build: int) -> dict[str, Any]:
    """Return the {class_name: statue record} map at a build from the misc entities endpoint."""
    return {
        r["class_name"]: _statue_snapshot(r)
        for r in _versioned("v1/assets/misc-entities", build)
        if statues.is_statue(r.get("class_name") or "")
    }


def build_statue_history(
    start_date: str = HISTORY_START,
    path: Path | None = None,
    progress: Callable[[int, int, list[int]], None] | None = None,
    *,
    full: bool = False,
) -> int:
    """Build the committed statue history from the assets API.

    - one era per patch that changed any statue magnitude
    - path defaults to the committed history table
    """
    path = statues.STATUE_HISTORY_PARQUET if path is None else path

    return build_asset_history(_statue_load, path, start_date, progress, full=full)


def refresh_abilities(path: Path | None = None) -> int:
    """Redownload abilities.json (hero abilities + guns) and clear the lookup cache.

    path defaults to the bundled snapshot.
    """
    path = abilities.ABILITIES_JSON if path is None else path
    records = [
        _ability_snapshot(r, kind)
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

    path.write_text(json.dumps([_hero_snapshot(r) for r in records]), encoding="utf-8")
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


def refresh_accolades(path: Path | None = None) -> int:
    """Redownload accolades.json (the end of match stat awards) and clear the lookup cache.

    path defaults to the bundled snapshot.
    """
    path = accolades.ACCOLADES_JSON if path is None else path
    records = api.get_json("v1/assets/accolades", use_cache=False)

    path.write_text(
        json.dumps(
            [
                {"id": r["id"], "class_name": r["class_name"], "name": r["flavor_name"]}
                for r in records
            ]
        ),
        encoding="utf-8",
    )
    accolades.accolade_map.cache_clear()

    return len(records)


def refresh_statues(path: Path | None = None) -> int:
    """Redownload statues.json (the permanent buff statue pickups) and clear the lookup cache.

    path defaults to the bundled snapshot.
    """
    path = statues.STATUES_JSON if path is None else path
    records = api.get_json("v1/assets/misc-entities", use_cache=False)
    kept = [_statue_snapshot(r) for r in records if statues.is_statue(r.get("class_name") or "")]

    path.write_text(json.dumps(kept), encoding="utf-8")
    statues.statue_map.cache_clear()

    return len(kept)


def refresh_items(path: Path | None = None) -> int:
    """Redownload items.json (upgrade items only) and clear the lookup caches.

    path defaults to the bundled snapshot.
    """
    path = items.ITEMS_JSON if path is None else path
    records = api.get_json("v1/assets/items/by-type/upgrade", use_cache=False)

    path.write_text(json.dumps([_item_snapshot(r) for r in records]), encoding="utf-8")
    items.item_map.cache_clear()
    items.item_by_name.cache_clear()
    items.item_by_class_name.cache_clear()

    return len(records)


LIVE_HISTORY_CHECKS = (
    ("items", items.ITEMS_JSON, items.ITEM_HISTORY_PARQUET, "id"),
    ("heroes", heroes.HEROES_JSON, heroes.HERO_HISTORY_PARQUET, "id"),
    ("abilities", abilities.ABILITIES_JSON, abilities.ABILITY_HISTORY_PARQUET, "class_name"),
    ("ranks", skill_rating.SKILL_RATING_JSON, skill_rating.RANK_HISTORY_PARQUET, "tier"),
    ("statues", statues.STATUES_JSON, statues.STATUE_HISTORY_PARQUET, "class_name"),
)


def history_lags() -> list[tuple[str, str, int]]:
    """Return (name, date, build) for each asset type whose committed history trails its live snapshot.

    - compares the live snapshot the refresh just wrote against the newest committed
      record, so a live patch already captured stays quiet
    - types with no committed history are skipped
    """
    now = dt.datetime.now(tz=dt.UTC)
    out = []

    for name, json_path, hist_path, field in LIVE_HISTORY_CHECKS:
        newest = history.records_asof(hist_path, now)

        if newest is None:
            continue

        records = json.loads(json_path.read_text(encoding="utf-8"))
        live = {str(rec[field]): rec for rec in records}

        if _digest(live) == _digest(newest):
            continue

        frm, build = history.eras(hist_path)[-1]
        out.append((name, frm[:10], build))

    return out
