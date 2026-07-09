import marimo

__generated_with = "0.23.13"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Getting started

    This notebook is the manual way to explore your match data. Every cell is a plain
    polars query over the parquet tables that `deadlock sync` builds, the same tables
    the CLI and the `queries` helpers read.

    Change a cell and everything downstream recomputes. The full list of helpers is in
    the README under *Writing your own queries*, and `deadlock schema [table]` prints
    the data dictionary for any table.

    Every cell follows the accounts picked below, all of them by default.
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


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Your matches

    `queries.my_games()` is one row per match you played, with the match details joined
    in and a `day` column in your local timezone. Note - we are selecting only a subset
    of columns here.
    """)
    return


@app.cell
def _(games, mo, pl):
    mo.ui.table(
        games.sort("start_local", descending=True)
        .with_columns((pl.col("duration_s") // 60).alias("minutes"))
        .select(
            "match_id",
            "day",
            "hero",
            "lane",
            "won",
            "kills",
            "deaths",
            "assists",
            "net_worth",
            "minutes",
        ),
        page_size=10,
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Win rate per hero

    The example from the README using your data.
    """)
    return


@app.cell
def _(games, pl):
    (
        games.group_by("hero")
        .agg(
            pl.len().alias("games"),
            pl.col("won").mean().mul(100).round(1).alias("win_rate"),
        )
        .sort("games", descending=True)
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Your record over time

    `queries.daily_record()` is the frame behind `deadlock winrate`. `cum_net` is the
    running total of wins minus losses.
    """)
    return


@app.cell
def _(accounts, queries):
    _record = queries.daily_record(accounts=accounts, by="day")
    _record.plot.line(x="day", y="cum_net")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Gun stats per hero

    Pick a hero and the chart below recomputes. `queries.final_stats()` has the final
    snapshot of every player in every match, so it gets filtered to your accounts first.
    """)
    return


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
def _(accounts, hero_pick, pl, queries):
    _gun = (
        queries.final_stats()
        .filter(
            pl.col("account_id").is_in(accounts),
            pl.col("hero") == hero_pick.value,
        )
        .group_by("day")
        .agg(pl.col("accuracy", "headshot_rate").mean())
        .sort("day")
        .collect()
        .unpivot(index="day", variable_name="stat")
    )

    _gun.plot.line(x="day", y="value", color="stat")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## What an item is worth

    `queries.item_value()` measures damage per minute owned. The dropdown is
    ordered by how often you build the item and starts on the one that has dealt you
    the most damage. Stat items have no damage source of their own, so they show zero.
    """)
    return


@app.cell
def _(accounts, mo, pl, queries):
    _counts = (
        queries.item_buys(accounts=accounts)
        .group_by("item")
        .len()
        .sort("len", descending=True)
        .collect()
    )

    _dealt = (
        queries.hero_damage()
        .filter(
            pl.col("dealer_account_id").is_in(accounts),
            pl.col("source_name").is_in(_counts["item"].to_list()),
        )
        .group_by("source_name")
        .agg(pl.col("damage").sum())
        .sort("damage", descending=True)
        .collect()
    )

    item_pick = mo.ui.dropdown(
        options=_counts["item"].to_list(),
        value=_dealt.item(0, "source_name")
        if not _dealt.is_empty()
        else _counts.item(0, "item"),
        label="Item",
    )
    item_pick
    return (item_pick,)


@app.cell
def _(accounts, item_pick, mo, queries):
    _value = queries.item_value(item_pick.value, accounts=accounts)

    if _value["per_min"]:
        _verdict = (
            f"It dealt {_value['per_min']:,.0f} damage per minute owned, "
            f"{_value['percent_of_hero_damage']:.1f}% of your hero damage "
            f"while you owned it."
        )
    else:
        _verdict = "It has no damage source of its own, so the damage matrix shows nothing for it."

    mo.md(
        f"You built **{item_pick.value}** {_value['builds']} times. {_verdict}"
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Match breakdown

    Pick a match and the cells below pull it apart. `queries.match_intervals()` splits
    it into five minute chunks of stat gains, the same frame behind `deadlock match`.
    """)
    return


@app.cell
def _(games, mo):
    _recent = games.sort("start_local", descending=True).head(25)

    _options = {
        f"{r['day']} {r['hero']} {'won' if r['won'] else 'lost'} ({r['match_id']})": r
        for r in _recent.iter_rows(named=True)
    }

    match_pick = mo.ui.dropdown(
        options=_options, value=next(iter(_options)), label="Match"
    )
    match_pick
    return (match_pick,)


@app.cell
def _(match_pick, queries):
    queries.match_intervals(
        match_pick.value["match_id"], match_pick.value["account_id"]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Your damage, healing, and prevented healing by source in that match.
    `queries.hero_damage()` keeps only the detail rows against hero targets, since the
    raw `damage` table also carries the match screen totals that double count them.
    """)
    return


@app.cell
def _(match_pick, pl, queries):
    _by_source = pl.concat(
        [
            queries.hero_damage(stat)
            .filter(
                pl.col("match_id") == match_pick.value["match_id"],
                pl.col("dealer_account_id") == match_pick.value["account_id"],
            )
            .group_by("source_name", "delivery")
            .agg(pl.col("damage").sum().alias(stat))
            .collect()
            for stat in ("damage", "healing", "heal_prevented")
        ],
        how="align",
    ).sort("damage", descending=True, nulls_last=True)

    _by_source
    return


if __name__ == "__main__":
    app.run()
