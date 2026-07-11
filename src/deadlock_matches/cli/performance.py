"""Commands comparing your play against top players and across your own days."""

from __future__ import annotations

import datetime as dt
import itertools
import re
import statistics as st
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl

from deadlock_matches import (
    accolades,
    export,
    extract,
    heroes,
    items,
    meta,
    paths,
    players,
    queries,
    skill_rating,
    statues,
)
from deadlock_matches.cli.cards import UNITS_PER_METER
from deadlock_matches.cli.data import MVP_LABELS, TEAMS, final_stats, no_pool_hint
from deadlock_matches.config import config_players, config_timezone, format_accounts

if TYPE_CHECKING:
    import argparse


def _cell(value: float | None, width: int = 8, *, sign: bool = False) -> str:
    """Format a number to a fixed width for table cells.

    - missing values print as '-'
    - small fractions keep two decimals
    """
    if value is None:
        return "-".rjust(width)

    if abs(value) < 10 and abs(value - round(value)) > 1e-9:
        return f"{value:>{'+' if sign else ''}{width},.2f}"

    return f"{value:>{'+' if sign else ''}{width},.0f}"


DELIVERY_LABELS = {
    "gun": "Gun",
    "ability": "Abilities",
    "gun_proc": "Items (gun)",
    "spirit_proc": "Items (spirit)",
}

SOUL_LABELS = {
    "troopers": "Troopers",
    "denies": "Denies",
    "jungle": "Neutral Enemies",
    "breakables": "Breakable Pickups",
    "players": "Enemy Kills",
    "assists": "Kill Assists",
    "bosses": "Objectives",
    "treasure": "Rift & Urn",
    "team_bonus": "Team Catch-Up",
    "trophy_collector": "Trophy Collector",
    "cultist_sacrifice": "Cultist Sacrifice",
    "assassinate": "Bounty",
    "goose_egg": "Goose Egg",
}

SOUL_GROUPS = {
    "troopers": "Lane",
    "denies": "Lane",
    "jungle": "Roaming",
    "breakables": "Roaming",
    "players": "Combat",
    "assists": "Combat",
    "bosses": "Objectives",
    "treasure": "Objectives",
    "team_bonus": "Catch-Up",
    "trophy_collector": "Other",
    "cultist_sacrifice": "Other",
    "assassinate": "Other",
    "goose_egg": "Other",
}

SOUL_GROUP_ORDER = ("Lane", "Roaming", "Combat", "Objectives", "Catch-Up", "Other")

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


def sources_report(
    mine: pl.LazyFrame,
    pool: pl.LazyFrame,
    my_dir: str | Path | None,
    pool_dir: str | Path | None,
) -> None:
    """Compare income from each soul source between your games and the pool."""
    marks = [6, 10, 15, 20, 25]
    marks_s = [m * 60 for m in marks]
    frames = pl.collect_all(
        [_mark_medians(queries.cumulative_at(mine, s, marks_s, my_dir)) for s in SOURCE_ROWS]
        + [_mark_medians(queries.cumulative_at(pool, s, marks_s, pool_dir)) for s in SOURCE_ROWS]
    )

    header = "".join(f"  {f'{m}m gap':>8}" for m in marks)
    print(f"\n  {'source':<12}{header}  {'you@20m':>9}  {'them@20m':>9}")

    for i, stat in enumerate(SOURCE_ROWS):
        you = dict(frames[i].iter_rows())
        them = dict(frames[i + len(SOURCE_ROWS)].iter_rows())
        gaps = "".join(f"  {_cell(_gap(you, them, m * 60), sign=True)}" for m in marks)

        print(f"  {stat:<12}{gaps}  {_cell(you.get(1200), 9)}  {_cell(them.get(1200), 9)}")

    print(
        "\n  souls is net worth. It runs a little over the other rows summed, the game"
        "\n  credits some income (sell refunds and similar) to no source"
    )


def _mark_medians(values: pl.LazyFrame) -> pl.LazyFrame:
    """Aggregate a cumulative_at frame to the median value per mark."""
    return values.group_by("mark_s").agg(pl.col("value").median())


def _gap(you: dict[int, float], them: dict[int, float], mark_s: int) -> float | None:
    """Difference of the two medians at a mark, None when either side is missing."""
    if mark_s not in you or mark_s not in them:
        return None

    return you[mark_s] - them[mark_s]


def compare_report(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Compare a stat between the player and the tracked players, interval by interval."""
    if args.stat != "soul_sources" and args.stat not in queries.COMPARE_STATS:
        print(f"Unknown stat: {args.stat}")
        print("Stats: " + ", ".join(queries.COMPARE_STATS) + ", soul_sources")
        return

    if args.interval <= 0:
        print("--interval must be at least 1 minute")
        return

    hero_id = heroes.hero_id_by_name(args.hero)
    if hero_id is None:
        print(f"Unknown hero: {args.hero}")
        return

    since = dt.date.fromisoformat(args.since) if args.since else None
    mine = queries.hero_games(args.hero, args.parquet, args.account, since=since).collect()
    ids = format_accounts(args.account, config)
    window = f" since {args.since}" if args.since else ""

    if mine.is_empty():
        print(f"No ranked games for accounts {ids} on {args.hero}{window}")
        return

    members = players.pool_members(args.hero, config_path=config)

    if not members:
        print(no_pool_hint(args.hero, tracked_in_config=False))
        return

    if not any(m["games"] for m in members):
        print(no_pool_hint(args.hero, tracked_in_config=True))
        return

    pool = players.pool_games(args.hero, config_path=config).collect()

    print(
        f"You ({ids}, {len(mine)} games{window}) vs "
        f"{len(members)} tracked {args.hero} players ({len(pool)} games): {args.stat}"
    )

    if args.stat == "soul_sources":
        print(f"\n  {'Player':<18} {'Games':>5} {'Rank':>5}  Last download")

        for m in members:
            rank = "-" if m["rank"] is None else str(m["rank"])
            when = f"{m['downloaded_at']:%Y-%m-%d}" if m["downloaded_at"] else "never"
            print(f"  {m['name']:<18} {m['games']:>5} {rank:>5}  {when}")

        sources_report(mine.lazy(), pool.lazy(), args.parquet, players.PARQUET_DIR)
        return

    interval_s = args.interval * 60
    my_rates, pool_rates, my_medians, pool_medians = pl.collect_all(
        [
            _per_game(mine.lazy(), args.stat, args.parquet),
            _per_game(pool.lazy(), args.stat, players.PARQUET_DIR),
            _interval_medians(
                queries.compare_intervals(mine.lazy(), args.stat, interval_s, args.parquet)
            ),
            _interval_medians(
                queries.compare_intervals(pool.lazy(), args.stat, interval_s, players.PARQUET_DIR)
            ),
        ]
    )

    unit = "game" if args.stat in COUNT_STATS else "min"
    print(
        f"\n  {'Player':<18} {'Games':>5} {'Rank':>5}  {'Last download':>13}"
        f"  {f'Avg/{unit}':>8} {f'Med/{unit}':>8}"
    )
    _summary_line("you", len(mine), "-", "-", my_rates.get_column("rate").to_list())

    for m in members:
        rank = "-" if m["rank"] is None else str(m["rank"])
        when = f"{m['downloaded_at']:%Y-%m-%d}" if m["downloaded_at"] else "never"
        rates = pool_rates.filter(pl.col("account_id") == m["account_id"])

        _summary_line(m["name"], m["games"], rank, when, rates.get_column("rate").to_list())

    _interval_table(args, my_medians, pool_medians, my_rates, pool_rates)


def _interval_medians(gains: pl.LazyFrame) -> pl.LazyFrame:
    """Aggregate a compare_intervals frame to the median gain and game count per interval."""
    return gains.group_by("interval").agg(pl.col("gain").median().alias("gain"), pl.len())


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
            f"  {span:<8} {_cell(rate_y)} {_cell(rate_t, 9)} {_cell(gap, 9, sign=True)}"
            f" {_cell(behind, 14, sign=True)} {games:>8}"
        )

    total_y = my_rates.get_column("rate").to_list()
    total_t = pool_rates.get_column("rate").to_list()

    if total_y and total_t:
        med_y = st.median(total_y)
        med_t = st.median(total_t)
        print(
            f"  {'Total':<8} {_cell(med_y)} {_cell(med_t, 9)} {_cell(med_y - med_t, 9, sign=True)}"
        )

    print("\n  This table shows the median values for each interval")

    if cut_side is not None:
        print(f"  Games past {shown_end}m left out, too few {cut_side} reach them")

    if worst is not None and worst[0] > 0:
        deficit, n, rate_y, rate_t = worst
        span = f"{n * args.interval}-{(n + 1) * args.interval}m"
        print(
            f"  Biggest {args.stat} gap: {span}, "
            f"you {_cell(rate_y, 1)}{per} vs tracked players {_cell(rate_t, 1)}{per}"
        )
    elif worst is not None:
        print(f"  No {args.stat} gap at any interval, you keep pace or better")


def _summary_line(name: str, games: int, rank: str, when: str, rates: list[float]) -> None:
    """Print one player row of the compare summary table."""
    avg = _cell(st.mean(rates)) if rates else _cell(None)
    med = _cell(st.median(rates)) if rates else _cell(None)

    print(f"  {name:<18} {games:>5} {rank:>5}  {when:>13}  {avg} {med}")


def _span(row: dict[str, Any]) -> str:
    """Label an interval row like 0-5m, or 30-34m for a shorter last interval."""
    return f"{row['start_s'] // 60}-{-(-row['end_s'] // 60)}m"


def _players_store_fallback(match_id: int, args: argparse.Namespace) -> bool:
    """Point args.parquet at the players tables when they hold the match.

    - only jumps from the default store, an explicit --parquet stays respected
    """
    if Path(args.parquet) != export.PARQUET_DIR:
        return False

    if not queries.table_exists("players", players.PARQUET_DIR):
        return False

    found = (
        queries.scan("players", players.PARQUET_DIR)
        .filter(pl.col("match_id") == match_id)
        .head(1)
        .collect()
    )

    if found.is_empty():
        return False

    args.parquet = players.PARQUET_DIR
    print(f"Reading match {match_id} from the players tables at {paths.tilde(players.PARQUET_DIR)}")

    return True


def _match_player(match_id: int, args: argparse.Namespace, tz: str) -> pl.DataFrame:
    """Look up the row for one player in a match, by hero name or your accounts."""
    lf = queries.scan("players", args.parquet).filter(pl.col("match_id") == match_id)

    if args.hero is not None:
        lf = lf.filter(pl.col("hero") == args.hero)
    else:
        lf = lf.filter(pl.col("account_id").is_in(args.account))

    return (
        lf.join(queries.scan("matches", args.parquet), on="match_id")
        .with_columns(pl.col("start_time").dt.convert_time_zone(tz).alias("start_local"))
        .collect()
    )


def _final_scoreboard(row: dict[str, Any], args: argparse.Namespace) -> None:
    """Print the 12-player post-game scoreboard with the resolved player starred."""
    badges = [
        f"{TEAMS[team]} {skill_rating.label(row[f'average_badge_team{team}'])}"
        for team in (0, 1)
        if row.get(f"average_badge_team{team}") is not None
    ]

    if badges:
        print("Lobby average: " + ", ".join(badges))

    match_ids = pl.LazyFrame({"match_id": [row["match_id"]]}, schema={"match_id": pl.Int64})
    lf = (
        queries.scan("players", args.parquet)
        .filter(pl.col("match_id") == row["match_id"])
        .join(final_stats(match_ids, args.parquet), on=["match_id", "account_id"], how="left")
        .with_columns(
            pl.col("player_damage", "boss_damage", "player_healing", "heal_prevented").fill_null(0)
        )
    )

    with_buffs = queries.table_exists("buffs", args.parquet)

    if with_buffs:
        totals = (
            queries.scan("buffs", args.parquet)
            .filter(pl.col("match_id") == row["match_id"], pl.col("permanent"))
            .group_by("match_id", "account_id")
            .agg(pl.col("count").sum().alias("buffs"))
        )
        lf = lf.join(totals, on=["match_id", "account_id"], how="left").with_columns(
            pl.col("buffs").fill_null(0)
        )

    board = lf.sort(["team", "net_worth"], descending=[False, True]).collect()

    header = (
        f"  {'Team':<16} {'Hero':<14} {'':<8} {'K/D/A':<8} {'Souls':>9} "
        f"{'Damage':>8} {'Obj damage':>10} {'Healing':>8} {'Prevented':>9} "
        f"{'Last hits':>9} {'Denies':>6}"
    )

    if with_buffs:
        header += f" {'Buffs':>8}"

    print()
    print(header)

    for p in board.iter_rows(named=True):
        kda = f"{p['kills']}/{p['deaths']}/{p['assists']}"
        hero = f"{p['hero']} *" if p["account_id"] == row["account_id"] else p["hero"]
        line = (
            f"  {TEAMS.get(p['team'], p['team']):<16} {hero:<14} "
            f"{MVP_LABELS.get(p['mvp_rank'], ''):<8} {kda:<8} {p['net_worth']:>9,} "
            f"{p['player_damage']:>8,} {p['boss_damage']:>10,} {p['player_healing']:>8,} "
            f"{p['heal_prevented']:>9,} {p['last_hits']:>9,} {p['denies']:>6}"
        )

        if with_buffs:
            line += f" {p['buffs']:>8}"

        print(line)
    print()


def _killer_meters(d: dict[str, Any]) -> float | None:
    """Return how far the killer stood from the death in meters."""
    if d["killer_x"] is None or d["x"] is None:
        return None

    units = (
        (d["x"] - d["killer_x"]) ** 2
        + (d["y"] - d["killer_y"]) ** 2
        + (d["z"] - d["killer_z"]) ** 2
    ) ** 0.5

    return units / UNITS_PER_METER


LANING_COLUMNS = (
    ("Souls", "souls", 8),
    ("Kills", "kills", 7),
    ("Deaths", "deaths", 8),
    ("Damage", "damage", 9),
    ("Taken", "damage_taken", 9),
    ("Healing", "healing", 9),
    ("Prevented", "heal_prevented", 11),
    ("Last hits", "last_hits", 11),
    ("Denies", "denies", 8),
)


def _laning_cells(r: dict[str, Any], *, signed: bool = False) -> str:
    """Format every stat column of one laning row."""
    sign = "+" if signed else ""

    return "".join(format(r[field], f">{sign}{width},") for _, field, width in LANING_COLUMNS)


def _guardian_falls(
    row: dict[str, Any], args: argparse.Namespace, lane: str, mark_s: int
) -> list[tuple[int, str]]:
    """List the guardian falls of one lane inside the window from the player side."""
    fallen = (
        queries.scan("objectives", args.parquet)
        .filter(
            pl.col("match_id") == row["match_id"],
            pl.col("lane") == lane,
            pl.col("objective") == "Guardian",
            pl.col("destroyed_time_s").is_not_null(),
            pl.col("destroyed_time_s") <= mark_s,
        )
        .sort("destroyed_time_s")
        .collect()
    )

    falls = []

    for o in fallen.iter_rows(named=True):
        side = "your" if o["team"] == row["team"] else "enemy"

        falls.append((o["destroyed_time_s"], f"{side} Guardian falls"))

    return falls


def laning_report(row: dict[str, Any], args: argparse.Namespace) -> None:
    """Print the laning phase lane by lane: team and player stats, kills, guardians."""
    if args.laning <= 0:
        print("--laning takes a positive number of minutes")
        return

    mark_s = args.laning * 60
    df = queries.laning_stats(row["match_id"], mark_s, args.parquet).with_columns(
        (pl.col("creeps") + pl.col("neutrals")).alias("last_hits")
    )

    lanes = [lane for lane in df["lane"].unique().sort().to_list() if lane is not None]

    if not lanes:
        print("No lane assignments in this match")
        return

    if row["lane"] in lanes:
        lanes.remove(row["lane"])
        lanes.insert(0, row["lane"])

    snap_s = df.select(pl.col("snap_s").max()).item()
    note = ""

    if snap_s is not None and snap_s != mark_s:
        minutes, seconds = divmod(snap_s, 60)
        note = f" (stat columns read at the {minutes}:{seconds:02d} snapshot)"

    print(f"Laning phase through {args.laning}:00{note}")

    names = dict(df.select("account_id", "hero").iter_rows())
    name_w = max(max(len(n) for n in names.values()), 11)
    label_w = name_w + 5
    kill_log = (
        queries.scan("deaths", args.parquet)
        .filter(pl.col("match_id") == row["match_id"], pl.col("game_time_s") <= mark_s)
        .select("account_id", "killer_account_id", "game_time_s")
        .sort("game_time_s")
        .collect()
    )

    header = "".join(f"{label:>{width}}" for label, _, width in LANING_COLUMNS)

    for lane in lanes:
        here = df.filter(pl.col("lane") == lane)
        yours = here.filter(pl.col("team") == row["team"]).sort(
            pl.col("account_id") != row["account_id"], pl.col("souls"), descending=[False, True]
        )
        enemy = here.filter(pl.col("team") != row["team"]).sort("souls", descending=True)
        title = f"{lane.capitalize()} (your lane)" if lane == row["lane"] else lane.capitalize()

        print(f"\n{title}")
        print(f"  {'Lane':<{label_w}}{header}")

        side_sums = {}

        for side, group in (("Yours", yours), ("Enemy", enemy)):
            sums = group.sum().row(0, named=True)
            side_sums[side] = sums

            print(f"  {side:<{label_w}}{_laning_cells(sums)}")

            for p in group.iter_rows(named=True):
                star = "*" if p["account_id"] == row["account_id"] else " "
                label = f" {star} {p['hero']}"

                print(f"  {label:<{label_w}}{_laning_cells(p)}")

        diff = {
            field: side_sums["Yours"][field] - side_sums["Enemy"][field]
            for _, field, _ in LANING_COLUMNS
        }

        print(f"  {'Net':<{label_w}}{_laning_cells(diff, signed=True)}")

        deaths_here = kill_log.filter(pl.col("account_id").is_in(here["account_id"].implode()))
        events = [
            (
                e["game_time_s"],
                f"{names.get(e['killer_account_id'], 'not a player')} kills {names[e['account_id']]}",
            )
            for e in deaths_here.iter_rows(named=True)
        ]
        falls = _guardian_falls(row, args, lane, mark_s)
        events = sorted(events + falls)

        if events:
            print()

        for t, text in events:
            minutes, seconds = divmod(t, 60)

            print(f"  {f'{minutes}:{seconds:02d}':<7} {text}")

        if not falls:
            print("  both guardians up")


def _enemy_damage_table(
    row: dict[str, Any],
    args: argparse.Namespace,
    *,
    dealt: bool,
    min_width: int | None = None,
) -> None:
    """Print the per enemy interval table of damage taken or dealt.

    - min_width matches the name column to a source table printed above it, so
      the interval columns of the two tables line up
    """
    if not queries.table_exists("damage_targets", args.parquet):
        print("No damage_targets table yet, run `deadlock sync`")
        return

    try:
        df = queries.enemy_damage_intervals(
            row["match_id"], row["account_id"], args.interval * 60, args.parquet, dealt=dealt
        )
    except ValueError as e:
        print(e)
        return

    title = "Damage dealt to enemy" if dealt else "Damage taken by enemy"
    spans = df.select("start_s", "end_s").unique().sort("start_s")
    width = max(max(len(n) for n in df["enemy"]), 14, (min_width or 0) - 2) + 2
    header = "".join(f"{_span(r):>9}" for r in spans.iter_rows(named=True))
    total = int(df["damage"].sum())

    print(f"{title}, {args.interval}-minute intervals")
    print(f"\n  {'Enemy':<{width}}{header}{'Total':>9}{'%':>7}")

    for (enemy,), g in df.group_by(["enemy"], maintain_order=True):
        cells = "".join(f"{v:>9,}" for v in g.sort("start_s")["damage"])
        enemy_total = int(g.item(0, "total"))
        percent = f"{100 * enemy_total / total:.0f}%" if total else "-"

        print(f"  {enemy:<{width}}{cells}{enemy_total:>9,}{percent:>7}")

    sums = df.group_by("start_s").agg(pl.col("damage").sum()).sort("start_s")
    cells = "".join(f"{v:>9,}" for v in sums["damage"])

    print(f"  {'Total':<{width}}{cells}{total:>9,}")
    print()


def death_log_report(row: dict[str, Any], args: argparse.Namespace, *, kills: bool) -> None:
    """Print each death in the match for one player, from the victim or the killer side."""
    _enemy_damage_table(row, args, dealt=kills)

    if not queries.table_exists("deaths", args.parquet):
        print("No deaths table yet, run `deadlock sync --full`")
        return

    heroes_in_match = (
        queries.scan("players", args.parquet)
        .filter(pl.col("match_id") == row["match_id"])
        .select("account_id", "hero")
        .collect()
    )
    hero_names = dict(heroes_in_match.iter_rows())

    log = queries.scan("deaths", args.parquet).filter(pl.col("match_id") == row["match_id"])

    if kills:
        log = log.filter(pl.col("killer_account_id") == row["account_id"])
    else:
        log = log.filter(pl.col("account_id") == row["account_id"])

    log = log.sort("game_time_s").collect()

    if log.is_empty():
        print("No kills in this match" if kills else "No deaths in this match")
        return

    who = "Kill" if kills else "Killed by"
    print(f"\n  {'Time':<7} {who:<14} {'Killed in':>9} {'Distance':>9} {'Respawn':>8}")

    for d in log.iter_rows(named=True):
        minutes, seconds = divmod(d["game_time_s"], 60)
        other = d["account_id"] if kills else d["killer_account_id"]
        name = hero_names.get(other, "not a player")
        ttk = d["time_to_kill_s"]
        fight = f"{ttk:.1f}s" if ttk is not None and ttk >= 0 else "-"
        meters = _killer_meters(d)
        distance = f"{meters:,.0f}m" if meters is not None else "-"
        print(
            f"  {f'{minutes}:{seconds:02d}':<7} {name:<14} {fight:>9} {distance:>9} "
            f"{d['death_duration_s']:>7}s"
        )


def match_report(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Break the match for one player into intervals of souls, damage, and last hits."""
    if args.interval <= 0:
        print("--interval must be a positive number of minutes")
        return

    tz = config_timezone(config)

    if args.match_id is None:
        latest = (
            queries.my_games(args.parquet, accounts=args.account, tz=tz)
            .sort("start_time")
            .select("match_id")
            .tail(1)
            .collect()
        )

        if latest.is_empty():
            print("No games found for the configured accounts")
            return

        match_id = int(latest.item())
    else:
        match_id = args.match_id

    game = _match_player(match_id, args, tz)

    if game.is_empty() and args.match_id is not None and _players_store_fallback(match_id, args):
        game = _match_player(match_id, args, tz)

    if game.is_empty():
        in_match = (
            queries.scan("players", args.parquet)
            .filter(pl.col("match_id") == match_id)
            .select("hero")
            .collect()
        )

        if in_match.is_empty():
            if extract.has_match(args.archive, match_id):
                print(
                    f"None of your accounts played in match {match_id}, so it is not in your tables"
                )
            else:
                print(f"Match {match_id} is not in the archive")

            print(
                f"`deadlock download --match {match_id}` pulls it into the players tables, "
                "then rerun this command"
            )
        elif args.hero is not None:
            print(f"No {args.hero} in match {match_id}: " + ", ".join(sorted(in_match["hero"])))
        else:
            print(f"None of the configured accounts played in match {match_id}")
            print("Pass --hero to pick a player from the match")

        return

    row = game.row(0, named=True)
    when = row["start_local"].strftime("%Y-%m-%d %H:%M")
    result = "win" if row["won"] else "loss"
    minutes, seconds = divmod(row["duration_s"], 60)

    print(f"Match {row['match_id']}: {row['hero']}, {result}, {when}, {minutes}:{seconds:02d}")

    if args.souls:
        souls_report(row, args)
        return

    if args.teams:
        teams_report(row, args)
        return

    if args.abilities:
        abilities_report(row, args)
        return

    if args.items:
        items_report(row, args)
        return

    if args.accolades:
        accolades_report(row, args)
        return

    if args.buffs:
        buffs_report(row, args)
        return

    if args.stacks:
        stacks_report(row, args)
        return

    if args.combat:
        combat_report(row, args)
        return

    if args.movement:
        match_movement_report(row, args)
        return

    if args.laning is not None:
        laning_report(row, args)
        return

    if args.deaths or args.kills:
        death_log_report(row, args, kills=args.kills)
        return

    if args.damage or args.healing:
        damage_source_table(row, args)
        return

    _final_scoreboard(row, args)

    df = queries.match_intervals(
        row["match_id"], row["account_id"], args.interval * 60, args.parquet
    )

    print(
        f"  {'Time':<9}{'Souls':>8}{'/min':>7}{'K/D/A':>8}{'Damage':>9}{'Taken':>8}"
        f"{'Obj damage':>11}{'Healing':>9}{'Prevented':>11}{'Last hits':>10}"
        f"{'Troopers':>10}{'Neutrals':>9}{'Denies':>8}"
    )

    def table_line(label: str, r: dict[str, Any]) -> str:
        interval_kda = f"{r['kills']}/{r['deaths']}/{r['assists']}"

        return (
            f"  {label:<9}{r['souls']:>8,}{r['souls_min']:>7,.0f}{interval_kda:>8}"
            f"{r['damage']:>9,}{r['damage_taken']:>8,}{r['obj_damage']:>11,}"
            f"{r['healing']:>9,}{r['heal_prevented']:>11,}"
            f"{r['creeps'] + r['neutrals']:>10}{r['creeps']:>10}{r['neutrals']:>9}{r['denies']:>8}"
        )

    for r in df.iter_rows(named=True):
        print(table_line(_span(r), r))

    totals = df.sum().row(0, named=True)
    totals["souls_min"] = totals["souls"] / (row["duration_s"] / 60)
    print(table_line("Total", totals))


def _objective_events(row: dict[str, Any], args: argparse.Namespace) -> list[tuple[int, str]]:
    """List what fell and when, worded from the player point of view."""
    yours = row["team"]
    events = []

    objectives = (
        queries.scan("objectives", args.parquet)
        .filter(
            pl.col("match_id") == row["match_id"],
            pl.col("destroyed_time_s").is_not_null(),
        )
        .collect()
    )
    for o in objectives.iter_rows(named=True):
        actor = "enemy team" if o["team"] == yours else "your team"
        side = "your" if o["team"] == yours else "the enemy"
        lane = f" ({o['lane']})" if o["lane"] else ""

        events.append((o["destroyed_time_s"], f"{actor} destroys {side} {o['objective']}{lane}"))

    rejuvs = (
        queries.scan("mid_boss", args.parquet)
        .filter(pl.col("match_id") == row["match_id"])
        .collect()
    )
    for m in rejuvs.iter_rows(named=True):
        killer = "your team" if m["team_killed"] == yours else "enemy team"
        claimer = "your team" if m["team_claimed"] == yours else "enemy team"

        if m["team_claimed"] == m["team_killed"]:
            line = f"{killer} kills the mid boss and claims the Rejuvenator"
        else:
            line = f"{killer} kills the mid boss, {claimer} steals the Rejuvenator"

        events.append((m["destroyed_time_s"], line))

    events.extend(_objective_income_events(row, args))

    return sorted(events)


RIFT_ERA_START = dt.datetime(2026, 6, 30, 10, 7, 19, tzinfo=dt.UTC)
"""Release of client build 6601, the Unstable Rift rework in the deadlock-api version timeline.

- earlier matches ran the old urn-KOTH rules with a different bounty
- the build and its date come from assets.client_version_dates
"""

RIFT_SHARE_BASE = 247
RIFT_SHARE_PER_MIN = 37
RIFT_START_MIN = 13

URN_BOUNTY_BASE = 250
URN_BOUNTY_PER_MIN = 70
URN_FIRST_SPAWN_MIN = 10


def _rift_minute(share: int) -> float:
    """Recover the capture minute from a rift share of souls."""
    return (share - RIFT_SHARE_BASE) / RIFT_SHARE_PER_MIN + RIFT_START_MIN


def _urn_minute(bounty: int) -> float:
    """Recover the spawn minute from an urn runner bounty."""
    return (bounty - URN_BOUNTY_BASE) / URN_BOUNTY_PER_MIN


def _detect_rift(gains: list[int], team_size: int, comeback: int, duration_s: int) -> int | None:
    """Detect a rift win in this snapshot window from the shared team payout.

    - a rift win pays every player on the winning team the same souls at once
    """
    modal = max(set(gains), key=gains.count)
    modal_count = gains.count(modal)

    if modal_count < 5 or modal_count < team_size - 1:
        return None

    minute = _rift_minute(modal - comeback)

    if abs(minute - round(minute)) > 0.05:
        return None

    if not RIFT_START_MIN - 0.5 <= minute <= duration_s / 60 + 1:
        return None

    return modal


def _detect_urn(
    gains: list[int], hero_names: list[str], shared: int, duration_s: int
) -> tuple[str, int] | None:
    """Detect an urn delivery in this window and name the runner.

    - the runner banks the largest treasure gain once any shared rift payout is set aside
    """
    top_gain, runner = max(zip(gains, hero_names, strict=True))
    bounty = top_gain - shared

    if bounty < URN_BOUNTY_BASE + URN_BOUNTY_PER_MIN * (URN_FIRST_SPAWN_MIN - 0.5):
        return None

    if _urn_minute(bounty) > duration_s / 60 + 2:
        return None

    return runner, bounty


def _objective_income_events(
    row: dict[str, Any], args: argparse.Namespace
) -> list[tuple[int, str]]:
    """List every Unstable Rift win and Soul Urn delivery in the match.

    - both pay into the treasure soul source
    - a rift win pays the whole team at once, a comeback win adds the Comeback Gold Koth stat
    - an urn delivery pays one runner
    - only games on the rework build are read, earlier eras ran other rules
    """
    if row["start_time"] < RIFT_ERA_START:
        return []

    if not queries.table_exists("soul_sources", args.parquet):
        return []

    match_id = row["match_id"]

    roster = (
        queries.scan("players", args.parquet)
        .filter(pl.col("match_id") == match_id)
        .select("account_id", "team", "hero")
        .collect()
    )
    team_size = dict(roster.group_by("team").len().iter_rows())

    treasure = (
        queries.scan("soul_sources", args.parquet)
        .filter(pl.col("match_id") == match_id, pl.col("source_name") == "treasure")
        .select("account_id", "time_stamp_s", "souls", "souls_orbs")
        .sort("account_id", "time_stamp_s")
        .with_columns((pl.col("souls") + pl.col("souls_orbs")).alias("total"))
        .with_columns(
            pl.col("total").diff().over("account_id").fill_null(pl.col("total")).alias("gain")
        )
        .filter(pl.col("gain") > 0)
        .collect()
        .join(roster, on="account_id")
    )

    if treasure.is_empty():
        return []

    comeback = _comeback_by_window(match_id, roster, args)

    windows = (
        treasure.group_by("team", "time_stamp_s")
        .agg(pl.col("gain"), pl.col("hero"))
        .sort("time_stamp_s")
    )

    events = []

    for w in windows.iter_rows(named=True):
        team, t = w["team"], w["time_stamp_s"]
        actor = "your team" if team == row["team"] else "enemy team"
        c = comeback.get((team, t), 0)

        payout = _detect_rift(w["gain"], team_size.get(team, 6), c, row["duration_s"])

        if payout is not None:
            behind = " while behind" if c else ""
            events.append((t, f"{actor} wins an Unstable Rift{behind} (+{payout:,} souls each)"))

        urn = _detect_urn(w["gain"], w["hero"], payout or 0, row["duration_s"])

        if urn is not None:
            runner, bounty = urn
            events.append((t, f"{actor} delivers the Soul Urn ({runner}, +{bounty:,} souls)"))

    return events


def _comeback_by_window(
    match_id: int, roster: pl.DataFrame, args: argparse.Namespace
) -> dict[tuple[int, int], int]:
    """Read the comeback souls for each team and snapshot from the rift Koth stat."""
    if not queries.table_exists("custom_stats", args.parquet):
        return {}

    koth = queries.custom_stats(
        stat="Comeback Gold Koth", final=False, matches=[match_id], parquet_dir=args.parquet
    ).collect()

    if koth.is_empty():
        return {}

    windows = (
        koth.join(roster.select("account_id", "team"), on="account_id")
        .sort("account_id", "time_stamp_s")
        .with_columns(
            pl.col("value").diff().over("account_id").fill_null(pl.col("value")).alias("inc")
        )
        .filter(pl.col("inc") > 0)
        .group_by("team", "time_stamp_s")
        .agg(pl.col("inc").first().alias("comeback"))
    )

    return {
        (t, ts): c for t, ts, c in windows.select("team", "time_stamp_s", "comeback").iter_rows()
    }


def teams_report(row: dict[str, Any], args: argparse.Namespace) -> None:
    """Print souls per interval for both teams, then the objectives that fell."""
    if not queries.table_exists("objectives", args.parquet):
        print("No objectives table yet, run `deadlock sync`")
        return

    try:
        df = queries.team_intervals(row["match_id"], args.interval * 60, args.parquet)
    except ValueError as e:
        print(e)
        return

    yours = row["team"]
    print(f"Your team: {TEAMS.get(yours, yours)}")

    mine, theirs = ("souls_team0", "souls_team1") if yours == 0 else ("souls_team1", "souls_team0")
    sign = 1 if yours == 0 else -1

    print(f"\n  {'Time':<9}{'Your team':>11}{'Enemy team':>12}{'Lead':>10}")

    for r in df.iter_rows(named=True):
        print(f"  {_span(r):<9}{r[mine]:>11,}{r[theirs]:>12,}{sign * r['lead']:>+10,}")

    events = _objective_events(row, args)

    if events:
        print("\n  Objectives:")

        for t, line in events:
            mm, ss = divmod(int(t), 60)
            print(f"  {mm:>3}:{ss:02d}  {line}")


def abilities_report(row: dict[str, Any], args: argparse.Namespace) -> None:
    """Print ability unlocks and upgrades in the order they were spent."""
    df = (
        queries.ability_upgrades(row["hero"], args.parquet, accounts=[row["account_id"]])
        .filter(pl.col("match_id") == row["match_id"])
        .collect()
    )

    if df.is_empty():
        print(f"No ability upgrades found for {row['hero']} in match {row['match_id']}")
        return

    print("\n  Ability upgrades")
    print(
        f"  {'Time':>6}  {'#':>2}  {'Level':>5}  {'Req souls':>9}  "
        f"{'Reward':<6}  {'Ability':<18} {'Rank':>4}"
    )

    for r in df.iter_rows(named=True):
        mm, ss = divmod(int(r["game_time_s"]), 60)
        reward = "unlock" if r["reward"] == "ability_unlocks" else "point"

        print(
            f"  {mm:>3}:{ss:02d}  {r['ability_event_n']:>2}  {r['level']:>5}  "
            f"{r['required_souls']:>9,}  {reward:<6}  {r['ability']:<18} "
            f"{r['ability_upgrade_n']:>4}"
        )

    print("\n  Req souls is the threshold for that unlock or cumulative AP spend.")


def _game_time(seconds: int) -> str:
    """Format seconds of game time as m:ss."""
    mm, ss = divmod(int(seconds), 60)

    return f"{mm}:{ss:02d}"


def _item_note(r: dict[str, Any], buys: list[dict[str, Any]]) -> str:
    """Say what happened to a bought item after the purchase.

    - imbues names the ability the item was slotted into
    - flags=1 means it was consumed by a higher-tier item bought at sold_time_s,
      so the note names that upgrade instead of calling it a sell
    """
    parts = []

    if r.get("imbued_ability"):
        parts.append(f"imbues {r['imbued_ability']}")

    if r["sold_time_s"]:
        when = _game_time(r["sold_time_s"])

        if r["flags"] != 1:
            parts.append(f"sold at {when}")
        else:
            parts.append(_upgrade_target(r, buys) or f"upgraded at {when}")

    return ", ".join(parts)


def _upgrade_target(r: dict[str, Any], buys: list[dict[str, Any]]) -> str | None:
    """Find the upgrade bought the moment this item was consumed as a component."""
    catalog = items.item_map()
    consumed = catalog.get(r["item_id"])

    if consumed is None or consumed.class_name is None:
        return None

    for other in buys:
        if other["game_time_s"] != r["sold_time_s"] or other is r:
            continue

        target = catalog.get(other["item_id"])

        if target and consumed.class_name in target.components:
            return f"into {other['item']} at {_game_time(r['sold_time_s'])}"

    return None


def items_report(row: dict[str, Any], args: argparse.Namespace) -> None:
    """Print every item purchase in buy order with sells, upgrades, and imbued abilities."""
    if not queries.table_exists("item_events", args.parquet):
        print("No item_events table yet, run `deadlock sync`")
        return

    df = (
        queries.scan("item_events", args.parquet)
        .filter(
            pl.col("match_id") == row["match_id"],
            pl.col("account_id") == row["account_id"],
            pl.col("item").is_not_null(),
        )
        .sort("game_time_s")
        .collect()
    )

    if df.is_empty():
        print(f"No item purchases found for {row['hero']} in match {row['match_id']}")
        return

    buys = df.to_dicts()
    width = max(max(len(r["item"]) for r in buys), 4) + 2

    print("\n  Item purchases")
    print(f"  {'Time':>6}  {'#':>2}  {'Item':<{width}} {'Slot':<9} {'Tier':>4} {'Cost':>7}")

    for n, r in enumerate(buys, 1):
        cost = f"{r['cost']:,}" if r["cost"] is not None else "-"
        note = _item_note(r, buys)

        print(
            f"  {_game_time(r['game_time_s']):>6}  {n:>2}  {r['item']:<{width}} "
            f"{r['slot'] or '-':<9} {r['tier'] or '-':>4} {cost:>7}" + (f"  {note}" if note else "")
        )

    print("\n  'into' means the item was consumed by that upgrade, not sold.")


def accolades_report(row: dict[str, Any], args: argparse.Namespace) -> None:
    """Print the end of match stat awards with the value and stars for each."""
    if not queries.table_exists("accolades", args.parquet):
        print("No accolades table yet, run `deadlock sync --full`")
        return

    df = (
        queries.scan("accolades", args.parquet)
        .filter(
            pl.col("match_id") == row["match_id"],
            pl.col("account_id") == row["account_id"],
        )
        .sort("accolade_id")
        .collect()
    )

    if df.is_empty():
        print(f"No accolades found for {row['hero']} in match {row['match_id']}")
        return

    catalog = accolades.accolade_map()
    rows = df.to_dicts()
    labels = [(r["accolade"] or f"id{r['accolade_id']}").replace("_", " ") for r in rows]
    width = max(max(len(s) for s in labels), 4) + 2

    print("\n  Accolades")
    print(f"  {'Stat':<{width}} {'Value':>8}  {'Stars':<6} {'Award'}")

    for label, r in zip(labels, rows, strict=True):
        entry = catalog.get(r["accolade_id"])
        award = entry.name if entry else ""
        stars = "*" * (r["threshold"] + 1)

        print(f"  {label:<{width}} {r['value']:>8,}  {stars:<6} {award}")

    print("\n  Stars counts the reward thresholds cleared, up to three.")


BUFF_LABELS = {
    "hp": ("max health", False),
    "spirit": ("spirit power", False),
    "wp": ("weapon damage", True),
    "firerate": ("fire rate", True),
    "ammo": ("ammo", True),
    "cd": ("cooldown reduction", True),
}

TEMP_BUFF_LABELS = {
    "gun": "weapon",
    "casting": "spirit",
    "survival": "vitality",
    "movement": "movement",
}

SINNER_JACKPOT_ACCOLADE = 14


def _gained_cell(total: float | None, *, percent: bool) -> str:
    """Format the permanent stat a buff family added up to."""
    if total is None:
        return "?"

    if total == 0:
        return "-"

    return f"+{total:g}%" if percent else f"+{total:g}"


def buffs_report(row: dict[str, Any], args: argparse.Namespace) -> None:
    """Print the buffs one player ended the match with.

    - permanent buffs per family and level, valued against the committed statue
      history era live at match time, so old matches use the values their patch granted
    - the temporary bridge buffs the player claimed
    - a sources breakdown from the pickup counters, sinner jackpots, and mid boss kills
    """
    if not queries.table_exists("buffs", args.parquet):
        print("No buffs table yet, run `deadlock sync --full`")
        return

    df = (
        queries.scan("buffs", args.parquet)
        .filter(
            pl.col("match_id") == row["match_id"],
            pl.col("account_id") == row["account_id"],
        )
        .select("type", "buff", "level", "count", "permanent")
        .collect()
    )

    if df.is_empty():
        print(f"No buffs for {row['hero']} in match {row['match_id']}")
        return

    catalog = statues.statue_map_asof(row["start_time"])
    counts: dict[str, dict[int, int]] = {}
    gained: dict[str, float] = {}
    unknown: set[str] = set()

    for r in df.filter(pl.col("permanent")).to_dicts():
        buff = r["buff"] or r["type"]
        counts.setdefault(buff, {})[r["level"] or 0] = r["count"]
        entry = catalog.get(r["type"])

        if entry is not None and entry.value is not None:
            gained[buff] = gained.get(buff, 0) + r["count"] * entry.value
        elif r["count"]:
            unknown.add(buff)

    labels = {**BUFF_LABELS, **{b: (b, False) for b in counts if b not in BUFF_LABELS}}
    width = max(len(label) for label, _ in labels.values()) + 2

    print("\n  Permanent buffs")
    print(f"  {'Buff':<{width}} {'lv1':>5} {'lv2':>5} {'lv3':>5} {'Total':>6} {'Gained':>10}")

    for buff, (label, percent) in labels.items():
        levels = counts.get(buff, {})
        total = sum(levels.values())
        cell = _gained_cell(None if buff in unknown else gained.get(buff, 0), percent=percent)

        print(
            f"  {label:<{width}} {levels.get(1, 0):>5} {levels.get(2, 0):>5} "
            f"{levels.get(3, 0):>5} {total:>6} {cell:>10}"
        )

    temp = df.filter(~pl.col("permanent"))

    if not temp.is_empty():
        print("\n  Bridge buffs")

        for r in temp.to_dicts():
            label = TEMP_BUFF_LABELS.get(r["buff"], r["buff"] or r["type"])
            print(f"  {label:<{width}} {r['count']:>5}")

    _buff_sources(row, args, sum(sum(lv.values()) for lv in counts.values()), width)

    print("\n  Gained uses the per statue values from the patch the match was played on.")


def _buff_sources(row: dict[str, Any], args: argparse.Namespace, total: int, width: int) -> None:
    """Print where the permanent buffs came from, when the counters are available."""
    if not queries.table_exists("custom_stats", args.parquet):
        return

    stats = (
        queries.scan("custom_stats", args.parquet)
        .filter(
            pl.col("match_id") == row["match_id"],
            pl.col("account_id") == row["account_id"],
            pl.col("stat").is_in(["PowerUp Permanent", "PowerUp Gold"]),
        )
        .select("stat", "value")
        .collect()
    )
    named = dict(stats.iter_rows())

    if "PowerUp Permanent" not in named:
        return

    collected = named["PowerUp Permanent"]
    broken = named.get("PowerUp Gold", 0)

    jackpots = 0
    if queries.table_exists("accolades", args.parquet):
        jackpots = (
            queries.scan("accolades", args.parquet)
            .filter(
                pl.col("match_id") == row["match_id"],
                pl.col("account_id") == row["account_id"],
                pl.col("accolade_id") == SINNER_JACKPOT_ACCOLADE,
            )
            .select(pl.col("value").sum())
            .collect()
            .item()
            or 0
        )

    bosses = (
        queries.scan("mid_boss", args.parquet)
        .filter(
            pl.col("match_id") == row["match_id"],
            pl.col("team_killed") == row["team"],
        )
        .select(pl.len())
        .collect()
        .item()
    )

    other = max(0, total - collected - 4 * jackpots - 2 * bosses)

    print("\n  Sources")
    print(f"  {'statues collected':<{width}} {collected:>5}   {broken} broken")

    if jackpots:
        print(f"  {'sinner jackpots':<{width}} {jackpots:>5}   +{4 * jackpots}")

    if bosses:
        print(f"  {'mid boss kills':<{width}} {bosses:>5}   +{2 * bosses} to the whole team")

    if other:
        print(
            f"  {'other sources':<{width}} {'':>5}   +{other} (urn runs and light melee jackpots)"
        )


def stacks_report(row: dict[str, Any], args: argparse.Namespace) -> None:
    """Print the stack counts for every player in the match.

    Counts only exist for abilities and items that track stacks
    (Sticky Bomb, Trophy Collector, etc), so most players show nothing.
    """
    if not queries.table_exists("stacks", args.parquet):
        print("No stacks table yet, run `deadlock sync --full`")
        return

    in_match = (
        queries.scan("players", args.parquet)
        .filter(pl.col("match_id") == row["match_id"])
        .select("account_id", "hero", "team")
    )
    df = (
        queries.scan("stacks", args.parquet)
        .filter(pl.col("match_id") == row["match_id"])
        .join(in_match, on="account_id")
        .with_columns(
            side=pl.when(pl.col("team") == row["team"])
            .then(pl.lit("ally"))
            .otherwise(pl.lit("enemy"))
        )
        .sort(
            pl.col("team") != row["team"],
            pl.col("account_id") != row["account_id"],
            pl.col("value"),
            descending=[False, False, True],
        )
        .collect()
    )

    if df.is_empty():
        print(f"No stack counters in match {row['match_id']}")
        return

    rows = df.to_dicts()
    names = [r["name"] or f"id {r['ability_id']}" for r in rows]
    heroes_shown = [
        f"{r['hero'] or '?'} *" if r["account_id"] == row["account_id"] else r["hero"] or "?"
        for r in rows
    ]
    width = max(max(len(s) for s in names), 5) + 2
    hero_width = max(max(len(h) for h in heroes_shown), 4) + 2

    print("\n  Stacks")
    print(f"  {'Hero':<{hero_width}} {'Side':<6} {'Stack':<{width}} {'Final':>7}")

    for name, hero, r in zip(names, heroes_shown, rows, strict=True):
        print(f"  {hero:<{hero_width}} {r['side']:<6} {name:<{width}} {r['value']:>7,}")

    print("\n  Counts only exist for abilities and items that track stacks.")


DIST_COLUMNS = (
    ("Outgoing Bullet Dist", "Gun dealt"),
    ("Outgoing Ability Dist", "Ability dealt"),
    ("Incoming Bullet Dist", "Gun taken"),
    ("Incoming Ability Dist", "Ability taken"),
)

DIST_SPANS = (
    ("10", "0-10m"),
    ("20", "10-20m"),
    ("30", "20-30m"),
    ("40", "30-40m"),
    ("50", "40-50m"),
    ("75", "50-75m"),
    ("100", "75-100m"),
    ("Infinite", "100m+"),
)

FALLOFF_ORDER = ("No Falloff", "Partial Falloff", "Max Falloff")
FALLOFF_LABELS = ("none", "partial", "max")
PARRY_ITEMS = (1414025773, 4204808176)
POWERUP_STATS = frozenset({"PowerUp Gold", "PowerUp Permanent", "PowerUp Temp"})
COMEBACK_LABELS = (
    ("Comeback Gold", "Comeback souls"),
    ("Comeback Gold Koth", "Unstable Rift comeback"),
    ("Comeback Gold Urn", "Soul Urn comeback"),
)
UPTIME_RE = re.compile(r"(?P<ability>.+?)TimeAt_(?P<stacks>\d+)_stacks")


def _uncamel(name: str) -> str:
    """Split a CamelCase wire name into lowercase words."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name).lower()


def _take_group(stats: dict[tuple[str | None, str], int], group: str) -> dict[str, int]:
    """Pop every stat of one group out of the pool."""
    taken = {stat: value for (g, stat), value in stats.items() if g == group}

    for stat in taken:
        del stats[group, stat]

    return taken


def _count_cell(values: dict[str, int], key: str, base: str) -> str:
    """Format a count with its share of a base count."""
    value = values.get(key, 0)
    whole = values.get(base, 0)

    if not whole:
        return f"{value:,}"

    return f"{value:,} ({round(100 * value / whole)}%)"


def _falloff_line(values: dict[str, int]) -> str | None:
    """Format the bullet falloff split as percents."""
    total = sum(values.get(k, 0) for k in FALLOFF_ORDER)

    if not total:
        return None

    parts = (
        f"{round(100 * values.get(key, 0) / total)}% {label}"
        for key, label in zip(FALLOFF_ORDER, FALLOFF_LABELS, strict=True)
    )

    return ", ".join(parts)


def _all_target_accuracy(row: dict[str, Any], args: argparse.Namespace) -> int | None:
    """Read the familiar accuracy over every target from the final snapshot."""
    df = (
        queries.scan("stats", args.parquet)
        .filter(
            pl.col("match_id") == row["match_id"],
            pl.col("account_id") == row["account_id"],
        )
        .select(pl.col("shots_hit").max(), pl.col("shots_missed").max())
        .collect()
    )

    if df.is_empty():
        return None

    hit, missed = df.row(0)

    if not hit and not missed:
        return None

    return round(100 * hit / (hit + missed))


def _aim_section(
    row: dict[str, Any], args: argparse.Namespace, stats: dict[tuple[str | None, str], int]
) -> None:
    """Print the lobby ranked by aim against heroes, then the counters only the player has."""
    you = _take_group(stats, "Enemy Hero Accuracy")
    them = _take_group(stats, "Enemy Hero Accuracy - Incoming")
    rates = _take_group(stats, "Bullet Stats")
    _take_group(stats, "Bullet Stats - Incoming")

    _lobby_aim_table(row, args)

    lines = []

    if them.get("Shots"):
        hits = _count_cell(them, "Hits", "Shots")
        headshots = _count_cell(them, "Headshots", "Hits")
        lines.append(
            f"Enemy team at you: {them['Shots']:,} shots, {hits} hits, {headshots} headshots"
        )

    if you.get("LuckyShots"):
        lines.append(f"Lucky shots: {you['LuckyShots']:,}")

    if you.get("Immobile Hits"):
        lines.append(f"Hits on immobilized: {you['Immobile Hits']:,}")

    if you.get("Immobile Headshots"):
        lines.append(f"Headshots on immobilized: {you['Immobile Headshots']:,}")

    lines.extend(
        f"{_uncamel(key).capitalize().replace('hit rate', 'hit rate:')} {rates[key]}%"
        for key in ("StunHitRate", "StunHeadshotHitRate")
        if rates.get(key)
    )

    familiar = _all_target_accuracy(row, args)

    if familiar is not None:
        lines.append(f"Accuracy with troopers and everything else included: {familiar}%")

    if lines:
        print()

    for text in lines:
        print(f"  {text}")


def _range_section(stats: dict[tuple[str | None, str], int]) -> None:
    """Print damage split by the range it was dealt or taken at."""
    columns = {label: _take_group(stats, group) for group, label in DIST_COLUMNS}
    totals = {label: sum(values.values()) for label, values in columns.items()}

    if not any(totals.values()):
        return

    print("\n  Damage by range")
    print(f"  {'':<9}" + "".join(f"{label:>16}" for _, label in DIST_COLUMNS))

    for bucket, span in DIST_SPANS:
        values = [columns[label].get(bucket, 0) for _, label in DIST_COLUMNS]

        if not any(values):
            continue

        cells = []

        for (_, label), value in zip(DIST_COLUMNS, values, strict=True):
            share = round(100 * value / totals[label]) if totals[label] else 0
            cells.append(f"{value:,} ({share}%)" if value else "-")

        print(f"  {span:<9}" + "".join(f"{cell:>16}" for cell in cells))

    yours = _falloff_line(_take_group(stats, "Enemy Hero Falloff"))
    theirs = _falloff_line(_take_group(stats, "Enemy Hero Falloff - Incoming"))

    if yours:
        print(f"  Falloff on your hits: {yours}")

    if theirs:
        print(f"  Falloff on hits taken: {theirs}")


def _melee_taken(row: dict[str, Any], args: argparse.Namespace) -> tuple[int, str, int]:
    """Sum light and heavy melee damage this player took, with the top attacker."""
    attackers = queries.scan("players", args.parquet).select(
        "match_id",
        pl.col("account_id").alias("dealer_account_id"),
        pl.col("hero").alias("attacker"),
    )
    df = (
        queries.scan("damage", args.parquet)
        .filter(
            pl.col("match_id") == row["match_id"],
            pl.col("target_account_id") == row["account_id"],
            pl.col("stat") == "damage",
            pl.col("category") != "total",
            pl.col("source_class").str.contains("ability_melee_"),
        )
        .join(attackers, on=["match_id", "dealer_account_id"], how="left")
        .group_by("attacker")
        .agg(pl.col("damage").sum())
        .sort("damage", descending=True)
        .collect()
    )

    if df.is_empty():
        return (0, "", 0)

    top = df.row(0, named=True)

    return (int(df["damage"].sum()), top["attacker"] or "?", int(top["damage"]))


def _parry_item_buys(row: dict[str, Any], args: argparse.Namespace) -> list[tuple[str, int]]:
    """List the parry item purchases with their buy times."""
    df = (
        queries.scan("item_events", args.parquet)
        .filter(
            pl.col("match_id") == row["match_id"],
            pl.col("account_id") == row["account_id"],
            pl.col("item_id").is_in(PARRY_ITEMS),
        )
        .sort("game_time_s")
        .select("item", "game_time_s")
        .collect()
    )

    return df.rows()


def _parry_section(
    row: dict[str, Any], args: argparse.Namespace, stats: dict[tuple[str | None, str], int]
) -> None:
    """Print parries with the melee pressure and parry items for context."""
    success = stats.pop((None, "Parry Success"), 0)
    missed = stats.pop((None, "Parry Miss"), 0)
    total, attacker, top_damage = _melee_taken(row, args)
    buys = _parry_item_buys(row, args)

    if not (success or missed or total or buys):
        return

    print("\n  Parries")
    print(f"  Successful {success}, missed {missed}")

    if total:
        print(
            f"  Melee damage taken (light/heavy melee): {total:,}, "
            f"most from {attacker} ({top_damage:,})"
        )

    for item, game_time_s in buys:
        print(f"  {item} bought at {_game_time(game_time_s)}")


def _comeback_section(row: dict[str, Any], stats: dict[tuple[str | None, str], int]) -> None:
    """Print comeback souls and the average unspent balances."""
    lines = []

    for stat, label in COMEBACK_LABELS:
        value = stats.pop((None, stat), 0)

        if value:
            lines.append(f"  {label}: {value:,}")

    minutes = row["duration_s"] / 60
    gold_minutes = stats.pop((None, "Unspent Gold Minutes"), 0)
    ap_minutes = stats.pop((None, "Unspent AP Minutes"), 0)

    if gold_minutes:
        lines.append(f"  Souls held unspent on average: {round(gold_minutes / minutes):,}")

    if ap_minutes:
        lines.append(f"  Ability points held unspent on average: {ap_minutes / minutes:.1f}")

    if not lines:
        return

    print("\n  Souls")

    for line in lines:
        print(line)


def _uptime_tables(values: dict[str, int]) -> None:
    """Print a stacks/time/share table for each TimeAt counter family."""
    tables: dict[str, dict[int, int]] = {}

    for stat in list(values):
        m = UPTIME_RE.fullmatch(stat)

        if m:
            tables.setdefault(m["ability"], {})[int(m["stacks"])] = values.pop(stat)

    for ability, by_stacks in tables.items():
        total = sum(by_stacks.values())

        print(f"  {_uncamel(ability).title()} uptime")
        print(f"  {'Stacks':<8}{'Time':>8}{'Share':>7}")

        for stacks in sorted(by_stacks):
            seconds = by_stacks[stacks]
            share = round(100 * seconds / total) if total else 0
            print(f"  {stacks:<8}{_game_time(seconds):>8}{share:>6}%")


def _leftover_sections(stats: dict[tuple[str | None, str], int]) -> None:
    """Print whatever no curated section consumed, hero counters included."""
    groups: dict[str | None, dict[str, int]] = {}

    for (group, stat), value in stats.items():
        if value:
            groups.setdefault(group, {})[stat] = value

    bare = groups.pop(None, {})

    for group, values in groups.items():
        print(f"\n  {group}")
        _uptime_tables(values)

        for stat, value in values.items():
            print(f"  {_uncamel(stat).capitalize()}: {value:,}")

    if bare:
        print("\n  Other")

        for stat, value in bare.items():
            print(f"  {stat}: {value:,}")


def combat_report(row: dict[str, Any], args: argparse.Namespace) -> None:
    """Print the fight stats the game tracks but never shows for one player."""
    if not queries.table_exists("custom_stats", args.parquet):
        print("No custom_stats table yet, run `deadlock sync --full`")
        return

    df = (
        queries.custom_stats(
            matches=[row["match_id"]],
            accounts=[row["account_id"]],
            parquet_dir=args.parquet,
        )
        .select("group", "stat", "value")
        .collect()
    )

    if df.is_empty():
        print(f"No combat stats for {row['hero']} in match {row['match_id']}")
        return

    stats = {(r["group"], r["stat"]): r["value"] for r in df.iter_rows(named=True)}

    for key in list(stats):
        if key[1] in POWERUP_STATS:
            del stats[key]

    _aim_section(row, args, stats)
    _range_section(stats)
    _parry_section(row, args, stats)
    _comeback_section(row, stats)
    _leftover_sections(stats)


def _lobby_aim_table(row: dict[str, Any], args: argparse.Namespace) -> None:
    """Print every player in the match ranked by aim against heroes."""
    lobby = (
        queries.custom_stats(
            group="Enemy Hero Accuracy",
            matches=[row["match_id"]],
            parquet_dir=args.parquet,
        )
        .select("match_id", "account_id", "hero", "stat", "value")
        .collect()
        .pivot(on="stat", index=["match_id", "account_id", "hero"], values="value")
        .fill_null(0)
    )

    if lobby.is_empty():
        return

    teams = queries.scan("players", args.parquet).select("match_id", "account_id", "team")
    gun = (
        queries.scan("damage", args.parquet)
        .filter(
            pl.col("match_id") == row["match_id"],
            pl.col("stat") == "damage",
            pl.col("category") == "gun",
            pl.col("target_account_id").is_not_null(),
        )
        .group_by(pl.col("dealer_account_id").alias("account_id"))
        .agg(
            pl.col("damage")
            .filter(~pl.col("source_class").str.ends_with("_crit"))
            .sum()
            .alias("gun_damage"),
            pl.col("damage")
            .filter(pl.col("source_class").str.ends_with("_crit"))
            .sum()
            .alias("crit_damage"),
        )
    )

    df = (
        lobby.lazy()
        .join(teams, on=["match_id", "account_id"])
        .join(gun, on="account_id", how="left")
        .with_columns(
            hit_rate=(100 * pl.col("Hits") / pl.col("Shots").clip(1)),
            headshot_rate=(100 * pl.col("Headshots") / pl.col("Hits").clip(1)),
            side=pl.when(pl.col("team") == row["team"])
            .then(pl.lit("ally"))
            .otherwise(pl.lit("enemy")),
        )
        .sort("headshot_rate", descending=True)
        .collect()
    )

    rows = df.to_dicts()
    heroes_shown = [
        f"{r['hero'] or '?'} *" if r["account_id"] == row["account_id"] else r["hero"] or "?"
        for r in rows
    ]
    width = max(max(len(h) for h in heroes_shown), 4) + 2

    print("\n  Aim vs heroes")
    print(
        f"  {'Hero':<{width}} {'Side':<6} {'Shots':>7} {'Hit rate':>9} {'HS rate':>8}"
        f" {'Gun damage':>11} {'Headshot damage':>16}"
    )

    for hero_shown, r in zip(heroes_shown, rows, strict=True):
        gun_cell = f"{r['gun_damage']:,}" if r["gun_damage"] else "-"
        crit_cell = f"{r['crit_damage']:,}" if r["crit_damage"] else "-"

        print(
            f"  {hero_shown:<{width}} {r['side']:<6} {r['Shots']:>7,} {r['hit_rate']:>8.1f}%"
            f" {r['headshot_rate']:>7.1f}% {gun_cell:>11} {crit_cell:>16}"
        )

    print(
        "\n  Rates count heroes only, the postgame screen counts every target."
        "\n  Gun and headshot damage are the two bullet series from the damage graph."
    )


MOVEMENT_HEADER = (
    f"{'Meters':>8}{'/min':>7}{'Stationary':>12}{'Slide':>8}"
    f"{'In air':>8}{'Zipline':>9}{'Fighting':>10}{'Dashes':>8}{'Air dash':>10}"
)


def _movement_cells(r: dict[str, Any]) -> str:
    """Format the movement metric cells of one row, matching MOVEMENT_HEADER."""

    def pct(value: float | None) -> str:
        return f"{value:.1f}%" if value is not None else "-"

    meters = f"{r['distance'] / UNITS_PER_METER:,.0f}"
    pace = "-"

    if r["distance_min"] is not None:
        pace = f"{r['distance_min'] / UNITS_PER_METER:,.0f}"

    return (
        f"{meters:>8}{pace:>7}{pct(r['stationary_percent']):>12}"
        f"{pct(r['slide_percent']):>8}{pct(r['in_air_percent']):>8}"
        f"{pct(r['zipline_percent']):>9}{pct(r['combat_percent']):>10}"
        f"{r['dashes']:>8}{r['air_dashes']:>10}"
    )


def match_movement_report(row: dict[str, Any], args: argparse.Namespace) -> None:
    """Print movement summed for every player in the match, then one player per interval.

    - percents cover alive seconds, stationary and the pace cover moving seconds
    - intervals spent fully dead print "-" for every percent
    """
    try:
        intervals = queries.movement_intervals(
            row["match_id"], row["account_id"], args.interval * 60, args.parquet
        )
        total = queries.movement_intervals(
            row["match_id"], row["account_id"], max(row["duration_s"], 60), args.parquet
        )
    except ValueError as e:
        print(e)
        return

    lobby = (
        queries.movement_scoreboard(row["match_id"], args.parquet)
        .sort(pl.col("team") == row["team"], "distance", descending=[True, True])
        .collect()
        .to_dicts()
    )
    heroes_shown = [
        f"{r['hero'] or '?'} *" if r["account_id"] == row["account_id"] else r["hero"] or "?"
        for r in lobby
    ]
    width = max(max(len(h) for h in heroes_shown), 4) + 2

    print("\n  Movement")
    print(f"  {'Hero':<{width}} {'Side':<5}{MOVEMENT_HEADER}")

    for hero_shown, r in zip(heroes_shown, lobby, strict=True):
        side = "ally" if r["team"] == row["team"] else "enemy"
        print(f"  {hero_shown:<{width}} {side:<5}{_movement_cells(r)}")

    print(f"\n  {row['hero']} per interval")
    print(f"  {'Time':<9}{MOVEMENT_HEADER}")

    for r in intervals.iter_rows(named=True):
        print(f"  {_span(r):<9}{_movement_cells(r)}")

    print(f"  {'Total':<9}{_movement_cells(total.row(0, named=True))}")


def souls_report(row: dict[str, Any], args: argparse.Namespace) -> None:
    """Print the souls by source per interval for one player, then the farm grouping.

    - source rows use the in game souls-screen labels, ordered by match total
    - the group block splits souls into lane, roaming, combat, objectives,
      catch-up, and other, the way you earned them
    """
    if not queries.table_exists("soul_sources", args.parquet):
        print("No soul_sources table yet, run `deadlock sync`")
        return

    try:
        df = queries.soul_intervals(
            row["match_id"], row["account_id"], args.interval * 60, args.parquet
        )
    except ValueError as e:
        print(e)
        return

    df = df.with_columns(
        pl.col("source_name").replace(SOUL_LABELS).alias("label"),
        pl.col("source_name").replace(SOUL_GROUPS).alias("group"),
    )

    spans = df.select("start_s", "end_s").unique().sort("start_s")
    width = max(max(len(s) for s in df["label"]), 16) + 2
    header = "".join(f"{_span(r):>9}" for r in spans.iter_rows(named=True))
    total = int(df["souls"].sum())

    print(f"Souls by source, {args.interval}-minute intervals")
    print(f"\n  {'Source':<{width}}{header}{'Total':>9}{'%':>7}")

    for (label,), g in df.group_by(["label"], maintain_order=True):
        cells = "".join(f"{v:>9,}" for v in g.sort("start_s")["souls"])
        source_total = int(g.item(0, "total"))
        percent = f"{100 * source_total / total:.0f}%" if total else "-"

        print(f"  {label:<{width}}{cells}{source_total:>9,}{percent:>7}")

    sums = df.group_by("start_s").agg(pl.col("souls").sum()).sort("start_s")
    cells = "".join(f"{v:>9,}" for v in sums["souls"])

    print(f"  {'Total':<{width}}{cells}{total:>9,}")
    print()

    order = pl.DataFrame({"group": SOUL_GROUP_ORDER, "group_n": range(len(SOUL_GROUP_ORDER))})
    grouped = (
        df.group_by("group", "start_s")
        .agg(pl.col("souls").sum())
        .with_columns(pl.col("souls").sum().over("group").alias("total"))
        .join(order, on="group")
        .sort(["group_n", "start_s"])
    )

    for (group,), g in grouped.group_by(["group"], maintain_order=True):
        cells = "".join(f"{v:>9,}" for v in g.sort("start_s")["souls"])
        group_total = int(g.item(0, "total"))
        percent = f"{100 * group_total / total:.0f}%" if total else "-"

        print(f"  {group:<{width}}{cells}{group_total:>9,}{percent:>7}")

    print(
        f"\n  Total is gross souls earned by source, the in game souls breakdown. "
        f"Net worth ({row['net_worth']:,}) adds starting souls and subtracts souls lost to deaths."
    )


def damage_source_table(row: dict[str, Any], args: argparse.Namespace) -> None:
    """Print the per source intervals for one player, damage or healing plus prevented healing."""
    if not queries.table_exists("damage_sources", args.parquet):
        print("No damage_sources table yet, run `deadlock sync`")
        return

    if args.healing:
        shown = _source_intervals(row, args, "healing", "Healing by source")
        _source_intervals(
            row, args, "heal_prevented", "Healing prevented", groups=False, required=not shown
        )
    else:
        width = _source_intervals(row, args, "damage", "Damage to heroes by source")
        _enemy_damage_table(row, args, dealt=True, min_width=width)


def _source_intervals(
    row: dict[str, Any],
    args: argparse.Namespace,
    stat: str,
    title: str,
    *,
    groups: bool = True,
    required: bool = True,
) -> int | None:
    """Print the per source interval table for one stat.

    - groups adds the Gun/Abilities/Items block under the total
    - a stat with no rows prints the error only when required
    - returns the name column width so a table under it can line up
    """
    try:
        df = queries.damage_intervals(
            row["match_id"], row["account_id"], args.interval * 60, args.parquet, stat
        )
    except ValueError as e:
        if required:
            print(e)

        return None

    spans = df.select("start_s", "end_s").unique().sort("start_s")
    width = max(max(len(s) for s in df["source_name"]), 14) + 2
    header = "".join(f"{_span(r):>9}" for r in spans.iter_rows(named=True))
    total = int(df["damage"].sum())

    print(f"{title}, {args.interval}-minute intervals")
    print(f"\n  {'Source':<{width}}{header}{'Total':>9}{'%':>7}")

    for (source,), g in df.group_by(["source_name"], maintain_order=True):
        cells = "".join(f"{v:>9,}" for v in g.sort("start_s")["damage"])
        source_total = int(g.item(0, "total"))
        percent = f"{100 * source_total / total:.0f}%" if total else "-"

        print(f"  {source:<{width}}{cells}{source_total:>9,}{percent:>7}")

    sums = df.group_by("start_s").agg(pl.col("damage").sum()).sort("start_s")
    cells = "".join(f"{v:>9,}" for v in sums["damage"])

    print(f"  {'Total':<{width}}{cells}{total:>9,}")
    print()

    if not groups:
        return width

    grouped = (
        df.with_columns(pl.col("delivery").replace(DELIVERY_LABELS).alias("group"))
        .group_by("group", "start_s")
        .agg(pl.col("damage").sum())
        .with_columns(pl.col("damage").sum().over("group").alias("total"))
        .sort(["total", "group", "start_s"], descending=[True, False, False])
    )

    for (group,), g in grouped.group_by(["group"], maintain_order=True):
        cells = "".join(f"{v:>9,}" for v in g.sort("start_s")["damage"])
        group_total = int(g.item(0, "total"))
        percent = f"{100 * group_total / total:.0f}%" if total else "-"

        print(f"  {group:<{width}}{cells}{group_total:>9,}{percent:>7}")

    print()

    return True


def winrate_report(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """W/L table per day, week, or month with net wins and a running total."""
    tz = config_timezone(config)
    try:
        df = queries.daily_record(
            args.parquet,
            accounts=args.account,
            tz=tz,
            days=args.days,
            since=args.since,
            hero=args.hero,
            by=args.by,
        )
    except ValueError as e:
        print(e)
        return

    if df.is_empty():
        print("No games found for the configured accounts")
        _unscored_line(args, tz)

        if args.hero is not None:
            _hero_baseline_line(args.hero, args.min_rating, args.since)

        return

    print(f"Dates below are grouped by {tz} {args.by}.\n")
    print(
        f"  {args.by.capitalize():<12}{'Games':>7}{'W':>5}{'L':>5}"
        f"{'Win rate':>11}{'Lobby':>14}{'MVP':>6}{'Key':>6}{'Abandons':>10}"
        f"{'Net wins':>11}{'Cumulative net':>17}"
    )

    for r in df.iter_rows(named=True):
        day = f"{r['day']:%Y-%m}" if args.by == "month" else r["day"]
        left = str(r["abandons"]) if r["abandons"] else ""
        lobby = r["lobby"] or ""

        print(
            f"  {day!s:<12}{r['games']:>7}{r['wins']:>5}{r['losses']:>5}"
            f"{r['win_rate']:>10.1f}%{lobby:>14}{r['mvps']:>6}{r['key_players']:>6}{left:>10}"
            f"{r['net']:>+11}{r['cum_net']:>+17}"
        )

    games = int(df.get_column("games").sum())
    wins = int(df.get_column("wins").sum())
    rate = wins / games * 100
    net = df.item(-1, "cum_net")
    mvps = int(df.get_column("mvps").sum())
    keys = int(df.get_column("key_players").sum())
    rated = int(df.get_column("rated_games").sum())
    lobbies = ""

    if rated:
        subrank = round(float(df.get_column("subrank_sum").sum()) / rated)
        average = skill_rating.label(skill_rating.badge_from_subrank(subrank))
        lobbies = f", {average} lobbies"

    print(
        f"\nOverall: {games} games, {wins}-{games - wins}, {rate:.1f}% win rate, "
        f"{net:+} net wins, {mvps} MVP, {keys} Key Player{lobbies}."
    )

    abandons = queries.abandon_record(
        args.parquet,
        accounts=args.account,
        tz=tz,
        days=args.days,
        since=args.since,
        hero=args.hero,
    )

    if not abandons.is_empty():
        _abandon_lines(abandons, games, wins)

    _unscored_line(args, tz)

    if args.hero is not None:
        _hero_baseline_line(args.hero, args.min_rating, args.since)


def _abandon_lines(abandons: pl.DataFrame, games: int, wins: int) -> None:
    """Print the abandon breakdown under the overall line.

    Abandoned games stay in the table above since they are still scored as
    wins and losses, these lines just separate them out.
    """
    sides = []

    for col, label in (("you", "you left"), ("ally", "an ally left"), ("enemy", "an enemy left")):
        part = abandons.filter(pl.col(col))

        if part.is_empty():
            continue

        won = int(part.get_column("won").cast(pl.Int32).sum())
        sides.append(f"{label} {len(part)} ({won}-{len(part) - won})")

    total = len(abandons)
    plural = "s" if total != 1 else ""
    print(f"\nAbandons: {total} game{plural} — {', '.join(sides)}.")

    returned = int(abandons.get_column("returned").cast(pl.Int32).sum())

    if returned:
        plural = "s" if returned != 1 else ""
        print(f"  {returned} leaver{plural} reconnected and finished.")

    clean_games = games - total
    clean_wins = wins - int(abandons.get_column("won").cast(pl.Int32).sum())

    if clean_games > 0:
        clean_rate = clean_wins / clean_games * 100
        print(
            f"  Without them: {clean_games} games, "
            f"{clean_wins}-{clean_games - clean_wins}, {clean_rate:.1f}% win rate."
        )


def _unscored_line(args: argparse.Namespace, tz: str) -> None:
    """Print the unscored games the table left out, nothing when there are none."""
    unscored = queries.unscored_record(
        args.parquet,
        accounts=args.account,
        tz=tz,
        days=args.days,
        since=args.since,
        hero=args.hero,
    )

    if unscored.is_empty():
        return

    total = len(unscored)
    won = int(unscored.get_column("won").cast(pl.Int32).sum())
    plural = "s" if total != 1 else ""

    print(
        f"\nNot scored: {total} game{plural} left out of the table (safe to leave), "
        f"{won}-{total - won} in match history."
    )


def _hero_baseline_line(hero: str, rating: str, since: str | None) -> None:
    """Print the public win rate for a hero under the daily table.

    Prints nothing when the API is unreachable, so the command still works offline.
    """
    hero_id = heroes.hero_id_by_name(hero)

    if hero_id is None:
        return

    try:
        badge = meta.min_badge(rating)
        rows = meta.get_hero_stats(badge=badge, since=since)
    except ValueError as e:
        print(f"\n{e}")
        return
    except OSError:
        return

    baseline = meta.hero_baseline(rows, hero_id)

    if baseline is None:
        return

    scope = "all ratings" if badge is None else f"{rating}+ lobbies"
    window = f" since {since}" if since else ""

    print(
        f"{hero} in {scope}{window}: {baseline['win_rate']:.1f}% win rate "
        f"over {baseline['matches']:,} games (deadlock-api.com)"
    )


DEATH_PHASES = [(0, "0-10 min"), (600, "10-20 min"), (1200, "20-30 min"), (1800, "30+ min")]


def _mean(df: pl.DataFrame, column: str, scale: float = 1.0) -> float:
    """Take the mean of a column as a float for printing.

    - scale 100 turns a boolean mean into a percent
    """
    value = df.select(pl.col(column).mean().mul(scale)).item()

    return float(value or 0)


def _death_frame(args: argparse.Namespace, tz: str, *, has_context: bool) -> pl.DataFrame:
    """Load deaths for the player with the command line filters applied.

    - joins nearby ally and enemy context when the movement table is exported
    """
    if has_context:
        lf = queries.death_context(args.radius, args.parquet, accounts=args.account, tz=tz)
    else:
        lf = queries.my_deaths(args.parquet, accounts=args.account, tz=tz)

    if args.hero is not None:
        lf = lf.filter(pl.col("hero") == args.hero)

    if args.since is not None:
        lf = lf.filter(pl.col("day") >= dt.date.fromisoformat(args.since))

    df = lf.collect()

    if args.days is not None and not df.is_empty():
        keep = df["day"].unique().sort().tail(args.days).implode()
        df = df.filter(pl.col("day").is_in(keep))

    return df


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
        print("No deaths found for the configured accounts")
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
                f"{_mean(p, 'solo', 100):>6.0f}%{_mean(p, 'outnumbered', 100):>7.0f}%"
                f"{_mean(p, 'enemies'):>9.1f}"
            )
        print(line)

    for won, tag in [(True, "wins"), (False, "losses")]:
        w = df.filter(pl.col("won") == won)

        if w.is_empty():
            continue

        line = f"\n  {tag}: {len(w)} deaths"
        if has_context:
            line += (
                f", {_mean(w, 'solo', 100):.0f}% solo, "
                f"{_mean(w, 'outnumbered', 100):.0f}% outnumbered"
            )
        print(line, end="")
    print()

    killers = (
        df.filter(pl.col("killer_account_id").is_not_null())
        .join(
            queries.scan("players", args.parquet)
            .select(
                "match_id",
                killer_account_id=pl.col("account_id"),
                killer=pl.col("hero"),
            )
            .collect(),
            on=["match_id", "killer_account_id"],
        )
        .group_by("killer")
        .len()
        .sort("len", descending=True)
        .head(5)
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
    ("meters /min", "distance_min"),
    ("stationary %", "stationary_percent"),
    ("slide %", "slide_percent"),
    ("in air %", "in_air_percent"),
    ("zipline %", "zipline_percent"),
    ("fighting players %", "combat_percent"),
    ("ground dashes /min", "dashes_min"),
    ("air dashes /min", "air_dashes_min"),
]


def movement_report(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Compare movement metrics between the player and select other players."""
    if not queries.table_exists("movement_intervals", args.parquet):
        print("No movement_intervals table yet: run `deadlock sync`")
        return

    hero_id = heroes.hero_id_by_name(args.hero)
    if hero_id is None:
        print(f"Unknown hero: {args.hero}")
        return

    hero = heroes.hero_name(hero_id)
    metric_columns = [col for _, col in MOVEMENT_METRICS]
    mine = (
        queries.my_games(args.parquet, accounts=args.account)
        .filter(pl.col("hero_id") == hero_id)
        .select("match_id", "account_id")
    )
    you = (
        queries.movement_profile(args.parquet)
        .join(mine, on=["match_id", "account_id"])
        .select(metric_columns)
        .collect()
    )

    if you.is_empty():
        print(f"No {hero} games in your tables")
        return

    labels = {a: name for name, a in config_players(hero, config).items()}
    top = None
    tracked = None

    if labels and queries.table_exists("movement_intervals", players.PARQUET_DIR):
        tracked = players.pool_games(hero, config_path=config).collect()
        top = (
            queries.movement_profile(players.PARQUET_DIR)
            .join(tracked.lazy().select("match_id", "account_id"), on=["match_id", "account_id"])
            .select("match_id", "account_id", *metric_columns)
            .collect()
        )

        if top.is_empty():
            top = None

    title = f"{hero} movement: you ({len(you)} games)"
    if top is not None and tracked is not None:
        newest = tracked.get_column("downloaded_at").max()
        title += (
            f" vs {tracked.get_column('account_id').n_unique()} tracked players "
            f"({len(top)} games, last download {newest:%Y-%m-%d})"
        )
    print(title + "\n")

    if args.by == "player":
        if top is None or tracked is None:
            print(no_pool_hint(hero, tracked_in_config=bool(labels)))
            return

        _movement_by_player(you, top, tracked, labels)
        return

    header = f"  {'Metric':<24}{'You':>9}"
    if top is not None:
        header += f"{'Tracked':>9}{'Gap':>9}"
    print(header)

    for label, col in MOVEMENT_METRICS:
        scale = UNITS_PER_METER if col == "distance_min" else 1.0
        yours = _mean(you, col) / scale
        line = f"  {label:<24}{yours:>9,.1f}"

        if top is not None:
            theirs = _mean(top, col) / scale
            line += f"{theirs:>9,.1f}{theirs - yours:>+9,.1f}"

        print(line)

    if top is None:
        print("\n" + no_pool_hint(hero, tracked_in_config=bool(labels)))


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


def _movement_by_player(
    you: pl.DataFrame, top: pl.DataFrame, tracked: pl.DataFrame, labels: dict[int, str]
) -> None:
    """Print one movement row per tracked player and a you row for contrast.

    - each row averages the per game metrics of that player
    - names are the labels from [players.<hero>] in config.toml
    - Rank is the best hero ladder rank at download time, "-" when they were
      never on the ladder
    """
    columns = [col for _, col in MOVEMENT_METRICS]
    rows = (
        top.join(
            tracked.select("match_id", "account_id", "rank"),
            on=["match_id", "account_id"],
        )
        .group_by("account_id")
        .agg(
            pl.len().alias("games"),
            pl.col("rank").min().alias("rank"),
            pl.col(columns).mean(),
        )
        .sort("distance_min", descending=True)
        .to_dicts()
    )

    print(
        f"  {_fit_name('Player', NAME_WIDTH)}{'Account':>11}{'Games':>7}{'Rank':>8}"
        f"{'m /min':>9}{'Stationary':>12}{'Slide':>8}{'In air':>8}{'Zipline':>9}"
        f"{'Fighting':>10}{'Dash/min':>10}{'Air dash':>10}"
    )

    def line(label: str, account: str, games: int, rank: str, r: dict[str, Any]) -> str:
        return (
            f"  {_fit_name(label, NAME_WIDTH)}{account:>11}{games:>7,}{rank:>8}"
            f"{r['distance_min'] / UNITS_PER_METER:>9,.1f}"
            f"{r['stationary_percent']:>11,.1f}%{r['slide_percent']:>7,.1f}%"
            f"{r['in_air_percent']:>7,.1f}%{r['zipline_percent']:>8,.1f}%"
            f"{r['combat_percent']:>9,.1f}%{r['dashes_min']:>10,.1f}{r['air_dashes_min']:>10,.1f}"
        )

    yours = {col: _mean(you, col) for col in columns}
    print(line("you", "-", len(you), "-", yours))

    for r in rows:
        name = labels.get(r["account_id"], str(r["account_id"]))
        rank = "-" if r["rank"] is None else str(r["rank"])

        print(line(name, str(r["account_id"]), r["games"], rank, r))
