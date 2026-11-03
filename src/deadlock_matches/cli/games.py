"""Reports that read every game of a hero and print the totals across them."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl

from deadlock_matches import queries
from deadlock_matches.cli import render
from deadlock_matches.cli.match import (
    DELIVERY_LABELS,
    POWERUP_STATS,
    SOUL_GROUPS,
    SOUL_LABELS,
    leftover_sections,
    range_section,
    snapshot_accuracy,
    take_group,
    uncamel,
)
from deadlock_matches.cli.winrate import no_games_line, win_rate
from deadlock_matches.config import account_labels, config_timezone, format_accounts
from deadlock_matches.queries.movement import UNITS_PER_METER, meters_min

if TYPE_CHECKING:
    import argparse


LANE_CUTS = [-3000, -1000, 1000, 3000]
LANE_LABELS = ["behind 3k+", "behind 1k-3k", "even within 1k", "ahead 1k-3k", "ahead 3k+"]
FEED_CUTS = [1, 3]
FEED_LABELS = ["0-1", "2-3", "4+"]
OWN_CUTS = [0, 1, 3]
OWN_LABELS = ["0", "1", "2-3", "4+"]
FED_AT = 4


def _rate_table(games: pl.DataFrame, bucket: pl.Expr, header: str) -> None:
    """Print a wins and losses table for one way of bucketing the games."""
    rows = (
        games.group_by(bucket=bucket)
        .agg(games=pl.len(), wins=pl.col("won").cast(pl.Int32).sum())
        .sort("bucket")
    )

    print(f"  {header:<24}{'Games':>7}{'W':>6}{'L':>6}{'Win rate':>11}")

    for r in rows.iter_rows(named=True):
        print(
            f"  {r['bucket']!s:<24}{r['games']:>7}{r['wins']:>6}"
            f"{r['games'] - r['wins']:>6}{win_rate(r['wins'], r['games']):>11}"
        )


def laning_games_report(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Win rate by lane result at the laning mark and by teammate deaths."""
    tz = config_timezone(config)
    mark_s = args.minutes * 60

    try:
        games = queries.lane_records(
            args.parquet,
            accounts=args.account,
            tz=tz,
            days=args.days,
            since=args.since,
            hero=args.hero,
            mark_s=mark_s,
        )
    except ValueError as e:
        print(e)
        return

    if games.is_empty():
        print(no_games_line(args, config))
        return

    mark = f"{args.minutes}:00"
    lane = (
        pl.when(pl.col("lane_net") > 0)
        .then(pl.lit("won lane"))
        .when(pl.col("lane_net") < 0)
        .then(pl.lit("lost lane"))
        .otherwise(pl.lit("even lane"))
    )

    print(f"Lane result at {mark}: your lane's souls minus the enemy side's, scored games only.\n")
    _rate_table(games, pl.col("lane_net").cut(LANE_CUTS, labels=LANE_LABELS), f"Lane at {mark}")
    print()
    _rate_table(games, lane, "Lane result")

    print(f"\nYour deaths by {mark}:\n")
    _rate_table(games, pl.col("my_early").cut(OWN_CUTS, labels=OWN_LABELS), "Deaths")

    clean = games.filter(pl.col("ally_left").not_())
    left_out = len(games) - len(clean)
    note = f" ({left_out} games with an ally abandon left out)" if left_out else ""

    if not clean.is_empty():
        print(f"\nWorst teammate deaths by {mark}, you excluded{note}:\n")
        _rate_table(clean, pl.col("worst_early").cut(FEED_CUTS, labels=FEED_LABELS), "Deaths")

        fed = (
            pl.when(pl.col("worst_early") >= FED_AT)
            .then(pl.lit("ally fed"))
            .otherwise(pl.lit("no feeder"))
        )

        print(f"\nLane result and a feeding teammate ({FED_AT}+ deaths by {mark}):\n")
        _rate_table(clean, lane + pl.lit(", ") + fed, "")

    total = len(games)
    wins = int(games.get_column("won").cast(pl.Int32).sum())

    print(f"\nOverall: {total} games, {wins}-{total - wins}, {win_rate(wins, total)} win rate.")


DAMAGE_SHARES = (
    ("Gun %", "gun_pct", 6),
    ("Abil %", "abilities_pct", 7),
    ("Items %", "items_pct", 8),
)

HEALING_SHARES = (
    ("Abil %", "abilities_pct", 7),
    ("Items %", "items_pct", 8),
    ("Self %", "self_pct", 7),
)

SOUL_SHARES = (
    ("Waves %", "waves_pct", 8),
    ("Roam %", "roaming_pct", 7),
    ("Combat %", "combat_pct", 9),
    ("Obj %", "objectives_pct", 6),
)


def _source_rows(sources: pl.DataFrame, width: int) -> None:
    """Print the per source rows under their column header."""
    print(
        f"\n  {'Games':>5}  {'Source':<{width}}"
        f"{'Total':>12}{'/game':>9}{'/min':>9}{'/min owned':>12}{'/1k souls':>11}{'%':>7}"
    )

    for r in sources.iter_rows(named=True):
        owned = f"{r['per_min_owned']:,.1f}" if r["per_min_owned"] is not None else "-"
        per_1k = f"{r['per_1k']:,.1f}" if r["per_1k"] is not None else "-"
        print(
            f"  {r['games']:>5}  {r['source_name']:<{width}}"
            f"{r['total']:>12,}{r['total'] / r['games']:>9,.0f}{r['per_min']:>9,.1f}"
            f"{owned:>12}{per_1k:>11}{r['percent']:>6.1f}%"
        )


def _source_tables(
    games: pl.DataFrame, sources: pl.DataFrame, prevented: pl.DataFrame | None = None
) -> None:
    """Print the delivery block and the per source table with their rate notes.

    - prevented adds a healing prevented table with the same columns, its
      percent column shares out the prevented total
    """
    total = int(sources.get_column("total").sum())
    minutes = games.get_column("duration_s").sum() / 60
    n_games = len(games)
    names = sources.get_column("source_name")

    if prevented is not None:
        names = pl.concat([names, prevented.get_column("source_name")])

    width = max(max(len(n) for n in names), 14) + 2

    print(f"  {'Delivery':<{width}}{'Total':>12}{'/game':>9}{'/min':>9}{'%':>7}")

    groups = sources.group_by("delivery").agg(pl.col("total").sum()).sort("total", descending=True)

    for r in groups.iter_rows(named=True):
        label = DELIVERY_LABELS.get(r["delivery"], r["delivery"])
        percent = f"{100 * r['total'] / total:.0f}%" if total else "-"

        print(
            f"  {label:<{width}}{r['total']:>12,}{r['total'] / n_games:>9,.0f}"
            f"{r['total'] / minutes:>9,.1f}{percent:>7}"
        )

    print(f"  {'Total':<{width}}{total:>12,}{total / n_games:>9,.0f}{total / minutes:>9,.1f}")

    _source_rows(sources, width)

    if prevented is not None:
        print("\nHealing prevented:")
        _source_rows(prevented, width)

    print(
        "\n  /game divides a delivery row by every game and a source row by the games"
        " it appeared in."
        "\n  /min divides the same way with the minutes of those games."
        "\n  /min owned divides an item row by the minutes the item was owned instead."
        "\n  /1k souls divides an item row by every 1,000 souls it actually cost,"
        " so an upgrade does not recount the components you already bought."
    )


def _per_game_lines(
    games: pl.DataFrame,
    args: argparse.Namespace,
    config: str | Path | None,
    shares: tuple[tuple[str, str, int], ...],
    values: tuple[tuple[str, str, int], ...],
) -> None:
    """Print the newest games one per line with the given percent and total columns."""
    names = account_labels(config)
    shown = games.tail(max(args.games, 0))
    header = "Per game, newest last"

    if len(shown) < len(games):
        header = (
            f"Per game, the last {len(shown)} of {len(games)} (--games N lists more), newest last"
        )

    share_heads = " ".join(f"{label:>{w}}" for label, _, w in shares)
    value_heads = " ".join(f"{label:>{w}}" for label, _, w in values)

    print(f"\n{header}\n")
    print(
        f"  {'Account':<10} {'Day':<10} {'Result':<7} {'K/D/A':<9} "
        f"{share_heads} {value_heads}  Match ID"
    )

    for g in shown.iter_rows(named=True):
        account = names.get(g["account_id"], str(g["account_id"]))
        result = "win" if g["won"] else "loss"
        kda = f"{g['kills']}/{g['deaths']}/{g['assists']}"
        cells = " ".join(
            f"{g[col]:>{w}.1f}" if g[col] is not None else f"{'-':>{w}}" for _, col, w in shares
        )
        totals = " ".join(f"{g[col]:>{w},}" for _, col, w in values)

        print(
            f"  {account:<10} {g['day']!s:<10} {result:<7} {kda:<9} "
            f"{cells} {totals}  {g['match_id']}"
        )


def damage_games_report(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Print damage to heroes by source across every game of a hero and then one line per game.

    - the delivery block splits the total into gun, abilities, and item procs
    - the source table is one row per gun, ability, or item source with the
      games it appeared in
    - the per game table lists the newest games with the percent of damage
      from gun, abilities, and items
    """
    if not queries.table_exists("damage", args.parquet):
        print("No damage table yet, run `deadlock sync`")
        return

    tz = config_timezone(config)

    try:
        games = queries.damage_game_records(
            args.hero,
            accounts=args.account,
            parquet_dir=args.parquet,
            tz=tz,
            days=args.days,
            since=args.since,
        )
        hero = games.item(0, "hero")
        sources = queries.damage_by_source(
            hero,
            accounts=args.account,
            matches=games.get_column("match_id").to_list(),
            parquet_dir=args.parquet,
        )
    except queries.NoGames:
        print(no_games_line(args, config))
        return
    except ValueError as e:
        print(e)
        return

    print(f"Damage to heroes by source, {len(games)} games of {hero}\n")
    _source_tables(games, sources)
    _per_game_lines(games, args, config, DAMAGE_SHARES, (("Damage", "total", 9),))


def healing_games_report(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Print healing by source across every game of a hero and then one line per game.

    - the delivery block splits the total into abilities and item procs
    - the source table is one row per ability or item source with the games
      it appeared in
    - a healing prevented table follows with the sources that denied enemy
      healing and is skipped when no game has any
    - the per game table adds the percent of healing that landed on the
      healer
    """
    if not queries.table_exists("damage", args.parquet):
        print("No damage table yet, run `deadlock sync`")
        return

    tz = config_timezone(config)

    try:
        games = queries.healing_game_records(
            args.hero,
            accounts=args.account,
            parquet_dir=args.parquet,
            tz=tz,
            days=args.days,
            since=args.since,
        )
        hero = games.item(0, "hero")
        matches = games.get_column("match_id").to_list()
        sources = queries.damage_by_source(
            hero,
            accounts=args.account,
            matches=matches,
            parquet_dir=args.parquet,
            stat="healing",
        )
    except queries.NoGames:
        print(no_games_line(args, config))
        return
    except ValueError as e:
        print(e)
        return

    try:
        prevented = queries.damage_by_source(
            hero,
            accounts=args.account,
            matches=matches,
            parquet_dir=args.parquet,
            stat="heal_prevented",
        )
    except ValueError:
        prevented = None

    print(f"Healing by source, {len(games)} games of {hero}\n")
    _source_tables(games, sources, prevented=prevented)
    _per_game_lines(
        games,
        args,
        config,
        HEALING_SHARES,
        (("Healing", "total", 9), ("Prevented", "prevented", 10)),
    )


MILESTONE_MIN_GAMES = 3
MILESTONE_CAP = 80000


def hero_games(n: int, hero: str) -> str:
    """Format a game count with the hero name."""
    noun = "game" if n == 1 else "games"
    return f"{n} {hero} {noun}"


def milestone_targets(step: int) -> list[int]:
    """Net-worth targets to print."""
    return list(range(step, MILESTONE_CAP + 1, step))


MILESTONE_MINUTES = queries.view_measure(queries.milestone_games, "minutes").display_format


def milestone_rows(frame: pl.DataFrame) -> dict[int, dict[str, Any]]:
    """Index a milestone result by the target each row reached."""
    return {r["target"]: r for r in frame.iter_rows(named=True)}


def souls_milestones_report(
    games: pl.DataFrame, args: argparse.Namespace, ids: str, hero: str
) -> None:
    """Print the median minute you reach each net-worth mark across your games."""
    targets = milestone_targets(args.step)
    you = milestone_rows(
        queries.summarize(
            queries.milestone_games,
            by="target",
            measures=("minutes", "games"),
            games=games.lazy(),
            targets=targets,
            parquet_dir=args.parquet,
        ).collect()
    )

    print("  Minutes to reach a net worth, median across games")
    print(f"  You: {ids}, {hero_games(len(games), hero)}\n")
    print(f"  {'Souls':>7}  {'Minute':>7}  {'games':>5}")

    for target in targets:
        row = you.get(target)

        if row is None or row["games"] < MILESTONE_MIN_GAMES:
            n = 0 if row is None else row["games"]
            print(f"\n  Stopped before {target:,}: only {n} games reached it.")
            break

        print(f"  {target:>7}  {MILESTONE_MINUTES.render(row['minutes']):>7}  {row['games']:>5}")


def _soul_tables(games: pl.DataFrame, sources: pl.DataFrame) -> None:
    """Print the group block and the per source table for souls."""
    sources = sources.filter(pl.col("souls") > 0).with_columns(
        pl.col("source_name").replace(SOUL_GROUPS).alias("group"),
        pl.col("source_name").replace(SOUL_LABELS).alias("label"),
    )
    total = int(sources.get_column("souls").sum())
    minutes = games.get_column("duration_s").sum() / 60
    width = max(max(len(n) for n in sources.get_column("label")), 14) + 2

    print(f"  {'Group':<{width}}{'Total':>12}{'/game':>9}{'/min':>9}{'%':>7}")

    groups = sources.group_by("group").agg(pl.col("souls").sum()).sort("souls", descending=True)

    for r in groups.iter_rows(named=True):
        percent = f"{100 * r['souls'] / total:.0f}%" if total else "-"

        print(
            f"  {r['group']:<{width}}{r['souls']:>12,}{r['souls'] / len(games):>9,.0f}"
            f"{r['souls'] / minutes:>9,.1f}{percent:>7}"
        )

    print(f"  {'Total':<{width}}{total:>12,}{total / len(games):>9,.0f}{total / minutes:>9,.1f}")

    print(
        f"\n  {'Games':>5}  {'Source':<{width}}{'Group':<12}"
        f"{'Souls':>12}{'/game':>9}{'/min':>9}{'%':>7}"
    )

    for r in sources.iter_rows(named=True):
        print(
            f"  {r['games']:>5}  {r['label']:<{width}}{r['group']:<12}"
            f"{r['souls']:>12,}{r['souls'] / r['games']:>9,.0f}"
            f"{r['souls'] / r['minutes']:>9,.1f}{r['percent']:>6.1f}%"
        )

    print(
        "\n  /game divides a group row by every game and a source row by the games"
        " it appeared in."
        "\n  /min divides the same way with the minutes of those games."
    )


def souls_games_report(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Print souls by source group across every game of a hero and then one line per game.

    - the group block splits gross souls into waves, roaming, combat,
      objectives, and catch up
    - the source table is one row per income source with the games it
      appeared in
    - the per game table lists the newest games with the percent of souls
      from each group and souls per minute
    """
    if not queries.table_exists("soul_sources", args.parquet):
        print("No soul_sources table yet, run `deadlock sync`")
        return

    if args.step < 1:
        print("--step must be at least 1")
        return

    tz = config_timezone(config)

    try:
        games = queries.souls_game_records(
            args.hero,
            accounts=args.account,
            parquet_dir=args.parquet,
            tz=tz,
            days=args.days,
            since=args.since,
        )
        hero = games.item(0, "hero")
    except queries.NoGames:
        print(no_games_line(args, config))
        return
    except ValueError as e:
        print(e)
        return

    if args.milestones:
        souls_milestones_report(games, args, format_accounts(args.account, config), hero)
        return

    try:
        sources = queries.souls_by_source(
            hero,
            accounts=args.account,
            matches=games.get_column("match_id").to_list(),
            parquet_dir=args.parquet,
        )
    except ValueError as e:
        print(e)
        return

    games = games.with_columns(
        (pl.col("total") / (pl.col("duration_s") / 60)).round(0).cast(pl.Int64).alias("per_min")
    )

    print(f"Souls by source, {len(games)} games of {hero}\n")
    _soul_tables(games, sources)
    _per_game_lines(
        games, args, config, SOUL_SHARES, (("Souls", "total", 9), ("/min", "per_min", 6))
    )


COMBAT_SHARES = (
    ("Hit %", "hit_pct", 6),
    ("HS %", "headshot_pct", 6),
)

AIM_EXTRA_ROWS = (
    ("Lucky shots", "LuckyShots"),
    ("Hits on immobilized", "Immobile Hits"),
    ("Headshots on immobilized", "Immobile Headshots"),
)


def _aim_share(values: dict[str, int], key: str, base: str) -> float | None:
    """Give one counter as a percent of another, None without a base."""
    whole = values.get(base, 0)

    if not whole:
        return None

    return 100 * values.get(key, 0) / whole


def _aim_totals_table(title: str, values: dict[str, int], n_games: int) -> None:
    """Print one aim counter table with totals, per game, and rates."""
    rows = [
        ("Shots", values.get("Shots", 0), None),
        ("Hits", values.get("Hits", 0), _aim_share(values, "Hits", "Shots")),
        ("Headshots", values.get("Headshots", 0), _aim_share(values, "Headshots", "Hits")),
    ]
    rows += [(label, values[key], None) for label, key in AIM_EXTRA_ROWS if values.get(key)]

    print(f"  {title:<26}{'Total':>12}{'/game':>9}{'Rate':>8}")

    for label, value, rate in rows:
        cell = f"{rate:.1f}%" if rate is not None else ""

        print(f"  {label:<26}{value:>12,}{value / n_games:>9,.0f}{cell:>8}")


def _all_target_accuracy_totals(games: pl.DataFrame, args: argparse.Namespace) -> int | None:
    """Read the familiar all target accuracy summed over every listed game."""
    return snapshot_accuracy(games, args.parquet)


def _combat_aim_sections(
    games: pl.DataFrame,
    args: argparse.Namespace,
    stats: dict[tuple[str | None, str], int],
    rates: dict[tuple[str | None, str], float],
) -> None:
    """Print your aim table, the enemy fire table, and the rate lines."""
    you = take_group(stats, "Enemy Hero Accuracy")
    them = take_group(stats, "Enemy Hero Accuracy - Incoming")
    take_group(stats, "Bullet Stats")
    take_group(stats, "Bullet Stats - Incoming")

    if you.get("Shots"):
        _aim_totals_table("Aim vs heroes", you, len(games))

    if them.get("Shots"):
        print()
        _aim_totals_table("Enemy fire at you", them, len(games))

    lines = [
        f"{uncamel(stat).capitalize().replace('hit rate', 'hit rate:')}"
        f" {rates['Bullet Stats', stat]:.0f}% averaged per game"
        for stat in ("StunHitRate", "StunHeadshotHitRate")
        if rates.get(("Bullet Stats", stat))
    ]

    familiar = _all_target_accuracy_totals(games, args)

    if familiar is not None:
        lines.append(f"Accuracy with troopers and everything else included: {familiar}%")

    lines.append("Rates count heroes only, troopers and other NPCs left out.")

    print()

    for text in lines:
        print(f"  {text}")


def _combat_parry_lines(games: pl.DataFrame, stats: dict[tuple[str | None, str], int]) -> None:
    """Print the parry totals with the per game rate."""
    success = stats.pop((None, "Parry Success"), 0)
    missed = stats.pop((None, "Parry Miss"), 0)

    if not (success or missed):
        return

    print(
        f"\n  Parries {success:,} landed, {missed:,} missed,"
        f" {success / len(games):.1f} landed per game"
        "\n  Counterspell auto-parries count as landed parries."
    )


def combat_games_report(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Print the hidden fight counters across every game of a hero and then one line per game.

    - the aim tables total fire at enemy heroes and enemy fire at the player
    - damage by range and parries follow as whole window sums
    - per hero counters close the window view with uptime shares included
    """
    if not queries.table_exists("custom_stats", args.parquet):
        print("No custom_stats table yet, run `deadlock sync --full`")
        return

    tz = config_timezone(config)

    try:
        games = queries.combat_game_records(
            args.hero,
            accounts=args.account,
            parquet_dir=args.parquet,
            tz=tz,
            days=args.days,
            since=args.since,
        )
    except queries.NoGames:
        print(no_games_line(args, config))
        return
    except ValueError as e:
        print(e)
        return

    hero = games.item(0, "hero")
    agg = queries.custom_stat_totals(
        args.account, games.get_column("match_id").to_list(), parquet_dir=args.parquet
    )

    stats: dict[tuple[str | None, str], int] = {}
    rates: dict[tuple[str | None, str], float] = {}

    for r in agg.iter_rows(named=True):
        rates[r["group"], r["stat"]] = float(r["avg"])

        if r["stat"] not in POWERUP_STATS:
            stats[r["group"], r["stat"]] = int(r["total"])

    if not any(stats.values()):
        print(f"No combat stats in {len(games)} games of {hero}")
        return

    print(f"Combat stats, {len(games)} games of {hero}\n")
    _combat_aim_sections(games, args, stats, rates)
    range_section(stats)
    _combat_parry_lines(games, stats)
    leftover_sections(stats, bare=False)
    _per_game_lines(
        games, args, config, COMBAT_SHARES, (("Shots", "shots", 8), ("Parry", "parries", 6))
    )


DEATH_PHASES = [(0, "0-10 min"), (600, "10-20 min"), (1200, "20-30 min"), (1800, "30+ min")]


def column_mean(df: pl.DataFrame, column: str, scale: float = 1.0) -> float:
    """Take the mean of a column as a float for printing.

    - scale 100 turns a boolean mean into a percent
    """
    value = df.select(pl.col(column).mean().mul(scale)).item()

    return float(value or 0)


def _death_frame(args: argparse.Namespace, tz: str, *, has_context: bool) -> pl.DataFrame:
    """Load deaths for the player with the command line filters applied.

    - joins nearby ally and enemy context when the movement table is exported
    - keeps only the columns the report reads
    """
    columns = [
        "match_id",
        "day",
        "won",
        "game_time_s",
        "time_to_kill_s",
        "death_duration_s",
        "killer_account_id",
    ]

    if has_context:
        lf = queries.death_context(
            args.radius, args.parquet, accounts=args.account, tz=tz, days=args.days
        )
        columns += ["solo", "outnumbered", "enemies"]
    else:
        lf = queries.my_deaths(args.parquet, accounts=args.account, tz=tz, days=args.days)

    if args.hero is not None:
        lf = lf.filter(pl.col("hero") == args.hero)

    if args.since is not None:
        lf = lf.filter(pl.col("day") >= dt.date.fromisoformat(args.since))

    return lf.select(columns).collect()


def deaths_report(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Break down deaths by game time buckets, killer, and nearby players."""
    tz = config_timezone(config)
    has_context = queries.table_exists("movement", args.parquet)

    try:
        df = _death_frame(args, tz, has_context=has_context)
    except ValueError as e:
        print(e)
        return

    if df.is_empty():
        print(no_games_line(args, config, subject="deaths"))
        return

    games = df["match_id"].n_unique()
    downtime = df["death_duration_s"].sum() / games
    print(
        f"{len(df)} deaths across {games} games "
        f"({len(df) / games:.1f} per game, {downtime:.0f}s dead per game)\n"
    )

    df = df.with_columns(
        pl.col("game_time_s")
        .cut([t for t, _ in DEATH_PHASES[1:]], labels=[label for _, label in DEATH_PHASES])
        .alias("phase")
    )

    header = f"  {'Time':<11}{'Deaths':>7}{'/game':>7}{'Killed in':>11}"
    if has_context:
        header += f"{'Solo':>7}{'Outnum':>8}{'Enemies':>9}"
    print(header)

    for _, label in DEATH_PHASES:
        p = df.filter(pl.col("phase") == label)

        if p.is_empty():
            continue

        ttk = float(p.select(pl.col("time_to_kill_s").median()).item() or 0)
        line = f"  {label:<11}{len(p):>7}{len(p) / games:>7.1f}{ttk:>11.1f}"
        if has_context:
            line += (
                f"{column_mean(p, 'solo', 100):>6.0f}%{column_mean(p, 'outnumbered', 100):>7.0f}%"
                f"{column_mean(p, 'enemies'):>9.1f}"
            )
        print(line)

    for won, tag in [(True, "wins"), (False, "losses")]:
        w = df.filter(pl.col("won") == won)

        if w.is_empty():
            continue

        line = f"\n  {tag}: {len(w)} deaths"
        if has_context:
            line += (
                f", {column_mean(w, 'solo', 100):.0f}% solo, "
                f"{column_mean(w, 'outnumbered', 100):.0f}% outnumbered"
            )
        print(line, end="")
    print()

    killers = (
        df.lazy()
        .filter(pl.col("killer_account_id").is_not_null())
        .join(
            queries.player_rows(args.parquet).select(
                "match_id",
                killer_account_id=pl.col("account_id"),
                killer=pl.col("hero"),
            ),
            on=["match_id", "killer_account_id"],
        )
        .group_by("killer")
        .len()
        .sort(["len", "killer"], descending=[True, False])
        .head(5)
        .collect()
    )

    if not killers.is_empty():
        top = ", ".join(f"{k} {n}" for k, n in killers.iter_rows())
        print(f"\nKilled most by: {top}")

    if not has_context:
        print(
            '\nAlly/enemy context needs the movement table: remove "movement" from '
            '"exclude" in config.toml and run `deadlock sync`'
        )


MOVEMENT_METRICS = [
    ("meters /min", "meters_min"),
    ("stationary %", "stationary_percent"),
    ("slide %", "slide_percent"),
    ("in air %", "in_air_percent"),
    ("zipline %", "zipline_percent"),
    ("fighting players %", "combat_percent"),
    ("ground dashes /min", "dashes_min"),
    ("air dashes /min", "air_dashes_min"),
]

MOVEMENT_MEASURES = {
    column: "distance_min" if column == "meters_min" else column for _, column in MOVEMENT_METRICS
}

MOVEMENT_SHARES = (
    ("m /min", "meters_min", 7),
    ("Stationary %", "stationary_percent", 12),
    ("In air %", "in_air_percent", 9),
    ("Fighting %", "combat_percent", 10),
    ("Dash /min", "dashes_min", 9),
)


def _movement_table(games: pl.DataFrame) -> None:
    """Print each movement metric averaged per game and split by result.

    - the wins and losses columns only appear when the window has both
    - games without movement rows stay out of the averages
    """
    measures = tuple(MOVEMENT_MEASURES.values())
    overall = queries.summarize(
        queries.movement_games,
        measures=measures,
        lf=games.lazy(),
    ).collect()
    buckets = [(f"All ({len(games)})", overall.row(0, named=True))]

    if games.get_column("won").drop_nulls().n_unique() > 1:
        results = queries.summarize(
            queries.movement_games,
            by="won",
            measures=("games", *measures),
            lf=games.lazy(),
        ).collect()
        by_result = {row["won"]: row for row in results.iter_rows(named=True)}
        buckets += [
            (f"Wins ({by_result[True]['games']})", by_result[True]),
            (f"Losses ({by_result[False]['games']})", by_result[False]),
        ]

    print(f"  {'Metric':<24}" + "".join(f"{label:>14}" for label, _ in buckets))

    for label, col in MOVEMENT_METRICS:
        measure = MOVEMENT_MEASURES[col]
        scale = UNITS_PER_METER if col == "meters_min" else 1
        cells = "".join(
            render.cell(row[measure], 14, scale=scale, decimals=1) for _, row in buckets
        )

        print(f"  {label:<24}{cells}")

    print(
        "\n  Percents cover seconds alive. Stationary and the pace cover seconds moving."
        "\n  Meters skip ziplines, respawns, and other teleports."
    )


def movement_games_report(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Print the movement metrics across every game of a hero and then one line per game.

    - the metric table averages each game with wins and losses as their own columns
    - the per game table lists the newest games with pace, stationary time,
      air time, fight time, and dashes
    """
    if not queries.table_exists("movement_intervals", args.parquet):
        print("No movement_intervals table yet: run `deadlock sync`")
        return

    tz = config_timezone(config)

    try:
        games = queries.movement_game_records(
            args.hero,
            accounts=args.account,
            parquet_dir=args.parquet,
            tz=tz,
            days=args.days,
            since=args.since,
        )
    except queries.NoGames:
        print(no_games_line(args, config))
        return
    except ValueError as e:
        print(e)
        return

    hero = games.item(0, "hero")
    games = games.with_columns(meters_min())

    print(f"Movement, {len(games)} games of {hero}\n")
    _movement_table(games)
    _per_game_lines(games, args, config, MOVEMENT_SHARES, ())
