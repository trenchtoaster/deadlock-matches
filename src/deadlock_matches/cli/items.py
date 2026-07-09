"""Commands judging item value and what top players build."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from deadlock_matches import heroes, items, meta, players, queries
from deadlock_matches.cli import cards
from deadlock_matches.config import format_accounts

if TYPE_CHECKING:
    import argparse


def item_report(args: argparse.Namespace, config: str | Path | None = None) -> None:
    """Print the stat card for an item, or its damage, win rate, and synergy numbers on a hero."""
    item = items.item_by_name(args.item)
    if item is None:
        print(f"Unknown item: {args.item}")
        return

    if getattr(args, "changes", False):
        cards.print_changes(item.name, "item", items.ITEM_HISTORY_PARQUET, item.id)
        return

    when = getattr(args, "as_of", None)

    if when is not None:
        item = items.item_asof(item.id, when) or item

    if args.hero is None:
        cards.item_card(item, when)
        return

    hero_id = heroes.hero_id_by_name(args.hero)
    if hero_id is None:
        print(f"Unknown hero: {args.hero}")
        return

    print(f"{item.name} ({item.slot} tier {item.tier}, {item.cost:,} souls) on {args.hero}\n")

    if args.account:
        ids = format_accounts(args.account, config)
        rows = queries.item_games(
            item.name, args.hero, args.parquet, args.account, args.since
        ).collect()
        built = [
            r
            for r in rows.iter_rows(named=True)
            if r["game_time_s"] is not None and item.class_name
        ]
        skipped_wins = sum(r["won"] for r in rows.iter_rows(named=True)) - sum(
            r["won"] for r in built
        )
        skipped_losses = len(rows) - len(built) - skipped_wins
        window = f" since {args.since}" if args.since else ""
        print(f"Your games (accounts {ids}, {len(rows)} found{window}):\n")

        if built:
            print(f"  {'Match':<10} {'Result':<6} {'Damage':>7} {'Owned':>6} {'% of dmg':>9}")

        dmgs = []
        owned_s = 0.0
        dealt_s = 0.0
        for r in built:
            d = r["damage"] or 0.0
            owned = r["owned_s"]
            dealt = r["dealt_after_buy"] or 0.0
            dmgs.append(d)
            owned_s += owned
            dealt_s += dealt
            percent = f"{d / dealt * 100:.1f}%" if dealt else "-"
            result = "WIN" if r["won"] else "loss"
            print(f"  {r['match_id']:<10} {result:<6} {d:>7,.0f} {owned / 60:>5.0f}m {percent:>9}")

        if built or skipped_wins or skipped_losses:
            print(
                f"\n  {'':<10} {'Games':>6} {'W':>4} {'L':>4} {'Win rate':>9} "
                f"{'Avg dmg':>8} {'Dmg/min':>8} {'% of dmg':>9}"
            )

        if built:
            wins = sum(r["won"] for r in built)
            rate = wins / len(built) * 100
            per_min = f"{sum(dmgs) * 60 / owned_s:,.0f}" if owned_s else "-"
            percent = f"{sum(dmgs) / dealt_s * 100:.1f}%" if dealt_s else "-"
            print(
                f"  {'Built':<10} {len(built):>6} {wins:>4} {len(built) - wins:>4} "
                f"{rate:>8.1f}% {sum(dmgs) / len(dmgs):>8,.0f} {per_min:>8} {percent:>9}"
            )

        if skipped_wins or skipped_losses:
            n = skipped_wins + skipped_losses
            rate = skipped_wins / n * 100
            print(
                f"  {'Not built':<10} {n:>6} {skipped_wins:>4} {skipped_losses:>4} "
                f"{rate:>8.1f}% {'-':>8} {'-':>8} {'-':>9}"
            )

        print()

    players_events = Path(players.PARQUET_DIR) / "item_events.parquet"

    if players_events.exists():
        top = queries.item_value(item.name, parquet_dir=players.PARQUET_DIR, hero=args.hero)

        if top["builds"]:
            percent = top["percent_of_hero_damage"]
            note = f", {percent:.1f}% of their hero damage" if percent else ""
            print(
                f"Top {args.hero} players: {top['per_min']:,.0f} damage per minute owned "
                f"across {top['builds']} builds{note} (deadlock-api.com)\n"
            )
    else:
        print(f'Run `deadlock download --hero "{args.hero}"` to compare against top players\n')

    try:
        badge = meta.min_badge(args.min_rating)
        stats = meta.get_item_stats(hero_id, badge=badge, since=args.since)
    except ValueError as e:
        print(e)
        return

    pool = max((r["matches"] for r in stats), default=0)
    floor = max(100, min(2000, pool // 10))
    v = meta.verdict(stats, item.name, min_matches=floor)
    scope = "all ratings" if badge is None else f"{args.min_rating}+ lobbies"
    print(f"Results ({scope}):")

    if v.get("matches"):
        edge = v["edge_vs_peers"]
        direction = "above" if edge >= 0 else "below"
        print(
            f"  win rate {v['win_rate']:.1f}% over {v['matches']:,} games, usually bought around {v['buy_min']:.0f}m"
        )
        print(
            f"  items at the same price average {v['peer_cost_avg']:.1f}%, "
            f"so it sits {abs(edge):.1f} points {direction} them"
        )
    else:
        print(f"  {v.get('note', 'no data')}")

    pairs = meta.get_item_pairs(hero_id, badge=badge, since=args.since)
    syn = meta.synergies(pairs, stats, item.name, top=args.top, min_matches=floor)
    print("\nBought together (win rate of games with both, vs the item alone):\n")
    print(f"  {'Item':<24} {'Win rate':>8} {'Vs alone':>8} {'Games':>8}")

    for p in syn["pairs"]:
        print(
            f"  {p['name']:<24} {p['pair_win_rate']:>7.1f}% {p['vs_solo']:>+8.1f} {p['matches']:>8,}"
        )


def builds_report(args: argparse.Namespace) -> None:
    """Print the items top players buy on a hero, in wins and in losses."""
    hero_id = heroes.hero_id_by_name(args.hero)
    if hero_id is None:
        print(f"Unknown hero: {args.hero}")
        return

    top = players.top_players(hero_id, limit=args.players)
    print(f"Top {len(top)} {args.hero} players:\n")
    print(f"  {'Player':<18} {'Rank':>5}  {'Region':<9} Record")

    wins, losses = [], []
    for m in top:
        bs = players.player_builds(m["account_id"], hero_id, n=args.games)
        w = [b for b in bs if b["win"]]
        losses += [b for b in bs if not b["win"]]
        wins += w

        print(f"  {m['name']:<18} {m['rank']:>5}  {m['region']:<9} {len(w)}W {len(bs) - len(w)}L")

    aw = players.item_frequency(wins)
    lossmap = {r["name"]: r["percent"] for r in players.item_frequency(losses)["items"]}
    print(f"\nShared core across {aw['n']} winning builds:\n")
    print(f"  {'Item':<24} {'Win %':>6} {'Loss %':>7} {'Median buy':>11}   Slot")

    for r in aw["items"]:
        if r["percent"] < args.min_percent:
            continue

        print(
            f"  {r['name']:<24} {r['percent']:>5}% {lossmap.get(r['name'], 0):>6}% "
            f"{str(r['median_min']) + 'm':>11}   {r['slot']} T{r['tier']}"
        )
