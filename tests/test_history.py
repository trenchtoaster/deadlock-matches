import datetime as dt

from deadlock_matches.assets import history

STATES = [
    {"from": "2026-01-01T00:00:00", "build": 1, "records": {"7": {"id": 7, "cost": 500}}},
    {"from": "2026-02-01T00:00:00", "build": 2, "records": {"7": {"id": 7, "cost": 800}}},
]


def test_has_history_reflects_the_file(tmp_path):
    missing = tmp_path / "none.parquet"

    assert not history.has_history(missing)

    path = tmp_path / "h.parquet"
    history.write(path, STATES)

    assert history.has_history(path)


def test_empty_history_file_reads_as_no_history(tmp_path):
    path = tmp_path / "h.parquet"
    history.write(path, [])

    assert not history.has_history(path)
    assert history.eras(path) == []
    assert history.record_asof(path, 7, dt.datetime(2026, 1, 5)) is None
    assert history.records_asof(path, dt.datetime(2026, 1, 5)) is None


def test_record_asof_picks_the_latest_era_on_or_before(tmp_path):
    path = tmp_path / "h.parquet"
    history.write(path, STATES)

    january = history.record_asof(path, 7, dt.datetime(2026, 1, 15))
    march = history.record_asof(path, 7, dt.datetime(2026, 3, 1))

    assert january is not None

    assert january["cost"] == 500
    assert march is not None
    assert march["cost"] == 800


def test_record_asof_older_than_all_gets_earliest(tmp_path):
    path = tmp_path / "h.parquet"
    history.write(path, STATES)

    earliest = history.record_asof(path, 7, dt.datetime(2025, 1, 1))

    assert earliest is not None

    assert earliest["cost"] == 500


def test_record_asof_unknown_id_returns_none(tmp_path):
    path = tmp_path / "h.parquet"
    history.write(path, STATES)

    assert history.record_asof(path, 999, dt.datetime(2026, 3, 1)) is None


def test_record_asof_missing_file_returns_none(tmp_path):
    assert history.record_asof(tmp_path / "none.parquet", 7, dt.datetime(2026, 3, 1)) is None


def test_eras_lists_each_era_oldest_first(tmp_path):
    path = tmp_path / "h.parquet"
    history.write(path, STATES)

    assert history.eras(path) == [("2026-01-01T00:00:00", 1), ("2026-02-01T00:00:00", 2)]
    assert history.eras(tmp_path / "none.parquet") == []


def test_read_states_round_trips_written_states(tmp_path):
    path = tmp_path / "h.parquet"
    history.write(path, STATES)

    assert history.read_states(path) == STATES
    assert history.read_states(tmp_path / "none.parquet") == []


def test_record_history_returns_each_era_for_one_id(tmp_path):
    path = tmp_path / "h.parquet"
    history.write(path, STATES)

    series = history.record_history(path, 7)

    assert [(frm, build, rec["cost"]) for frm, build, rec in series] == [
        ("2026-01-01T00:00:00", 1, 500),
        ("2026-02-01T00:00:00", 2, 800),
    ]
    assert history.record_history(path, 999) == []
    assert history.record_history(tmp_path / "none.parquet", 7) == []
