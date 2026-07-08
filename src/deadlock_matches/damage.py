"""Damage broken down by source from a match's damage_matrix.

- stat_type 0 is the hero-damage figure from the end-of-match screen
- only real player slots count (slot 0 is an objective, not a hero)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from deadlock_matches import items

if TYPE_CHECKING:
    from deadlock_matches.extract import MatchInfo

HERO_DAMAGE = 0


def _player_slot(info: MatchInfo, account_id: int) -> int | None:
    """player_slot for an account in this match, or None."""
    for p in info.players:
        if p.account_id == account_id:
            return p.player_slot

    return None


def _damage_dealer(info: MatchInfo, account_id: int) -> Any | None:
    """The damage_dealers entry for an account, or None if they dealt none."""
    slot = _player_slot(info, account_id)
    if slot is None:
        return None

    for d in info.damage_matrix.damage_dealers:
        if d.dealer_player_slot == slot:
            return d

    return None


def damage_from_source(
    info: MatchInfo, account_id: int, source_name: str, stat_type: int = HERO_DAMAGE
) -> float:
    """Total damage one player dealt through a single source (engine class_name).

    Sums each target's final cumulative value, hero targets only, matching the
    damage screen in game. Comes back 0.0 when the source was never used. account_id
    is the dealer's account ID.
    """
    dealer = _damage_dealer(info, account_id)
    if dealer is None:
        return 0.0

    details = info.damage_matrix.source_details
    real_slots = {p.player_slot for p in info.players}

    total = 0.0
    for src in dealer.damage_sources:
        i = src.source_details_index

        if details.source_name[i] == source_name and details.stat_type[i] == stat_type:
            for t in src.damage_to_players:
                if t.damage and t.target_player_slot in real_slots:
                    total += t.damage[-1]

    return total


def damage_by_source(
    info: MatchInfo, account_id: int, stat_type: int = HERO_DAMAGE
) -> dict[str, float]:
    """Maps each source name to the hero damage one player dealt with it, highest first."""
    dealer = _damage_dealer(info, account_id)
    if dealer is None:
        return {}

    details = info.damage_matrix.source_details
    real_slots = {p.player_slot for p in info.players}

    agg: dict[str, float] = {}
    for src in dealer.damage_sources:
        i = src.source_details_index

        if details.stat_type[i] != stat_type:
            continue

        name = details.source_name[i]
        s = sum(
            t.damage[-1]
            for t in src.damage_to_players
            if t.damage and t.target_player_slot in real_slots
        )
        agg[name] = agg.get(name, 0.0) + s

    return dict(sorted(agg.items(), key=lambda kv: -kv[1]))


def item_damage(
    info: MatchInfo, account_id: int, item_name: str, stat_type: int = HERO_DAMAGE
) -> float:
    """Damage a player dealt via an item, looked up by display name (e.g. "Escalating Exposure")."""
    item = items.item_by_name(item_name)

    if item is None or not item.class_name:
        msg = f"unknown item: {item_name!r}"
        raise ValueError(msg)

    return damage_from_source(info, account_id, item.class_name, stat_type)
