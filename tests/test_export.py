import bz2
import datetime as dt

import polars as pl
import pytest
from google.protobuf import json_format

from deadlock_matches import export, extract, items, queries
from deadlock_matches.extract import pb

EE = 3005970438


def build_match(match_id=100, winning_team=pb.k_ECitadelLobbyTeam_Team1):
    info = pb.CMsgMatchMetaDataContents().match_info
    info.match_id = match_id
    info.start_time = 1783000000
    info.duration_s = 1800
    info.winning_team = winning_team
    info.match_mode = pb.k_ECitadelMatchMode_Unranked

    a = info.players.add()
    a.account_id = 42
    a.hero_id = 52
    a.team = pb.k_ECitadelLobbyTeam_Team1
    a.player_slot = 5
    a.kills = 7
    a.mvp_rank = 1

    b = info.players.add()
    b.account_id = 43
    b.hero_id = 1
    b.team = pb.k_ECitadelLobbyTeam_Team0
    b.player_slot = 6

    s = a.stats.add()
    s.time_stamp_s = 180
    s.net_worth = 3000
    s.gold_player = 500
    s.gold_denied = 40
    g = s.gold_sources.add()
    g.source = 2
    g.gold = 700
    g.gold_orbs = 300
    g = s.gold_sources.add()
    g.source = 12
    g.gold = 90

    it = a.items.add()
    it.item_id = EE
    it.game_time_s = 1200
    it.flags = 0
    it.imbued_ability_id = 1336069669

    it2 = a.items.add()
    it2.item_id = 999999999
    it2.game_time_s = 60
    it2.sold_time_s = 300
    it2.flags = 1

    acc = a.accolades.add()
    acc.accolade_id = 1
    acc.accolade_stat_value = 7
    acc.accolade_threshold_achieved = 1

    acc2 = a.accolades.add()
    acc2.accolade_id = 999
    acc2.accolade_stat_value = 3
    acc2.accolade_threshold_achieved = -1

    mb = info.mid_boss.add()
    mb.destroyed_time_s = 1300
    mb.team_killed = pb.k_ECitadelLobbyTeam_Team1
    mb.team_claimed = pb.k_ECitadelLobbyTeam_Team0

    mb2 = info.mid_boss.add()
    mb2.destroyed_time_s = 1700
    mb2.team_killed = pb.k_ECitadelLobbyTeam_Team1
    mb2.team_claimed = pb.k_ECitadelLobbyTeam_Team1

    o = info.objectives.add()
    o.team = pb.k_ECitadelLobbyTeam_Team0
    o.team_objective_id = pb.k_eCitadelTeamObjective_Tier1_Lane1
    o.destroyed_time_s = 660
    o.first_damage_time_s = 120
    o.player_damage = 4000
    o.player_spirit_damage = 1500
    o.creep_damage = 800

    o2 = info.objectives.add()
    o2.team = pb.k_ECitadelLobbyTeam_Team1
    o2.team_objective_id = pb.k_eCitadelTeamObjective_Titan
    o2.player_damage = 500

    d = a.death_details.add()
    d.game_time_s = 2
    d.time_to_kill_s = 1.5
    d.death_duration_s = 20
    d.killer_player_slot = 6
    d.death_pos.x = 1000.0
    d.death_pos.y = 500.0
    d.death_pos.z = 128.0
    d.killer_pos.x = 900.0
    d.killer_pos.y = 450.0
    d.killer_pos.z = 128.0

    mp = info.match_paths
    mp.interval_s = 1.0
    mp.x_resolution = 100
    mp.y_resolution = 100
    path = mp.paths.add()
    path.player_slot = 5
    path.x_min = -1000.0
    path.x_max = 1000.0
    path.y_min = 0.0
    path.y_max = 500.0
    path.x_pos.extend([0, 50, 100])
    path.y_pos.extend([0, 50, 100])
    path.health.extend([100, 40, 0])
    path.combat_type.extend([0, 1, 2])
    path.move_type.extend([0, 4, 8])

    dm = info.damage_matrix
    dm.sample_time_s.extend([600, 1200])
    dm.source_details.source_name.append("upgrade_escalating_exposure")
    dm.source_details.stat_type.append(0)

    d = dm.damage_dealers.add()
    d.dealer_player_slot = 5
    src = d.damage_sources.add()
    src.source_details_index = 0
    t = src.damage_to_players.add()
    t.target_player_slot = 6
    t.damage.extend([100, 809])

    return info


def test_from_api_json_matches_local_decode():
    info = build_match()
    as_json = json_format.MessageToDict(info, preserving_proto_field_name=True)

    assert extract.from_api_json(as_json) == info


def test_from_api_json_ignores_unknown_fields():
    info = build_match()
    as_json = json_format.MessageToDict(info, preserving_proto_field_name=True)
    as_json["some_future_field"] = 7

    assert extract.from_api_json(as_json) == info


def test_tables_have_expected_rows():
    tables = export.build_tables([build_match()])

    assert len(tables["matches"]) == 1
    assert len(tables["players"]) == 2
    assert len(tables["stats"]) == 1
    assert len(tables["soul_sources"]) == 2
    assert len(tables["item_events"]) == 2
    assert len(tables["damage"]) == 1
    assert len(tables["damage_sources"]) == 2
    assert len(tables["mid_boss"]) == 2
    assert len(tables["objectives"]) == 2
    assert len(tables["movement"]) == 3
    assert len(tables["deaths"]) == 1


def test_players_lane_columns():
    info = build_match()
    info.players[0].assigned_lane = 1
    info.players[1].assigned_lane = 6
    players = export.build_tables([info])["players"]

    assert players["assigned_lane"].to_list() == [1, 6]
    assert players["lane"].to_list() == ["yellow", "green"]


def test_damage_sources_cumulative_matches_damage_total():
    tables = export.build_tables([build_match()])
    ds = tables["damage_sources"]

    assert ds["time_stamp_s"].to_list() == [600, 1200]
    assert ds["damage"].to_list() == [100, 809]
    assert ds["vs_heroes"].to_list() == [True, True]
    assert ds["damage"][-1] == tables["damage"]["damage"][0]


def test_damage_sources_right_aligned_and_split_by_target():
    info = build_match()
    src = info.damage_matrix.damage_dealers[0].damage_sources[0]

    late = src.damage_to_players.add()
    late.target_player_slot = 6
    late.damage.extend([70])

    creep = src.damage_to_players.add()
    creep.target_player_slot = 0
    creep.damage.extend([500, 900])

    ds = export.build_tables([info])["damage_sources"]
    hero_rows = ds.filter(pl.col("vs_heroes"))
    creep_rows = ds.filter(~pl.col("vs_heroes"))

    assert hero_rows["damage"].to_list() == [100, 879]
    assert creep_rows["time_stamp_s"].to_list() == [600, 1200]
    assert creep_rows["damage"].to_list() == [500, 900]


def test_damage_sources_empty_without_sample_times():
    info = build_match()
    del info.damage_matrix.sample_time_s[:]

    assert export.build_tables([info])["damage_sources"].is_empty()


def test_exclude_skips_movement():
    tables = export.build_tables([build_match()], exclude=("movement",))

    assert "movement" not in tables
    assert len(tables["deaths"]) == 1


def test_matches_average_badges():
    info = build_match()
    info.average_badge_team0 = 76
    info.average_badge_team1 = 83
    matches = export.build_tables([info])["matches"]

    assert matches["average_badge_team0"][0] == 76
    assert matches["average_badge_team1"][0] == 83


def test_matches_average_badges_null_when_unset():
    matches = export.build_tables([build_match()])["matches"]

    assert matches["average_badge_team0"][0] is None
    assert matches["average_badge_team1"][0] is None


def test_gold_fields_renamed_to_souls():
    stats = export.build_tables([build_match()])["stats"]

    assert "souls_player" in stats.columns
    assert "souls_denied" in stats.columns
    assert not any(c.startswith("gold") for c in stats.columns)
    assert stats["souls_player"][0] == 500


def test_soul_sources_named():
    src = export.build_tables([build_match()])["soul_sources"]
    named = dict(zip(src["source_name"], src["souls"], strict=True))

    assert named == {"troopers": 700, "breakables": 90}


def test_players_won_flag():
    players = export.build_tables([build_match(winning_team=pb.k_ECitadelLobbyTeam_Team1)])[
        "players"
    ]
    won = dict(zip(players["account_id"], players["won"], strict=True))

    assert won == {42: True, 43: False}


def test_players_mvp_rank():
    players = export.build_tables([build_match()])["players"]
    ranks = dict(zip(players["account_id"], players["mvp_rank"], strict=True))

    assert ranks == {42: 1, 43: 0}


def test_item_events_denormalized():
    events = export.build_tables([build_match()])["item_events"]

    ee = events.filter(pl.col("item_id") == EE)

    assert ee["item"][0] == "Escalating Exposure"
    assert ee["cost"][0] == 6400
    assert ee["imbued_ability_id"][0] == 1336069669
    assert ee["imbued_ability"][0] == "Dust Devil"

    unknown = events.filter(pl.col("item_id") == 999999999)

    assert unknown["item"][0] is None
    assert unknown["flags"][0] == 1
    assert unknown["imbued_ability_id"][0] is None
    assert unknown["imbued_ability"][0] is None


def test_item_events_priced_from_committed_history():
    start = dt.datetime.fromtimestamp(1783000000, dt.UTC)
    events = export.build_tables([build_match()])["item_events"]

    ee = events.filter(pl.col("item_id") == EE)

    priced = items.item_asof(EE, start)

    assert priced is not None
    assert ee["cost"][0] == priced.cost


def test_accolades_named_from_snapshot():
    acc = export.build_tables([build_match()])["accolades"]
def test_matches_not_scored_flag():
    info = build_match()
    info.not_scored = True

    matches = export.build_tables([info])["matches"]

    assert matches["not_scored"].to_list() == [True]


def test_matches_not_scored_defaults_false():
    matches = export.build_tables([build_match()])["matches"]

    assert matches["not_scored"].to_list() == [False]


def test_players_party_from_wire_field():
    info = build_match()
    raw = info.players[0].SerializeToString() + bytes([0x80, 0x01, 2])
    info.players[0].Clear()
    info.players[0].MergeFromString(raw)

    players = export.build_tables([info])["players"]
    parties = dict(zip(players["account_id"], players["party"], strict=True))

    assert parties == {42: 2, 43: None}


def test_players_abandon_time():
    info = build_match()
    info.players[1].abandon_match_time_s = 367

    players = export.build_tables([info])["players"]
    abandons = dict(zip(players["account_id"], players["abandon_time_s"], strict=True))

    assert abandons == {42: None, 43: 367}



    kills = acc.filter(pl.col("accolade_id") == 1)

    assert kills["accolade"][0] == "kills"
    assert kills["value"][0] == 7
    assert kills["threshold"][0] == 1

    unknown = acc.filter(pl.col("accolade_id") == 999)

    assert unknown["accolade"][0] is None
    assert unknown["threshold"][0] == -1


def test_damage_maps_slots_to_accounts():
    dmg = export.build_tables([build_match()])["damage"]

    assert dmg["dealer_account_id"][0] == 42
    assert dmg["target_account_id"][0] == 43
    assert dmg["damage"][0] == 809
    assert dmg["stat"][0] == "damage"


def test_stat_names_from_proto_enum():
    assert export.STAT_NAMES[0] == "damage"
    assert export.STAT_NAMES[1] == "healing"
    assert export.STAT_NAMES[2] == "heal_prevented"
    assert export.STAT_NAMES[3] == "mitigated"
    assert export.STAT_NAMES[4] == "lethal_damage"


def test_damage_source_names_resolved():
    dmg = export.build_tables([build_match()])["damage"]

    assert dmg["source_name"][0] == "Escalating Exposure"
    assert dmg["source_class"][0] == "upgrade_escalating_exposure"
    assert dmg["category"][0] == "item"


def test_damage_categories():
    assert export._damage_category("Bullet") == "total"
    assert export._damage_category("Ability") == "total"
    assert export._damage_category("Melee") == "total"
    assert export._damage_category("UnknownAbility") == "total"
    assert export._damage_category("citadel_weapon_mirage_set") == "gun"
    assert export._damage_category("upgrade_escalating_exposure") == "item"
    assert export._damage_category("mirage_tornado") == "ability"
    assert export._damage_category("ability_blood_bomb_bloodspill") == "ability"


def test_item_attribution(tmp_path):
    for name, df in export.build_tables([build_match()]).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    events = queries.item_attribution(tmp_path).collect()

    ee = events.filter(pl.col("item_id") == EE)

    assert ee["attribution"][0] == "proc"

    unknown = events.filter(pl.col("item_id") == 999999999)

    assert unknown["attribution"][0] == "stat"


def test_damage_delivery():
    assert export._delivery("Bullet") is None
    assert export._delivery("Ability") is None
    assert export._delivery("citadel_weapon_mirage_set") == "gun"
    assert export._delivery("citadel_weapon_mirage_set_crit") == "gun"
    assert export._delivery("upgrade_crackshot") == "gun_proc"
    assert export._delivery("upgrade_headhunter") == "gun_proc"
    assert export._delivery("upgrade_toxic_bullets") == "gun_proc"
    assert export._delivery("upgrade_ethereal_bullets") == "gun_proc"
    assert export._delivery("upgrade_quick_silver") == "gun_proc"
    assert export._delivery("upgrade_siphon_bullets") == "gun_proc"
    assert export._delivery("upgrade_escalating_exposure") == "spirit_proc"
    assert export._delivery("mirage_tornado") == "ability"
    assert export._delivery("upgrade_nonexistent_item") == "spirit_proc"


def test_damage_delivery_column():
    dmg = export.build_tables([build_match()])["damage"]

    assert dmg["delivery"][0] == "spirit_proc"


def test_mid_boss_rows():
    mb = export.build_tables([build_match()])["mid_boss"]

    assert mb["destroyed_time_s"].to_list() == [1300, 1700]
    assert mb["team_killed"].to_list() == [1, 1]
    assert mb["team_claimed"].to_list() == [0, 1]
    assert mb["match_id"].to_list() == [100, 100]


def test_objectives_rows():
    obj = export.build_tables([build_match()])["objectives"]

    assert obj["objective"].to_list() == ["Guardian", "Patron"]
    assert obj["lane"].to_list() == ["yellow", None]
    assert obj["team"].to_list() == [0, 1]
    assert obj["destroyed_time_s"].to_list() == [660, None]
    assert obj["first_damage_time_s"].to_list() == [120, None]
    assert obj["player_damage"].to_list() == [4000, 500]
    assert obj["player_spirit_damage"].to_list() == [1500, 0]
    assert obj["creep_damage"].to_list() == [800, 0]


def test_movement_positions_decoded():
    movement = export.build_tables([build_match()])["movement"]

    assert movement["account_id"].to_list() == [42, 42, 42]
    assert movement["game_time_s"].to_list() == [0, 1, 2]
    assert movement["x"].to_list() == [-1000.0, 0.0, 1000.0]
    assert movement["y"].to_list() == [0.0, 250.0, 500.0]


def test_movement_enum_names():
    movement = export.build_tables([build_match()])["movement"]

    assert movement["health_percent"].to_list() == [100, 40, 0]
    assert movement["combat_type"].to_list() == ["out", "player", "enemy_npc"]
    assert movement["move_type"].to_list() == ["normal", "slide", "air_dash"]


def test_movement_drops_samples_past_match_end():
    info = build_match()
    info.duration_s = 1
    movement = export.build_tables([info])["movement"]

    assert movement["game_time_s"].to_list() == [0, 1]


def test_move_names_from_proto_enum():
    assert export.MOVE_NAMES[0] == "normal"
    assert export.MOVE_NAMES[3] == "ground_dash"
    assert export.MOVE_NAMES[5] == "rope_climbing"
    assert export.MOVE_NAMES[7] == "in_air"
    assert export.MOVE_NAMES[8] == "air_dash"
    assert export.COMBAT_NAMES[0] == "out"
    assert export.COMBAT_NAMES[2] == "enemy_npc"


def test_deaths_rows():
    deaths = export.build_tables([build_match()])["deaths"]

    assert deaths["account_id"][0] == 42
    assert deaths["game_time_s"][0] == 2
    assert deaths["time_to_kill_s"][0] == 1.5
    assert deaths["death_duration_s"][0] == 20
    assert deaths["killer_account_id"][0] == 43
    assert deaths["x"][0] == 1000.0
    assert deaths["y"][0] == 500.0
    assert deaths["z"][0] == 128.0
    assert deaths["killer_x"][0] == 900.0
    assert deaths["killer_y"][0] == 450.0
    assert deaths["killer_z"][0] == 128.0


def test_export_all_writes_parquet(tmp_path):
    raw = build_match(match_id=7)
    contents = pb.CMsgMatchMetaDataContents()
    contents.match_info.CopyFrom(raw)
    meta_msg = pb.CMsgMatchMetaData()
    meta_msg.match_details = contents.SerializeToString()

    arc = tmp_path / "arc"
    arc.mkdir()
    header = b"replay1.valve.net\x00/1422450/7_1.meta.bz2\x00"
    (arc / "7_1.bin").write_bytes(header + bz2.compress(meta_msg.SerializeToString()))

    out = tmp_path / "pq"
    result = export.export_all(arc, out)

    assert result.counts["matches"] == 1
    assert result.counts["players"] == 2
    assert result.counts["movement"] == 3
    assert result.decoded == 1
    assert (out / "movement").is_dir()
    assert next((out / "movement").glob("*.parquet"), None) is not None

    df = queries.scan("players", out).collect()

    assert df.filter(pl.col("account_id") == 42)["hero"][0] == "Mirage"

    result = export.export_all(arc, out, exclude=("movement",))

    assert "movement" not in result.counts
    assert (out / "movement").is_dir()


def _archive_match(arc, match_id, start, accounts=None):
    """Write one match into the .bin archive at a chosen start time."""
    info = build_match(match_id=match_id)
    info.start_time = int(start.timestamp())

    if accounts is not None:
        for player, account_id in zip(info.players, accounts, strict=False):
            player.account_id = account_id

    contents = pb.CMsgMatchMetaDataContents()
    contents.match_info.CopyFrom(info)

    meta = pb.CMsgMatchMetaData()
    meta.match_details = contents.SerializeToString()

    header = f"replay1.valve.net\x00/1422450/{match_id}_1.meta.bz2\x00".encode()
    (arc / f"{match_id}_1.bin").write_bytes(header + bz2.compress(meta.SerializeToString()))


def test_export_all_keeps_only_matches_a_listed_account_played(tmp_path):
    arc = tmp_path / "arc"
    arc.mkdir()
    _archive_match(arc, 7, dt.datetime(2026, 6, 1, tzinfo=dt.UTC))

    kept = export.export_all(arc, tmp_path / "keep", accounts=[42])
    assert kept.counts["matches"] == 1

    df = queries.scan("players", tmp_path / "keep").collect()
    assert set(df["account_id"].to_list()) == {42, 43}

    dropped = export.export_all(arc, tmp_path / "drop", accounts=[999])
    assert dropped.counts.get("matches", 0) == 0


def test_export_new_filters_new_matches_by_account(tmp_path):
    arc = tmp_path / "arc"
    arc.mkdir()
    out = tmp_path / "pq"
    _archive_match(arc, 7, dt.datetime(2026, 6, 1, tzinfo=dt.UTC))

    export.export_new(arc, out, accounts=[42])
    assert export.exported_match_ids(out) == {7}

    _archive_match(arc, 8, dt.datetime(2026, 6, 2, tzinfo=dt.UTC))
    result = export.export_new(arc, out, accounts=[999])

    assert result.counts.get("matches", 0) == 0
    assert export.exported_match_ids(out) == {7}


def test_export_new_never_decodes_a_skipped_match_twice(tmp_path, monkeypatch):
    arc = tmp_path / "arc"
    arc.mkdir()
    out = tmp_path / "pq"
    _archive_match(arc, 7, dt.datetime(2026, 6, 1, tzinfo=dt.UTC))
    _archive_match(arc, 8, dt.datetime(2026, 6, 2, tzinfo=dt.UTC))

    export.export_new(arc, out, accounts=[42])
    assert export.exported_match_ids(out) == {7, 8}

    _archive_match(arc, 9, dt.datetime(2026, 6, 3, tzinfo=dt.UTC), accounts=(500, 501))
    export.export_new(arc, out, accounts=[42])

    assert export.exported_match_ids(out) == {7, 8}
    assert export.skipped_match_ids(out, [42]) == {9}

    decoded = []
    original = export._decode_matches

    def spy(paths):
        decoded.extend(paths)

        return original(paths)

    monkeypatch.setattr(export, "_decode_matches", spy)
    export.export_new(arc, out, accounts=[42])

    assert decoded == []


def test_skipped_matches_reset_when_the_accounts_change(tmp_path):
    arc = tmp_path / "arc"
    arc.mkdir()
    out = tmp_path / "pq"
    _archive_match(arc, 7, dt.datetime(2026, 6, 1, tzinfo=dt.UTC))
    export.export_new(arc, out, accounts=[42])

    _archive_match(arc, 9, dt.datetime(2026, 6, 3, tzinfo=dt.UTC), accounts=(500, 501))
    export.export_new(arc, out, accounts=[42])
    assert export.skipped_match_ids(out, [42]) == {9}

    assert export.skipped_match_ids(out, [42, 500]) == set()

    result = export.export_new(arc, out, accounts=[42, 500])

    assert result.counts["matches"] == 1
    assert export.exported_match_ids(out) == {7, 9}


def _meta_body(match_id):
    """A .meta.bz2 body for a built match, the shape the API and Valve return."""
    info = build_match(match_id=match_id)
    contents = pb.CMsgMatchMetaDataContents()
    contents.match_info.CopyFrom(info)
    meta = pb.CMsgMatchMetaData()
    meta.match_details = contents.SerializeToString()

    return bz2.compress(meta.SerializeToString())


def test_store_meta_writes_a_loadable_bin(tmp_path):
    assert not extract.has_match(tmp_path, 55)

    extract.store_meta(tmp_path, 55, 2062213690, _meta_body(55))

    assert extract.has_match(tmp_path, 55)
    assert extract.archived_match_ids(tmp_path) == {55}
    assert extract.load(tmp_path / "55_2062213690.bin").match_id == 55


def test_download_metadata_stores_then_skips(tmp_path, monkeypatch):
    from deadlock_matches import api, players

    monkeypatch.setattr(
        players, "salts", lambda mid: {"metadata_salt": 9, "metadata_url": "http://x"}
    )
    monkeypatch.setattr(api, "get_bytes", lambda url: _meta_body(55))

    written, missing = players.download_metadata([55], tmp_path)

    assert written == 1
    assert missing == []
    assert extract.has_match(tmp_path, 55)

    again, _ = players.download_metadata([55], tmp_path)
    assert again == 0


def test_download_metadata_reports_unavailable(tmp_path, monkeypatch):
    from deadlock_matches import players

    monkeypatch.setattr(players, "salts", lambda mid: None)

    written, missing = players.download_metadata([77], tmp_path)

    assert written == 0
    assert missing == [77]


def test_export_partitions_by_month(tmp_path):
    arc = tmp_path / "arc"
    arc.mkdir()
    out = tmp_path / "pq"

    _archive_match(arc, 10, dt.datetime(2026, 6, 5, tzinfo=dt.UTC))
    _archive_match(arc, 11, dt.datetime(2026, 7, 5, tzinfo=dt.UTC))

    result = export.export_all(arc, out)

    assert result.counts["matches"] == 2

    written = {p.name for p in (out / "matches").glob("*.parquet")}

    assert written == {"2026-06.parquet", "2026-07.parquet"}

    matches = queries.scan("matches", out).collect()

    assert sorted(matches["match_id"].to_list()) == [10, 11]


def test_movement_is_partitioned_and_readable(tmp_path):
    arc = tmp_path / "arc"
    arc.mkdir()
    out = tmp_path / "pq"

    _archive_match(arc, 10, dt.datetime(2026, 6, 5, tzinfo=dt.UTC))
    export.export_all(arc, out)

    assert (out / "movement").is_dir()

    movement = queries.scan("movement", out).collect()

    assert movement.height == 3
    assert movement["match_id"].unique().to_list() == [10]


def test_incremental_decodes_only_new_matches(tmp_path):
    arc = tmp_path / "arc"
    arc.mkdir()
    out = tmp_path / "pq"

    _archive_match(arc, 10, dt.datetime(2026, 6, 5, tzinfo=dt.UTC))
    export.export_all(arc, out)

    _archive_match(arc, 11, dt.datetime(2026, 7, 5, tzinfo=dt.UTC))
    result = export.export_new(arc, out)

    assert result.decoded == 1
    assert result.skipped == 1

    matches = queries.scan("matches", out).collect()

    assert sorted(matches["match_id"].to_list()) == [10, 11]


def test_incremental_leaves_untouched_month_alone(tmp_path):
    arc = tmp_path / "arc"
    arc.mkdir()
    out = tmp_path / "pq"

    _archive_match(arc, 10, dt.datetime(2026, 6, 5, tzinfo=dt.UTC))
    export.export_all(arc, out)

    june = out / "matches" / "2026-06.parquet"
    before = june.stat().st_mtime_ns

    _archive_match(arc, 11, dt.datetime(2026, 7, 5, tzinfo=dt.UTC))
    export.export_new(arc, out)

    assert june.stat().st_mtime_ns == before
    assert (out / "matches" / "2026-07.parquet").exists()


def test_incremental_is_idempotent(tmp_path):
    arc = tmp_path / "arc"
    arc.mkdir()
    out = tmp_path / "pq"

    _archive_match(arc, 10, dt.datetime(2026, 6, 5, tzinfo=dt.UTC))
    _archive_match(arc, 11, dt.datetime(2026, 6, 6, tzinfo=dt.UTC))
    export.export_all(arc, out)

    names = ("matches", "players", "damage", "movement")
    before = {name: len(queries.scan(name, out).collect()) for name in names}

    result = export.export_new(arc, out)

    assert result.decoded == 0
    assert result.skipped == 2

    after = {name: len(queries.scan(name, out).collect()) for name in names}

    assert before == after

    matches = queries.scan("matches", out).collect()

    assert matches["match_id"].n_unique() == matches.height


def test_write_partitioned_replaces_rather_than_duplicating(tmp_path):
    df = export.build_tables([build_match(match_id=5)])["matches"]

    export.write_partitioned("matches", df, "2026-06", tmp_path)
    export.write_partitioned("matches", df, "2026-06", tmp_path)

    got = pl.read_parquet(tmp_path / "matches" / "2026-06.parquet")

    assert got.height == 1
    assert got["match_id"].to_list() == [5]


def test_write_partitioned_raises_on_schema_drift_and_keeps_the_old_file(tmp_path):
    df = export.build_tables([build_match(match_id=5)])["matches"]

    export.write_partitioned("matches", df, "2026-06", tmp_path)

    target = tmp_path / "matches" / "2026-06.parquet"
    before = target.read_bytes()

    with pytest.raises((pl.exceptions.ShapeError, pl.exceptions.SchemaError, ValueError)):
        export.write_partitioned("matches", df.drop("duration_s"), "2026-06", tmp_path)

    assert target.read_bytes() == before


def test_write_partitioned_rejects_an_old_schema_month_file(tmp_path):
    df = export.build_tables([build_match(match_id=5)])["matches"]

    export.write_partitioned("matches", df, "2026-06", tmp_path)

    target = tmp_path / "matches" / "2026-06.parquet"
    pl.read_parquet(target).drop("duration_s").write_parquet(target)
    before = target.read_bytes()

    with pytest.raises(ValueError, match="full rebuild"):
        export.write_partitioned("matches", df, "2026-06", tmp_path)

    assert target.read_bytes() == before


def test_export_new_migrates_a_legacy_single_file_store(tmp_path):
    arc = tmp_path / "arc"
    arc.mkdir()
    out = tmp_path / "pq"
    out.mkdir()

    _archive_match(arc, 10, dt.datetime(2026, 6, 5, tzinfo=dt.UTC))
    _archive_match(arc, 11, dt.datetime(2026, 7, 5, tzinfo=dt.UTC))

    for name, df in export.build_tables(
        list(export._decode_matches(export._archive_paths(arc)))
    ).items():
        df.write_parquet(out / f"{name}.parquet")

    assert (out / "matches.parquet").exists()

    result = export.export_new(arc, out, exclude=("movement",))

    assert (out / "matches").is_dir()
    assert not (out / "matches.parquet").exists()

    matches = queries.scan("matches", out).collect()

    assert sorted(matches["match_id"].to_list()) == [10, 11]
    assert result.decoded == 0
    assert result.skipped == 2


def test_migrate_to_partitions_preserves_all_rows_without_decoding(tmp_path):
    out = tmp_path / "pq"
    out.mkdir()

    tables = export.build_tables([build_match(match_id=10)])

    for name, df in tables.items():
        df.write_parquet(out / f"{name}.parquet")

    before = {name: len(df) for name, df in tables.items()}

    export.migrate_to_partitions(out)

    for name in ("matches", "players", "damage", "movement"):
        assert not (out / f"{name}.parquet").exists()
        assert (out / name).is_dir()
        assert queries.scan(name, out).collect().height == before[name]
