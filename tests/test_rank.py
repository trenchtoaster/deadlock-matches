import datetime as dt
import zoneinfo

import pytest

from deadlock_matches import export, players, schemas
from deadlock_matches.cli import rank
from deadlock_matches.cli.main import main
from deadlock_matches.extract import pb

START = 1785500000

ZONE = zoneinfo.ZoneInfo("America/Chicago")

MIRAGE = 52

INFERNUS = 1

PLACEMENT_WIN = {
    "initial_display_rank": 0,
    "initial_flat_progress": 0,
    "final_flat_progress": 125,
    "desired_progress_change": 125,
    "initial_calibration_games": 8,
    "initial_demotion_protection_games": 0,
    "consumed_demotion_protection": False,
    "initial_win_streak": 0,
}

PLACEMENT_LOSS = {
    "initial_display_rank": 0,
    "initial_flat_progress": 0,
    "final_flat_progress": 0,
    "desired_progress_change": -125,
    "initial_calibration_games": 7,
    "initial_demotion_protection_games": 0,
    "consumed_demotion_protection": False,
    "initial_win_streak": 1,
}

PROTECTED_LOSS = {
    "initial_display_rank": 86,
    "initial_flat_progress": 54045,
    "final_flat_progress": 54000,
    "desired_progress_change": -375,
    "initial_calibration_games": 0,
    "initial_demotion_protection_games": 2,
    "consumed_demotion_protection": True,
    "initial_win_streak": 3,
}

PLAIN_LOSS = {
    "initial_display_rank": 86,
    "initial_flat_progress": 54300,
    "final_flat_progress": 54000,
    "desired_progress_change": -300,
    "initial_calibration_games": 0,
    "initial_demotion_protection_games": 1,
    "consumed_demotion_protection": False,
    "initial_win_streak": 0,
}

PLAIN_WIN = {
    "initial_display_rank": 86,
    "initial_flat_progress": 54000,
    "final_flat_progress": 54300,
    "desired_progress_change": 300,
    "initial_calibration_games": 0,
    "initial_demotion_protection_games": 2,
    "consumed_demotion_protection": False,
    "initial_win_streak": 0,
}

SMALL_SEASON = {
    "name": "Test Season",
    "min_wins": 3,
    "min_hero_wins": 2,
    "min_hero_unlocks": 2,
}


def local_day(day):
    """Local date of the match started day days after START."""
    return dt.datetime.fromtimestamp(START + day * 86400, dt.UTC).astimezone(ZONE).date()


def add_player(info, account_id, hero_id, team, slot, *, outcome, ranking=None):
    """Add one scoreboard player, with the Ranked progression block when given."""
    p = info.players.add()
    p.account_id = account_id
    p.hero_id = hero_id
    p.team = team
    p.player_slot = slot
    p.player_match_outcome = outcome
    p.kills = 5
    p.deaths = 4
    p.assists = 6
    p.net_worth = 40000 - slot * 1000
    p.last_hits = 100
    p.denies = 2

    s = p.stats.add()
    s.time_stamp_s = 600
    s.player_damage = 10000

    if ranking is not None:
        for name, value in ranking.items():
            setattr(p.player_rank_data, name, value)

    return p


def build_ranked_match(match_id, day, *, mine, theirs, won=True):
    """Build a two-player Ranked match where account 42 carries the mine progression."""
    info = pb.CMsgMatchMetaDataContents().match_info
    info.match_id = match_id
    info.start_time = START + day * 86400
    info.duration_s = 1800
    info.winning_team = pb.k_ECitadelLobbyTeam_Team1
    info.match_mode = pb.k_ECitadelMatchMode_Ranked
    info.game_mode = pb.k_ECitadelGameMode_Normal
    info.ranked_type = pb.k_ECitadelRankedType_Normal
    info.rank_interval = 1

    outcome = pb.k_EPlayerMatchOutcome_Win if won else pb.k_EPlayerMatchOutcome_Loss
    other = pb.k_EPlayerMatchOutcome_Loss if won else pb.k_EPlayerMatchOutcome_Win

    add_player(
        info,
        42,
        MIRAGE,
        pb.k_ECitadelLobbyTeam_Team1,
        1,
        outcome=outcome,
        ranking=mine,
    )
    add_player(
        info,
        43,
        INFERNUS,
        pb.k_ECitadelLobbyTeam_Team0,
        2,
        outcome=other,
        ranking=theirs,
    )

    return info


def build_standard_match(match_id, day, hero_id, *, account_id=42, won=True, game_mode=None):
    """Build a Standard match the eligibility counts can read."""
    info = pb.CMsgMatchMetaDataContents().match_info
    info.match_id = match_id
    info.start_time = START + day * 86400
    info.duration_s = 1800
    info.winning_team = pb.k_ECitadelLobbyTeam_Team1
    info.match_mode = pb.k_ECitadelMatchMode_Unranked
    info.game_mode = pb.k_ECitadelGameMode_Normal if game_mode is None else game_mode

    outcome = pb.k_EPlayerMatchOutcome_Win if won else pb.k_EPlayerMatchOutcome_Loss
    add_player(info, account_id, hero_id, pb.k_ECitadelLobbyTeam_Team1, 1, outcome=outcome)
    add_player(
        info,
        43,
        INFERNUS,
        pb.k_ECitadelLobbyTeam_Team0,
        2,
        outcome=pb.k_EPlayerMatchOutcome_Loss,
    )

    return info


def write_tables(out_dir, infos):
    """Write the parquet tables for these matches into a flat directory."""
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, df in export.build_tables(infos, exclude=("movement",)).items():
        df.write_parquet(out_dir / f"{name}.parquet")

    return out_dir


def season_infos():
    """Take the placement win, the protected loss, and the plain win of one Ranked season."""
    return [
        build_ranked_match(901, 0, mine=PLACEMENT_WIN, theirs=PLACEMENT_LOSS),
        build_ranked_match(902, 1, mine=PROTECTED_LOSS, theirs=PLAIN_WIN, won=False),
        build_ranked_match(903, 2, mine=PLAIN_WIN, theirs=PLAIN_LOSS),
    ]


@pytest.fixture(autouse=True)
def offline_seasons(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError

    monkeypatch.setattr(rank.api, "get_json", boom)


@pytest.fixture
def ranked_pq(tmp_path):
    return write_tables(tmp_path / "pq", season_infos())


@pytest.fixture
def unranked_pq(tmp_path):
    infos = [
        build_standard_match(910, 0, MIRAGE),
        build_standard_match(911, 1, MIRAGE),
        build_standard_match(912, 2, INFERNUS),
        build_standard_match(913, 3, INFERNUS, won=False),
    ]

    return write_tables(tmp_path / "pq", infos)


def run(tmp_path, parquet, *args, accounts="you = 42"):
    """Run the CLI against a prepared parquet directory."""
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'timezone = "America/Chicago"\n[accounts]\n{accounts}\n')
    (tmp_path / "cache").mkdir(exist_ok=True)

    base = ["--cache", str(tmp_path / "cache"), "--archive", str(tmp_path / "arc")]

    if parquet is not None:
        base += ["--parquet", str(parquet)]

    main([*base, *args], config=cfg)


def test_rank_table_shows_a_placement_a_protected_loss_and_a_win(tmp_path, ranked_pq, capsys):
    run(tmp_path, ranked_pq, "rank")

    lines = capsys.readouterr().out.splitlines()
    header, first, second, third = lines[0], lines[1], lines[2], lines[3]

    assert "Rating" in header
    assert "Points" in header
    assert "Change" in header
    assert "Streak" in header

    assert str(local_day(0)) in first
    assert "Placing" in first
    assert "0 -> 125" in first
    assert "+125" in first
    assert "8 placements left" in first

    assert "Oracle VI" in second
    assert "loss" in second
    assert "54,045 -> 54,000" in second
    assert "-45 (-375)" in second
    assert "demotion protection used" in second

    assert "win" in third
    assert "54,000 -> 54,300" in third
    assert "+300" in third
    assert "demotion protection" not in third


def test_rank_footer_reports_the_rating_record_and_net_points(tmp_path, ranked_pq, capsys):
    run(tmp_path, ranked_pq, "rank")

    out = capsys.readouterr().out

    assert "Rating: Oracle VI at 54,300 points. 300 of 2,000 into the subrank." in out
    assert "Season record: 2-1. Net over the 2 games since placing is +255 points." in out


def test_subrank_span_floors_and_widths():
    assert rank._subrank_span(11) == (0, 1000)
    assert rank._subrank_span(36) == (19000, 2000)
    assert rank._subrank_span(74) == (45000, 1000)
    assert rank._subrank_span(86) == (54000, 2000)


def test_rank_footer_measures_from_the_subrank_floor(tmp_path, capsys):
    win = {
        **PLAIN_WIN,
        "initial_display_rank": 74,
        "initial_flat_progress": 45400,
        "final_flat_progress": 45700,
    }
    parquet = write_tables(
        tmp_path / "pq", [build_ranked_match(950, 0, mine=win, theirs=PLAIN_LOSS)]
    )

    run(tmp_path, parquet, "rank")

    out = capsys.readouterr().out

    assert "at 45,700 points. 700 of 1,000 into the subrank." in out


def test_rank_footer_skips_the_subrank_for_eternus(tmp_path, capsys):
    win = {
        **PLAIN_WIN,
        "initial_display_rank": 111,
        "initial_flat_progress": 70100,
        "final_flat_progress": 70400,
    }
    parquet = write_tables(
        tmp_path / "pq", [build_ranked_match(951, 0, mine=win, theirs=PLAIN_LOSS)]
    )

    run(tmp_path, parquet, "rank")

    out = capsys.readouterr().out

    assert "Rating: Eternus I at 70,400 points." in out
    assert "into the subrank" not in out


def test_rank_footer_skips_the_subrank_while_placing(tmp_path, capsys):
    parquet = write_tables(tmp_path / "pq", [season_infos()[0]])

    run(tmp_path, parquet, "rank")

    out = capsys.readouterr().out

    assert "Rating: Placing." in out
    assert "Placing at" not in out
    assert "into the subrank" not in out
    assert "Season record: 1-0." in out
    assert "Net over" not in out


def test_rank_net_skips_placement_banks(tmp_path, capsys):
    second_win = {**PLACEMENT_WIN, "initial_calibration_games": 7, "final_flat_progress": 150}
    infos = [
        build_ranked_match(904, 0, mine=PLACEMENT_WIN, theirs=PLACEMENT_LOSS),
        build_ranked_match(905, 1, mine=second_win, theirs=PLACEMENT_LOSS),
        build_ranked_match(906, 2, mine=PLAIN_LOSS, theirs=PLAIN_WIN, won=False),
    ]
    parquet = write_tables(tmp_path / "pq", infos)

    run(tmp_path, parquet, "rank")

    out = capsys.readouterr().out

    assert "0 -> 150" in out
    assert "Season record: 2-1. Net over the 1 game since placing is -300 points." in out


def test_rank_flags_an_archive_gap(tmp_path, capsys):
    later_win = {
        **PLAIN_WIN,
        "initial_flat_progress": 55600,
        "final_flat_progress": 55900,
    }
    infos = [
        build_ranked_match(940, 0, mine=PLAIN_WIN, theirs=PLAIN_LOSS),
        build_ranked_match(941, 1, mine=later_win, theirs=PLAIN_LOSS, won=True),
    ]
    parquet = write_tables(tmp_path / "pq", infos)

    run(tmp_path, parquet, "rank")

    out = capsys.readouterr().out
    gap_row = next(line for line in out.splitlines() if "55,600 -> 55,900" in line)

    assert "archive gap before this" in gap_row
    assert (
        "Archive gaps: 1 game started on points the stored game before does not explain. "
        "Run deadlock sync --source api to backfill." in out
    )


def test_rank_gap_check_skips_the_placement_boundary(tmp_path, ranked_pq, capsys):
    run(tmp_path, ranked_pq, "rank")

    out = capsys.readouterr().out

    assert "archive gap" not in out
    assert "Archive gaps" not in out


def test_rank_gap_check_keeps_accounts_apart(tmp_path, ranked_pq, capsys):
    run(tmp_path, ranked_pq, "rank", "--account", "42,43", accounts="you = 42\nthem = 43")

    out = capsys.readouterr().out

    assert "archive gap" not in out
    assert "Archive gaps" not in out


def test_rank_survives_a_ranked_game_without_rank_data(tmp_path, capsys):
    parquet = write_tables(tmp_path / "pq", [build_ranked_match(907, 0, mine=None, theirs=None)])

    run(tmp_path, parquet, "rank")

    out = capsys.readouterr().out

    assert "Rating: -." in out
    assert "Season record: 1-0." in out
    assert "Net over" not in out


def test_rank_drops_games_before_the_season_start(tmp_path, capsys, monkeypatch):
    rules = {**SMALL_SEASON, "start_timestamp": START - 43200}
    monkeypatch.setattr(rank, "season_rules", lambda: dict(rules))
    infos = [
        build_ranked_match(908, -2, mine=PLAIN_LOSS, theirs=PLAIN_WIN, won=False),
        build_ranked_match(909, 0, mine=PLAIN_WIN, theirs=PLAIN_LOSS),
    ]
    parquet = write_tables(tmp_path / "pq", infos)

    run(tmp_path, parquet, "rank")

    out = capsys.readouterr().out

    assert "54,000 -> 54,300" in out
    assert "54,300 -> 54,000" not in out
    assert "Season record: 1-0." in out


def test_rank_eligibility_ignores_street_brawl_wins(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(rank, "season_rules", lambda: dict(SMALL_SEASON))
    infos = [
        build_standard_match(910, 0, MIRAGE),
        build_standard_match(911, 1, MIRAGE, game_mode=pb.k_ECitadelGameMode_StreetBrawl),
    ]
    parquet = write_tables(tmp_path / "pq", infos)

    run(tmp_path, parquet, "rank")

    out = capsys.readouterr().out

    assert "Wins                     1 of 3" in out
    assert "Mirage               1\n" in out


def test_rank_eligibility_compacts_several_accounts(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(rank, "season_rules", lambda: dict(SMALL_SEASON))
    infos = [
        build_standard_match(910, 0, MIRAGE),
        build_standard_match(911, 1, MIRAGE, account_id=44),
        build_standard_match(912, 2, INFERNUS, account_id=44),
    ]
    parquet = write_tables(tmp_path / "pq", infos)

    run(tmp_path, parquet, "rank", "--account", "42,44", accounts="you = 42\nalt = 44")

    out = capsys.readouterr().out

    assert "Ranked eligibility (Test Season)" in out
    assert "  Account             Wins  Heroes at 2 wins" in out
    assert "  you               1 of 3  0 of 2" in out
    assert "  alt               2 of 3  0 of 2" in out
    assert "qualified" not in out
    assert "No Ranked games stored" not in out
    assert rank.ARCHIVE_NOTE in out


def test_rank_days_narrows_the_window_but_not_the_season_record(tmp_path, ranked_pq, capsys):
    run(tmp_path, ranked_pq, "rank", "--days", "1")

    out = capsys.readouterr().out

    assert "0 -> 125" not in out
    assert "54,000 -> 54,300" in out
    assert "Season record: 2-1. Net over the 1 game above is +300 points." in out


def test_rank_since_drops_every_game_in_the_window(tmp_path, ranked_pq, capsys):
    run(tmp_path, ranked_pq, "rank", "--since", str(local_day(30)))

    assert "No Ranked games in that window" in capsys.readouterr().out


def test_rank_eligibility_counts_wins_and_qualified_heroes(
    tmp_path, unranked_pq, capsys, monkeypatch
):
    monkeypatch.setattr(rank, "season_rules", lambda: dict(SMALL_SEASON))

    run(tmp_path, unranked_pq, "rank")

    out = capsys.readouterr().out

    assert "No Ranked games stored for you." in out
    assert "Ranked eligibility (Test Season)" in out
    assert "Wins                     3 of 3" in out
    assert "Heroes at 2 wins         1 of 2" in out
    assert "Mirage               2  qualified" in out
    assert "Infernus             1\n" in out
    assert rank.ARCHIVE_NOTE in out


def test_rank_eligibility_skips_the_accounts_that_already_play_ranked(
    tmp_path, ranked_pq, capsys, monkeypatch
):
    monkeypatch.setattr(rank, "season_rules", lambda: dict(SMALL_SEASON))

    run(tmp_path, ranked_pq, "rank", "--account", "42,43", accounts="you = 42\nthem = 43")

    out = capsys.readouterr().out

    assert "Ranked eligibility" not in out
    assert "you" in out
    assert "them" in out


def test_rank_mixes_a_ranked_account_with_an_eligibility_block(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(rank, "season_rules", lambda: dict(SMALL_SEASON))
    infos = [*season_infos(), build_standard_match(920, 3, MIRAGE, account_id=44)]
    parquet = write_tables(tmp_path / "pq", infos)

    run(tmp_path, parquet, "rank", "--account", "42,44", accounts="you = 42\nalt = 44")

    out = capsys.readouterr().out

    assert "54,000 -> 54,300" in out
    assert "No Ranked games stored for alt." in out
    assert "Wins                     1 of 3" in out


def test_rank_without_stored_wins_says_so(tmp_path, unranked_pq, capsys, monkeypatch):
    monkeypatch.setattr(rank, "season_rules", lambda: dict(SMALL_SEASON))

    run(tmp_path, unranked_pq, "rank", "--account", "77", accounts="you = 42")

    out = capsys.readouterr().out

    assert "Wins                     0 of 3" in out
    assert "No wins stored for this account yet." in out


def test_rank_reads_the_players_store_for_a_downloaded_account(tmp_path, capsys, monkeypatch):
    main_store = tmp_path / "parquet"
    players_store = tmp_path / "parquet-players"
    monkeypatch.setattr(export, "PARQUET_DIR", main_store)
    monkeypatch.setattr(players, "PARQUET_DIR", players_store)
    write_tables(main_store, [build_standard_match(930, 0, MIRAGE, account_id=99)])
    write_tables(players_store, season_infos())
    schemas.conform(
        "downloads",
        [
            {
                "match_id": 903,
                "account_id": 42,
                "player": "someone",
                "hero_id": MIRAGE,
                "rank": 1,
                "region": "Europe",
                "downloaded_at": dt.datetime(2026, 8, 1, tzinfo=dt.UTC),
            }
        ],
    ).write_parquet(players_store / "downloads.parquet")

    run(tmp_path, None, "rank", "--account", "42", accounts="you = 99")

    out = capsys.readouterr().out

    assert "54,000 -> 54,300" in out
    assert "Season record: 2-1" in out


def test_season_rules_reads_the_api(monkeypatch):
    payload = [
        {
            "class_name": "season_1",
            "name": "Beta Season 1",
            "ranked_type": "normal",
            "min_wins": 60,
            "min_hero_wins": 15,
            "min_hero_unlocks": 3,
        }
    ]
    monkeypatch.setattr(rank.api, "get_json", lambda *a, **k: payload)

    assert rank.season_rules() == {
        "name": "Beta Season 1",
        "min_wins": 60,
        "min_hero_wins": 15,
        "min_hero_unlocks": 3,
        "start_timestamp": 1_785_430_800,
    }


def test_season_rules_reads_the_season_start(monkeypatch):
    payload = [
        {
            "name": "Beta Season 2",
            "ranked_type": "normal",
            "intervals": [
                {"interval": 1, "start_timestamp": 1_791_500_000, "end_timestamp": 1_797_000_000},
                {"interval": 2, "start_timestamp": 1_794_000_000, "end_timestamp": 1_799_000_000},
            ],
        }
    ]
    monkeypatch.setattr(rank.api, "get_json", lambda *a, **k: payload)

    assert rank.season_rules()["start_timestamp"] == 1_791_500_000


def test_season_rules_falls_back_when_the_request_fails(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError

    monkeypatch.setattr(rank.api, "get_json", boom)

    assert rank.season_rules() == rank.SEASON_FALLBACK


def test_season_rules_falls_back_on_an_unexpected_shape(monkeypatch):
    monkeypatch.setattr(rank.api, "get_json", lambda *a, **k: {"seasons": []})

    assert rank.season_rules() == rank.SEASON_FALLBACK


def test_match_scoreboard_adds_rating_and_points_for_ranked(tmp_path, ranked_pq, capsys):
    run(tmp_path, ranked_pq, "match", "903", "--hero", "Mirage")

    lines = capsys.readouterr().out.splitlines()
    header = next(line for line in lines if "K/D/A" in line)
    mine = next(line for line in lines if "Mirage *" in line)
    theirs = next(line for line in lines if "Infernus" in line and "K/D/A" not in line)

    assert header.rstrip().endswith("Rating         Points")
    assert "Oracle VI" in mine
    assert "+300" in mine
    assert "Oracle VI" in theirs
    assert "-300" in theirs


def test_match_scoreboard_calls_a_placement_player_placing(tmp_path, ranked_pq, capsys):
    run(tmp_path, ranked_pq, "match", "901", "--hero", "Mirage")

    out = capsys.readouterr().out
    mine = next(line for line in out.splitlines() if "Mirage *" in line)

    assert "Placing" in mine
    assert "+125" in mine
    assert "Points: 0 -> 125 (+125), 8 placements left." in out


def test_match_points_line_reports_the_assigned_change_and_protection(tmp_path, ranked_pq, capsys):
    run(tmp_path, ranked_pq, "match", "902", "--hero", "Mirage")

    out = capsys.readouterr().out

    assert "Points: 54,045 -> 54,000 (-45, -375 assigned), demotion protection used." in out


def test_match_scoreboard_leaves_a_standard_game_alone(tmp_path, unranked_pq, capsys):
    run(tmp_path, unranked_pq, "match", "910", "--hero", "Mirage")

    out = capsys.readouterr().out
    header = next(line for line in out.splitlines() if "K/D/A" in line)

    assert "Rating" not in header
    assert "Points:" not in out
    assert "Placing" not in out
