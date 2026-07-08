import pytest

from deadlock_matches import damage
from deadlock_matches.extract import pb


def build_match():
    """Build a match where slot 5 deals Escalating Exposure and Bullet damage, some to a non-hero."""
    info = pb.CMsgMatchMetaDataContents().match_info

    a = info.players.add()
    a.account_id = 100
    a.player_slot = 5

    b = info.players.add()
    b.account_id = 200
    b.player_slot = 6

    dm = info.damage_matrix
    dm.source_details.source_name.extend(
        ["upgrade_escalating_exposure", "upgrade_escalating_exposure", "Bullet"]
    )
    dm.source_details.stat_type.extend([0, 3, 0])

    d = dm.damage_dealers.add()
    d.dealer_player_slot = 5

    ee0 = d.damage_sources.add()
    ee0.source_details_index = 0
    t = ee0.damage_to_players.add()
    t.target_player_slot = 6
    t.damage.extend([100, 250, 809])
    t0 = ee0.damage_to_players.add()
    t0.target_player_slot = 0
    t0.damage.extend([500, 1400])

    ee3 = d.damage_sources.add()
    ee3.source_details_index = 1
    t = ee3.damage_to_players.add()
    t.target_player_slot = 6
    t.damage.extend([10, 20])

    bull = d.damage_sources.add()
    bull.source_details_index = 2
    t = bull.damage_to_players.add()
    t.target_player_slot = 6
    t.damage.extend([1000, 2000, 3000])

    return info


def test_damage_from_source_hero_only_stat0():
    info = build_match()

    assert damage.damage_from_source(info, 100, "upgrade_escalating_exposure") == 809


def test_damage_from_source_respects_stat_type():
    info = build_match()

    assert damage.damage_from_source(info, 100, "upgrade_escalating_exposure", stat_type=3) == 20


def test_damage_from_source_unknown_source_is_zero():
    info = build_match()

    assert damage.damage_from_source(info, 100, "upgrade_nonexistent") == 0.0


def test_damage_from_source_player_not_in_match():
    info = build_match()

    assert damage.damage_from_source(info, 999, "Bullet") == 0.0


def test_dealer_with_no_damage_block():
    info = build_match()

    assert damage.damage_from_source(info, 200, "Bullet") == 0.0


def test_damage_by_source_ranks_and_excludes_objective():
    info = build_match()

    agg = damage.damage_by_source(info, 100)

    assert agg["Bullet"] == 3000
    assert agg["upgrade_escalating_exposure"] == 809
    assert list(agg) == ["Bullet", "upgrade_escalating_exposure"]


def test_item_damage_by_display_name():
    info = build_match()

    assert damage.item_damage(info, 100, "Escalating Exposure") == 809

    with pytest.raises(ValueError):
        damage.item_damage(info, 100, "Not An Item")
