import pytest

from deadlock_matches import export, extract
from deadlock_matches.extract import pb


@pytest.mark.parametrize(
    "labels",
    [
        extract.MATCH_MODES,
        extract.GAME_MODES,
        export.STAT_NAMES,
        export.COMBAT_NAMES,
        export.MOVE_NAMES,
    ],
    ids=["match_modes", "game_modes", "stat_names", "combat_names", "move_names"],
)
def test_enum_labels_strip_the_generated_prefix(labels):
    assert labels
    assert not [label for label in labels.values() if label.lower().startswith("k_")]


def test_match_mode_labels_read_as_words():
    assert extract.MATCH_MODES[pb.k_ECitadelMatchMode_Unranked] == "Standard"
    assert extract.MATCH_MODES[pb.k_ECitadelMatchMode_Ranked] == "Ranked"
    assert extract.GAME_MODES[pb.k_ECitadelGameMode_StreetBrawl] == "Street Brawl"


def test_ranked_type_values_survive_the_rename():
    enum = pb.DESCRIPTOR.enum_types_by_name["ECitadelRankedType"]

    assert extract.RANKED_TYPE_UNRANKED == 0
    assert extract.RANKED_TYPE_RANKED == 1
    assert {v.name: v.number for v in enum.values} == {
        "k_eCitadelRankedType_Invalid": 0,
        "k_eCitadelRankedType_Normal": 1,
    }


def test_hero_xp_grant_reason_values_survive_the_rename():
    enum = pb.DESCRIPTOR.enum_types_by_name["EHeroXPGrantReason"]

    assert (pb.k_eGrant_Win, pb.k_eGrant_Loss, pb.k_eGrant_Award) == (0, 1, 2)
    assert {v.name for v in enum.values} == {"k_eGrant_Win", "k_eGrant_Loss", "k_eGrant_Award"}
