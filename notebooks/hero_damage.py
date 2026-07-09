import marimo

__generated_with = "0.23.13"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Hero damage and build report

    Pick your accounts and a hero. Every table is your own games from the exported
    parquet: where your damage and souls come from, and how a few build choices line
    up with wins. Run `deadlock history` first so the tables are current.
    """)
    return


@app.cell
def _():
    import marimo as mo
    import polars as pl

    from deadlock_matches import config, queries

    return config, mo, pl, queries


@app.cell
def _(config, mo):
    _names = config.config_account_names()

    account_pick = mo.ui.multiselect(
        options=_names,
        value=list(_names),
        label="Accounts",
    )
    account_pick
    return (account_pick,)


@app.cell
def _(account_pick, mo, queries):
    mo.stop(
        not queries.table_exists("matches"),
        mo.md(
            "**No exported tables yet.** Run `uv run deadlock history` to archive and "
            "export your matches, then rerun this cell."
        ).callout(kind="warn"),
    )

    mo.stop(
        not account_pick.value,
        mo.md(
            "**No accounts picked.** If the picker above is empty, fill in `[accounts]` "
            "in `config.toml` first."
        ).callout(kind="warn"),
    )

    accounts = account_pick.value
    games = queries.my_games(accounts=accounts).collect()
    return accounts, games


@app.cell
def _(games, mo):
    _played = games.group_by("hero").len().sort("len", descending=True)

    hero_pick = mo.ui.dropdown(
        options=sorted(games["hero"].unique()),
        value=_played.item(0, "hero"),
        label="Hero",
    )
    hero_pick
    return (hero_pick,)


@app.cell
def _(games, hero_pick, mo, pl):
    _hero_games = games.filter(pl.col("hero") == hero_pick.value).sort(
        "start_local", descending=True
    )
    _options = {
        f"{r['start_local']:%m-%d %H:%M} {'W' if r['won'] else 'L'} ({r['match_id']})": r[
            "match_id"
        ]
        for r in _hero_games.iter_rows(named=True)
    }

    match_pick = mo.ui.multiselect(options=_options, value=list(_options), label="Matches")
    match_pick
    return (match_pick,)


@app.cell
def _(games, hero_pick, match_pick, pl):
    matches = (
        match_pick.value or games.filter(pl.col("hero") == hero_pick.value)["match_id"].to_list()
    )
    return (matches,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Where your damage comes from

    Every gun, ability, and item source summed across your games of the hero.
    `per_min` is over your minutes on the hero, `percent` is the share of your hero damage.
    """)
    return


@app.cell
def _(accounts, hero_pick, matches, queries):
    queries.damage_by_source(hero_pick.value, accounts=accounts, matches=matches)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Where your souls come from

    `souls` is the in-game figure (guaranteed plus secured orbs), `orb_share` is how
    much of each source arrived as deniable orbs you actually kept.
    """)
    return


@app.cell
def _(accounts, hero_pick, matches, queries):
    queries.souls_by_source(hero_pick.value, accounts=accounts, matches=matches)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Build split by first 6400 item

    Groups your games by which 6400 item you buy first, then compares the outcome.
    Pick the slot to match the hero: `weapon` for gun carries (Ricochet, Magnum),
    `spirit` for casters, or `any` to group on whatever you bought first. `t4_min` is
    when that item landed.
    """)
    return


@app.cell
def _(mo):
    slot_pick = mo.ui.dropdown(
        options=["any", "weapon", "spirit", "vitality"],
        value="any",
        label="Item slot",
    )
    slot_pick
    return (slot_pick,)


@app.cell
def _(accounts, hero_pick, matches, pl, queries, slot_pick):
    _mir = (
        queries.final_stats()
        .filter(
            pl.col("hero") == hero_pick.value,
            pl.col("account_id").is_in(accounts),
            pl.col("match_id").is_in(matches),
        )
        .collect()
    )
    _deaths = (
        queries.scan("deaths")
        .filter(pl.col("account_id").is_in(accounts))
        .group_by("match_id", "account_id")
        .agg(pl.len().alias("deaths"))
        .collect()
    )
    _events = queries.scan("item_events").filter(
        pl.col("account_id").is_in(accounts),
        pl.col("cost") == 6400,
    )

    if slot_pick.value != "any":
        _events = _events.filter(pl.col("slot") == slot_pick.value)

    _first = (
        _events.sort("game_time_s")
        .group_by("match_id", "account_id")
        .agg(
            pl.col("item").first().alias("first_t4"),
            pl.col("game_time_s").first().alias("t4_t"),
        )
        .collect()
    )
    (
        _mir.select("match_id", "account_id", "won", "player_damage", "net_worth")
        .join(_deaths, on=["match_id", "account_id"], how="left")
        .join(_first, on=["match_id", "account_id"], how="left")
        .with_columns(
            pl.col("deaths").fill_null(0),
            pl.col("first_t4").fill_null("(none reached)"),
        )
        .group_by("first_t4")
        .agg(
            pl.len().alias("games"),
            (pl.col("won").mean() * 100).round(0).alias("win_percent"),
            pl.col("player_damage").mean().round(0).alias("avg_dmg"),
            pl.col("deaths").mean().round(1).alias("deaths"),
            pl.col("net_worth").mean().round(0).alias("net_worth"),
            (pl.col("t4_t").mean() / 60).round(1).alias("t4_min"),
        )
        .select("games", "first_t4", "win_percent", "avg_dmg", "deaths", "net_worth", "t4_min")
        .sort("games", descending=True)
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Build split by ability maxed first

    Which of the three damage abilities you fully max first, and how kills, deaths,
    damage, and farm compare. Set the abilities below to match your hero.
    """)
    return


@app.cell
def _(accounts, hero_pick, matches, pl, queries):
    friendly = {"Dust Devil": "tornado", "Djinn's Mark": "mark", "Fire Scarabs": "scarabs"}

    _mir = (
        queries.final_stats()
        .filter(
            pl.col("hero") == hero_pick.value,
            pl.col("account_id").is_in(accounts),
            pl.col("match_id").is_in(matches),
        )
        .collect()
    )
    _deaths = (
        queries.scan("deaths")
        .filter(pl.col("account_id").is_in(accounts))
        .group_by("match_id", "account_id")
        .agg(pl.len().alias("deaths"))
        .collect()
    )
    _kills = (
        queries.scan("deaths")
        .filter(pl.col("killer_account_id").is_in(accounts))
        .group_by("match_id", pl.col("killer_account_id").alias("account_id"))
        .agg(pl.len().alias("kills"))
        .collect()
    )
    _maxed = (
        queries.ability_upgrades()
        .filter(
            pl.col("account_id").is_in(accounts),
            pl.col("ability_upgrade_n") == 4,
            pl.col("ability").is_in(list(friendly)),
        )
        .group_by("match_id", "account_id")
        .agg(pl.col("ability").sort_by("game_time_s").first().alias("maxed_first"))
        .with_columns(pl.col("maxed_first").replace(friendly))
        .collect()
    )
    (
        _mir.select("match_id", "account_id", "won", "player_damage", "net_worth")
        .join(_maxed, on=["match_id", "account_id"], how="left")
        .join(_kills, on=["match_id", "account_id"], how="left")
        .join(_deaths, on=["match_id", "account_id"], how="left")
        .with_columns(
            pl.col("maxed_first").fill_null("none maxed"),
            pl.col("kills").fill_null(0),
            pl.col("deaths").fill_null(0),
        )
        .group_by("maxed_first")
        .agg(
            pl.len().alias("games"),
            (pl.col("won").mean() * 100).round(0).alias("win_percent"),
            pl.col("kills").mean().round(1).alias("kills"),
            pl.col("deaths").mean().round(1).alias("deaths"),
            pl.col("player_damage").mean().round(0).alias("avg_dmg"),
            pl.col("net_worth").mean().round(0).alias("net_worth"),
        )
        .select("games", "maxed_first", "win_percent", "kills", "deaths", "avg_dmg", "net_worth")
        .sort("games", descending=True)
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Item cost efficiency

    Each damaging item's damage per minute owned, and per 1000 souls spent. Late
    closeout buys are owned briefly, so per-minute-owned reads them fairer than a
    raw total. `item_value()` is the single-item version of this.
    """)
    return


@app.cell
def _(accounts, hero_pick, matches, pl, queries):
    _hero = hero_pick.value
    _sources = queries.damage_by_source(_hero, accounts=accounts, matches=matches)
    _items = _sources.filter(pl.col("delivery").is_in(["gun_proc", "spirit_proc"]))["source_name"]
    _cost = dict(
        queries.scan("item_events")
        .filter(pl.col("account_id").is_in(accounts))
        .group_by("item")
        .agg(pl.col("cost").max())
        .collect()
        .iter_rows()
    )
    _rows = []
    for _name in _items:
        _b = (
            queries.item_games(_name, _hero)
            .collect()
            .filter(
                pl.col("account_id").is_in(accounts),
                pl.col("match_id").is_in(matches),
                pl.col("owned_s") > 0,
            )
        )
        if _b.is_empty() or _cost.get(_name, 0) == 0:
            continue

        _tot = _b["damage"].sum()
        _dpm = _tot / (_b["owned_s"].sum() / 60)
        _rows.append(
            {
                "games": len(_b),
                "item": _name,
                "total": int(_tot),
                "cost": _cost[_name],
                "buy_min": round(_b["game_time_s"].mean() / 60, 1),
                "owned_min": round(_b["owned_s"].mean() / 60, 1),
                "dmg/min_owned": round(_dpm),
                "per_1k": round(_dpm / (_cost[_name] / 1000), 1),
            }
        )

    pl.DataFrame(_rows).sort("per_1k", descending=True)
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
