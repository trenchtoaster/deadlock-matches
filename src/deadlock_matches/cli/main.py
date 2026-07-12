"""Argument parsing and dispatch for the deadlock command."""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

from deadlock_matches import export, extract, paths, players, queries, schemas
from deadlock_matches.cli import cards, data, items, meta, performance
from deadlock_matches.config import (
    config_account_names,
    config_accounts,
    config_exclude,
    ensure_config,
    find_config,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

AS_OF_HELP = (
    "show the card as the game was on this date (YYYY-MM-DD), like 2026-03-01, "
    "from the versioned asset history; defaults to the current patch"
)
CHANGES_HELP = "list every patch that changed this, from the versioned asset history, and quit"

COMMAND_HELP = {
    "sync": "pull your matches into the parquet tables from the archive or the API",
    "history": "one line per game of yours with the match ID",
    "match": "one match: the final scoreboard, then your intervals of souls and damage",
    "winrate": "wins and losses per day",
    "laning": "whether winning your lane or a feeding teammate decides your games",
    "deaths": "how you die: when, to whom, alone or ganked",
    "leaderboard": "the current top players of a hero, with paste-ready lines for config.toml",
    "download": "fetch recent games from your tracked players into their own tables",
    "compare": "your stats vs your tracked players, minute by minute",
    "movement": "movement profile on one hero, you vs your tracked players",
    "builds": "the items your tracked players buy, in wins and in losses",
    "item": "item stat card, plus whether it is worth buying on a hero",
    "hero": "base stats and boon gains, or stats at a breakpoint",
    "ability": "base numbers, spirit scaling and tier upgrades",
    "meta": "public hero win rates and pick rates across all matches",
    "assets": "redownload heroes.json / items.json (run after a patch)",
    "accounts": "Steam accounts on this PC that have run Deadlock, for config.toml",
    "schema": "column docs for the parquet tables (the data dictionary)",
}

SECTIONS = (
    ("your matches", ("sync", "history", "match", "winrate", "laning", "deaths")),
    (
        "the players you track (config.toml [players], data via download)",
        ("leaderboard", "download", "compare", "movement", "builds", "item"),
    ),
    ("game knowledge", ("hero", "ability", "meta", "assets")),
    ("setup", ("accounts", "schema")),
)


def _command_sections() -> str:
    """Render the grouped command list for the top-level help."""
    lines = []

    for title, names in SECTIONS:
        lines.append(f"{title}:")
        lines.extend(f"  {name:<12} {COMMAND_HELP[name]}" for name in names)
        lines.append("")

    return "\n".join(lines).rstrip()


def parse_accounts(v: str, names: dict[str, int] | None = None) -> list[int]:
    """Turn "id1,id2" or account names from config.toml like "main" into Steam32 account IDs.

    - names with spaces need commas between accounts, ids also split on spaces
    """
    lookup = {name.lower(): a for name, a in (names or {}).items()}
    ids = []

    for part in v.split(","):
        part = part.strip()

        if part.lower() in lookup:
            ids.append(lookup[part.lower()])
            continue

        for token in part.split():
            if token.lower() in lookup:
                ids.append(lookup[token.lower()])
            elif token.isdigit():
                ids.append(int(token))
            else:
                known = ", ".join(names) if names else "none set"
                msg = f"unknown account {token!r}, config.toml account names: {known}"
                raise argparse.ArgumentTypeError(msg)

    return ids


def int_list(v: str) -> list[int]:
    """Parse "id1,id2" or space-separated ids into a list of ints, for match and account IDs."""
    ids = []

    for token in v.replace(",", " ").split():
        if not token.isdigit():
            msg = f"not a numeric id: {token!r}"
            raise argparse.ArgumentTypeError(msg)

        ids.append(int(token))

    return ids


def build_parser(config: str | Path | None = None) -> argparse.ArgumentParser:
    """Build the CLI parser, where --account defaults to the accounts in config.toml."""
    accounts = config_accounts(config)
    names = config_account_names(config)

    def account_list(v: str) -> list[int]:
        return parse_accounts(v, names)

    ap = argparse.ArgumentParser(
        prog="deadlock",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=_command_sections(),
    )
    ap.add_argument(
        "--cache",
        default=str(extract.DEFAULT_CACHE),
        help="Steam httpcache folder, detected automatically",
    )
    ap.add_argument(
        "--archive", default=str(extract.ARCHIVE_DIR), help="where match protobufs are archived"
    )
    ap.add_argument(
        "--parquet", default=str(export.PARQUET_DIR), help="where the parquet tables are written"
    )
    sub = ap.add_subparsers(dest="cmd", metavar="<command>")

    def command(name: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, description=COMMAND_HELP[name])

    d = command("history")
    d.add_argument(
        "--days", type=int, default=None, help="your last N days of games instead of the last 10"
    )
    d.add_argument(
        "--account",
        type=account_list,
        default=accounts,
        help="only matches where these accounts (IDs or names from config.toml) played, "
        "defaults to config.toml. Matches you only viewed in game stay hidden unless "
        "you name their players",
    )
    d.add_argument(
        "--since",
        default=None,
        help="only matches on or after this date (YYYY-MM-DD), like 2026-07-01",
    )

    it = command("item")
    it.add_argument("item", help='item display name, like "Escalating Exposure"')
    it.add_argument(
        "--hero",
        default=None,
        help="analyze the item on this hero: your win rate with it built vs not, top "
        "players' damage with it, and its public win rate. Omit for just the stat card",
    )
    it.add_argument(
        "--account",
        type=account_list,
        default=accounts,
        help="your account IDs or names from config.toml, comma-separated, "
        "to include your own games",
    )
    it.add_argument(
        "--top", type=int, default=10, help="how many items to show in the bought together table"
    )
    it.add_argument(
        "--min-rating",
        default="Eternus",
        help="meta stats only count lobbies at this average skill rating or higher, "
        "like Eternus, 'all' disables",
    )
    it.add_argument(
        "--since",
        default=None,
        help="only count matches on or after this date (YYYY-MM-DD), like 2026-06-30, "
        "for both your games and the meta stats",
    )
    it.add_argument("--as-of", type=dt.date.fromisoformat, default=None, help=AS_OF_HELP)
    it.add_argument("--changes", action="store_true", help=CHANGES_HELP)

    b = command("builds")
    b.add_argument("--hero", required=True, help="hero display name, like Mirage")
    b.add_argument(
        "--min-percent",
        type=int,
        default=30,
        help="hide items bought in fewer than this percent of builds",
    )

    c = command("compare")
    c.add_argument("--hero", required=True, help="hero display name, like Mirage")
    c.add_argument(
        "--account",
        type=account_list,
        default=accounts,
        help="your account IDs or names from config.toml, defaults to all accounts there",
    )
    c.add_argument(
        "--stat",
        default="souls",
        help=f"{', '.join(queries.COMPARE_STATS)}, "
        "or soul_sources (every income source as one gap table)",
    )
    c.add_argument("--interval", type=int, default=5, help="interval length in minutes")
    c.add_argument(
        "--since",
        default=None,
        help="only your games on or after this date (YYYY-MM-DD), like 2026-06-30, "
        "to keep the comparison inside one patch window",
    )

    mt = command("match")
    mt.add_argument(
        "match_id",
        nargs="?",
        type=int,
        default=None,
        help="match ID, defaults to your most recent match",
    )
    mt.add_argument(
        "--account",
        type=account_list,
        default=accounts,
        help="your account IDs or names from config.toml, defaults to all accounts there",
    )
    mt.add_argument(
        "--hero",
        default=None,
        help="show another player from the match instead of you, by hero name, like Wraith",
    )
    mt.add_argument("--interval", type=int, default=5, help="interval length in minutes")
    mt.add_argument(
        "--ago",
        type=int,
        default=0,
        help="step back from your latest match, 0 is latest, 1 is the one before",
    )
    view = mt.add_mutually_exclusive_group()
    view.add_argument(
        "--souls",
        action="store_true",
        help="souls by source per interval, like the in game souls graph, grouped "
        "into lane, roaming, combat, and objectives",
    )
    view.add_argument(
        "--damage",
        action="store_true",
        help="damage to heroes by source per interval, like the in game source graph, "
        "plus the same damage split per enemy",
    )
    view.add_argument(
        "--healing",
        action="store_true",
        help="healing by source per interval, plus the healing your anti-heal prevented",
    )
    view.add_argument(
        "--teams",
        action="store_true",
        help="both teams per interval: souls and the lead, plus every objective "
        "and Rejuvenator as it fell",
    )
    view.add_argument(
        "--deaths",
        action="store_true",
        help="the damage each enemy dealt to you per interval, then each death with "
        "the killer, the game time, the fight length, the killer distance, and the "
        "respawn timer",
    )
    view.add_argument(
        "--kills",
        action="store_true",
        help="the damage you dealt to each enemy per interval, then each kill with "
        "the victim, the game time, the distance, and the respawn it cost them",
    )
    view.add_argument(
        "--laning",
        type=int,
        nargs="?",
        const=9,
        default=None,
        metavar="MINUTES",
        help="the laning phase lane by lane through the first MINUTES minutes "
        "(default 9, matching the snapshot cadence): team and player stat rows "
        "per lane with the diff, the lane kills, and guardian falls",
    )
    view.add_argument(
        "--abilities",
        action="store_true",
        help="ability unlocks and upgrades in game-time order",
    )
    view.add_argument(
        "--items",
        action="store_true",
        help="every item purchase in buy order, with when it was sold, what upgrade "
        "consumed it, and the ability it was imbued into",
    )
    view.add_argument(
        "--accolades",
        action="store_true",
        help="the end of match stat awards: your number and stars for each graded "
        "stat, including stats no other table records (gun/melee/ability kills, "
        "close and long range kills, killstreaks, urn deliveries)",
    )
    view.add_argument(
        "--buffs",
        action="store_true",
        help="permanent buffs per family and level with the stats they added, "
        "valued at the patch the match was played on, plus the bridge buffs "
        "claimed and where the permanent buffs came from (statues, sinner "
        "jackpots, mid boss kills)",
    )
    view.add_argument(
        "--stacks",
        action="store_true",
        help="stack counts for every player in the match, from the abilities "
        "and items that track stacks (Sticky Bomb stacks, Trophy Collector, etc)",
    )
    view.add_argument(
        "--combat",
        action="store_true",
        help="fight stats the game tracks but never shows: the lobby ranked "
        "by aim against heroes, the fire the enemy team put at you, damage "
        "by range, parries, comeback souls, and per-hero counters",
    )
    view.add_argument(
        "--movement",
        action="store_true",
        help="how you moved per interval: meters covered and the pace while "
        "moving, time standing still, sliding, in the air, on ziplines, and "
        "in fights, plus dashes and air dashes",
    )

    f = command("download")
    f.add_argument(
        "--hero",
        default=None,
        help="hero the players are tracked for, like Mirage. Without --account this "
        "downloads everyone under [players.<Hero>] in config.toml",
    )
    f.add_argument(
        "--match",
        type=int_list,
        default=None,
        help="specific match ID(s), comma-separated: stores every player in them, no --hero needed",
    )
    f.add_argument(
        "--account",
        type=int_list,
        default=None,
        help="account ID(s) to download from instead of the tracked players, comma-separated, "
        "needs --hero. Their games archive for `deadlock match` but only players in "
        "config.toml join the comparisons",
    )
    f.add_argument("--games", type=int, default=5, help="recent ranked games per player")
    f.add_argument("--out", default=str(players.PARQUET_DIR), help="players parquet directory")

    sy = command("sync")
    sy.add_argument(
        "--source",
        choices=("local", "api"),
        default="local",
        help="the local archive (default) or the match-history API",
    )
    sy.add_argument(
        "--account",
        type=account_list,
        default=accounts,
        help="account IDs or names from config.toml, defaults to every config account",
    )
    sy.add_argument(
        "--full",
        action="store_true",
        help="rebuild every table from scratch instead of adding only new matches",
    )
    sy.add_argument(
        "--since", default=None, help="only api matches on or after this date (YYYY-MM-DD)"
    )
    sy.add_argument(
        "--dry-run", action="store_true", help="show what would be written without writing anything"
    )

    mn = command("leaderboard")
    mn.add_argument("--hero", required=True, help="hero display name, like Mirage")
    mn.add_argument("--players", type=int, default=8, help="how many top players to list")
    mn.add_argument(
        "--matches",
        nargs="?",
        const=5,
        type=int,
        default=None,
        metavar="N",
        help="also list the recent ranked match IDs per player (default 5)",
    )

    de = command("deaths")
    de.add_argument(
        "--account",
        type=account_list,
        default=accounts,
        help="your account IDs or names from config.toml, defaults to all accounts there",
    )
    de.add_argument("--hero", default=None, help="hero display name, like Mirage")
    de.add_argument("--days", type=int, default=None, help="only your last N days of games")
    de.add_argument(
        "--since",
        default=None,
        help="only days on or after this date (YYYY-MM-DD), like 2026-07-01",
    )
    de.add_argument(
        "--radius",
        type=int,
        default=2000,
        help="units counted as nearby for the ally/enemy context",
    )

    mv = command("movement")
    mv.add_argument("--hero", required=True, help="hero display name, like Mirage")
    mv.add_argument(
        "--by",
        choices=("player",),
        default=None,
        help="one row per tracked player instead of the pooled Tracked column, with "
        "their games, ladder rank at download time, and the same metrics",
    )
    mv.add_argument(
        "--account",
        type=account_list,
        default=accounts,
        help="your account IDs or names from config.toml, defaults to all accounts there",
    )

    dy = command("winrate")
    dy.add_argument(
        "--account",
        type=account_list,
        default=accounts,
        help="your account IDs or names from config.toml, defaults to all accounts there",
    )
    dy.add_argument("--days", type=int, default=None, help="only your last N days of games")
    dy.add_argument(
        "--since",
        default=None,
        help="only days on or after this date (YYYY-MM-DD or YYYYMMDD), like 2026-07-01",
    )
    dy.add_argument(
        "--by",
        choices=("day", "week", "month"),
        default="day",
        help="group the table by day, week, or month",
    )
    dy.add_argument("--hero", default=None, help="hero display name, like Mirage")
    dy.add_argument(
        "--min-rating",
        default="Eternus",
        help="with --hero, the public win rate line only counts lobbies at this average "
        "skill rating or higher, 'all' disables",
    )

    ln = command("laning")
    ln.add_argument(
        "--account",
        type=account_list,
        default=accounts,
        help="your account IDs or names from config.toml, defaults to all accounts there",
    )
    ln.add_argument("--days", type=int, default=None, help="only your last N days of games")
    ln.add_argument(
        "--since",
        default=None,
        help="only days on or after this date (YYYY-MM-DD or YYYYMMDD), like 2026-07-01",
    )
    ln.add_argument("--hero", default=None, help="hero display name, like Mirage")
    ln.add_argument(
        "--minutes",
        type=int,
        default=9,
        help="laning window in minutes, default 9 like match --laning",
    )

    he = command("hero")
    he.add_argument("hero", help="hero display name, like Mirage")
    he.add_argument("--souls", type=int, default=None, help="total souls earned")
    he.add_argument("--level", type=int, default=None, help="level, instead of souls")
    he.add_argument("--as-of", type=dt.date.fromisoformat, default=None, help=AS_OF_HELP)
    he.add_argument("--changes", action="store_true", help=CHANGES_HELP)

    ab = command("ability")
    ab.add_argument("ability", help='ability display name, like "Dust Devil"')
    ab.add_argument(
        "--hero",
        default=None,
        help="hero display name, for ability names that exist on several heroes",
    )
    ab.add_argument(
        "--souls", type=int, default=None, help="resolve boon scaling at this soul count"
    )
    ab.add_argument("--level", type=int, default=None, help="level, instead of souls")
    ab.add_argument(
        "--spirit",
        type=float,
        default=None,
        help="resolve scaling at this total spirit power, the number the in-game "
        "stat screen shows, items included",
    )
    ab.add_argument(
        "--melee",
        type=float,
        default=None,
        help="resolve melee scaling at this light melee damage, the number the in-game "
        "stat screen shows, items included; heavy melee keeps the hero's ratio",
    )
    ab.add_argument(
        "--weapon",
        type=float,
        default=None,
        help="resolve weapon scaling at this bonus weapon damage percent, the number "
        "the in-game stat screen shows, items and weapon shop investment included",
    )
    ab.add_argument("--as-of", type=dt.date.fromisoformat, default=None, help=AS_OF_HELP)
    ab.add_argument("--changes", action="store_true", help=CHANGES_HELP)

    me = command("meta")
    me.add_argument("--hero", default=None, help="one hero's numbers per bucket, like Mirage")
    me.add_argument(
        "--by",
        choices=sorted(meta.BUCKETS),
        default=None,
        help="split into buckets: rating (Oracle 3) or day/week/month",
    )
    me.add_argument(
        "--min-rating",
        default="all",
        help="only count lobbies at this average skill rating or higher, like Eternus",
    )
    me.add_argument("--since", default=None, help="only matches on or after this date (YYYY-MM-DD)")
    me.add_argument(
        "--until", default=None, help="only matches on or before this date (YYYY-MM-DD)"
    )

    command("accounts")

    at = command("assets")
    at.add_argument(
        "--backfill",
        action="store_true",
        help="build the versioned asset history instead of the current snapshot",
    )
    at.add_argument(
        "--confirm",
        action="store_true",
        help="run the backfill, otherwise it only says what it would do",
    )
    at.add_argument(
        "--full",
        action="store_true",
        help="rescan every build instead of resuming from the last stored era",
    )
    at.add_argument(
        "--seed",
        action="store_true",
        help="write the bundled seed instead of your user store (maintainer, source checkout)",
    )

    sc = command("schema")
    sc.add_argument(
        "table", nargs="?", default=None, help="one table name, all tables when omitted"
    )
    sc.add_argument(
        "--sample",
        nargs="?",
        const=5,
        type=int,
        default=None,
        metavar="N",
        help="also print the first N parquet rows for one table (default: 5)",
    )

    return ap


def schema_report(args: argparse.Namespace) -> None:
    """Print schema docs and, optionally, a few rows from the matching parquet table."""
    if args.sample is not None and args.table is None:
        print("--sample needs a table name, for example: deadlock schema players --sample")
        return

    if args.sample is not None and args.sample < 1:
        print("--sample must be at least 1")
        return

    print(schemas.describe(args.table))

    if args.sample is None:
        return

    path = schemas.table_path(args.table, args.parquet)

    if not queries.table_exists(args.table, args.parquet):
        print(f"\nNo parquet file at {paths.tilde(path)}")

        if args.table in schemas.ASSET_TABLES:
            print("Run deadlock sync to write the asset tables from the committed history.")

        return

    frame = queries.scan(args.table, args.parquet).head(args.sample).collect()
    print(f"\nSample rows from {paths.tilde(path)}:")

    with pl.Config(tbl_rows=args.sample, tbl_cols=-1, tbl_width_chars=240):
        print(frame)


def main(argv: Sequence[str] | None = None, config: str | Path | None = None) -> None:
    """Entry point for the deadlock CLI."""
    args = build_parser(config).parse_args(argv)

    if config is None:
        ensure_config()

    card_only = args.cmd == "item" and args.hero is None

    if (
        args.cmd
        in (None, "history", "item", "compare", "winrate", "laning", "deaths", "movement", "match")
        and not card_only
    ):
        new = data.sync_archive(args.cache, args.archive, quiet=True)

        if new:
            accounts = config_accounts(config)

            if accounts:
                data.refresh_tables(
                    args.archive, args.parquet, accounts, config_exclude(config), quiet=True
                )

    needs_account = args.cmd in (
        "history",
        "compare",
        "winrate",
        "laning",
        "deaths",
        "movement",
    ) or (args.cmd == "match" and (args.match_id is None or args.hero is None))

    if needs_account and not args.account:
        print(f"No account set: pass --account or add one to {paths.tilde(find_config())}")
        print("`deadlock accounts` lists the accounts on this PC with their IDs")
        return

    if args.cmd == "schema":
        try:
            schema_report(args)
        except ValueError as e:
            print(e)
    elif args.cmd == "item":
        items.item_report(args, config)
    elif args.cmd == "builds":
        items.builds_report(args, config)
    elif args.cmd == "compare":
        performance.compare_report(args, config)
    elif args.cmd == "match":
        performance.match_report(args, config)
    elif args.cmd == "download":
        data.download_matches(args, config)
    elif args.cmd == "sync":
        data.sync_tables(args, config)
    elif args.cmd == "leaderboard":
        data.leaderboard_report(args, config)
    elif args.cmd == "winrate":
        performance.winrate_report(args, config)
    elif args.cmd == "laning":
        performance.laning_games_report(args, config)
    elif args.cmd == "deaths":
        performance.deaths_report(args, config)
    elif args.cmd == "movement":
        performance.movement_report(args, config)
    elif args.cmd == "hero":
        cards.hero_report(args)
    elif args.cmd == "ability":
        cards.ability_report(args)
    elif args.cmd == "meta":
        meta.meta_report(args)
    elif args.cmd == "accounts":
        data.list_accounts(args, config)
    elif args.cmd == "assets" and args.backfill:
        data.rebuild_history(args)
    elif args.cmd == "assets":
        data.refresh_assets(args)
    else:
        data.match_history(args, config)


if __name__ == "__main__":
    main()
