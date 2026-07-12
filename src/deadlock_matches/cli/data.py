"""Commands that sync the archive, rebuild the tables, and show raw matches."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl

from deadlock_matches import (
    api,
    export,
    extract,
    paths,
    players,
    queries,
)
from deadlock_matches.assets import (
    heroes,
    history,
    items,
    snapshots,
    store,
)
from deadlock_matches.config import (
    config_account_names,
    config_accounts,
    config_exclude,
    config_players,
    config_timezone,
    find_config,
)

if TYPE_CHECKING:
    import argparse
    from collections.abc import Collection, Iterable


def _tilde(path: str | Path) -> str:
    """Shorten paths under the home directory to ~ for printing."""
    return paths.tilde(path)


TEAMS = {0: "The Hidden King", 1: "The Archmother"}

MVP_LABELS = {1: "1 (MVP)", 2: "2 (Key)", 3: "3 (Key)"}


def final_stats(match_ids: pl.LazyFrame, parquet_dir: str | Path) -> pl.LazyFrame:
    """Return the end-of-match damage and healing totals per player from the stats snapshots."""
    return (
        queries.scan("stats", parquet_dir)
        .join(match_ids, on="match_id")
        .group_by("match_id", "account_id")
        .agg(
            pl.col("player_damage").max(),
            pl.col("boss_damage").max(),
            pl.col("player_healing").max(),
            pl.col("heal_prevented").max(),
        )
    )


def sync_archive(cache: str | Path, archive_dir: str | Path, *, quiet: bool = False) -> int:
    """Snapshot the live cache into the archive and say where the data lives."""
    archive_dir = Path(archive_dir)
    new = extract.archive(cache, archive_dir)

    if quiet:
        return new

    total = sum(1 for _ in archive_dir.glob("*.bin"))
    note = f"+{new} new" if new else "no new"
    print(f"Archive: {total} matches ({note}) at {_tilde(archive_dir)}\n")

    return new


def refresh_tables(
    archive_dir: str | Path,
    out_dir: str | Path,
    accounts: Collection[int],
    exclude: Collection[str] = (),
    *,
    quiet: bool = False,
) -> None:
    """Bring the parquet tables up to date with the archive by decoding only new matches."""
    result = export.export_new(
        archive_dir=archive_dir, out_dir=out_dir, exclude=exclude, accounts=accounts
    )

    if result.rebuilt:
        print(f"Rebuilt all tables from the archive ({result.rebuilt})\n")

    elif result.decoded and not quiet:
        print(f"Added {result.decoded:,} new matches to the parquet tables\n")


def match_history(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Print one line per game of yours, newest last, with the match ID for the other commands.

    - shows the last 10 games unless --days or --since widen the window
    """
    tz = config_timezone(config)

    if not queries.table_exists("matches", args.parquet):
        accounts = config_accounts(config)

        if accounts:
            refresh_tables(args.archive, args.parquet, accounts, config_exclude(config))

    since = getattr(args, "since", None)
    since = dt.date.fromisoformat(since) if since else None
    days = getattr(args, "days", None)

    accounts = args.account
    players_lf = queries.scan("players", args.parquet).filter(pl.col("account_id").is_in(accounts))

    matches_lf = (
        queries.scan("matches", args.parquet)
        .join(players_lf.select("match_id").unique(), on="match_id")
        .with_columns(pl.col("start_time").dt.convert_time_zone(tz).alias("start_local"))
        .with_columns(pl.col("start_local").dt.date().alias("day"))
    )

    if since is not None:
        matches_lf = matches_lf.filter(pl.col("day") >= since)

    matches = matches_lf.sort("start_time").select("match_id", "start_local", "day").collect()

    if days is not None:
        keep = matches["day"].unique().sort().tail(days).implode()
        matches = matches.filter(pl.col("day").is_in(keep))

    if matches.is_empty():
        print("No match metadata found in cache")
        return

    games = (
        players_lf.join(matches.lazy().select("match_id", "start_local"), on="match_id")
        .join(
            final_stats(matches.lazy().select("match_id"), args.parquet),
            on=["match_id", "account_id"],
            how="left",
        )
        .with_columns(pl.col("player_damage").fill_null(0))
        .sort("start_local")
        .select(
            "match_id",
            "account_id",
            "hero",
            "won",
            "kills",
            "deaths",
            "assists",
            "net_worth",
            "player_damage",
            "start_local",
        )
        .collect()
    )

    if since is None and days is None:
        games = games.tail(10)

    names = {account_id: name for name, account_id in config_account_names(config).items()}

    print(
        f"  {'Account':<10} {'Hero':<14} {'Result':<7} {'K/D/A':<9} {'Souls':>8} "
        f"{'Damage':>8}  {'Timestamp':<16}  Match ID"
    )

    for g in games.iter_rows(named=True):
        account = names.get(g["account_id"], str(g["account_id"]))
        result = "win" if g["won"] else "loss"
        kda = f"{g['kills']}/{g['deaths']}/{g['assists']}"
        when = g["start_local"].strftime("%Y-%m-%d %H:%M")
        print(
            f"  {account:<10} {g['hero']:<14} {result:<7} {kda:<9} {g['net_worth']:>8,} "
            f"{g['player_damage']:>8,}  {when:<16}  {g['match_id']}"
        )


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

    print(
        f"\nAdd the ones that are you to {_tilde(find_config())}, the names are yours to change:\n"
    )
    print("[accounts]")

    suggested = _suggest_names(len(missing), config_account_names(config))

    for name, a in zip(suggested, missing, strict=True):
        print(f"{name} = {a.account_id}")


def refresh_assets(args: argparse.Namespace) -> None:
    """Redownload the hero/item snapshots and report what changed.

    Writes the user asset store by default, --seed writes the bundled seed for a
    maintainer to commit.
    """
    seed = getattr(args, "seed", False)

    if seed and not store.is_source_checkout():
        print("--seed writes the bundled seed and needs a source checkout")
        return

    def target(name: str) -> Path | None:
        return store.seed_path(name) if seed else None

    old_items = {i.name for i in items.item_map(target("items.json")).values()}
    old_heroes = {h.name for h in heroes.hero_map(target("heroes.json")).values()}

    n_heroes = snapshots.refresh_heroes(target("heroes.json"))
    n_items = snapshots.refresh_items(target("items.json"))
    n_abilities = snapshots.refresh_abilities(target("abilities.json"))
    n_tiers = snapshots.refresh_skill_rating(target("skill_rating.json"))
    n_accolades = snapshots.refresh_accolades(target("accolades.json"))
    n_statues = snapshots.refresh_statues(target("statues.json"))

    new_items = {i.name for i in items.item_map(target("items.json")).values()}
    new_heroes = {h.name for h in heroes.hero_map(target("heroes.json")).values()}

    print(f"heroes.json: {n_heroes} heroes")
    print(f"items.json: {n_items} upgrade items")
    print(f"abilities.json: {n_abilities} abilities/guns")
    print(f"skill_rating.json: {n_tiers} skill rating tiers")
    print(f"accolades.json: {n_accolades} accolades")
    print(f"statues.json: {n_statues} statue pickups")

    for name in sorted(new_heroes - old_heroes):
        print(f"  new hero: {name}")

    for name in sorted(old_heroes - new_heroes):
        print(f"  gone hero: {name}")

    for name in sorted(new_items - old_items):
        print(f"  new item: {name}")

    for name in sorted(old_items - new_items):
        print(f"  gone item: {name}")

    lags = snapshots.history_lags(seed=seed)

    if lags:
        print()

        for name, date, build in lags:
            print(f"  {name} history is behind the live patch (newest build {build}, {date})")

        hint = "deadlock assets --backfill --seed" if seed else "deadlock assets --backfill"
        print(f"  run {hint} to capture the current patch")


HISTORY_BUILDERS = (
    ("items", "item_history.parquet", "build_item_history"),
    ("heroes", "hero_history.parquet", "build_hero_history"),
    ("abilities", "ability_history.parquet", "build_ability_history"),
    ("ranks", "rank_history.parquet", "build_rank_history"),
    ("statues", "statue_history.parquet", "build_statue_history"),
)


def rebuild_history(args: argparse.Namespace) -> None:
    """Build the item, hero, ability, rank, and statue history from the assets API.

    - writes the user asset store by default, resuming on top of the bundled seed,
      so an install stays current without a maintainer
    - --seed writes the bundled seed instead, for a maintainer to commit
    - refreshes the build list first so a backfill run right after a patch sees the
      new build instead of a day-old cached list
    - builder functions resolve by name at run time so tests can patch every entry
      of HISTORY_BUILDERS without knowing the names
    """
    seed = getattr(args, "seed", False)

    if seed and not store.is_source_checkout():
        print("--seed writes the bundled seed and needs a source checkout")

        return

    snapshots.client_version_dates(max_age=0)

    if not args.confirm:
        where = "the bundled seed" if seed else "your local asset store"
        print(f"Building the asset history into {where}:")

        for name, file, _ in HISTORY_BUILDERS:
            target = store.seed_path(file) if seed else store.store_dir() / file
            resume = store.seed_path(file) if seed else store.read_path(file)
            print(f"  {name:<9} {len(history.eras(resume))} eras -> {_tilde(target)}")

        builds = sum(
            d >= snapshots.HISTORY_START for d in snapshots.client_version_dates().values()
        )

        if args.full:
            print(
                f"\n--full rescans every client build since {snapshots.HISTORY_START} ({builds} "
                f"builds per asset type) and overwrites the target."
            )
        else:
            print(
                "\nThis scans only the builds newer than the last stored era and appends any "
                "new ones. Use --full to rescan every build after an old-build correction."
            )

        print("The API calls are cached after the first run, so a rerun is cheap.")
        print("Re-run with --confirm to proceed.")

        return

    for name, file, builder in HISTORY_BUILDERS:
        build = getattr(snapshots, builder)
        target = store.seed_path(file) if seed else store.write_path(file)
        resume = store.seed_path(file) if seed else store.read_path(file)
        before = len(history.eras(resume))
        api.fetch_counts.clear()
        missing: list[int] = []

        def show(
            done: int,
            total: int,
            skipped: list[int],
            name: str = name,
            missing: list[int] = missing,
        ) -> None:
            missing[:] = skipped
            cached = api.fetch_counts["cached"]
            downloaded = api.fetch_counts["downloaded"]
            line = (
                f"  {name:<9} {done}/{total} builds"
                f" ({cached} cached, {downloaded} downloaded, {len(skipped)} missing)"
            )
            print(f"\r{line:<76}", end="", flush=True)

        eras = build(path=target, resume_from=resume, progress=show, full=args.full)
        size = target.stat().st_size / 1024 if target.is_file() else 0.0
        line = f"  {name:<9} {before} -> {eras} eras  {size:.0f} KB at {_tilde(target)}"
        print(f"\r{line:<76}")

        if missing:
            builds = ", ".join(str(b) for b in missing)
            print(f"    no asset data for client build {builds}, skipped")

    tail = (
        "Review the diff and commit the updated tables."
        if seed
        else "Your local asset history is current."
    )
    print(f"\n{tail}")


def no_pool_hint(hero: str, *, tracked_in_config: bool) -> str:
    """Pick the hint that matches how far the tracking setup got for a hero."""
    if tracked_in_config:
        return (
            f"No downloaded games from the tracked {hero} players yet: "
            f'run `deadlock download --hero "{hero}"`'
        )

    return (
        f"No players tracked for {hero} in config.toml: "
        f'`deadlock leaderboard --hero "{hero}"` prints paste-ready lines, '
        f'then run `deadlock download --hero "{hero}"`'
    )


def download_matches(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Build player tables from the API for specific match IDs, specific accounts, or top players."""
    if args.match:
        rows = players.matches_by_id(args.match, args.archive)
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

        if rows is None:
            return

    counts = players.write_player_tables(
        rows, out_dir=args.out, exclude=config_exclude(config), archive_dir=args.archive
    )

    for name, n in counts.items():
        print(f"  {name:<14} {n:>7,} rows")

    print(f"Players parquet tables at {_tilde(args.out)}")


def _download_players(
    args: argparse.Namespace, hero_id: int, config: str | Path | None
) -> list[dict[str, Any]] | None:
    """Recent games for the given accounts, or the config watchlist for the hero.

    - never downloads anyone on its own, every player was named by the user
    - the current leaderboards only fill in rank, region, and missing names
    - None when there is nobody to download
    """
    watchlist = config_players(args.hero, config)

    if args.account:
        tracked = [{"name": str(a), "account_id": a} for a in args.account]
    else:
        tracked = [{"name": name, "account_id": a} for name, a in watchlist.items()]

    if not tracked:
        print(f"No players tracked for {args.hero}")
        print(
            f'`deadlock leaderboard --hero "{args.hero}"` prints paste-ready lines for '
            "config.toml, or pass specific account IDs with --account"
        )
        return None

    ladder = players.ladder_positions(hero_id)
    watchlisted = set(watchlist.values())

    for t in tracked:
        spot = ladder.get(t["account_id"])

        if spot is None:
            continue

        t["rank"] = spot["rank"]
        t["region"] = spot["region"]

        if str(t["name"]).isdigit() and spot.get("name"):
            t["name"] = spot["name"]

    print(f"Downloading recent {args.hero} games for {len(tracked)} players:")

    for t in tracked:
        if t.get("rank"):
            where = f"rank {t['rank']:<4} {t['region']}"
        elif t["account_id"] in watchlisted:
            where = "tracked"
        else:
            where = "picked"

        print(f"  {t['name']:<18} {where}")

    rows = players.download_matches(tracked, hero_id, n=args.games, archive_dir=args.archive)
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

    watchlist = config_players(args.hero, config)
    top = players.top_players(hero_id, limit=args.players)
    known = {m["account_id"] for m in top}
    top += [
        {"name": name, "account_id": a, "rank": None, "region": "tracked"}
        for name, a in watchlist.items()
        if a not in known
    ]

    print(f"{args.hero} leaderboard:")

    for m in top:
        where = f"rank {m['rank']:<4} {m['region']}" if m.get("rank") else "tracked"

        if m["account_id"] in set(watchlist.values()) and m.get("rank"):
            where += "  tracked"

        print(f"  {m['name']:<20} {m['account_id']:<12} {where}")

        if args.matches:
            for row in players.recent_hero_matches(m["account_id"], hero_id, n=args.matches):
                when = dt.datetime.fromtimestamp(row["start_time"], dt.UTC).strftime("%Y-%m-%d")
                result = "win " if row["match_result"] == row["player_team"] else "loss"
                kda = f"{row['player_kills']}/{row['player_deaths']}/{row['player_assists']}"
                print(f"      {row['match_id']}  {when}  {result}  {kda}")

    fresh = [m for m in top if m["account_id"] not in set(watchlist.values())]

    if fresh:
        print(
            "\nTrack players by pasting lines into config.toml, "
            f'then `deadlock download --hero "{args.hero}"`:'
        )
        print(f"\n[players.{json.dumps(args.hero)}]")

        for m in fresh:
            print(f"{json.dumps(m['name'], ensure_ascii=False)} = {m['account_id']}")


def sync_tables(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Pull matches into the parquet tables from the local archive or the match-history API."""
    accounts = _sync_accounts(args, config)

    if accounts is None:
        return

    if args.source == "api":
        _sync_from_api(args, config, accounts)

    else:
        _sync_from_archive(args, config, accounts)


def _sync_accounts(args: argparse.Namespace, config: str | Path | None) -> list[int] | None:
    """Return the config accounts to sync.

    - prints the fix when none are configured or one is not yours
    """
    configured = set(config_accounts(config) or [])
    requested = getattr(args, "account", None)

    if not requested:
        print("sync needs --account or an [accounts] table in config.toml")
        print("`deadlock accounts` lists the accounts on this PC with their IDs")

        return None

    stray = [a for a in requested if a not in configured]

    if stray:
        listed = ", ".join(str(a) for a in stray)
        print(f"not your accounts: {listed}")
        print("sync only pulls the accounts in your config.toml")

        return None

    return list(requested)


def _sync_from_archive(
    args: argparse.Namespace, config: str | Path | None, accounts: list[int]
) -> None:
    """Snapshot the cache, then export the account matches from the local archive into the tables."""
    sync_archive(args.cache, args.archive)
    exclude = config_exclude(config)

    if getattr(args, "dry_run", False):
        pending = _pending_archive(args.archive, args.parquet, accounts)
        print(f"{pending} archived matches not yet in the tables")
        print("sync filters them to your accounts as it writes")

        return

    if getattr(args, "full", False):
        result = export.export_all(args.archive, args.parquet, exclude, accounts)

    else:
        result = export.export_new(args.archive, args.parquet, exclude, accounts)

    if result.rebuilt:
        print(f"Rebuilt all tables from the archive ({result.rebuilt})")

    _print_table_counts(result.counts)

    if result.skipped:
        print(
            f"Decoded {result.decoded:,} new matches "
            f"and skipped {result.skipped:,} already exported"
        )


def _sync_from_api(
    args: argparse.Namespace, config: str | Path | None, accounts: list[int]
) -> None:
    """Download the raw metadata for the API match history into the archive, then export it."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(config_timezone(config))
    since = getattr(args, "since", None)
    since = dt.date.fromisoformat(since) if since else None
    names = {account_id: name for name, account_id in config_account_names(config).items()}

    def local_day(start_time: int) -> dt.date:
        return dt.datetime.fromtimestamp(start_time, dt.UTC).astimezone(tz).date()

    match_ids: set[int] = set()

    print("Match history per account:")

    for account_id in accounts:
        rows = players.match_history(account_id)
        kept = [r for r in rows if since is None or local_day(r["start_time"]) >= since]

        if kept:
            days = [local_day(r["start_time"]) for r in kept]
            span = f"{min(days)} to {max(days)}"

        else:
            span = "none"

        match_ids.update(r["match_id"] for r in kept)
        label = names.get(account_id, str(account_id))
        print(f"  {label:<18} {len(kept):>5} games   {span}")

    archived = extract.archived_match_ids(args.archive)
    to_get = sorted(match_ids - archived)
    have = len(match_ids & archived)

    print(
        f"\n{len(match_ids)} games in the API: {have} already archived, {len(to_get)} to download"
    )

    if getattr(args, "dry_run", False) or not to_get:
        return

    written, missing = players.download_metadata(to_get, args.archive)
    print(f"Downloaded {written} matches into the archive")

    if missing:
        print(f"{len(missing)} not available from the API")
        print("open those in game to archive them")

    result = export.export_new(args.archive, args.parquet, config_exclude(config), accounts)

    if result.rebuilt:
        print(f"Rebuilt all tables from the archive ({result.rebuilt})")

    _print_table_counts(result.counts)

    print(f"Parquet tables at {_tilde(args.parquet)}")


def _pending_archive(
    archive_dir: str | Path, out_dir: str | Path, accounts: list[int] | None = None
) -> int:
    """Count archived matches not yet written to the tables or dropped by the account filter."""
    archive_ids = {int(p.name.split("_")[0]) for p in Path(archive_dir).glob("*.bin")}
    exported = export.exported_match_ids(Path(out_dir))
    skipped = export.skipped_match_ids(out_dir, accounts)

    return len(archive_ids - exported - skipped)


def _print_table_counts(counts: dict[str, int]) -> None:
    """Print the row count written to each table."""
    for name, n in counts.items():
        print(f"  {name:<16} {n:>8,} rows")
