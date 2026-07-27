import datetime as dt
import inspect
from typing import Any

import polars as pl
import pytest

from deadlock_matches import queries, schemas
from deadlock_matches.assets import heroes

START = dt.datetime(2026, 7, 1, 18, tzinfo=dt.UTC)


def untyped(value: Any) -> Any:
    """Hand a value over with its static type erased.

    - the runtime guards exist for callers that run no type checker, so a
      test of one has to reach them the same way
    """
    return value


MATCHES = [
    (1, False),
    (2, False),
    (3, False),
    (4, True),
]

PLAYERS = [
    (1, 10, "Mirage", True),
    (2, 10, "Mirage", False),
    (3, 20, "Mirage", True),
    (4, 10, "Haze", True),
]


def _write(parquet_dir):
    matches = [
        {
            "match_id": match_id,
            "start_time": START + dt.timedelta(hours=match_id),
            "duration_s": 1800,
            "winning_team": 0,
            "match_mode": 1,
            "game_mode": 1,
            "average_badge_team0": 71,
            "average_badge_team1": 75,
            "not_scored": not_scored,
        }
        for match_id, not_scored in MATCHES
    ]
    players = [
        {
            "match_id": match_id,
            "start_time": START + dt.timedelta(hours=match_id),
            "account_id": account_id,
            "hero_id": heroes.hero_id_by_name(hero),
            "team": 0 if won else 1,
            "player_slot": 1,
            "assigned_lane": 1,
            "lane": "yellow",
            "won": won,
            "kills": 6,
            "deaths": 3,
            "assists": 3,
            "net_worth": 40000,
            "last_hits": 200,
            "denies": 20,
            "mvp_rank": 0,
            "party": None,
            "abandon_time_s": None,
        }
        for match_id, account_id, hero, won in PLAYERS
    ]

    for name, rows in (("matches", matches), ("players", players)):
        schemas.conform(name, rows).write_parquet(schemas.table_path(name, parquet_dir))


@pytest.fixture
def semantic_pq(tmp_path):
    _write(tmp_path)

    return tmp_path


def summarize(pq, **kwargs):
    return queries.summarize(
        queries.my_games,
        parquet_dir=pq,
        accounts=[10, 20],
        tz="America/Chicago",
        **kwargs,
    ).collect()


def test_only_composable_sources_are_registered():
    assert [spec.name for spec in queries.registered_views()] == [
        "buff_games",
        "combat_games",
        "compare_intervals",
        "cumulative_marks",
        "damage_source_games",
        "hero_damage_games",
        "milestone_games",
        "movement_games",
        "my_games",
        "record_games",
        "soul_source_games",
        "stack_games",
        "stat_snapshots",
    ]

    assert queries.view_spec(queries.daily_record) is None
    assert queries.view_spec(queries.combat_game_records) is None
    assert queries.view_spec(queries.item_games) is None
    assert queries.view_spec(queries.scan) is None


def test_summarize_groups_by_declared_dimensions(semantic_pq):
    df = summarize(semantic_pq, by=["account"], measures=["games", "scored_games", "wins"])

    assert df.get_column("account").to_list() == [10, 20]
    assert df.get_column("games").to_list() == [3, 1]
    assert df.get_column("scored_games").to_list() == [2, 1]
    assert df.get_column("wins").to_list() == [1, 1]


def test_win_rate_recomposes_from_totals_not_from_group_rates(semantic_pq):
    per_account = summarize(
        semantic_pq, by=["account"], measures=["wins", "scored_games", "win_rate"]
    )
    overall = summarize(semantic_pq, measures=["wins", "scored_games", "win_rate"])

    assert per_account.get_column("win_rate").to_list() == [0.5, 1.0]
    assert per_account.get_column("win_rate").mean() == 0.75

    pooled = overall.get_column("win_rate").item()

    assert pooled == pytest.approx(2 / 3)
    assert overall.get_column("wins").item() == per_account.get_column("wins").sum()
    assert overall.get_column("scored_games").item() == per_account.get_column("scored_games").sum()


def test_summarize_without_dimensions_returns_one_row(semantic_pq):
    df = summarize(semantic_pq, measures=["games"])

    assert df.height == 1
    assert df.get_column("games").item() == 4


def test_metric_views_and_summarize_stay_lazy(semantic_pq):
    records = queries.view_frame(
        queries.record_games(accounts=[10, 20], tz="America/Chicago"), parquet_dir=semantic_pq
    )
    grouped = queries.summarize(
        queries.my_games,
        by="hero",
        measures=["games"],
        parquet_dir=semantic_pq,
        accounts=[10, 20],
        tz="America/Chicago",
    )
    total = queries.summarize(
        queries.my_games,
        measures=["games"],
        parquet_dir=semantic_pq,
        accounts=[10, 20],
        tz="America/Chicago",
    )

    assert isinstance(records, pl.LazyFrame)
    assert isinstance(grouped, pl.LazyFrame)
    assert isinstance(total, pl.LazyFrame)


def test_unscored_games_count_as_games_but_never_as_wins(semantic_pq):
    df = summarize(semantic_pq, by=["scored"], measures=["games", "wins", "losses", "win_rate"])
    rows = {row["scored"]: row for row in df.iter_rows(named=True)}

    assert rows[False]["games"] == 1
    assert rows[False]["wins"] == 0
    assert rows[False]["win_rate"] is None
    assert rows[True]["games"] == 3
    assert rows[True]["wins"] == 2


def test_filters_take_a_value_a_collection_or_an_expression(semantic_pq):
    hero = summarize(semantic_pq, measures=["games"], filters={"hero": "Mirage"})
    accounts = summarize(semantic_pq, measures=["games"], filters={"account": [20]})
    expression = summarize(
        semantic_pq, measures=["games"], filters={"account": pl.col("kills") > 99}
    )

    assert hero.get_column("games").item() == 3
    assert accounts.get_column("games").item() == 1
    assert expression.get_column("games").item() == 0


def test_a_filter_expression_can_name_a_derived_dimension(semantic_pq):
    scored = summarize(semantic_pq, measures=["games"], filters={"scored": pl.col("scored")})
    since = summarize(
        semantic_pq, measures=["games"], filters={"day": pl.col("day") >= dt.date(2026, 7, 2)}
    )
    from_the_first = summarize(
        semantic_pq, measures=["games"], filters={"day": pl.col("day") >= dt.date(2026, 7, 1)}
    )

    assert scored.get_column("games").item() == 3
    assert since.get_column("games").item() == 0
    assert from_the_first.get_column("games").item() == 4


def test_a_collection_filter_resolves_every_member(semantic_pq):
    both = summarize(semantic_pq, measures=["games"], filters={"hero": ["Mirage", "Haze"]})
    one = summarize(semantic_pq, measures=["games"], filters={"hero": ["Haze"]})

    assert both.get_column("games").item() == 4
    assert one.get_column("games").item() == 1


def test_an_empty_collection_filter_matches_nothing(semantic_pq):
    heroes = summarize(semantic_pq, measures=["games"], filters={"hero": []})
    accounts = summarize(semantic_pq, measures=["games"], filters={"account": []})

    assert heroes.get_column("games").item() == 0
    assert accounts.get_column("games").item() == 0


def test_hero_filter_rejects_an_unknown_name(semantic_pq):
    with pytest.raises(ValueError, match="Unknown hero 'Mirge'"):
        summarize(semantic_pq, measures=["games"], filters={"hero": "Mirge"})

    with pytest.raises(ValueError, match="Unknown hero 'Mirge'"):
        summarize(semantic_pq, measures=["games"], filters={"hero": ["Mirage", "Mirge"]})


def test_lobby_badge_is_a_badge_level_and_the_subrank_is_not(semantic_pq):
    df = queries.summarize(
        queries.record_games,
        measures=["lobby_subrank", "lobby_badge"],
        parquet_dir=semantic_pq,
        accounts=[10, 20],
        tz="America/Chicago",
    ).collect()
    labelled = df.with_columns(queries.skill_rating("lobby_badge").alias("lobby"))

    assert df.get_column("lobby_subrank").item() == 45.0
    assert df.get_column("lobby_badge").item() == 73
    assert labelled.get_column("lobby").item() == "Archon 3"


def test_unknown_dimension_and_measure_list_the_valid_names(semantic_pq):
    with pytest.raises(ValueError, match="my_games has no dimension 'patch'; available: account"):
        summarize(semantic_pq, by=["patch"], measures=["games"])

    with pytest.raises(ValueError, match="my_games has no measure 'gpm'; available: assists"):
        summarize(semantic_pq, measures=["gpm"])


def test_summarize_needs_at_least_one_measure(semantic_pq):
    with pytest.raises(ValueError, match="needs at least one measure"):
        summarize(semantic_pq, by=["account"])


def test_measures_belong_to_one_dataset(semantic_pq):
    assert "net_worth" in queries.MY_GAMES_MEASURES
    assert "net_worth" not in queries.RECORD_GAMES_MEASURES

    with pytest.raises(ValueError, match="record_games has no measure 'net_worth'"):
        queries.summarize(
            queries.record_games,
            measures=["net_worth"],
            parquet_dir=semantic_pq,
            accounts=[10, 20],
            tz="America/Chicago",
        )


def test_record_games_counts_one_row_per_match(semantic_pq):
    df = queries.summarize(
        queries.record_games,
        measures=["games", "scored_games", "wins", "net", "rated_games"],
        parquet_dir=semantic_pq,
        accounts=[10, 20],
        tz="America/Chicago",
    ).collect()

    assert df.get_column("games").item() == 4
    assert df.get_column("scored_games").item() == 3
    assert df.get_column("wins").item() == 2
    assert df.get_column("net").item() == 1
    assert df.get_column("rated_games").item() == 3


def test_summarize_reuses_an_existing_frame(semantic_pq):
    games = queries.view_frame(
        queries.record_games(accounts=[10, 20], tz="America/Chicago"), parquet_dir=semantic_pq
    ).collect()
    df = queries.summarize(
        queries.record_games,
        by="day",
        measures=["games", "wins"],
        lf=games.lazy(),
    ).collect()

    assert df.get_column("games").sum() == 4
    assert df.get_column("wins").sum() == 2

    with pytest.raises(ValueError, match="cannot take lf with source arguments: hero"):
        queries.summarize(
            queries.record_games,
            measures=["games"],
            lf=games.lazy(),
            hero="Mirage",
        )


def test_a_supplied_row_set_has_to_be_lazy(semantic_pq):
    games = queries.view_frame(
        queries.record_games(accounts=[10, 20], tz="America/Chicago"), parquet_dir=semantic_pq
    ).collect()

    with pytest.raises(TypeError, match=r"lf takes a LazyFrame, not a DataFrame"):
        queries.summarize(queries.record_games, measures=["games"], lf=untyped(games)).collect()

    with pytest.raises(TypeError, match=r"scope 'you': lf takes a LazyFrame"):
        queries.Scope("you", lf=untyped(games))


def test_try_divide_is_null_when_the_denominator_is_zero():
    df = pl.DataFrame({"wins": [0], "games": [0]}).select(
        queries.try_divide(pl.col("wins").sum(), pl.col("games").sum()).alias("win_rate")
    )

    assert df.get_column("win_rate").item() is None


def test_a_view_resolves_by_factory_or_name():
    assert queries.semantic_spec(queries.my_games) is queries.semantic_spec("my_games")
    assert queries.semantic_spec(queries.record_games) is queries.semantic_spec("record_games")

    with pytest.raises(ValueError, match="not a metric view"):
        queries.semantic_spec(queries.daily_record)


def test_validate_grain_catches_duplicate_rows(semantic_pq):
    df = queries.view_frame(
        queries.my_games(accounts=[10, 20], tz="America/Chicago"), parquet_dir=semantic_pq
    ).collect()

    queries.validate_grain(queries.my_games, df)

    with pytest.raises(AssertionError, match="not unique on grain"):
        queries.validate_grain(queries.my_games, pl.concat([df, df.head(1)]))


def test_validate_grain_catches_missing_grain_columns():
    with pytest.raises(AssertionError, match=r"missing grain columns \['account_id'\]"):
        queries.validate_grain(
            queries.my_games,
            pl.DataFrame({"match_id": [1]}),
        )


def test_every_measure_declares_a_known_unit():
    for spec in queries.registered_views():
        for name, measure in spec.measures.items():
            assert measure.unit in queries.UNITS, f"{spec.name}.{name}"

    assert queries.MY_GAMES_MEASURES["win_rate"].unit == "proportion"
    assert queries.MY_GAMES_MEASURES["net_worth"].unit == "souls"
    assert queries.RECORD_GAMES_MEASURES["lobby_badge"].unit == "badge"

    with pytest.raises(ValueError, match="unknown unit 'percent'; available: badge"):
        queries.Measure(pl.len(), "percent")


def test_a_measure_without_a_format_gets_the_one_its_unit_implies():
    assert queries.MY_GAMES_MEASURES["win_rate"].format is None
    assert queries.MY_GAMES_MEASURES["win_rate"].display_format == queries.Format(
        decimals=1, scale=100, suffix="%"
    )
    assert queries.MY_GAMES_MEASURES["net_worth"].display_format == queries.Format(group=True)

    declared = queries.Measure(pl.len(), "proportion", format=queries.Format(decimals=3))

    assert declared.display_format == queries.Format(decimals=3)


def test_a_format_scales_and_prints_but_the_unit_never_does():
    percent = queries.Format(decimals=1, scale=100, suffix="%")
    souls = queries.Format(group=True)

    assert percent.render(0.6667) == "66.7%"
    assert percent.render(None) == ""
    assert percent.render(None, blank="-") == "-"
    assert souls.render(41250) == "41,250"
    assert queries.Format(decimals=2).render(1.5) == "1.50"


def test_a_gap_column_keeps_its_sign_and_a_value_column_does_not():
    souls = queries.Format(group=True)

    assert souls.render(1250, sign=True) == "+1,250"
    assert souls.render(-1250, sign=True) == "-1,250"
    assert souls.render(0, sign=True) == "+0"
    assert souls.render(1250) == "1,250"


def test_small_keeps_the_decimals_a_whole_number_column_would_round_away():
    flat = queries.Format(group=True, small=2)

    assert flat.render(9257) == "9,257"
    assert flat.render(8.333) == "8.33"
    assert flat.render(-7.01) == "-7.01"
    assert flat.render(8.0) == "8"
    assert flat.render(12.4) == "12"
    assert queries.Format(group=True).render(8.333) == "8"


def test_a_composed_measure_divides_two_named_measures(semantic_pq):
    df = summarize(semantic_pq, measures=["wins", "scored_games", "win_rate"])

    assert df.get_column("win_rate").item() == pytest.approx(
        df.get_column("wins").item() / df.get_column("scored_games").item()
    )
    assert callable(queries.MY_GAMES_MEASURES["win_rate"].expr)
    assert isinstance(queries.semantic_spec("my_games").measures["win_rate"].expr, pl.Expr)


def test_composition_is_transitive(semantic_pq):
    resolved = queries.semantic_spec("record_games").measures

    assert isinstance(resolved["lobby_badge"].expr, pl.Expr)

    df = queries.summarize(
        queries.record_games,
        measures=["subrank_sum", "rated_games", "lobby_subrank", "lobby_badge"],
        parquet_dir=semantic_pq,
        accounts=[10, 20],
        tz="America/Chicago",
    ).collect()

    assert df.get_column("lobby_subrank").item() == pytest.approx(
        df.get_column("subrank_sum").item() / df.get_column("rated_games").item()
    )
    assert df.get_column("lobby_badge").item() == 73


def test_a_composed_measure_cannot_read_an_unknown_or_circular_sibling():
    with pytest.raises(ValueError, match="reads unknown measure 'nope'"):
        queries.resolve_measures({"rate": queries.Measure(lambda m: m["nope"], "ratio")})

    with pytest.raises(ValueError, match="'a' composes itself: a -> b -> a"):
        queries.resolve_measures(
            {
                "a": queries.Measure(lambda m: m["b"], "ratio"),
                "b": queries.Measure(lambda m: m["a"], "ratio"),
            }
        )

    with pytest.raises(TypeError, match="composed to int, not an expression"):
        queries.resolve_measures({"a": queries.Measure(untyped(lambda m: 1), "ratio")})


def test_a_synonym_reaches_the_measure_and_lands_under_its_declared_name(semantic_pq):
    df = summarize(semantic_pq, measures=["winrate"])

    assert df.columns == ["win_rate"]
    assert df.get_column("win_rate").item() == pytest.approx(2 / 3)


def test_a_synonym_reaches_a_dimension_too(semantic_pq):
    measures = {"games": queries.Measure(pl.len(), "count")}
    dimensions = {"hero": queries.Dimension(pl.col("hero"), synonyms=("character",))}
    view = queries.MetricView(
        name="games",
        source="players",
        grain=("match_id",),
        dimensions=dimensions,
        measures=measures,
    )
    tables = _lookup_tables()
    lazy = queries.build_view_frame(view, {"hero"}, tables.__getitem__)

    assert view.dimension("character") is dimensions["hero"]
    assert "hero" in lazy.collect_schema().names()


def test_a_synonym_cannot_shadow_a_name_or_be_claimed_twice():
    with pytest.raises(ValueError, match="already a measure"):
        queries.check_synonyms(
            {
                "wins": queries.Measure(pl.len(), "count"),
                "losses": queries.Measure(pl.len(), "count", synonyms=("wins",)),
            },
            "games",
            "measure",
        )

    with pytest.raises(ValueError, match="both claim the synonym 'w'"):
        queries.check_synonyms(
            {
                "wins": queries.Measure(pl.len(), "count", synonyms=("w",)),
                "losses": queries.Measure(pl.len(), "count", synonyms=("w",)),
            },
            "games",
            "measure",
        )


def test_describe_names_the_display_name_and_the_synonyms():
    text = queries.describe_views("my_games")
    line = next(line for line in text.splitlines() if line.strip().startswith("win_rate"))

    assert "(also winrate)" in line


def test_a_view_needs_a_grain_and_a_measure():
    measures = {"games": queries.Measure(pl.len(), "count")}

    with pytest.raises(ValueError, match="non-empty grain"):
        queries.view(grain=(), dimensions={}, measures=measures)

    with pytest.raises(ValueError, match="at least one measure"):
        queries.view(grain=("match_id",), dimensions={}, measures={})


def test_describe_views_lists_every_view_with_its_grain():
    text = queries.describe_views()

    for spec in queries.registered_views():
        assert f"{spec.name}  one row per {', '.join(spec.grain)}" in text


def _described(name):
    """Split one describe_views block into its sections of listed names."""
    sections = {}

    for line in queries.describe_views(name).splitlines():
        if line.startswith("  ") and not line.startswith("    "):
            current = sections.setdefault(line.strip(), set())

        elif line.startswith("    "):
            current.add(line.split()[0])

    return sections


def test_describe_views_names_every_dimension_and_measure():
    for spec in queries.registered_views():
        sections = _described(spec.name)

        assert sections["group by"] == set(spec.dimensions), spec.name
        assert sections["measures"] == set(spec.measures), spec.name


def test_describe_views_lists_the_view_arguments():
    sections = _described("compare_intervals")

    assert sections["arguments"] == {"games", "stat", "interval_s"}

    text = queries.describe_views("compare_intervals")

    assert "    stat         required" in text
    assert "    interval_s   = 300" in text


def test_a_measure_whose_meaning_depends_on_an_argument_says_so():
    for name in ("compare_intervals", "damage_source_games"):
        spec = queries.semantic_spec(name)

        assert "stat" in spec.parameters

        for key, measure in spec.measures.items():
            assert measure.comment, f"{name}.{key} needs a comment, its name is not self-describing"


def test_describe_views_narrows_to_one_view():
    text = queries.describe_views("my_games")

    assert text.startswith("my_games  one row per match_id, account_id")
    assert "record_games" not in text
    assert "win_rate" in text
    assert "proportion" in text


def test_describe_views_marks_a_dimension_that_checks_its_value():
    text = queries.describe_views("my_games")
    hero = next(line for line in text.splitlines() if line.strip().startswith("hero"))

    assert "Takes a name and checks it." in hero


def test_describe_views_rejects_an_unknown_name():
    with pytest.raises(ValueError, match="not a metric view"):
        queries.describe_views("nope")


def _lookup_tables():
    """Three tiny tables for the view tests, matches is a clean m:1 lookup."""
    return {
        "players": pl.LazyFrame(
            {
                "match_id": [1, 2, 3],
                "account_id": [10, 10, 10],
                "hero": ["Mirage", "Mirage", "Bebop"],
                "kills": [3, 4, 5],
                "won": [True, False, True],
            }
        ),
        "matches": pl.LazyFrame(
            {"match_id": [1, 2, 3], "not_scored": [False, False, True], "duration_s": [60, 90, 30]}
        ),
        "accounts": pl.LazyFrame({"id": [10], "label": ["main"]}),
    }


def _lookup_view(joins=None, measures=None):
    """A view over players enriched by matches."""
    if joins is None:
        joins = (queries.Join("matches", using="match_id"),)

    if measures is None:
        measures = {
            "kills": queries.Measure(pl.col("kills").sum(), "count"),
            "scored": queries.Measure(
                (~pl.col("matches.not_scored")).sum(), "count", comment="Needs the matches join."
            ),
        }

    return queries.MetricView(
        name="games",
        source="players",
        grain=("match_id", "account_id"),
        joins=joins,
        dimensions={"hero": queries.Dimension(pl.col("hero"))},
        measures=measures,
    )


def test_a_join_is_skipped_when_nothing_names_its_alias():
    tables = _lookup_tables()
    view = _lookup_view()

    only_source = queries.build_view_frame(view, {"kills"}, tables.__getitem__)
    with_lookup = queries.build_view_frame(view, {"matches.not_scored"}, tables.__getitem__)

    assert "matches.not_scored" not in only_source.collect_schema().names()
    assert "matches.not_scored" in with_lookup.collect_schema().names()


def test_a_skipped_join_never_changes_the_row_set():
    tables = _lookup_tables()
    tables["matches"] = tables["matches"].filter(pl.col("match_id") < 3)
    view = _lookup_view()

    kept = queries.build_view_frame(view, {"kills"}, tables.__getitem__).collect()
    joined = queries.build_view_frame(view, {"matches.not_scored"}, tables.__getitem__).collect()

    assert kept.height == 3
    assert joined.height == 3


def test_a_lookup_that_fans_out_raises_instead_of_double_counting():
    tables = _lookup_tables()
    tables["matches"] = pl.LazyFrame(
        {"match_id": [1, 1, 2, 3], "not_scored": [False] * 4, "duration_s": [60, 61, 90, 30]}
    )
    view = _lookup_view()

    with pytest.raises(pl.exceptions.ComputeError, match="m:1"):
        queries.build_view_frame(view, {"matches.not_scored"}, tables.__getitem__).collect()


def test_one_to_one_is_validated_more_strictly_than_many_to_one():
    tables = _lookup_tables()
    view = _lookup_view(
        joins=(queries.Join("matches", using="match_id", cardinality="one_to_one"),)
    )

    assert view.joins[0].validate == "1:1"

    tables["players"] = pl.concat([tables["players"], tables["players"].head(1)])

    with pytest.raises(pl.exceptions.ComputeError, match="1:1"):
        queries.build_view_frame(view, {"matches.not_scored"}, tables.__getitem__).collect()


def test_a_join_key_missing_from_the_source_is_rejected():
    tables = _lookup_tables()
    view = _lookup_view(joins=(queries.Join("matches", using="missing_key"),))

    with pytest.raises(ValueError, match="does not have"):
        queries.build_view_frame(view, {"matches.not_scored"}, tables.__getitem__)


def test_a_join_needs_exactly_one_key_form_and_a_known_cardinality():
    with pytest.raises(ValueError, match="exactly one of using= or on="):
        queries.Join("matches")

    with pytest.raises(ValueError, match="exactly one of using= or on="):
        queries.Join(
            "matches", using="match_id", on=pl.col("match_id") == pl.col("matches.match_id")
        )

    with pytest.raises(ValueError, match="unknown cardinality 'one_to_many'"):
        queries.Join("matches", using="match_id", cardinality="one_to_many")


def test_two_joins_cannot_share_one_alias():
    with pytest.raises(ValueError, match="share the alias"):
        _lookup_view(
            joins=(
                queries.Join("matches", using="match_id"),
                queries.Join("accounts", name="matches", using="match_id"),
            )
        )


def _alias_view():
    """A view whose lookup is keyed by an expression and reached through an alias."""
    return queries.MetricView(
        name="games",
        source="players",
        grain=("match_id", "account_id"),
        joins=(
            queries.Join(
                "accounts",
                name="owner",
                on=pl.col("account_id") == pl.col("owner.id"),
            ),
        ),
        dimensions={"owner": queries.Dimension(pl.col("owner.label"))},
        measures={"kills": queries.Measure(pl.col("kills").sum(), "count")},
    )


def test_an_expression_join_keys_off_differently_named_columns():
    tables = _lookup_tables()
    df = queries.build_view_frame(_alias_view(), {"owner.label"}, tables.__getitem__).collect()

    assert df.get_column("owner.label").to_list() == ["main"] * 3
    assert "owner.id" not in df.columns


def test_an_expression_join_is_skipped_by_its_alias_too():
    tables = _lookup_tables()
    lazy = queries.build_view_frame(_alias_view(), {"kills"}, tables.__getitem__)

    assert "owner.label" not in lazy.collect_schema().names()


def test_an_expression_join_key_must_come_from_the_source():
    tables = _lookup_tables()
    view = queries.MetricView(
        name="games",
        source="players",
        grain=("match_id",),
        joins=(queries.Join("accounts", name="owner", on=pl.col("nope") == pl.col("owner.id")),),
        dimensions={},
        measures={"kills": queries.Measure(pl.col("kills").sum(), "count")},
    )

    with pytest.raises(ValueError, match="keys off"):
        queries.build_view_frame(view, {"owner.label"}, tables.__getitem__)


def test_an_expression_join_needs_one_side_per_frame():
    tables = _lookup_tables()
    view = queries.MetricView(
        name="games",
        source="players",
        grain=("match_id",),
        joins=(
            queries.Join("accounts", name="owner", on=pl.col("account_id") == pl.col("match_id")),
        ),
        dimensions={},
        measures={"kills": queries.Measure(pl.col("kills").sum(), "count")},
    )

    with pytest.raises(ValueError, match="equality between a source column"):
        queries.build_view_frame(view, {"owner.label"}, tables.__getitem__)


def test_a_declared_expression_is_checked_against_the_real_schema():
    tables = _lookup_tables()
    view = _lookup_view(
        measures={"typo": queries.Measure(pl.col("killz").sum(), "count")},
    )

    with pytest.raises(ValueError, match=r"measure 'typo' reads \['killz'\]"):
        queries.build_view_frame(view, {"kills"}, tables.__getitem__)


def test_an_unqueried_measure_is_checked_too():
    tables = _lookup_tables()
    view = _lookup_view(
        measures={
            "kills": queries.Measure(pl.col("kills").sum(), "count"),
            "typo": queries.Measure(pl.col("matches.nope").sum(), "count"),
        },
    )

    with pytest.raises(ValueError, match=r"measure 'typo' reads \['matches.nope'\]"):
        queries.build_view_frame(view, {"kills"}, tables.__getitem__)


def test_a_callable_source_must_stay_lazy():
    tables = _lookup_tables()
    lazy = queries.MetricView(
        name="games",
        source=lambda: tables["players"],
        grain=("match_id",),
        dimensions={"hero": queries.Dimension(pl.col("hero"))},
        measures={"kills": queries.Measure(pl.col("kills").sum(), "count")},
    )
    eager = queries.MetricView(
        name="games",
        source=lambda: tables["players"].collect(),
        grain=("match_id",),
        dimensions={"hero": queries.Dimension(pl.col("hero"))},
        measures={"kills": queries.Measure(pl.col("kills").sum(), "count")},
    )

    assert queries.build_view_frame(lazy, {"kills"}, tables.__getitem__).collect().height == 3

    with pytest.raises(TypeError, match="not a LazyFrame"):
        queries.build_view_frame(eager, {"kills"}, tables.__getitem__)


def test_a_view_can_sit_on_another_view_and_group_its_dimensions():
    tables = _lookup_tables()
    parent = queries.MetricView(
        name="games",
        source="players",
        grain=("match_id", "account_id"),
        joins=(queries.Join("matches", using="match_id"),),
        dimensions={
            "hero": queries.Dimension(pl.col("hero")),
            "scored": queries.Dimension(~pl.col("matches.not_scored")),
        },
        measures={"kills": queries.Measure(pl.col("kills").sum(), "count")},
    )
    child = queries.MetricView(
        name="scored_games",
        source=parent,
        grain=("match_id", "account_id"),
        dimensions={"hero": queries.Dimension(pl.col("hero"))},
        measures={"scored_games": queries.Measure(pl.col("scored").sum(), "count")},
    )
    df = queries.build_view_frame(child, {"scored", "hero"}, tables.__getitem__).collect()

    assert df.get_column("scored").to_list() == [True, True, False]


def test_a_parent_view_filter_still_applies_to_the_child():
    tables = _lookup_tables()
    parent = queries.MetricView(
        name="games",
        source="players",
        grain=("match_id", "account_id"),
        dimensions={"hero": queries.Dimension(pl.col("hero"))},
        measures={"kills": queries.Measure(pl.col("kills").sum(), "count")},
        filter=pl.col("hero") == "Mirage",
    )
    child = queries.MetricView(
        name="mirage_games",
        source=parent,
        grain=("match_id", "account_id"),
        dimensions={"hero": queries.Dimension(pl.col("hero"))},
        measures={"kills": queries.Measure(pl.col("kills").sum(), "count")},
    )

    assert queries.build_view_frame(child, {"kills"}, tables.__getitem__).collect().height == 2


def test_view_parameters_come_from_the_signature_without_parquet_dir():
    def hero_games(hero: str, parquet_dir=None, minimum_kills: int = 0) -> queries.MetricView:
        """A factory that is only read, never called."""
        raise AssertionError

    parameters = queries.view_parameters(hero_games)

    assert list(parameters) == ["hero", "minimum_kills"]
    assert parameters["hero"].default is inspect.Parameter.empty
    assert parameters["hero"].annotation is str
    assert parameters["minimum_kills"].default == 0


def test_a_required_parameter_cannot_follow_a_defaulted_one():
    def broken(*, hero: str = "Mirage", stat: str) -> queries.MetricView:
        """A factory whose keyword-only parameters break the ordering rule."""
        raise AssertionError

    def variadic(**kwargs) -> queries.MetricView:
        """A factory polars parameters cannot be read from."""
        raise AssertionError

    with pytest.raises(ValueError, match="required parameter 'stat' after 'hero'"):
        queries.view_parameters(broken)

    with pytest.raises(ValueError, match="parameters must be named"):
        queries.view_parameters(variadic)


@pytest.fixture
def hero_games():
    """Register a parameterized view for one test and drop it again afterwards."""
    from deadlock_matches.queries import semantic

    @queries.view(
        grain=("match_id", "account_id"),
        dimensions={
            "hero": queries.Dimension(pl.col("hero")),
            "account": queries.Dimension(pl.col("account_id")),
        },
        measures={
            "games": queries.Measure(pl.len(), "count"),
            "kills": queries.Measure(pl.col("kills").sum(), "count"),
            "scored_games": queries.Measure(
                (~pl.col("matches.not_scored")).sum(), "count", comment="Needs the matches join."
            ),
        },
    )
    def hero_games(hero: str, minimum_kills: int = 0) -> queries.MetricView:
        """One row per game of one hero."""
        return queries.MetricView(
            source=lambda: queries.player_rows(),
            joins=(queries.Join("matches", using="match_id"),),
            filter=(pl.col("hero") == hero) & (pl.col("kills") >= minimum_kills),
        )

    yield hero_games

    semantic._VIEWS.pop("hero_games")


def test_registered_views_never_call_a_factory_with_a_required_parameter(hero_games):
    specs = {spec.name: spec for spec in queries.registered_views()}

    assert specs["hero_games"].grain == ("match_id", "account_id")
    assert list(specs["hero_games"].parameters) == ["hero", "minimum_kills"]
    assert queries.view_spec("hero_games") is queries.view_spec(hero_games)


def test_summarize_forwards_its_arguments_to_the_view_factory(hero_games, semantic_pq):
    df = queries.summarize(
        hero_games,
        by=["account"],
        measures=["games", "kills", "scored_games"],
        parquet_dir=semantic_pq,
        hero="Mirage",
    ).collect()

    assert df.get_column("account").to_list() == [10, 20]
    assert df.get_column("games").to_list() == [2, 1]
    assert df.get_column("scored_games").to_list() == [2, 1]


def test_a_view_parameter_reaches_the_filter(hero_games, semantic_pq):
    kept = queries.summarize(
        hero_games,
        measures=["games"],
        parquet_dir=semantic_pq,
        hero="Mirage",
        minimum_kills=7,
    ).collect()

    assert kept.get_column("games").item() == 0


def test_a_view_rejects_an_unknown_parameter(hero_games, semantic_pq):
    with pytest.raises(ValueError, match="has no parameter stat; available: hero, minimum_kills"):
        queries.summarize(
            hero_games,
            measures=["games"],
            parquet_dir=semantic_pq,
            hero="Mirage",
            stat="damage",
        )


def test_describe_and_grain_checking_cover_views_too(hero_games, semantic_pq):
    text = queries.describe_views("hero_games")

    assert text.startswith("hero_games  one row per match_id, account_id")
    assert "    hero           required" in text
    assert "    minimum_kills  = 0" in text
    assert "parquet_dir" not in text
    assert "scored_games" in text
    assert "hero_games" in queries.describe_views()

    frame = pl.DataFrame({"match_id": [1, 2], "account_id": [10, 10]})

    queries.validate_grain("hero_games", frame)

    with pytest.raises(AssertionError, match="not unique on grain"):
        queries.validate_grain(hero_games, pl.concat([frame, frame.head(1)]))


def test_the_ambient_parquet_dir_only_lasts_for_the_block(semantic_pq):
    with queries.parquet_dir_context(semantic_pq):
        inside = queries.scan("players").collect()

    assert inside.height == 4
    assert queries.scan("players", semantic_pq).collect().height == 4


def test_summarize_rejects_arguments_on_a_built_view_but_takes_a_frame():
    view = _lookup_view()
    df = queries.summarize(view, measures=["kills"], lf=pl.LazyFrame({"kills": [1, 2]})).collect()

    assert df.get_column("kills").item() == 3

    with pytest.raises(ValueError, match="takes no arguments"):
        queries.summarize(view, measures=["kills"], hero="Mirage")


def test_a_view_cannot_take_a_frame_and_the_arguments_that_would_build_one(hero_games, semantic_pq):
    rows = queries.view_frame(
        queries.my_games(accounts=[10, 20], tz="America/Chicago"), parquet_dir=semantic_pq
    )
    reused = queries.summarize(queries.my_games, measures=["games"], lf=rows).collect()

    assert reused.get_column("games").item() == 4

    with pytest.raises(ValueError, match="cannot take lf with source arguments: hero"):
        queries.summarize(hero_games, measures=["games"], lf=rows, hero="Mirage")


def test_resolve_view_never_calls_an_unmarked_function():
    called = []

    def not_a_view():
        called.append(True)
        return "definitely not a view"

    assert queries.resolve_view(not_a_view) is None
    assert not called
    assert queries.resolve_view(queries.daily_record) is None
    resolved = queries.resolve_view(queries.my_games)

    assert resolved is not None
    assert resolved.name == "my_games"


def _snapshot_rows():
    return pl.LazyFrame(
        {
            "match_id": [1, 1, 1, 2, 2],
            "account_id": [10, 10, 10, 10, 10],
            "time_stamp_s": [180, 600, 300, 180, 600],
            "net_worth": [1000, 900, 2000, 500, 4000],
        }
    )


SERIES = queries.Window(
    order="time_stamp_s", partition=("match_id", "account_id"), semiadditive="last"
)


def test_a_semiadditive_measure_reads_the_last_sample_not_the_biggest():
    collapsed = queries.MetricView(
        source=_snapshot_rows,
        name="snaps",
        grain=("match_id", "account_id", "time_stamp_s"),
        dimensions={"match_id": queries.Dimension(pl.col("match_id"))},
        measures={
            "net_worth": queries.Measure(pl.col("net_worth").sum(), "souls", window=SERIES),
            "games": queries.Measure(pl.len(), "count", window=SERIES),
        },
    )
    total = queries.summarize(collapsed, measures=["net_worth", "games"]).collect()
    per_match = queries.summarize(collapsed, by="match_id", measures=["net_worth"]).collect()

    assert total.get_column("games").item() == 2
    assert total.get_column("net_worth").item() == 4900
    assert per_match.get_column("net_worth").to_list() == [900, 4000]


def test_a_semiadditive_measure_can_read_the_first_sample():
    first = queries.Window(
        order="time_stamp_s",
        partition=("match_id", "account_id"),
        semiadditive="first",
    )
    view = queries.MetricView(
        source=_snapshot_rows,
        name="snaps",
        dimensions={},
        measures={
            "net_worth": queries.Measure(pl.col("net_worth").sum(), "souls", window=first),
        },
    )

    assert queries.summarize(view, measures=["net_worth"]).collect().item() == 1500


def test_filters_run_on_the_surviving_semiadditive_sample():
    view = queries.MetricView(
        source=_snapshot_rows,
        name="snaps",
        dimensions={"worth": queries.Dimension(pl.col("net_worth"))},
        measures={
            "games": queries.Measure(pl.len(), "count", window=SERIES),
        },
    )
    df = queries.summarize(view, measures=["games"], filters={"worth": 2000}).collect()

    assert df.item() == 0


def test_a_window_declared_on_one_measure_has_to_cover_them_all():
    with pytest.raises(ValueError, match=r"measures \['games'\] have no window"):
        queries.MetricView(
            source=_snapshot_rows,
            name="snaps",
            dimensions={},
            measures={
                "net_worth": queries.Measure(pl.col("net_worth").sum(), "souls", window=SERIES),
                "games": queries.Measure(pl.len(), "count"),
            },
        )


def test_a_semiadditive_view_rejects_every_different_window_shape():
    first = queries.Window(
        order="time_stamp_s",
        partition=("match_id", "account_id"),
        semiadditive="first",
    )
    cumulative = queries.Window(order="time_stamp_s", range="cumulative")

    with pytest.raises(ValueError, match="different semiadditive windows"):
        queries.MetricView(
            source=_snapshot_rows,
            name="snaps",
            dimensions={},
            measures={
                "last": queries.Measure(pl.col("net_worth").sum(), "souls", window=SERIES),
                "first": queries.Measure(pl.col("net_worth").sum(), "souls", window=first),
            },
        )

    with pytest.raises(ValueError, match="declare a different window"):
        queries.MetricView(
            source=_snapshot_rows,
            name="snaps",
            dimensions={},
            measures={
                "last": queries.Measure(pl.col("net_worth").sum(), "souls", window=SERIES),
                "running": queries.Measure(
                    pl.col("net_worth").sum(),
                    "souls",
                    window=cumulative,
                ),
            },
        )


def test_a_window_needs_something_to_do_and_a_series_to_collapse():
    with pytest.raises(ValueError, match="does nothing"):
        queries.Window(order="t")

    with pytest.raises(ValueError, match="needs the partition"):
        queries.Window(order="t", semiadditive="last")

    with pytest.raises(ValueError, match="unknown semiadditive 'largest'"):
        queries.Window(order="t", partition=("id",), semiadditive="largest")

    with pytest.raises(ValueError, match="unknown range 'trailing'"):
        queries.Window(order="t", range="trailing")

    with pytest.raises(ValueError, match="has to be the one column"):
        queries.Window(order=("t", "u"), partition=("id",), semiadditive="last")


def test_a_semiadditive_window_is_checked_against_the_source_columns():
    view = queries.MetricView(
        source=_snapshot_rows,
        name="snaps",
        dimensions={},
        measures={
            "net_worth": queries.Measure(
                pl.col("net_worth").sum(),
                "souls",
                window=queries.Window(
                    order="sample_time_s", partition=("match_id",), semiadditive="last"
                ),
            )
        },
    )

    with pytest.raises(ValueError, match=r"orders and partitions by \['sample_time_s'\]"):
        queries.summarize(view, measures=["net_worth"]).collect()


def test_a_cumulative_measure_accumulates_down_the_grouped_bucket(semantic_pq):
    for bucket in ("day", "week", "month"):
        df = queries.summarize(
            queries.record_games,
            by=bucket,
            measures=["net", "cum_net"],
            parquet_dir=semantic_pq,
            accounts=[10, 20],
            tz="America/Chicago",
        ).collect()

        assert df.get_column("cum_net").to_list() == df.get_column("net").cum_sum().to_list()


def test_a_cumulative_measure_needs_its_ordered_dimension_grouped(semantic_pq):
    with pytest.raises(ValueError, match="accumulates by day or week or month"):
        queries.summarize(
            queries.record_games,
            by="won",
            measures=["cum_net"],
            parquet_dir=semantic_pq,
            accounts=[10, 20],
            tz="America/Chicago",
        ).collect()


@pytest.fixture
def tracked_pq(tmp_path_factory):
    directory = tmp_path_factory.mktemp("tracked")
    _write(directory)

    return directory


def scope(name, pq, **arguments):
    return queries.Scope(name, parquet_dir=pq, arguments={"tz": "America/Chicago", **arguments})


def test_compare_reads_a_different_export_on_each_side(semantic_pq, tracked_pq):
    pl.read_parquet(schemas.table_path("players", tracked_pq)).filter(
        pl.col("account_id") == 20
    ).write_parquet(schemas.table_path("players", tracked_pq))

    df = queries.compare(
        queries.my_games,
        [scope("you", semantic_pq, accounts=[10]), scope("them", tracked_pq, accounts=[20])],
        measures=["games", "wins"],
    ).collect()

    assert df.get_column("you_games").item() == 3
    assert df.get_column("them_games").item() == 1
    assert df.get_column("gap_games").item() == 2
    assert df.get_column("gap_wins").item() == 0


def test_the_gap_always_reads_the_first_scope_minus_the_second(semantic_pq):
    sides = [scope("you", semantic_pq, accounts=[20]), scope("them", semantic_pq, accounts=[10])]
    df = queries.compare(queries.my_games, sides, measures=["games"]).collect()

    assert df.get_column("gap_games").item() == -2


def test_compare_keeps_every_group_key_either_side_has(semantic_pq):
    df = queries.compare(
        queries.my_games,
        [
            scope("you", semantic_pq, accounts=[10]),
            scope("them", semantic_pq, accounts=[20]),
        ],
        by="hero",
        measures=["games", "win_rate"],
    ).collect()

    assert df.get_column("hero").to_list() == ["Haze", "Mirage"]
    assert df.get_column("you_games").to_list() == [1, 2]
    assert df.get_column("them_games").to_list() == [None, 1]
    assert df.get_column("gap_games").to_list() == [1, 1]
    assert df.get_column("you_win_rate").to_list() == [None, 0.5]
    assert df.get_column("them_win_rate").to_list() == [None, 1.0]
    assert df.get_column("gap_win_rate").to_list() == [None, -0.5]


def test_compare_does_not_invent_a_median_for_a_missing_group():
    you = pl.LazyFrame({"match_id": [1], "account_id": [10], "mark_s": [300], "value": [1000.0]})
    them = pl.LazyFrame({"match_id": [2], "account_id": [20], "mark_s": [600], "value": [2000.0]})
    df = queries.compare(
        queries.cumulative_marks,
        [queries.Scope("you", lf=you), queries.Scope("them", lf=them)],
        by="mark_s",
        measures=["games", "median"],
    ).collect()

    assert df.get_column("mark_s").to_list() == [300, 600]
    assert df.get_column("gap_games").to_list() == [1, -1]
    assert df.get_column("gap_median").to_list() == [None, None]


def test_a_scope_can_narrow_its_own_side_with_a_filter(semantic_pq):
    sides = [
        queries.Scope(
            "you",
            parquet_dir=semantic_pq,
            arguments={"accounts": [10, 20]},
            filters={"won": True},
        ),
        queries.Scope(
            "them",
            parquet_dir=semantic_pq,
            arguments={"accounts": [10, 20]},
            filters={"won": False},
        ),
    ]
    df = queries.compare(
        queries.my_games,
        sides,
        measures=["games"],
        filters={"hero": "Mirage"},
    ).collect()

    assert df.get_column("you_games").item() == 2
    assert df.get_column("them_games").item() == 1


def test_scope_filters_intersect_with_shared_compare_filters(semantic_pq):
    sides = [
        queries.Scope(
            "you",
            parquet_dir=semantic_pq,
            arguments={"accounts": [10, 20], "tz": "America/Chicago"},
            filters={"hero": "Haze"},
        ),
        queries.Scope(
            "them",
            parquet_dir=semantic_pq,
            arguments={"accounts": [10, 20], "tz": "America/Chicago"},
            filters={"hero": "Mirage"},
        ),
    ]
    df = queries.compare(
        queries.my_games,
        sides,
        measures=["games"],
        filters={"hero": "Mirage"},
    ).collect()

    assert df.get_column("you_games").item() == 0
    assert df.get_column("them_games").item() == 3


def test_a_scope_can_supply_its_own_frame(semantic_pq):
    built = queries.view_frame(queries.my_games(accounts=[10, 20]), parquet_dir=semantic_pq)
    sides = [
        queries.Scope("you", lf=built.filter(pl.col("account_id") == 10)),
        queries.Scope("them", lf=built.filter(pl.col("account_id") == 20)),
    ]
    df = queries.compare(queries.my_games, sides, measures=["games"]).collect()

    assert df.get_column("gap_games").item() == 2


def test_a_supplied_frame_can_still_be_filtered(semantic_pq):
    built = queries.view_frame(
        queries.my_games(accounts=[10, 20], tz="America/Chicago"),
        parquet_dir=semantic_pq,
    )
    df = queries.summarize(
        queries.my_games,
        measures=["games"],
        filters={"hero": "Haze"},
        lf=built,
    ).collect()

    assert df.item() == 1


def test_a_scope_with_a_frame_cannot_also_bind_arguments():
    with pytest.raises(ValueError, match="supplies lf"):
        queries.Scope("you", lf=pl.LazyFrame(), arguments={"accounts": [10]})


def test_a_scope_with_a_frame_cannot_silently_ignore_parquet_dir(tmp_path):
    with pytest.raises(ValueError, match="parquet_dir would be ignored"):
        queries.Scope("you", lf=pl.LazyFrame(), parquet_dir=tmp_path)


def test_compare_takes_exactly_two_differently_named_scopes(semantic_pq):
    one = scope("you", semantic_pq, accounts=[10])

    with pytest.raises(ValueError, match="exactly two scopes"):
        queries.compare(queries.my_games, [one], measures=["games"])

    with pytest.raises(ValueError, match="both scopes are named 'you'"):
        queries.compare(queries.my_games, [one, one], measures=["games"])

    with pytest.raises(ValueError, match="'gap' names the delta columns"):
        queries.compare(queries.my_games, [one, scope("gap", semantic_pq)], measures=["games"])

    with pytest.raises(ValueError, match="needs at least one measure"):
        queries.compare(queries.my_games, [one, scope("them", semantic_pq)])


def test_a_scope_needs_a_name():
    with pytest.raises(ValueError, match="needs a name"):
        queries.Scope("")


def test_a_view_name_cannot_be_registered_twice():
    def my_games():
        return queries.MetricView(source="players")

    with pytest.raises(ValueError, match="already registered"):
        queries.view(
            grain=("match_id",),
            dimensions={},
            measures={"games": queries.Measure(pl.len(), "count")},
        )(my_games)


def test_compare_lands_a_synonym_under_the_declared_name(semantic_pq):
    df = queries.compare(
        queries.my_games,
        [scope("you", semantic_pq, accounts=[10]), scope("them", semantic_pq, accounts=[20])],
        measures=["winrate"],
    ).collect()

    assert "you_win_rate" in df.columns
    assert "gap_win_rate" in df.columns


def test_a_measure_says_which_way_is_good():
    measures = queries.semantic_spec(queries.my_games).measures

    assert measures["deaths"].direction == "minimize"
    assert measures["wins"].direction == "maximize"
    assert measures["last_hits"].direction == "maximize"
    assert measures["games"].direction == ""


def test_a_measure_says_what_an_absent_group_contributes():
    assert queries.MY_GAMES_MEASURES["games"].missing == "zero"
    assert queries.MY_GAMES_MEASURES["net_worth"].missing == "zero"
    assert queries.MY_GAMES_MEASURES["win_rate"].missing == "null"
    assert queries.CUMULATIVE_MARK_MEASURES["median"].missing == "null"
    assert queries.MILESTONE_MEASURES["minutes"].missing == "null"


def test_a_direction_outside_the_vocabulary_is_rejected():
    with pytest.raises(ValueError, match="unknown direction 'higher'"):
        queries.Measure(pl.len(), "count", direction="higher")


def test_a_missing_policy_outside_the_vocabulary_is_rejected():
    with pytest.raises(ValueError, match="unknown missing policy 'average'"):
        queries.Measure(pl.len(), "count", missing="average")  # ty: ignore[invalid-argument-type]


def test_describe_names_the_direction():
    lines = {
        line.split()[0]: line
        for line in queries.describe_views("my_games").splitlines()
        if line.startswith("    ")
    }

    assert "[minimize]" in lines["deaths"]
    assert "[maximize]" in lines["wins"]
    assert "[zero if missing]" in lines["wins"]
    assert "[zero if missing]" not in lines["win_rate"]
    assert "[minimize]" not in lines["games"]
    assert "[maximize]" not in lines["games"]
