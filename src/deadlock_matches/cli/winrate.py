"""Wins and losses grouped by day, week, month, game mode, or account."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl

from deadlock_matches import extract, meta, queries
from deadlock_matches.assets import heroes, skill_rating
from deadlock_matches.cli import render
from deadlock_matches.config import (
    account_labels,
    config_account_names,
    config_timezone,
    format_accounts,
)

if TYPE_CHECKING:
    import argparse


WIN_RATE = queries.view_measure(queries.record_games, "win_rate").display_format

NET_POINTS = queries.view_measure(queries.record_games, "net_points").display_format

NET_POINTS_WIDTH = 12

POINT_PART_WIDTH = 9

RANKED_LABEL = "Ranked"


def _net_points_cell(points: int | None) -> str:
    """Print a Rank Point change the way record_games declares it."""
    return NET_POINTS.render(points, render.BLANK, sign=True).rjust(NET_POINTS_WIDTH)


def _point_part_cell(points: int | None) -> str:
    """Print one share of a Rank Point change in the narrower split columns."""
    return NET_POINTS.render(points, render.BLANK, sign=True).rjust(POINT_PART_WIDTH)


def win_rate(wins: int, games: int) -> str:
    """Print a win rate the way record_games declares it."""
    return WIN_RATE.render(wins / games if games else None, render.BLANK)


def winrate_report(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Print W/L by mode or over time with net wins and the Rank Points split."""
    tz = config_timezone(config)

    if args.by == "mode":
        _winrate_mode_report(args, tz)
        return

    if args.by == "account":
        _winrate_account_report(args, tz, config)
        return

    try:
        games = queries.view_frame(
            queries.record_games(
                accounts=args.account,
                tz=tz,
                days=args.days,
                since=args.since,
                hero=args.hero,
            ),
            parquet_dir=args.parquet,
        ).collect()
        df = queries.daily_record(args.parquet, by=args.by, games=games)
    except ValueError as e:
        print(e)
        return

    if df.is_empty():
        print(no_games_line(args, config))
        _unscored_line(games)

        if args.hero is not None and _default_mode(args):
            _hero_baseline_line(args.hero, args.min_rating, args.since)

        return

    ranked = _has_ranked_games(games)
    points_heading = (
        f"{'Net points':>{NET_POINTS_WIDTH}}{'Streak':>{POINT_PART_WIDTH}}"
        f"{'Shields':>{POINT_PART_WIDTH}}"
        if ranked
        else ""
    )

    season = queries.selected_season()

    if season is not None and _default_mode(args):
        print(f"Ranked {season.name}. --season picks another, like --season 1 or --season all.")

    print(f"Dates below are grouped by {tz} {args.by}.\n")
    print(
        f"  {args.by.capitalize():<12}{'Games':>7}{'W':>5}{'L':>5}"
        f"{'Win rate':>11}{'Lobby':>14}{'MVP':>6}{'Key':>6}{'Abandons':>10}"
        f"{'Net wins':>11}{points_heading}"
    )

    for r in df.iter_rows(named=True):
        day = f"{r['day']:%Y-%m}" if args.by == "month" else r["day"]
        left = str(r["abandons"]) if r["abandons"] else ""
        lobby = r["lobby"] or ""
        points = (
            f"{_net_points_cell(r['net_points'])}{_point_part_cell(r['streak_points'])}"
            f"{_point_part_cell(r['shield_points'])}"
            if ranked
            else ""
        )

        print(
            f"  {day!s:<12}{r['games']:>7}{r['wins']:>5}{r['losses']:>5}"
            f"{WIN_RATE.render(r['win_rate'], render.BLANK):>11}{lobby:>14}"
            f"{r['mvps']:>6}{r['key_players']:>6}{left:>10}"
            f"{r['net']:>+11}{points}"
        )

    overall = queries.summarize(
        queries.record_games,
        measures=(
            "scored_games",
            "wins",
            "net",
            "win_rate",
            "mvps",
            "key_players",
            "subrank_sum",
            "rated_games",
            "last_rated_at",
            "net_points",
            "result_points",
            "streak_points",
            "shield_points",
        ),
        lf=games.lazy(),
    ).collect()
    total_games = int(overall.item(0, "scored_games"))
    wins = int(overall.item(0, "wins"))
    rate = WIN_RATE.render(overall.item(0, "win_rate"), render.BLANK)
    net = int(overall.item(0, "net"))
    mvps = int(overall.item(0, "mvps"))
    keys = int(overall.item(0, "key_players"))
    rated = int(overall.item(0, "rated_games"))
    lobbies = ""

    if rated:
        subrank = round(float(overall.item(0, "subrank_sum")) / rated)
        average = skill_rating.label_asof(
            skill_rating.badge_from_subrank(subrank), overall.item(0, "last_rated_at")
        )
        lobbies = f", {average} lobbies"

    season = ""

    net_points = overall.item(0, "net_points")

    if ranked and net_points is not None:
        points = NET_POINTS.render(net_points, render.BLANK, sign=True)
        season = f", {points} net points"

    print(
        f"\nOverall: {total_games} games, {wins}-{total_games - wins}, {rate} win rate, "
        f"{net:+} net wins, {mvps} MVP, {keys} Key Player{lobbies}{season}."
    )

    if ranked and net_points is not None:
        _points_line(overall)

    abandons = queries.abandon_record(args.parquet, accounts=args.account, games=games)

    if not abandons.is_empty():
        _abandon_lines(abandons, total_games, wins)

    _unscored_line(games)

    if args.hero is not None and _default_mode(args):
        _hero_baseline_line(args.hero, args.min_rating, args.since)


def _winrate_mode_report(args: argparse.Namespace, tz: str) -> None:
    """Print scored-game totals for every stored match/game mode pair."""
    if not _default_mode(args):
        print("--by mode already includes every mode. Remove the mode-selection flag")
        return

    try:
        games = queries.view_frame(
            queries.record_games(
                accounts=args.account,
                tz=tz,
                days=args.days,
                since=args.since,
                hero=args.hero,
                match_mode=None,
                game_mode=None,
                ranked=None,
            ),
            parquet_dir=args.parquet,
        ).collect()
        modes = queries.summarize(
            queries.record_games,
            by=("match_mode", "game_mode", "ranked_type"),
            measures=("games", "wins", "losses", "win_rate", "net_points"),
            filters={"scored": True},
            lf=games.lazy(),
        ).collect()
    except ValueError as e:
        print(e)
        return

    if modes.is_empty():
        print("No games found for the configured accounts")
        _unscored_line(games)
        return

    rows: list[dict[str, Any]] = [
        {
            **row,
            "mode": _mode_pair_label(row["match_mode"], row["game_mode"], row["ranked_type"]),
        }
        for row in modes.iter_rows(named=True)
    ]
    order = {
        "Standard (ranked)": 0,
        "New Player Placement": 1,
        RANKED_LABEL: 2,
        "Standard (unranked)": 3,
        "Street Brawl": 4,
        "Private Lobby": 5,
    }
    rows.sort(key=lambda row: (order.get(row["mode"], len(order)), row["mode"]))
    width = max(12, *(len(row["mode"]) for row in rows))

    print(
        f"  {'Mode':<{width}}{'Games':>8}{'W':>6}{'L':>6}{'Win rate':>11}"
        f"{'Net points':>{NET_POINTS_WIDTH}}"
    )

    for row in rows:
        rate = None if row["win_rate"] is None else float(row["win_rate"])
        ranked = row["mode"] == RANKED_LABEL
        points = _net_points_cell(row["net_points"]) if ranked else " " * NET_POINTS_WIDTH
        print(
            f"  {row['mode']:<{width}}{row['games']:>8}{row['wins']:>6}{row['losses']:>6}"
            f"{WIN_RATE.render(rate, render.BLANK):>11}{points}".rstrip()
        )

    _unscored_line(games)


def _winrate_account_report(
    args: argparse.Namespace, tz: str, config: str | Path | None = None
) -> None:
    """Print scored-game totals for every account in the window.

    - rows follow the config.toml account order and unlisted IDs go last
    - the mode selection applies like the daily table and stands at ranked
      play unless a mode flag says otherwise
    """
    try:
        games = queries.view_frame(
            queries.record_games(
                accounts=args.account,
                tz=tz,
                days=args.days,
                since=args.since,
                hero=args.hero,
            ),
            parquet_dir=args.parquet,
        ).collect()
        totals = queries.summarize(
            queries.record_games,
            by="account_id",
            measures=(
                "games",
                "wins",
                "losses",
                "win_rate",
                "lobby_badge",
                "last_rated_at",
                "mvps",
                "key_players",
                "net_points",
            ),
            filters={"scored": True},
            lf=games.lazy(),
        ).collect()
    except ValueError as e:
        print(e)
        return

    if totals.is_empty():
        print("No games found for the configured accounts")
        _unscored_line(games)
        return

    names = account_labels(config)
    order = {account: index for index, account in enumerate(config_account_names(config).values())}
    rows = sorted(
        totals.iter_rows(named=True),
        key=lambda row: (order.get(row["account_id"], len(order)), row["account_id"]),
    )
    ranked = _has_ranked_games(games)
    points_heading = f"{'Net points':>{NET_POINTS_WIDTH}}" if ranked else ""
    width = max(12, *(len(names.get(row["account_id"], str(row["account_id"]))) for row in rows))

    print(
        f"  {'Account':<{width}}{'Games':>8}{'W':>6}{'L':>6}{'Win rate':>11}"
        f"{'Lobby':>14}{'MVP':>6}{'Key':>6}{points_heading}"
    )

    for row in rows:
        label = names.get(row["account_id"], str(row["account_id"]))
        rate = None if row["win_rate"] is None else float(row["win_rate"])
        badge = row["lobby_badge"]
        lobby = "" if badge is None else skill_rating.label_asof(int(badge), row["last_rated_at"])
        points = _net_points_cell(row["net_points"]) if ranked else ""

        print(
            f"  {label:<{width}}{row['games']:>8}{row['wins']:>6}{row['losses']:>6}"
            f"{WIN_RATE.render(rate, render.BLANK):>11}{lobby:>14}"
            f"{row['mvps']:>6}{row['key_players']:>6}{points}".rstrip()
        )

    _unscored_line(games)


def _points_line(overall: pl.DataFrame) -> None:
    """Print where the net points came from under the overall line.

    Args:
        overall: The one row summary holding the three point shares.
    """
    results, streaks, shields = (
        NET_POINTS.render(overall.item(0, name), render.BLANK, sign=True)
        for name in ("result_points", "streak_points", "shield_points")
    )

    print(
        f"Points: {results} from results, {streaks} win-streak bonuses, {shields} saved by shields."
    )


def _mode_pair_label(
    match_mode: str | None,
    game_mode: str | None,
    ranked_type: int | None = None,
) -> str:
    """Collapse the wire mode names into the label people use.

    Standard covers two different queues, so ranked_type splits them: it went
    unrecorded while Standard was itself the ranked queue, and reads 0 once
    build 6652 made Standard unranked.
    """
    match_label = match_mode or "Unknown match mode"
    game_label = game_mode or "Unknown game mode"

    if match_label == "Standard" and game_label == "Normal":
        return (
            "Standard (unranked)"
            if ranked_type == extract.RANKED_TYPE_UNRANKED
            else ("Standard (ranked)")
        )

    if game_label == "Normal":
        return match_label

    if match_label == "Standard":
        return game_label

    return f"{match_label} / {game_label}"


def _args_mode(args: argparse.Namespace) -> queries.Modes:
    """Take the mode triple a command parsed, falling back to the standing default."""
    return getattr(args, "mode", queries.RANKED_PLAY)


def _default_mode(args: argparse.Namespace) -> bool:
    """Whether a report is reading the standing ranked-play selection.

    - the default spans both queue eras, so its match mode is a group rather
      than the single mode every explicit flag pins
    """
    match_mode, _, ranked = _args_mode(args)

    return ranked is True and not isinstance(match_mode, int)


def _has_ranked_games(games: pl.DataFrame) -> bool:
    """Whether the window actually holds Ranked games, which are the only ones with points.

    Read from the games rather than the mode flag, because the default
    selection spans both queue eras and a window entirely before build 6652
    has no points column to show.
    """
    if games.is_empty() or "match_mode" not in games.columns:
        return False

    return bool((games.get_column("match_mode") == RANKED_LABEL).any())


def selected_mode_label(args: argparse.Namespace) -> str:
    """Label the mode a command was given, for output."""
    return queries.mode_label(*_args_mode(args))


def _window_phrase(args: argparse.Namespace) -> str:
    """Name the day window a command was given, for lines that report nothing found."""
    since = getattr(args, "since", None)

    if since:
        return f" since {since}"

    days = getattr(args, "days", None)

    if days:
        return f" in the last {days} days"

    return ""


def no_games_line(
    args: argparse.Namespace,
    config: str | Path | None,
    subject: str = "games",
) -> str:
    """Say which queue, accounts, and window came back empty.

    An empty report reads as missing data unless the line names the queue.
    """
    hero = getattr(args, "hero", None)
    on_hero = f" on {hero}" if hero else ""
    named = " ".join(part for part in (selected_mode_label(args), subject) if part)
    accounts = format_accounts(args.account, config)

    return f"No {named} for accounts {accounts}{on_hero}{_window_phrase(args)}"


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
    who = ", ".join(sides)
    print(f"\nAbandons: {total} game{plural}. {who[0].upper()}{who[1:]}.")

    returned = int(abandons.get_column("returned").cast(pl.Int32).sum())

    if returned:
        plural = "s" if returned != 1 else ""
        print(f"  {returned} leaver{plural} reconnected and finished.")

    clean_games = games - total
    clean_wins = wins - int(abandons.get_column("won").cast(pl.Int32).sum())

    if clean_games > 0:
        print(
            f"  Without them: {clean_games} games, "
            f"{clean_wins}-{clean_games - clean_wins}, {win_rate(clean_wins, clean_games)} win rate."
        )


def _unscored_line(games: pl.DataFrame) -> None:
    """Print the unscored games the table left out, nothing when there are none."""
    unscored = queries.unscored_record(games=games)

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
