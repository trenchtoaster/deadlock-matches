"""Commands comparing your play against top players and across your own days."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

import polars as pl

from deadlock_matches import heroes, meta, players, queries, schemas, skill_rating, timeline
from deadlock_matches.cli.data import MVP_LABELS, TEAMS, final_stats
from deadlock_matches.config import config_timezone, format_accounts

if TYPE_CHECKING:
    import argparse
    from pathlib import Path


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
    "treasure": "Urn",
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
    "treasure",
    "gold_denied",
    "combat",
    "objectives",
    "catch_up",
    "other",
    "souls",
)


def sources_report(mine: list[Any], theirs: list[Any]) -> None:
    """Compare income from each soul source between two sets of games."""
    marks = [6, 10, 15, 20, 25]
    header = "".join(f"  {f'{m}m gap':>8}" for m in marks)
    print(f"\n  {'source':<12}{header}  {'you@20m':>9}  {'top@20m':>9}")

    for stat in SOURCE_ROWS:
        rows = timeline.compare(mine, theirs, stat, marks)
        gaps = "".join(f"  {_cell(r['gap'], sign=True)}" for r in rows)
        at20 = next(r for r in rows if r["min"] == 20)

        print(f"  {stat:<12}{gaps}  {_cell(at20['me'], 9)}  {_cell(at20['them'], 9)}")

    print(
        "\n  souls is net worth. It runs a little over the other rows summed, the game"
        "\n  credits some income (sell refunds and similar) to no source"
    )


def _snapshot_field(stat: str) -> str | None:
    """Resolve a stat to its protobuf snapshot field, accepting the parquet souls_* names."""
    if stat in schemas.STAT_FIELDS:
        return stat

    raw = "gold" + stat.removeprefix("souls")

    if stat.startswith("souls") and raw in schemas.STAT_FIELDS:
        return raw

    return None


def compare_report(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Compare a stat minute by minute between the player and top players of the hero."""
    stat = args.stat

    if stat not in timeline.STATS and stat != "soul_sources":
        stat = _snapshot_field(stat)

        if stat is None:
            print(f"Unknown stat: {args.stat}")
            print(f"Named stats: {', '.join(timeline.STATS)}, soul_sources")
            print(
                "Snapshot fields: "
                + ", ".join(sorted(schemas.souls(f) for f in schemas.STAT_FIELDS))
            )
            return

    hero_id = heroes.hero_id_by_name(args.hero)
    if hero_id is None:
        print(f"Unknown hero: {args.hero}")
        return

    mine = queries.snapshot_players(args.hero, args.parquet, args.account)
    ids = format_accounts(args.account, config)

    if not mine:
        print(f"No games for accounts {ids} on {args.hero}")
        return

    top = players.top_players(hero_id, limit=args.players)
    print(f"You ({ids}, {len(mine)} games) vs top {args.hero} players: {args.stat}")

    print(f"\n  {'Player':<18} {'Rank':>5}  {'Region':<9} {'Games':>5}")

    theirs = []
    for m in top:
        blocks = players.player_timelines(m["account_id"], hero_id, n=args.games)
        theirs += blocks
        print(f"  {m['name']:<18} {m['rank']:>5}  {m['region']:<9} {len(blocks):>5}")

    if not theirs:
        print("No games available from top players")
        return

    if args.stat == "soul_sources":
        sources_report(mine, theirs)
        return

    marks = [3, 6, 9, 12, 15, 20, 25, 30, 35, 40]
    rows = timeline.compare(mine, theirs, stat, marks)
    my_rates = timeline.interval_rates(rows, "me")
    top_rates = timeline.interval_rates(rows, "them")

    print("\n  Min       You (n)        Top (n)       Gap   You/min  Top/min")

    for r, ry, rt in zip(rows, my_rates, top_rates, strict=True):
        print(
            f"  {r['min']:>3}  {_cell(r['me'])} ({r['me_n']:>2})  {_cell(r['them'])} ({r['them_n']:>2})"
            f"  {_cell(r['gap'], sign=True)}  {_cell(ry)}  {_cell(rt)}"
        )

    deficits = [
        (rt - ry, prev, r["min"], ry, rt)
        for prev, r, ry, rt in zip([0] + marks, rows, my_rates, top_rates, strict=False)
        if ry is not None and rt is not None and r["me_n"] >= 3 and r["them_n"] >= 3
    ]
    if deficits:
        worst = max(deficits)
        d, start, end, ry, rt = worst

        if d > 0:
            print(
                f"\n  Biggest {args.stat} rate deficit: {start}-{end}m, "
                f"you {_cell(ry, 1)}/min vs top players {_cell(rt, 1)}/min"
            )
        else:
            print(f"\n  No {args.stat} rate deficit at any checkpoint, you keep pace or better")

    if args.stat == "farm":
        at20 = timeline.compare(mine, theirs, "combat", [20])[0]

        if at20["me"] is not None and at20["them"] is not None:
            print(
                f"\n  Kill and assist souls at 20m (not counted above): "
                f"you {at20['me']:,.0f} vs top players {at20['them']:,.0f} "
                f"({at20['gap']:+,.0f}), --stat combat for the full timeline"
            )


def _span(row: dict[str, Any]) -> str:
    """Label an interval row like 0-5m, or 30-34m for a shorter last interval."""
    return f"{row['start_s'] // 60}-{-(-row['end_s'] // 60)}m"


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
    board = (
        queries.scan("players", args.parquet)
        .filter(pl.col("match_id") == row["match_id"])
        .join(final_stats(match_ids, args.parquet), on=["match_id", "account_id"], how="left")
        .with_columns(
            pl.col("player_damage", "boss_damage", "player_healing", "heal_prevented").fill_null(0)
        )
        .sort(["team", "net_worth"], descending=[False, True])
        .collect()
    )

    print()
    print(
        f"  {'Team':<16} {'Hero':<14} {'':<8} {'K/D/A':<8} {'Souls':>9} "
        f"{'Damage':>8} {'Obj damage':>10} {'Healing':>8} {'Prevented':>9} "
        f"{'Last hits':>9} {'Denies':>6}"
    )

    for p in board.iter_rows(named=True):
        kda = f"{p['kills']}/{p['deaths']}/{p['assists']}"
        hero = f"{p['hero']} *" if p["account_id"] == row["account_id"] else p["hero"]
        print(
            f"  {TEAMS.get(p['team'], p['team']):<16} {hero:<14} "
            f"{MVP_LABELS.get(p['mvp_rank'], ''):<8} {kda:<8} {p['net_worth']:>9,} "
            f"{p['player_damage']:>8,} {p['boss_damage']:>10,} {p['player_healing']:>8,} "
            f"{p['heal_prevented']:>9,} {p['last_hits']:>9,} {p['denies']:>6}"
        )
    print()


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

    if game.is_empty():
        in_match = (
            queries.scan("players", args.parquet)
            .filter(pl.col("match_id") == match_id)
            .select("hero")
            .collect()
        )

        if in_match.is_empty():
            print(f"Match {match_id} is not in the archive (view it in game and rerun)")
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

    return sorted(events)


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
        _source_intervals(row, args, "damage", "Damage to heroes by source")


def _source_intervals(
    row: dict[str, Any],
    args: argparse.Namespace,
    stat: str,
    title: str,
    *,
    groups: bool = True,
    required: bool = True,
) -> bool:
    """Print the per source interval table for one stat.

    - groups adds the Gun/Abilities/Items block under the total
    - a stat with no rows prints the error only when required
    """
    try:
        df = queries.damage_intervals(
            row["match_id"], row["account_id"], args.interval * 60, args.parquet, stat
        )
    except ValueError as e:
        if required:
            print(e)

        return False

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
        return True

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

        if args.hero is not None:
            _hero_baseline_line(args.hero, args.min_rating, args.since)

        return

    print(f"Dates below are grouped by {tz} {args.by}.\n")
    print(
        f"  {args.by.capitalize():<12}{'Games':>7}{'W':>5}{'L':>5}"
        f"{'Win rate':>11}{'MVP':>6}{'Key':>6}{'Net wins':>11}{'Cumulative net':>17}"
    )

    for r in df.iter_rows(named=True):
        day = f"{r['day']:%Y-%m}" if args.by == "month" else r["day"]

        print(
            f"  {day!s:<12}{r['games']:>7}{r['wins']:>5}{r['losses']:>5}"
            f"{r['win_rate']:>10.1f}%{r['mvps']:>6}{r['key_players']:>6}{r['net']:>+11}{r['cum_net']:>+17}"
        )

    games = int(df["games"].sum())
    wins = int(df["wins"].sum())
    rate = wins / games * 100
    net = df.item(-1, "cum_net")
    mvps = int(df["mvps"].sum())
    keys = int(df["key_players"].sum())

    print(
        f"\nOverall: {games} games, {wins}-{games - wins}, {rate:.1f}% win rate, "
        f"{net:+} net wins, {mvps} MVP, {keys} Key Player."
    )

    if args.hero is not None:
        _hero_baseline_line(args.hero, args.min_rating, args.since)


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
    ("slide %", "slide_percent"),
    ("ground dashes /min", "dashes_min"),
    ("air dashes /min", "air_dashes_min"),
    ("in air %", "in_air_percent"),
    ("zipline %", "zipline_percent"),
    ("fighting players %", "combat_percent"),
    ("distance /min", "distance_min"),
    ("stationary %", "stationary_percent"),
]


def movement_report(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Compare movement metrics between the player and select other players."""
    if not queries.table_exists("movement", args.parquet):
        print(
            'No movement table: remove "movement" from the exclude list in config.toml '
            "and run `deadlock sync`"
        )
        return

    hero_id = heroes.hero_id_by_name(args.hero)
    if hero_id is None:
        print(f"Unknown hero: {args.hero}")
        return

    mine = (
        queries.my_games(args.parquet, accounts=args.account)
        .filter(pl.col("hero_id") == hero_id)
        .select("match_id", "account_id")
    )
    you = queries.movement_profile(args.parquet).join(mine, on=["match_id", "account_id"]).collect()

    if you.is_empty():
        print(f"No {args.hero} games in your tables")
        return

    top = None
    if queries.table_exists("movement", players.PARQUET_DIR):
        tracked = (
            queries.scan("downloads", players.PARQUET_DIR)
            .filter(pl.col("hero_id") == hero_id)
            .select("match_id", "account_id")
        )
        top = (
            queries.movement_profile(players.PARQUET_DIR)
            .join(tracked, on=["match_id", "account_id"])
            .collect()
        )

        if top.is_empty():
            top = None

    title = f"{args.hero} movement: you ({len(you)} games)"
    if top is not None:
        title += f" vs top players ({len(top)} games)"
    print(title + "\n")

    header = f"  {'Metric':<24}{'You':>9}"
    if top is not None:
        header += f"{'Top':>9}{'Gap':>9}"
    print(header)

    for label, col in MOVEMENT_METRICS:
        yours = _mean(you, col)
        line = f"  {label:<24}{yours:>9,.1f}"

        if top is not None:
            theirs = _mean(top, col)
            line += f"{theirs:>9,.1f}{theirs - yours:>+9,.1f}"

        print(line)

    if top is None:
        print(
            f'\nNo top player movement tables: run `deadlock download --hero "{args.hero}"` '
            'without "movement" in the config.toml exclude list'
        )
