"""Commands that sync the archive, rebuild the tables, and show raw matches."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl

from deadlock_matches import (
    assets,
    export,
    extract,
    heroes,
    items,
    players,
    queries,
    skill_rating,
)
from deadlock_matches.config import (
    config_account_names,
    config_exclude,
    config_players,
    config_timezone,
)

if TYPE_CHECKING:
    import argparse
    from collections.abc import Collection, Iterable


def _tilde(path: str | Path) -> str:
    """Shorten paths under the home directory to ~ for printing."""
    p = Path(path).resolve()
    home = Path.home().resolve()

    if p.is_relative_to(home):
        return "~/" + p.relative_to(home).as_posix()

    return str(p)


TEAMS = {0: "The Hidden King", 1: "The Archmother"}

MVP_LABELS = {1: "1 (MVP)", 2: "2 (Key)", 3: "3 (Key)"}


def _print_match(match: dict[str, Any], rows: list[dict[str, Any]], you: set[int]) -> None:
    """Print the match header and a table with one row per player.

    you is the set of your account IDs, whose hero names get a trailing star.
    """
    when = match["start_local"].strftime("%Y-%m-%d %H:%M")
    winner = TEAMS.get(match["winning_team"], match["winning_team"])
    print(f"Match {match['match_id']}: {match['duration_s']}s, {winner} won, {when}")

    badges = [
        f"{TEAMS[team]} {skill_rating.label(match[f'average_badge_team{team}'])}"
        for team in (0, 1)
        if match[f"average_badge_team{team}"] is not None
    ]
    if badges:
        print("Lobby average: " + ", ".join(badges))

    print()
    print(
        f"  {'Team':<16} {'Hero':<14} {'':<8} {'K/D/A':<8} {'Net worth':>9} "
        f"{'Damage':>8} {'Obj damage':>10} {'Healing':>8} {'Prevented':>9} "
        f"{'Last hits':>9} {'Denies':>6}"
    )

    for p in sorted(rows, key=lambda r: (r["team"], -r["net_worth"])):
        kda = f"{p['kills']}/{p['deaths']}/{p['assists']}"
        hero = f"{p['hero']} *" if p["account_id"] in you else p["hero"]
        print(
            f"  {TEAMS.get(p['team'], p['team']):<16} {hero:<14} "
            f"{MVP_LABELS.get(p['mvp_rank'], ''):<8} {kda:<8} {p['net_worth']:>9,} "
            f"{p['player_damage']:>8,} {p['boss_damage']:>10,} {p['player_healing']:>8,} "
            f"{p['heal_prevented']:>9,} {p['last_hits']:>9,} {p['denies']:>6}"
        )
    print()


def sync_archive(cache: str | Path, archive_dir: str | Path) -> int:
    """Snapshot the live cache into the archive and say where the data lives."""
    archive_dir = Path(archive_dir)
    new = extract.archive(cache, archive_dir)

    total = sum(1 for _ in archive_dir.glob("*.bin"))
    note = f"+{new} new" if new else "no new"
    print(f"Archive: {total} matches ({note}) at {_tilde(archive_dir)}\n")

    return new


def refresh_tables(
    archive_dir: str | Path, out_dir: str | Path, exclude: Collection[str] = ()
) -> None:
    """Rebuild the parquet tables so they cover everything in the archive."""
    counts = export.export_all(archive_dir=archive_dir, out_dir=out_dir, exclude=exclude)
    print(
        f"Rebuilt {len(counts)} parquet files from {counts['matches']:,} matches at {_tilde(out_dir)}\n"
    )
    warn_stale_heroes(out_dir)


def warn_stale_heroes(parquet_dir: str | Path) -> None:
    """Print a warning when current hero stats can't explain archived matches."""
    stale = queries.stale_hero_matches(parquet_dir)

    if stale:
        shown = ", ".join(str(m) for m in stale[:5]) + (" ..." if len(stale) > 5 else "")
        print(
            f"Warning: hero base stats changed since {len(stale)} matches were played "
            f"(computed base health exceeds what was recorded): {shown}\n"
        )


def match_history(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Print recent matches from the parquet tables, newest last so it ends at the prompt."""
    tz = config_timezone(config)

    if not queries.table_exists("matches", args.parquet):
        refresh_tables(args.archive, args.parquet, config_exclude(config))

    since = getattr(args, "since", None)
    since = dt.date.fromisoformat(since) if since else None
    days = getattr(args, "days", None)

    if since is None and days is None:
        days = 1

    accounts = getattr(args, "account", None) or []
    players_lf = queries.scan("players", args.parquet)
    wanted = players_lf

    if accounts:
        wanted = players_lf.filter(pl.col("account_id").is_in(accounts))

    matches = (
        queries.scan("matches", args.parquet)
        .join(wanted.select("match_id").unique(), on="match_id")
        .with_columns(pl.col("start_time").dt.convert_time_zone(tz).alias("start_local"))
        .with_columns(pl.col("start_local").dt.date().alias("day"))
        .sort("start_time")
        .collect()
    )

    if since is not None:
        matches = matches.filter(pl.col("day") >= since)

    if days is not None:
        keep = matches["day"].unique().sort().tail(days).implode()
        matches = matches.filter(pl.col("day").is_in(keep))

    if matches.is_empty():
        print("No match metadata found in cache")
        return

    finals = (
        queries.scan("stats", args.parquet)
        .group_by("match_id", "account_id")
        .agg(
            pl.col("player_damage").max(),
            pl.col("boss_damage").max(),
            pl.col("player_healing").max(),
            pl.col("heal_prevented").max(),
        )
    )
    rows = (
        players_lf.join(matches.lazy().select("match_id"), on="match_id")
        .join(finals, on=["match_id", "account_id"], how="left")
        .with_columns(
            pl.col("player_damage", "boss_damage", "player_healing", "heal_prevented").fill_null(0)
        )
        .collect()
    )
    by_match = {k[0]: part for k, part in rows.partition_by(["match_id"], as_dict=True).items()}

    names = {account_id: name for name, account_id in config_account_names(config).items()}
    you = set(accounts)

    if you:
        legend = ", ".join(f"{names[a]} ({a})" if a in names else str(a) for a in accounts)
        print(f"You (marked * below): {legend}\n")

    for m in matches.iter_rows(named=True):
        _print_match(m, by_match[m["match_id"]].to_dicts(), you)


def _archived_games(parquet_dir: str | Path, ids: list[int]) -> dict[int, int] | None:
    """Count archived games per account, None before the first export."""
    if not queries.table_exists("players", parquet_dir):
        return None

    rows = (
        queries.scan("players", parquet_dir)
        .filter(pl.col("account_id").is_in(ids))
        .group_by("account_id")
        .agg(pl.len().alias("games"))
        .collect()
    )

    return dict(rows.iter_rows())


def _suggest_names(count: int, taken: Iterable[str]) -> list[str]:
    """Suggest neutral config.toml account names, main then alt1, alt2, skipping taken ones.

    - deliberately not the Steam account names: config names print in report
      headers people share, and the account name is half of the credentials
    """
    used = {t.lower() for t in taken}
    names: list[str] = []
    n = 0

    while len(names) < count:
        name = "main" if n == 0 else f"alt{n}"
        n += 1

        if name not in used:
            names.append(name)

    return names


def list_accounts(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Print the Steam accounts on this PC that have run Deadlock, ready for config.toml."""
    found = extract.steam_accounts(args.cache)

    if not found:
        print(f"No Steam accounts with Deadlock found next to the cache at {_tilde(args.cache)}")
        print("Your Steam32 ID is the folder name under Steam's userdata/ directory")
        return

    games = _archived_games(args.parquet, [a.account_id for a in found])
    names = {a: name for name, a in config_account_names(config).items()}

    print("Steam accounts on this PC that have run Deadlock, newest login first:\n")
    games_head = f" {'Archived games':>14}" if games is not None else ""
    print(f"  {'Account':<12} {'Account name':<18} {'Profile name':<18}{games_head}  config.toml")

    for a in found:
        games_cell = f" {games.get(a.account_id, 0):>14,}" if games is not None else ""
        print(
            f"  {a.account_id:<12} {a.login or '?':<18} {a.persona or '?':<18}"
            f"{games_cell}  {names.get(a.account_id, '')}"
        )

    missing = [a for a in found if a.account_id not in names]

    if not missing:
        print("\nconfig.toml already covers all of them")
        return

    print("\nAdd the ones that are you to config.toml, the names are yours to change:\n")
    print("[accounts]")

    suggested = _suggest_names(len(missing), config_account_names(config))

    for name, a in zip(suggested, missing, strict=True):
        print(f"{name} = {a.account_id}")


def refresh_assets(_args: argparse.Namespace) -> None:
    """Redownload the hero/item snapshots and report what changed."""
    old_items = {i.name for i in items.item_map().values()}
    old_heroes = {h.name for h in heroes.hero_map().values()}

    n_heroes = assets.refresh_heroes()
    n_items = assets.refresh_items()
    n_abilities = assets.refresh_abilities()
    n_tiers = assets.refresh_skill_rating()

    new_items = {i.name for i in items.item_map().values()}
    new_heroes = {h.name for h in heroes.hero_map().values()}

    print(f"heroes.json: {n_heroes} heroes")
    print(f"items.json: {n_items} upgrade items")
    print(f"abilities.json: {n_abilities} abilities/guns")
    print(f"skill_rating.json: {n_tiers} skill rating tiers")

    for name in sorted(new_heroes - old_heroes):
        print(f"  new hero: {name}")

    for name in sorted(old_heroes - new_heroes):
        print(f"  gone hero: {name}")

    for name in sorted(new_items - old_items):
        print(f"  new item: {name}")

    for name in sorted(old_items - new_items):
        print(f"  gone item: {name}")

    dest = assets.archive_snapshots()
    print(f"History: dated copy at {_tilde(dest)}")


def download_matches(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Build player tables from the API for specific match IDs, specific accounts, or top players."""
    if args.match:
        rows = players.matches_by_id(args.match)
        got = len({r["match_id"] for r in rows})
        print(f"Downloading {len(args.match)} match ID(s), got {got}")
    else:
        if args.hero is None:
            print("download needs --hero, or --match with match IDs")
            return

        hero_id = heroes.hero_id_by_name(args.hero)
        if hero_id is None:
            print(f"Unknown hero: {args.hero}")
            return

        rows = _download_players(args, hero_id, config)

    counts = players.write_player_tables(rows, out_dir=args.out, exclude=config_exclude(config))

    for name, n in counts.items():
        print(f"  {name:<14} {n:>7,} rows")

    print(f"Players parquet tables at {_tilde(args.out)}")


def _download_players(
    args: argparse.Namespace, hero_id: int, config: str | Path | None
) -> list[dict[str, Any]]:
    """Recent games for the given accounts, or the top players plus config players by default."""
    if args.account:
        tracked = [{"name": str(a), "account_id": a} for a in args.account]
    else:
        tracked = players.top_players(hero_id, limit=args.players)
        known = {t["account_id"] for t in tracked}
        tracked += [
            {"name": name, "account_id": a}
            for name, a in config_players(args.hero, config).items()
            if a not in known
        ]

    print(f"Downloading recent {args.hero} games for {len(tracked)} players:")

    for t in tracked:
        where = f"rank {t['rank']:<4} {t['region']}" if t.get("rank") else "selected"
        print(f"  {t['name']:<18} {where}")

    rows = players.download_matches(tracked, hero_id, n=args.games)
    unique = len({r["match_id"] for r in rows})
    print(f"\nRetrieved {unique} unique matches across {len(rows)} player games")

    return rows


def leaderboard_report(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Print the top players of a hero.

    - --matches also lists recent match IDs per player
    """
    hero_id = heroes.hero_id_by_name(args.hero)
    if hero_id is None:
        print(f"Unknown hero: {args.hero}")
        return

    top = players.top_players(hero_id, limit=args.players)
    known = {m["account_id"] for m in top}
    top += [
        {"name": name, "account_id": a, "rank": None, "region": "config"}
        for name, a in config_players(args.hero, config).items()
        if a not in known
    ]

    print(f"{args.hero} leaderboard:")

    for m in top:
        where = f"rank {m['rank']:<4} {m['region']}" if m.get("rank") else "config"
        print(f"  {m['name']:<20} {m['account_id']:<12} {where}")

        if args.matches:
            for row in players.recent_hero_matches(m["account_id"], hero_id, n=args.matches):
                when = dt.datetime.fromtimestamp(row["start_time"], dt.UTC).strftime("%Y-%m-%d")
                result = "win " if row["match_result"] == row["player_team"] else "loss"
                kda = f"{row['player_kills']}/{row['player_deaths']}/{row['player_assists']}"
                print(f"      {row['match_id']}  {when}  {result}  {kda}")


def export_tables(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Rebuild the parquet tables and say what was written."""
    counts = export.export_all(
        archive_dir=args.archive, out_dir=args.parquet, exclude=config_exclude(config)
    )

    for name, n in counts.items():
        print(f"  {name:<14} {n:>7,} rows")

    print(f"Parquet tables at {_tilde(args.parquet)}")
    warn_stale_heroes(args.parquet)
