"""Compare a stat between your games and the tracked players, interval by interval."""

from __future__ import annotations

import datetime as dt
import itertools
import statistics as st
import unicodedata
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl

from deadlock_matches import players, queries
from deadlock_matches.assets import heroes
from deadlock_matches.cli import render
from deadlock_matches.cli.data import no_pool_hint
from deadlock_matches.cli.games import (
    MILESTONE_MIN_GAMES,
    MILESTONE_MINUTES,
    MOVEMENT_MEASURES,
    MOVEMENT_METRICS,
    column_mean,
    hero_games,
    milestone_rows,
    milestone_targets,
)
from deadlock_matches.cli.match import DELIVERY_LABELS
from deadlock_matches.cli.winrate import no_games_line
from deadlock_matches.config import config_timezone, format_accounts
from deadlock_matches.queries.movement import UNITS_PER_METER, meters_min

if TYPE_CHECKING:
    import argparse


SOURCE_ROWS = (
    "troopers",
    "jungle",
    "breakables",
    "rift_urn",
    "deny_souls",
    "combat",
    "objectives",
    "catch_up",
    "other",
    "souls",
)

LOWER_IS_BETTER = ("deaths", "damage_taken")

COUNT_STATS = ("kills", "deaths")


def _pool_scopes(
    mine: pl.DataFrame,
    pool: pl.DataFrame,
    args: argparse.Namespace,
    arguments: dict[str, Any] | None = None,
) -> list[queries.Scope]:
    """Build the two sides of one comparison over the personal and tracked exports.

    - the sides read different exports, so a scope carries the directory
      alongside the view arguments instead of only a predicate
    - arguments go to both sides, so only the accounts and matches differ
    """
    shared = dict(arguments or {})

    return [
        queries.Scope(
            "you",
            parquet_dir=args.parquet,
            arguments={
                **shared,
                "accounts": list(args.account),
                "matches": mine.get_column("match_id").to_list(),
            },
        ),
        queries.Scope(
            "them",
            parquet_dir=players.PLAYERS_PARQUET_DIR,
            arguments={
                **shared,
                "accounts": pool.get_column("account_id").unique().to_list(),
                "matches": pool.get_column("match_id").to_list(),
            },
        ),
    ]


MARK_MINUTES = (6, 10, 15, 20, 25)

STANDING_MARK_S = 20 * 60


def sources_report(
    mine: pl.LazyFrame,
    pool: pl.LazyFrame,
    my_dir: str | Path | None,
    pool_dir: str | Path | None,
) -> None:
    """Compare income from each soul source between your games and the pool."""
    marks_s = [m * 60 for m in MARK_MINUTES]
    frames = pl.collect_all(
        [
            queries.compare(
                queries.cumulative_marks,
                [
                    queries.Scope(
                        "you",
                        parquet_dir=my_dir,
                        arguments={"games": mine, "stat": stat, "marks_s": marks_s},
                    ),
                    queries.Scope(
                        "them",
                        parquet_dir=pool_dir,
                        arguments={"games": pool, "stat": stat, "marks_s": marks_s},
                    ),
                ],
                by="mark_s",
                measures=("median",),
            )
            for stat in SOURCE_ROWS
        ]
    )
    fmt = queries.view_measure(queries.cumulative_marks, "median").display_format
    header = "".join(f"{f'{m}m gap':>10}" for m in MARK_MINUTES)
    print(f"\n  {'source':<12}{header}  {'you@20m':>9}  {'them@20m':>9}")

    for stat, frame in zip(SOURCE_ROWS, frames, strict=True):
        rows = {r["mark_s"]: r for r in frame.iter_rows(named=True)}
        gaps = "".join(
            fmt.render(rows.get(m, {}).get("gap_median"), render.BLANK, sign=True).rjust(10)
            for m in marks_s
        )
        standing = rows.get(STANDING_MARK_S, {})

        print(
            f"  {stat:<12}{gaps}"
            f"  {fmt.render(standing.get('you_median'), render.BLANK):>9}"
            f"  {fmt.render(standing.get('them_median'), render.BLANK):>9}"
        )

    print(
        "\n  souls is net worth. It runs a little over the other rows summed, the game"
        "\n  credits some income (sell refunds and similar) to no source"
    )


SHARE = queries.Format(scale=100, suffix="%")

DELIVERY_WIDTH = max(len(label) for label in DELIVERY_LABELS.values()) + 2

_WINDOW_FIELDS = [
    *render.spread("per_window_game", ("You/game", "Them/game", "Gap/game"), (10, 11, 10)),
    *render.spread("per_window_min", ("You/min", "Them/min", "Gap/min"), (9, 10, 10)),
]

DELIVERY_COLUMNS = [
    render.Key("delivery", "Delivery", 23, DELIVERY_LABELS),
    *_WINDOW_FIELDS,
    *render.spread("share", ("You %", "Them %"), (8, 8), SHARE, ("you", "them")),
]

SOURCE_FIELDS = [
    *render.spread("per_game", ("You/game", "Them/game", "Gap/game"), (10, 11, 10)),
    *render.spread("per_min", ("You/min", "Them/min", "Gap/min"), (9, 10, 10)),
    *render.spread("per_1k", ("You/1k", "Them/1k"), (9, 9), sides=("you", "them")),
]

STAT_LABELS = {
    "damage": "Damage to heroes",
    "healing": "Healing",
    "heal_prevented": "Healing prevented",
}


def _compare_damage_sources(
    mine: pl.DataFrame,
    pool: pl.DataFrame,
    args: argparse.Namespace,
    hero: str,
    stat: str,
) -> None:
    """Print damage or healing by source before the interval table.

    - the delivery table divides by every game of the hero, the source table
      by the games each source appeared in, which is what per_window_game
      and per_game say apart
    """
    scopes = _pool_scopes(mine, pool, args, {"hero": hero, "stat": stat})
    delivery, sources, total = pl.collect_all(
        [
            queries.compare(
                queries.damage_source_games,
                scopes,
                by="delivery",
                measures=("total", "per_window_game", "per_window_min", "share"),
            ),
            queries.compare(
                queries.damage_source_games,
                scopes,
                by=("source_name", "delivery"),
                measures=("games", "per_game", "per_min", "per_1k"),
            ),
            queries.compare(
                queries.damage_source_games,
                scopes,
                measures=("per_window_game", "per_window_min"),
            ),
        ]
    )

    if total.is_empty() or total.item(0, "you_per_window_game") is None:
        msg = f"no {stat} rows for {hero} on accounts {args.account}"
        raise ValueError(msg)

    print(f"\n{STAT_LABELS[stat]} by source\n")
    delivery_rows = delivery.sort("them_total", descending=True, nulls_last=True).to_dicts()

    for line in render.table(queries.damage_source_games, delivery_rows, DELIVERY_COLUMNS):
        print(line)

    print(
        render.total_line(
            queries.damage_source_games,
            total.row(0, named=True),
            DELIVERY_COLUMNS[: 1 + len(_WINDOW_FIELDS)],
            delivery_rows,
        )
    )
    _source_compare_table(sources, total, len(mine), len(pool))


def _source_compare_table(
    sources: pl.DataFrame, total: pl.DataFrame, you_games: int, them_games: int
) -> None:
    """Print one line per damage source ordered by whichever side leans on it hardest."""
    pair = pl.format(
        "{}/{}", pl.col("you_games").fill_null(0), pl.col("them_games").fill_null(0)
    ).alias("games_pair")
    rows = (
        sources.with_columns(
            pair,
            pl.max_horizontal(
                pl.col("you_per_min").fill_null(0), pl.col("them_per_min").fill_null(0)
            ).alias("sort_min"),
        )
        .sort("sort_min", descending=True)
        .to_dicts()
    )
    width = max(max((len(r["source_name"]) for r in rows), default=0), 14) + 2
    columns = [
        render.Key("source_name", "Source", width),
        render.Key("delivery", "Delivery", DELIVERY_WIDTH, DELIVERY_LABELS),
        *SOURCE_FIELDS,
        render.Key("games_pair", "Games", 9, right=True),
    ]

    print()

    for line in render.table(queries.damage_source_games, rows, columns):
        print(line)

    summary = {
        **total.row(0, named=True),
        "you_per_game": total.item(0, "you_per_window_game"),
        "them_per_game": total.item(0, "them_per_window_game"),
        "gap_per_game": total.item(0, "gap_per_window_game"),
        "you_per_min": total.item(0, "you_per_window_min"),
        "them_per_min": total.item(0, "them_per_window_min"),
        "gap_per_min": total.item(0, "gap_per_window_min"),
        "games_pair": f"{you_games}/{them_games}",
    }
    print(render.total_line(queries.damage_source_games, summary, columns, rows))


def _tracked_players(n: int, hero: str) -> str:
    """Format the tracked player count."""
    noun = "player" if n == 1 else "players"
    return f"{n} tracked {hero} {noun}"


def _pool_since_filter(pool: pl.LazyFrame, since: dt.date, tz: str) -> pl.LazyFrame:
    """Filter tracked games by local match date."""
    return (
        pool.join(
            queries.scan("matches", players.PLAYERS_PARQUET_DIR).select("match_id", "start_time"),
            on="match_id",
        )
        .filter(pl.col("start_time").dt.convert_time_zone(tz).dt.date() >= since)
        .select("match_id", "account_id", "rank", "downloaded_at")
    )


def compare_milestones_report(
    mine: pl.DataFrame,
    pool: pl.DataFrame,
    args: argparse.Namespace,
    ids: str,
    hero: str,
) -> None:
    """Print your median minute to each net-worth mark against the tracked pool."""
    targets = milestone_targets(args.step)
    shared = {"targets": targets}
    rows = milestone_rows(
        queries.compare(
            queries.milestone_games,
            [
                queries.Scope("you", args.parquet, {**shared, "games": mine.lazy()}),
                queries.Scope(
                    "them", players.PLAYERS_PARQUET_DIR, {**shared, "games": pool.lazy()}
                ),
            ],
            by="target",
            measures=("minutes", "games"),
        ).collect()
    )

    print("  Minutes to reach a net worth, median across games")
    print(f"  You: {ids}, {hero_games(len(mine), hero)}     Them: {hero_games(len(pool), hero)}\n")
    print(f"  {'Souls':>7}  {'You':>7}  {'Them':>7}  {'Gap':>7}  {'Games':>7}")

    for target in targets:
        row = rows.get(target)

        if row is None or min(row["you_games"] or 0, row["them_games"] or 0) < MILESTONE_MIN_GAMES:
            break

        print(
            f"  {target:>7}  {MILESTONE_MINUTES.render(row['you_minutes']):>7}"
            f"  {MILESTONE_MINUTES.render(row['them_minutes']):>7}"
            f"  {MILESTONE_MINUTES.render(row['gap_minutes'], sign=True):>7}"
            f"  {row['you_games']:>3}/{row['them_games']:<3}"
        )


def compare_report(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Compare a stat between the player and the tracked players, interval by interval."""
    if args.stat not in ("souls", "damage", "healing", "combat", "movement"):
        print(f"Unknown compare report: {args.stat}")
        print("Reports: souls, damage, healing, combat, movement")
        return

    if args.interval <= 0:
        print("--interval must be at least 1 minute")
        return

    if args.step < 1:
        print("--step must be at least 1")
        return

    if args.milestones and args.stat != "souls":
        print("--milestones only works with --stat souls")
        return

    hero_id = heroes.hero_id_by_name(args.hero)
    if hero_id is None:
        print(f"Unknown hero: {args.hero}")
        return

    since = dt.date.fromisoformat(args.since) if args.since else None
    pool_since = dt.date.fromisoformat(args.pool_since) if args.pool_since else None
    mine = queries.hero_games(args.hero, args.parquet, args.account, since=since).collect()
    ids = format_accounts(args.account, config)
    window = f" since {args.since}" if args.since else ""
    pool_window = f" since {args.pool_since}" if args.pool_since else ""

    if mine.is_empty():
        print(no_games_line(args, config))
        return

    hero = heroes.hero_name(hero_id)
    subject_accounts = set(args.account)
    against = set(args.against or [])
    members = [
        member
        for member in players.pool_members(args.hero, config_path=config)
        if member["account_id"] not in subject_accounts
        and (not against or member["account_id"] in against)
    ]

    if not members:
        if against:
            ids = format_accounts(args.against, config)
            print(f"No tracked {args.hero} players match --against {ids}")
        else:
            print(no_pool_hint(args.hero, tracked_in_config=False, mode=args.mode))
        return

    pool_lf = players.pool_games(args.hero, config_path=config).filter(
        ~pl.col("account_id").is_in(args.account)
    )
    if against:
        pool_lf = pool_lf.filter(pl.col("account_id").is_in(args.against))
    if pool_since:
        pool_lf = _pool_since_filter(pool_lf, pool_since, config_timezone(config))
    pool = pool_lf.collect()

    if pool.is_empty():
        if pool_since:
            print(f"No tracked {args.hero} games since {args.pool_since}")
        else:
            print(no_pool_hint(args.hero, tracked_in_config=True, mode=args.mode))
        return

    counts = {
        r["account_id"]: r["games"]
        for r in pool.group_by("account_id")
        .agg(pl.col("match_id").n_unique().alias("games"))
        .iter_rows(named=True)
    }
    members = [
        {**m, "games": counts[m["account_id"]]} for m in members if m["account_id"] in counts
    ]

    print(
        f"You ({ids}, {hero_games(len(mine), hero)}{window}) vs "
        f"{_tracked_players(len(members), hero)} ({hero_games(len(pool), hero)}{pool_window}): "
        f"{args.stat}"
    )

    if args.stat in ("combat", "movement"):
        print(f"\n  {'Player':<18} {'Games':>5}  Last download")

        for m in members:
            when = f"{m['downloaded_at']:%Y-%m-%d}" if m["downloaded_at"] else "never"
            print(f"  {m['name']:<18} {m['games']:>5}  {when}")

        if args.stat == "combat":
            _combat_compare(mine, pool, args)
        else:
            _movement_compare(mine, pool, members, args)

        return

    if args.milestones:
        print()
        compare_milestones_report(mine, pool, args, ids, hero)
        return

    if args.stat == "souls":
        if queries.table_exists("soul_sources", args.parquet) and queries.table_exists(
            "soul_sources", players.PLAYERS_PARQUET_DIR
        ):
            sources_report(mine.lazy(), pool.lazy(), args.parquet, players.PLAYERS_PARQUET_DIR)
        print("\nSouls over time")

    elif args.stat in ("damage", "healing"):
        try:
            _compare_damage_sources(mine, pool, args, hero, args.stat)
            if args.stat == "healing":
                with suppress(ValueError):
                    _compare_damage_sources(mine, pool, args, hero, "heal_prevented")
        except ValueError as e:
            print(e)
            return

        print(f"\n{args.stat.capitalize()} over time")

    interval_s = args.interval * 60
    my_rates, pool_rates, my_medians, pool_medians = pl.collect_all(
        [
            _per_game(mine.lazy(), args.stat, args.parquet),
            _per_game(pool.lazy(), args.stat, players.PLAYERS_PARQUET_DIR),
            _interval_medians(
                queries.view_frame(
                    queries.compare_intervals(mine.lazy(), args.stat, interval_s),
                    parquet_dir=args.parquet,
                )
            ),
            _interval_medians(
                queries.view_frame(
                    queries.compare_intervals(pool.lazy(), args.stat, interval_s),
                    parquet_dir=players.PLAYERS_PARQUET_DIR,
                )
            ),
        ]
    )

    unit = "game" if args.stat in COUNT_STATS else "min"
    print(
        f"\n  {'Player':<18} {'Games':>5}  {'Last download':>13}"
        f"  {f'Avg/{unit}':>8} {f'Med/{unit}':>8}"
    )
    _summary_line("you", len(mine), "-", my_rates.get_column("rate").to_list())

    for m in members:
        when = f"{m['downloaded_at']:%Y-%m-%d}" if m["downloaded_at"] else "never"
        rates = pool_rates.filter(pl.col("account_id") == m["account_id"])

        _summary_line(m["name"], m["games"], when, rates.get_column("rate").to_list())

    _interval_table(args, my_medians, pool_medians, my_rates, pool_rates)


def _interval_medians(gains: pl.LazyFrame) -> pl.LazyFrame:
    """Aggregate a compare_intervals frame to the median gain and game count per interval."""
    return queries.summarize(
        queries.compare_intervals,
        by="interval",
        measures=("median_gain", "games"),
        lf=gains,
    ).rename({"median_gain": "gain", "games": "len"})


def _per_game(games: pl.LazyFrame, stat: str, parquet_dir: str | Path | None) -> pl.LazyFrame:
    """Pick the per game total for count stats and the per minute rate otherwise."""
    if stat in COUNT_STATS:
        return queries.game_totals(games, stat, parquet_dir).select(
            "match_id", "account_id", pl.col("total").alias("rate")
        )

    return queries.game_rates(games, stat, parquet_dir)


def _interval_table(
    args: argparse.Namespace,
    my_medians: pl.DataFrame,
    pool_medians: pl.DataFrame,
    my_rates: pl.DataFrame,
    pool_rates: pl.DataFrame,
) -> None:
    """Print the per interval medians of both sides with the running difference."""
    you = {r["interval"]: (r["gain"], r["len"]) for r in my_medians.iter_rows(named=True)}
    them = {r["interval"]: (r["gain"], r["len"]) for r in pool_medians.iter_rows(named=True)}
    per = "" if args.stat in COUNT_STATS else "/min"
    scale = 1 if args.stat in COUNT_STATS else args.interval

    print(
        f"\n  {'Min':<8} {f'You{per}':>8} {f'Them{per}':>9} {f'Gap{per}':>9}"
        f" {'Cumulative gap':>14} {'Games':>8}"
    )

    behind = 0.0
    shown_end = 0
    worst: tuple[float, int, float, float] | None = None
    cut_side = None

    for n in itertools.count():
        if n not in you and n not in them:
            break

        (gain_y, n_y) = you.get(n, (0.0, 0))
        (gain_t, n_t) = them.get(n, (0.0, 0))

        if n_y < 3 or n_t < 3:
            cut_side = "your games" if n_y < 3 else "tracked games"
            break

        rate_y = gain_y / scale
        rate_t = gain_t / scale
        gap = rate_y - rate_t
        behind += gap * scale
        shown_end = (n + 1) * args.interval
        span = f"{n * args.interval}-{shown_end}"
        deficit = (rate_y - rate_t) if args.stat in LOWER_IS_BETTER else (rate_t - rate_y)

        if worst is None or deficit > worst[0]:
            worst = (deficit, n, rate_y, rate_t)

        games = f"{n_y}/{n_t}"
        print(
            f"  {span:<8} {render.cell(rate_y)} {render.cell(rate_t, 9)} {render.cell(gap, 9, sign=True)}"
            f" {render.cell(behind, 14, sign=True)} {games:>8}"
        )

    total_y = my_rates.get_column("rate").to_list()
    total_t = pool_rates.get_column("rate").to_list()

    if total_y and total_t:
        med_y = st.median(total_y)
        med_t = st.median(total_t)
        print(
            f"  {'Total':<8} {render.cell(med_y)} {render.cell(med_t, 9)} {render.cell(med_y - med_t, 9, sign=True)}"
        )

    print("\n  This table shows the median values for each interval")

    if cut_side is not None:
        print(f"  Games past {shown_end}m left out, too few {cut_side} reach them")

    if worst is not None and worst[0] > 0:
        deficit, n, rate_y, rate_t = worst
        span = f"{n * args.interval}-{(n + 1) * args.interval}m"
        print(
            f"  Biggest {args.stat} gap: {span}, "
            f"you {render.cell(rate_y, 1)}{per} vs tracked players {render.cell(rate_t, 1)}{per}"
        )
    elif worst is not None:
        print(f"  No {args.stat} gap at any interval, you keep pace or better")


def _summary_line(name: str, games: int, when: str, rates: list[float]) -> None:
    """Print one player row of the compare summary table."""
    avg = render.cell(st.mean(rates)) if rates else render.cell(None)
    med = render.cell(st.median(rates)) if rates else render.cell(None)

    print(f"  {name:<18} {games:>5}  {when:>13}  {avg} {med}")


COMBAT_METRICS = (
    render.Metric("hit_rate", "Hero hit %"),
    render.Metric("headshot_rate", "Hero headshot %"),
    render.Metric("shots_per_game", "Hero shots /game"),
    render.Metric("gun_damage_per_game", "Gun damage /game"),
    render.Metric("gun_damage_per_hit", "Gun damage /hit"),
    render.Metric("incoming_hit_rate", "Incoming hit %"),
    render.Metric("parries_per_game", "Parries /game"),
    render.Metric("missed_parries_per_game", "Missed parries /game"),
)


def _combat_compare(mine: pl.DataFrame, pool: pl.DataFrame, args: argparse.Namespace) -> None:
    """Print the fight counters of both sides and the gap between them."""
    if not queries.table_exists("custom_stats", args.parquet):
        print("\nNo custom_stats table yet, run `deadlock sync --full`")
        return

    if not queries.table_exists("custom_stats", players.PLAYERS_PARQUET_DIR):
        print("\nNo downloaded combat stats yet: run `deadlock download --hero " + args.hero + "`")
        return

    gaps = (
        queries.compare(
            queries.combat_games,
            _pool_scopes(mine, pool, args, {"hero": args.hero}),
            measures=[metric.measure for metric in COMBAT_METRICS],
        )
        .collect()
        .row(0, named=True)
    )

    print()

    for line in render.gap_lines(queries.combat_games, gaps, COMBAT_METRICS):
        print(line)


def _movement_compare(
    mine: pl.DataFrame,
    pool: pl.DataFrame,
    members: list[dict[str, Any]],
    args: argparse.Namespace,
) -> None:
    """Print the pooled movement gap table and then one row per tracked player.

    - both tables average the per game metrics of each side
    - the per player rows sort by pace and include a you row for contrast
    """
    if not queries.table_exists("movement_intervals", args.parquet):
        print("\nNo movement_intervals table yet: run `deadlock sync`")
        return

    if not queries.table_exists("movement_intervals", players.PLAYERS_PARQUET_DIR):
        print("\nNo downloaded movement yet: run `deadlock download --hero " + args.hero + "`")
        return

    columns = [col for _, col in MOVEMENT_METRICS]
    you, top = pl.collect_all(
        [
            queries.movement_metrics(args.parquet)
            .join(mine.lazy().select("match_id", "account_id"), on=["match_id", "account_id"])
            .with_columns(meters_min())
            .select("distance_min", *columns),
            queries.movement_metrics(players.PLAYERS_PARQUET_DIR)
            .join(pool.lazy().select("match_id", "account_id"), on=["match_id", "account_id"])
            .with_columns(meters_min())
            .select("match_id", "account_id", "distance_min", *columns),
        ]
    )

    if you.is_empty() or top.is_empty():
        print("\nNo movement rows for these games yet: run `deadlock sync`")
        return

    gaps = (
        queries.compare(
            queries.movement_games,
            [queries.Scope("you", lf=you.lazy()), queries.Scope("them", lf=top.lazy())],
            measures=tuple(MOVEMENT_MEASURES.values()),
        )
        .collect()
        .row(0, named=True)
    )

    print(f"\n  {'Metric':<24}{'You':>9}{'Tracked':>9}{'Gap':>9}")

    for label, col in MOVEMENT_METRICS:
        measure = MOVEMENT_MEASURES[col]
        scale = UNITS_PER_METER if col == "meters_min" else 1
        cells = (
            render.cell(gaps[f"you_{measure}"], 9, scale=scale, decimals=1)
            + render.cell(gaps[f"them_{measure}"], 9, scale=scale, decimals=1)
            + render.cell(gaps[f"gap_{measure}"], 9, scale=scale, decimals=1, sign=True)
        )

        print(f"  {label:<24}{cells}")

    print()
    _movement_by_player(you, top, {m["account_id"]: m["name"] for m in members})


def _fit_name(name: str, width: int) -> str:
    """Cut a name to a display width and pad it there, wide characters count double."""
    out = ""
    used = 0

    for c in name:
        w = 2 if unicodedata.east_asian_width(c) in "WF" else 1

        if used + w > width:
            break

        out += c
        used += w

    return out + " " * (width - used)


NAME_WIDTH = 14


def _movement_by_player(you: pl.DataFrame, top: pl.DataFrame, labels: dict[int, str]) -> None:
    """Print one movement row per tracked player and a you row for contrast.

    - each row averages the per game metrics of that player
    - names are the labels from [players.<hero>] in config.toml
    """
    columns = [col for _, col in MOVEMENT_METRICS]
    rows = (
        top.group_by("account_id")
        .agg(pl.len().alias("games"), pl.col(columns).mean())
        .sort("meters_min", descending=True)
        .to_dicts()
    )

    print(
        f"  {_fit_name('Player', NAME_WIDTH)}{'Account':>11}{'Games':>7}"
        f"{'m /min':>9}{'Stationary':>12}{'Slide':>8}{'In air':>8}{'Zipline':>9}"
        f"{'Fighting':>10}{'Dash/min':>10}{'Air dash':>10}"
    )

    def line(label: str, account: str, games: int, r: dict[str, Any]) -> str:
        return (
            f"  {_fit_name(label, NAME_WIDTH)}{account:>11}{games:>7,}"
            f"{r['meters_min']:>9,.1f}"
            f"{r['stationary_percent']:>11,.1f}%{r['slide_percent']:>7,.1f}%"
            f"{r['in_air_percent']:>7,.1f}%{r['zipline_percent']:>8,.1f}%"
            f"{r['combat_percent']:>9,.1f}%{r['dashes_min']:>10,.1f}{r['air_dashes_min']:>10,.1f}"
        )

    yours = {col: column_mean(you, col) for col in columns}
    print(line("you", "-", len(you), yours))

    for r in rows:
        name = labels.get(r["account_id"], str(r["account_id"]))

        print(line(name, str(r["account_id"]), r["games"], r))
