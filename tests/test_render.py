import pytest

from deadlock_matches import queries
from deadlock_matches.cli import render


def test_reading_turns_a_sign_into_good_or_bad_news():
    kills = queries.MY_GAMES_MEASURES["kills"]
    deaths = queries.MY_GAMES_MEASURES["deaths"]
    games = queries.MY_GAMES_MEASURES["games"]

    assert render.reading(kills, 12) == "better"
    assert render.reading(kills, -12) == "worse"
    assert render.reading(deaths, 12) == "worse"
    assert render.reading(deaths, -12) == "better"
    assert render.reading(games, 12) == ""
    assert render.reading(kills, 0) == ""
    assert render.reading(kills, None) == ""


def test_spread_lays_one_measure_out_as_a_column_per_side():
    fields = render.spread("kills", ("You", "Them", "Gap"), (8, 9, 8))

    assert [f.column for f in fields] == ["you_kills", "them_kills", "gap_kills"]
    assert [f.title for f in fields] == ["You", "Them", "Gap"]
    assert [f.sign for f in fields] == [False, False, True]


def test_a_field_reads_a_plain_summarize_result_when_it_names_no_side():
    assert render.Field("kills").column == "kills"
    assert render.Field("kills").title == "kills"


def test_a_table_prints_every_number_through_the_format_its_measure_declares():
    rows = [
        {"hero": "Mirage", "win_rate": 0.6667, "net_worth": 41250},
        {"hero": "Haze", "win_rate": 0.5, "net_worth": 38000},
    ]
    lines = render.table(
        queries.my_games,
        rows,
        [
            render.Key("hero", "Hero", 10),
            render.Field("win_rate", heading="Win rate", width=10),
            render.Field("net_worth", heading="Souls", width=10),
        ],
    )

    assert lines == [
        "  Hero        Win rate     Souls",
        "  Mirage         66.7%    41,250",
        "  Haze           50.0%    38,000",
    ]


def test_a_key_with_no_width_is_sized_to_the_longest_label_it_holds():
    rows = [{"hero": "Mirage", "games": 1}, {"hero": "Seven", "games": 2}]
    lines = render.table(
        queries.my_games,
        rows,
        [render.Key("hero", "Hero"), render.Field("games", width=7)],
    )

    assert lines[0] == "  Hero      games"
    assert lines[1] == "  Mirage        1"


def test_a_key_swaps_a_stored_value_for_the_name_the_report_calls_it():
    lines = render.table(
        queries.damage_source_games,
        [{"delivery": "gun_proc", "total": 100}],
        [
            render.Key("delivery", "Delivery", 24, {"gun_proc": "Items (bullet procs)"}),
            render.Field("total", width=8),
        ],
    )

    assert lines[1] == "  Items (bullet procs)         100"


def test_a_missing_value_prints_the_blank_rather_than_a_zero():
    lines = render.table(
        queries.my_games,
        [{"hero": "Mirage"}],
        [render.Key("hero", "Hero", 10), render.Field("kills", width=8)],
    )

    assert lines[1] == "  Mirage           -"


def test_a_total_line_lands_on_the_same_columns_as_the_table_above_it():
    rows = [{"hero": "Mirage", "kills": 60}, {"hero": "Seven", "kills": 40}]
    columns = [render.Key("hero", "Hero"), render.Field("kills", width=8)]
    table = render.table(queries.my_games, rows, columns)
    total = render.total_line(queries.my_games, {"kills": 100}, columns, rows)

    assert total == "  Total        100"
    assert len(total) == len(table[1])


def test_a_total_line_leaves_a_column_it_carries_no_number_for_blank():
    columns = [
        render.Key("hero", "Hero", 10),
        render.Field("kills", width=8),
        render.Field("deaths", width=8),
    ]
    total = render.total_line(queries.my_games, {"kills": 100}, columns, blank="")

    assert total == "  Total          100        "


def test_gap_lines_read_each_measure_against_the_direction_it_declares():
    row = {
        "you_kills": 6,
        "them_kills": 4,
        "gap_kills": 2,
        "you_deaths": 3,
        "them_deaths": 8,
        "gap_deaths": -5,
        "you_games": 10,
        "them_games": 10,
        "gap_games": 0,
    }
    lines = render.gap_lines(
        queries.my_games,
        row,
        [render.Metric("kills", "Kills"), render.Metric("deaths"), render.Metric("games")],
        label_width=8,
        width=6,
    )

    assert lines == [
        "  Metric     You  Them   Gap",
        "  Kills        6     4    +2  better",
        "  deaths       3     8    -5  better",
        "  games       10    10    +0",
    ]


def test_gap_lines_skip_a_measure_neither_side_recorded():
    row = {"you_kills": None, "them_kills": None, "gap_kills": 0, "you_deaths": 3}
    lines = render.gap_lines(
        queries.my_games,
        row,
        [render.Metric("kills"), render.Metric("deaths")],
        label_width=8,
        width=6,
    )

    assert len(lines) == 2
    assert "kills" not in lines[1]


def test_gap_lines_keep_a_side_that_only_one_scope_has():
    row = {"you_kills": 6, "them_kills": None, "gap_kills": 6}
    lines = render.gap_lines(
        queries.my_games, row, [render.Metric("kills")], label_width=8, width=6
    )

    assert lines[1] == "  kills        6     -    +6  better"


def test_a_field_format_overrides_what_the_measure_declares():
    columns = [render.Field("win_rate", "you", "You %", 8, queries.Format(scale=100, suffix="%"))]
    lines = render.table(queries.my_games, [{"you_win_rate": 0.5872}], columns)

    assert lines[1] == "       59%"


def test_an_unknown_measure_names_the_valid_ones():
    with pytest.raises(ValueError, match="my_games has no measure 'kils'"):
        render.table(queries.my_games, [{}], [render.Field("kils")])
