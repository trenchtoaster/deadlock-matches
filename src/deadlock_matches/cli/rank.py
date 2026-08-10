"""Shows every Ranked game with the points it paid, the current rating, and the season record."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

import polars as pl

from deadlock_matches import api, extract, queries
from deadlock_matches.config import account_labels, config_timezone

if TYPE_CHECKING:
    import argparse
    from collections.abc import Mapping, Sequence
    from pathlib import Path


SUBRANK_POINTS = 1_000

TIER_POINTS = 7_000

ETERNUS_TIER = 11

SEASON_PATH = "v1/assets/ranked-seasons"

SEASON_FALLBACK = {
    "name": "Beta Season 1",
    "min_wins": 60,
    "min_hero_wins": 15,
    "min_hero_unlocks": 3,
    "start_timestamp": 1_785_430_800,
}

ELIGIBLE_MODES = (extract.MATCH_MODE_STANDARD, extract.MATCH_MODE_RANKED)

ARCHIVE_NOTE = "Counts come from the local archive, so games missing from it are not counted."


def season_rules() -> dict[str, Any]:
    """Read the season rules from the API or fall back to the numbers shipped here."""
    rules = dict(SEASON_FALLBACK)

    try:
        seasons = api.get_json(SEASON_PATH, max_age=api.DAY)

    except OSError:
        return rules

    if not isinstance(seasons, list):
        return rules

    tables = [s for s in seasons if isinstance(s, dict)]
    normal = [s for s in tables if s.get("ranked_type") == "normal"]
    known = normal or tables

    if not known:
        return rules

    season = known[-1]

    for key in ("min_wins", "min_hero_wins", "min_hero_unlocks"):
        value = season.get(key)

        if isinstance(value, int) and value > 0:
            rules[key] = value

    name = season.get("name")

    if isinstance(name, str) and name:
        rules["name"] = name

    intervals = season.get("intervals")

    if isinstance(intervals, list):
        starts = [
            i["start_timestamp"]
            for i in intervals
            if isinstance(i, dict) and isinstance(i.get("start_timestamp"), int)
        ]

        if starts:
            rules["start_timestamp"] = min(starts)

    return rules


def _mode_matches(parquet_dir: str | Path, modes: Sequence[int]) -> pl.LazyFrame:
    """Take the matches in these match modes with the scored flag under its view name."""
    return (
        queries.scan("matches", parquet_dir)
        .filter(
            pl.col("match_mode").is_in(modes) & (pl.col("game_mode") == extract.GAME_MODE_NORMAL)
        )
        .select("match_id", pl.col("not_scored").alias("matches.not_scored"))
    )


def _ranked_games(parquet_dir: str | Path, accounts: Sequence[int], tz: str) -> pl.DataFrame:
    """Take one row per Ranked game these accounts played and sort them oldest first.

    - applied is how far the points really moved, which can stop at the
      subrank floor instead of matching the change the matchmaker assigned
    - the rating is the badge the game started on
    - no final badge is recorded
    """
    rating = (
        pl.when(pl.col("player_rank_initial_display_rank") == 0)
        .then(pl.lit("Placing"))
        .otherwise(queries.skill_rating_asof("player_rank_initial_display_rank"))
    )

    return (
        queries.player_rows(parquet_dir)
        .filter(pl.col("account_id").is_in(accounts))
        .join(_mode_matches(parquet_dir, (extract.MATCH_MODE_RANKED,)), on="match_id")
        .with_columns(pl.col("start_time").dt.convert_time_zone(tz).alias("start_local"))
        .with_columns(
            pl.col("start_local").dt.date().alias("day"),
            queries.SCORED.alias("scored"),
            (
                pl.col("player_rank_final_flat_progress")
                - pl.col("player_rank_initial_flat_progress")
            ).alias("applied"),
            rating.alias("rating"),
        )
        .sort("start_local", "match_id")
        .collect()
    )


def _subrank_span(badge: int) -> tuple[int, int]:
    """Take the point floor and width of the subrank a badge sits in.

    - subranks I to V are 1,000 points wide and VI is 2,000, so every tier
      spans 7,000 points
    - Eternus subranks come from percentiles, so the span means nothing there
    """
    tier, level = divmod(badge, 10)
    floor = (tier - 1) * TIER_POINTS + (level - 1) * SUBRANK_POINTS
    width = 2 * SUBRANK_POINTS if level == 6 else SUBRANK_POINTS

    return floor, width


def _flag_gaps(season: pl.DataFrame) -> pl.DataFrame:
    """Mark each game whose starting points disagree with the ending points of the game before.

    - a mismatch means the archive is missing the games between the two
    - placement games stay out of the check because the placement bank
      resets every game
    """
    placed = pl.col("player_rank_initial_display_rank") > 0
    prev_placed = placed.shift(1).over("account_id")
    prev_final = pl.col("player_rank_final_flat_progress").shift(1).over("account_id")
    gap = placed & prev_placed & (pl.col("player_rank_initial_flat_progress") != prev_final)

    return season.with_columns(gap.fill_null(value=False).alias("gap_before"))


def _points(g: Mapping[str, Any]) -> str:
    """Show the points a game started and ended on."""
    before = g["player_rank_initial_flat_progress"]
    after = g["player_rank_final_flat_progress"]

    if before is None or after is None:
        return "-"

    return f"{before:,} -> {after:,}"


def _change(g: Mapping[str, Any]) -> str:
    """Show the points a game applied, with the assigned change when the two differ."""
    applied = g["applied"]

    if applied is None:
        return "-"

    assigned = g["player_rank_desired_progress_change"]

    if assigned is None or assigned == applied:
        return f"{applied:+,}"

    return f"{applied:+,} ({assigned:+,})"


def _games(n: int) -> str:
    """Count games with the plural attached."""
    return f"{n} game" if n == 1 else f"{n} games"


def _note(g: Mapping[str, Any]) -> str:
    """Mark the placements left, the protection a loss spent, and the games nothing scored."""
    notes = []
    placements = g["player_rank_initial_calibration_games"]

    if placements:
        left = "placement" if placements == 1 else "placements"
        notes.append(f"{placements} {left} left")

    if g["player_rank_consumed_demotion_protection"]:
        notes.append("demotion protection used")

    if not g["scored"]:
        notes.append("not scored")

    if g["gap_before"]:
        notes.append("archive gap before this")

    return ", ".join(notes)


def _game_table(games: pl.DataFrame, names: Mapping[int, str]) -> None:
    """Print one line per Ranked game with the points it paid and put the newest last."""
    print(
        f"  {'Day':<10}  {'Time':<5}  {'Account':<10} {'Hero':<14} {'Result':<7} "
        f"{'Rating':<13} {'Points':>17} {'Change':>12} {'Streak':>7}  Note"
    )

    last_day = ""

    for g in games.iter_rows(named=True):
        day = g["start_local"].strftime("%Y-%m-%d")
        day_cell = "" if day == last_day else day
        last_day = day
        account = names.get(g["account_id"], str(g["account_id"]))
        time = g["start_local"].strftime("%H:%M")
        result = "win" if g["won"] else "loss"
        streak = g["player_rank_initial_win_streak"] or 0

        print(
            f"  {day_cell:<10}  {time:<5}  {account:<10} {g['hero']:<14} {result:<7} "
            f"{g['rating'] or '-':<13} {_points(g):>17} {_change(g):>12} {streak:>7}  "
            f"{_note(g)}".rstrip()
        )


def _footer_lines(window: pl.DataFrame, whole: pl.DataFrame) -> list[str]:
    """Build the rating, season record, and archive gap lines for one account.

    - the net counts the placed games only
    - a placement bank resets every game and never reaches the placed rating
    - an account still placing shows no point total
    - Eternus shows no subrank progress because its subranks come from
      percentiles instead of points
    - the gap line counts the whole season and not just the window shown
    """
    newest = whole.sort("start_local", "match_id").row(-1, named=True)
    rating = newest["rating"] or "-"
    points = newest["player_rank_final_flat_progress"]
    scored = whole.filter(pl.col("scored"))
    wins = int(scored.get_column("won").sum())
    placed = window.filter(pl.col("player_rank_initial_display_rank") > 0)
    net = int(placed.get_column("applied").fill_null(0).sum())

    badge = newest["player_rank_initial_display_rank"]

    if points is None or not badge:
        standing = f"Rating: {rating}."

    elif badge // 10 == ETERNUS_TIER:
        standing = f"Rating: {rating} at {points:,} points."

    else:
        floor, width = _subrank_span(badge)
        standing = (
            f"Rating: {rating} at {points:,} points. "
            f"{points - floor:,} of {width:,} into the subrank."
        )

    record = f"Season record: {wins}-{len(scored) - wins}."

    if len(placed) == len(window):
        record += f" Net over the {_games(len(window))} above is {net:+,} points."

    elif not placed.is_empty():
        record += f" Net over the {_games(len(placed))} since placing is {net:+,} points."

    lines = [standing, record]
    gaps = int(whole.get_column("gap_before").sum())

    if gaps:
        lines.append(
            f"Archive gaps: {_games(gaps)} started on points the stored game before "
            f"does not explain. Run deadlock sync --source api to backfill."
        )

    return lines


def _footers(games: pl.DataFrame, season: pl.DataFrame, names: Mapping[int, str]) -> None:
    """Print where every account with Ranked games stands and put the newest last."""
    accounts = (
        games.group_by("account_id")
        .agg(pl.col("start_local").max().alias("last"))
        .sort("last")
        .get_column("account_id")
        .to_list()
    )

    for account_id in accounts:
        window = games.filter(pl.col("account_id") == account_id)
        whole = season.filter(pl.col("account_id") == account_id)
        lines = _footer_lines(window, whole)

        print()

        if len(accounts) > 1:
            print(names.get(account_id, str(account_id)))
            print("\n".join(f"  {line}" for line in lines))

        else:
            print("\n".join(lines))


def _hero_wins(parquet_dir: str | Path, account_id: int) -> pl.DataFrame:
    """Count scored wins per hero over the Standard and Ranked games the tables hold."""
    return (
        queries.player_rows(parquet_dir)
        .filter(pl.col("account_id") == account_id)
        .join(_mode_matches(parquet_dir, ELIGIBLE_MODES), on="match_id")
        .filter(pl.col("won") & queries.SCORED)
        .group_by("hero")
        .agg(pl.len().alias("wins"))
        .sort(["wins", "hero"], descending=[True, False])
        .collect()
    )


def _qualification(
    parquet_dir: str | Path, account_id: int, bar: int
) -> tuple[pl.DataFrame, int, int]:
    """Count the total wins of one account and the heroes past the qualification bar."""
    wins = _hero_wins(parquet_dir, account_id)
    total = int(wins.get_column("wins").sum())
    qualified = int((wins.get_column("wins") >= bar).sum())

    return wins, total, qualified


def _eligibility(
    parquet_dir: str | Path, account_id: int, label: str, rules: Mapping[str, Any]
) -> None:
    """Print how far one account sits from unlocking Ranked the way the game panel counts it."""
    bar = rules["min_hero_wins"]
    wins, total, qualified = _qualification(parquet_dir, account_id, bar)
    heroes = f"Heroes at {bar} wins"

    print(f"No Ranked games stored for {label}.\n")
    print(f"Ranked eligibility ({rules['name']})")
    print(f"  {'Wins':<22}{total:>4} of {rules['min_wins']}")
    print(f"  {heroes:<22}{qualified:>4} of {rules['min_hero_unlocks']}")

    if wins.is_empty():
        print("\n  No wins stored for this account yet.")
        return

    print(f"\n  {'Hero':<16}{'Wins':>6}")

    for row in wins.iter_rows(named=True):
        mark = "  qualified" if row["wins"] >= bar else ""
        print(f"  {row['hero']:<16}{row['wins']:>6}{mark}")


def _eligibility_summary(
    parquet_dir: str | Path,
    account_ids: Sequence[int],
    names: Mapping[int, str],
    rules: Mapping[str, Any],
) -> None:
    """Print one eligibility line for each account that has not unlocked Ranked."""
    bar = rules["min_hero_wins"]
    heroes = f"Heroes at {bar} wins"

    print(f"Ranked eligibility ({rules['name']})")
    print(f"  {'Account':<12}{'Wins':>12}  {heroes}")

    for account_id in account_ids:
        _, total, qualified = _qualification(parquet_dir, account_id, bar)
        wins_cell = f"{total} of {rules['min_wins']}"

        print(
            f"  {names.get(account_id, str(account_id)):<12}{wins_cell:>12}  "
            f"{qualified} of {rules['min_hero_unlocks']}"
        )


def rank_report(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Print the Ranked games of the season, the rating, and the season record."""
    tz = config_timezone(config)
    accounts = list(args.account or [])

    if not queries.table_exists("players", args.parquet):
        print("No match tables yet, run deadlock sync first")
        return

    rules = season_rules()
    season = _ranked_games(args.parquet, accounts, tz)
    start = rules.get("start_timestamp")

    if isinstance(start, int):
        season = season.filter(pl.col("start_time") >= dt.datetime.fromtimestamp(start, dt.UTC))

    season = _flag_gaps(season)
    games = season

    if args.since is not None:
        games = games.filter(pl.col("day") >= dt.date.fromisoformat(args.since))

    if args.days is not None:
        games = games.filter(pl.col("day").rank("dense", descending=True) <= args.days)

    names = account_labels(config)
    printed = False

    if not season.is_empty():
        printed = True

        if games.is_empty():
            print("No Ranked games in that window")

        else:
            _game_table(games, names)
            _footers(games, season, names)

    played = set(season.get_column("account_id").to_list())
    missing = [a for a in accounts if a not in played]

    if not missing:
        return

    if printed:
        print()

    if len(missing) == 1:
        account_id = missing[0]
        _eligibility(args.parquet, account_id, names.get(account_id, str(account_id)), rules)

    else:
        _eligibility_summary(args.parquet, missing, names, rules)

    print(f"\n{ARCHIVE_NOTE}")
