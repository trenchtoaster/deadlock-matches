import re

from deadlock_matches import timeline
from deadlock_matches.extract import pb


def test_gold_source_matches_protobuf_enum():
    descriptor = pb.CMsgMatchMetaDataContents.DESCRIPTOR

    assert descriptor is not None

    enum = descriptor.enum_types_by_name["EGoldSource"]
    expected = {
        re.sub(r"(?<!^)(?=[A-Z])", "_", v.name.removeprefix("k_e")).upper(): v.number
        for v in enum.values
    }

    assert {m.name: m.value for m in timeline.GoldSource} == expected


def _snap(t, **fields):
    return {"time_stamp_s": t, **fields}


def _player(*snaps):
    return {"stats": list(snaps)}


def test_stat_at_exact_snapshot():
    p = _player(_snap(180, net_worth=1000), _snap(360, net_worth=2000))

    assert timeline.stat_at(p, "net_worth", 180) == 1000
    assert timeline.stat_at(p, "net_worth", 360) == 2000


def test_stat_at_interpolates_between_snapshots():
    p = _player(_snap(180, net_worth=1000), _snap(360, net_worth=2000))

    assert timeline.stat_at(p, "net_worth", 270) == 1500
    assert timeline.stat_at(p, "net_worth", 90) == 500


def test_stat_at_past_match_end_is_none():
    p = _player(_snap(180, net_worth=1000))

    assert timeline.stat_at(p, "net_worth", 181) is None


def test_stat_at_no_snapshots_is_none():
    assert timeline.stat_at(_player(), "net_worth", 60) is None
    assert timeline.stat_at({}, "net_worth", 60) is None


def _sources(*entries):
    return [{"source": s, "gold": g, "gold_orbs": o} for s, g, o in entries]


def test_farm_composite_reads_gold_sources_including_breakables():
    p = _player(
        _snap(
            180,
            gold_player=900,
            gold_sources=_sources(
                (2, 700, 400), (3, 100, 0), (5, 50, 0), (7, 100, 0), (12, 250, 0), (1, 900, 0)
            ),
        )
    )

    assert timeline.stat_at(p, "farm", 180) == 1600
    assert timeline.stat_at(p, "troopers", 180) == 1100
    assert timeline.stat_at(p, "jungle", 180) == 100
    assert timeline.stat_at(p, "breakables", 180) == 250
    assert timeline.stat_at(p, "combat", 180) == 900


def test_gold_sources_none_values_treated_as_zero():
    p = _player(_snap(180, gold_sources=[{"source": 12, "gold": 500, "gold_orbs": None}]))

    assert timeline.stat_at(p, "breakables", 180) == 500
    assert timeline.stat_at(p, "farm", 180) == 500


def test_protobuf_player_matches_dict_player():
    msg = pb.CMsgMatchMetaDataContents.Players()

    s = msg.stats.add()
    s.time_stamp_s = 180
    s.net_worth = 1000
    s.gold_player = 300
    g = s.gold_sources.add()
    g.source = 2
    g.gold = 500
    g.gold_orbs = 100
    g = s.gold_sources.add()
    g.source = 12
    g.gold = 80

    s2 = msg.stats.add()
    s2.time_stamp_s = 360
    s2.net_worth = 2400
    s2.gold_player = 700
    g = s2.gold_sources.add()
    g.source = 2
    g.gold = 1000
    g.gold_orbs = 300

    assert timeline.stat_at(msg, "net_worth", 270) == 1700
    assert timeline.stat_at(msg, "farm", 180) == 680
    assert timeline.stat_at(msg, "troopers", 360) == 1300
    assert timeline.stat_at(msg, "combat", 360) == 700


def test_curve_marks_past_end_as_none():
    p = _player(_snap(180, net_worth=1000), _snap(600, net_worth=3000))

    assert timeline.curve(p, "net_worth", [3, 10, 15]) == [1000, 3000, None]


def test_median_curve_drops_finished_games():
    short = _player(_snap(180, net_worth=1000))
    long1 = _player(_snap(180, net_worth=2000), _snap(600, net_worth=5000))
    long2 = _player(_snap(180, net_worth=3000), _snap(600, net_worth=9000))

    rows = timeline.median_curve([short, long1, long2], "net_worth", [3, 10])

    assert rows[0] == {"min": 3, "value": 2000, "n": 3}
    assert rows[1] == {"min": 10, "value": 7000, "n": 2}


def test_median_curve_empty_checkpoint():
    p = _player(_snap(180, net_worth=1000))

    rows = timeline.median_curve([p], "net_worth", [10])

    assert rows == [{"min": 10, "value": None, "n": 0}]


def test_compare_gap():
    me = _player(_snap(180, net_worth=1000), _snap(600, net_worth=4000))
    other = _player(_snap(180, net_worth=1500), _snap(600, net_worth=6000))

    rows = timeline.compare([me], [other], "net_worth", [3, 10, 15])

    assert rows[0]["gap"] == -500
    assert rows[1]["gap"] == -2000
    assert rows[2]["gap"] is None


def test_interval_rates():
    rows = [
        {"min": 3, "me": 900},
        {"min": 6, "me": 2400},
        {"min": 10, "me": None},
        {"min": 15, "me": 9000},
    ]

    rates = timeline.interval_rates(rows, "me")

    assert rates[0] == 300
    assert rates[1] == 500
    assert rates[2] is None
    assert rates[3] is None
