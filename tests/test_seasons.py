import pytest

from deadlock_matches import seasons

PAYLOAD = [
    {
        "class_name": "season_1",
        "name": "Beta Season 1",
        "ranked_type": "normal",
        "base_win_loss_point_grant": 300,
        "intervals": [{"interval": 1, "start_timestamp": 100, "end_timestamp": 200}],
        "rank_info": [{"sub_rank_xp": [1000, 1000, 1000, 1000, 1000, 2000]}, {"rank_end": 111}],
    },
    {
        "class_name": "season_2",
        "name": "Beta Season 2",
        "ranked_type": "normal",
        "base_win_loss_point_grant": 350,
        "intervals": [{"interval": 2, "start_timestamp": 200, "end_timestamp": 300}],
        "rank_info": [{"sub_rank_xp": [1000, 1000, 1000, 1000, 1000, 1500]}, {"rank_end": 91}],
    },
]


@pytest.fixture
def live_seasons(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(seasons.api, "get_json", lambda *a, **k: PAYLOAD)


def test_known_reads_each_season_from_the_api(live_seasons):
    assert seasons.known() == (
        seasons.Season(1, "Beta Season 1", (1,), 100, 200, 300, 2000),
        seasons.Season(2, "Beta Season 2", (2,), 200, 300, 350, 1500),
    )


def test_known_falls_back_when_the_request_fails(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError

    monkeypatch.undo()
    monkeypatch.setattr(seasons.api, "get_json", boom)

    assert seasons.known() == seasons.SHIPPED


def test_known_falls_back_on_an_unexpected_shape(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(seasons.api, "get_json", lambda *a, **k: {"seasons": []})

    assert seasons.known() == seasons.SHIPPED


def test_tier_points_follow_the_top_subrank():
    one, two = seasons.SHIPPED

    assert one.tier_points == 7000
    assert two.tier_points == 6500


@pytest.mark.parametrize(("now", "number"), [(50, 1), (150, 1), (250, 2), (999, 2)])
def test_current_picks_the_newest_season_that_started(live_seasons, now, number):
    season = seasons.current(now)

    assert season is not None
    assert season.number == number


def test_current_is_none_when_no_season_is_known():
    assert seasons.current() is None


def test_pick_reads_each_season_word(live_seasons, monkeypatch):
    monkeypatch.setattr(seasons.time, "time", lambda: 250)

    assert seasons.pick(None) == seasons.known()[1]
    assert seasons.pick("current") == seasons.known()[1]
    assert seasons.pick("1") == seasons.known()[0]
    assert seasons.pick("pre") == seasons.PRE_SEASON
    assert seasons.pick("Pre-Season") == seasons.PRE_SEASON
    assert seasons.pick("all") is None
    assert seasons.pick("beta1") == seasons.known()[0]
    assert seasons.pick("Beta Season 2") == seasons.known()[1]


def test_pick_rejects_an_unknown_season(live_seasons):
    with pytest.raises(ValueError, match="Unknown season '7'"):
        seasons.pick("7")


def test_of_interval_finds_the_season(live_seasons):
    found = seasons.of_interval(2)

    assert found is not None
    assert found.name == "Beta Season 2"
    assert seasons.of_interval(9) is None
