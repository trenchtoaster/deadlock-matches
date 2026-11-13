import bz2

from deadlock_matches import extract
from deadlock_matches.cli.main import main
from deadlock_matches.extract import pb


def write_cache_entry(
    cache_dir,
    match_id=100,
    salt=1,
    start_time=1783000000,
    won=True,
    account=42,
    stats=(),
    damage=(),
    ability_items=(),
    item_events=(),
    accolades=(),
    buffs=(),
    stacks=(),
    custom_stats=(),
    shots=None,
    objectives=False,
    gold_sources=(),
    teammates=0,
    team_gold_sources=(),
    death_log=(),
    lanes=False,
    enemy_worth=None,
    abandon_s=None,
    not_scored=False,
    badges=None,
    paths=False,
    game_mode=None,
    match_mode=None,
    ranked_type=None,
    rank_interval=None,
    hero_id=52,
    rank_points=None,
    rank_assigned=None,
    shield_used=False,
    corrupted_penalty_seed=None,
):
    contents = pb.CMsgMatchMetaDataContents()
    info = contents.match_info
    info.match_id = match_id
    info.start_time = start_time
    info.duration_s = 1800
    info.winning_team = pb.k_ECitadelLobbyTeam_Team1 if won else pb.k_ECitadelLobbyTeam_Team0
    info.not_scored = not_scored
    info.match_mode = pb.k_ECitadelMatchMode_Unranked if match_mode is None else match_mode
    info.game_mode = pb.k_ECitadelGameMode_Normal if game_mode is None else game_mode

    if ranked_type is not None:
        info.ranked_type = ranked_type

    if rank_interval is not None:
        info.rank_interval = rank_interval

    if corrupted_penalty_seed is not None:
        info.corrupted_penalty_seed = corrupted_penalty_seed

    if badges is not None:
        info.average_badge_team0, info.average_badge_team1 = badges

    p = info.players.add()
    p.account_id = account
    p.hero_id = hero_id
    p.team = pb.k_ECitadelLobbyTeam_Team1

    if abandon_s is not None:
        p.abandon_match_time_s = abandon_s

    if rank_points is not None:
        p.player_rank_data.initial_display_rank = 15
        p.player_rank_data.initial_flat_progress, p.player_rank_data.final_flat_progress = (
            rank_points
        )

        if rank_assigned is not None:
            p.player_rank_data.desired_progress_change = rank_assigned

        if shield_used:
            p.player_rank_data.consumed_demotion_protection = True

    mates = []

    for i in range(teammates):
        mate = info.players.add()
        mate.account_id = 43 + i
        mate.hero_id = 2 + i
        mate.team = pb.k_ECitadelLobbyTeam_Team1
        mate.player_slot = 3 + i
        mates.append(mate)

    if stats:
        p.kills = 5
        p.deaths = 2
        p.assists = 8
        p.net_worth = stats[-1][1]
        p.last_hits = 150
        p.denies = 12
        p.player_slot = 1

        enemy = info.players.add()
        enemy.account_id = 77
        enemy.hero_id = 1
        enemy.team = pb.k_ECitadelLobbyTeam_Team0
        enemy.net_worth = enemy_worth if enemy_worth is not None else stats[-1][1] // 2
        enemy.player_slot = 2

        if lanes:
            p.assigned_lane = 1
            enemy.assigned_lane = 1

    sources_at = {}
    for t, source, gold, orbs in gold_sources:
        sources_at.setdefault(t, []).append((source, gold, orbs))

    team_sources_at = {}
    for t, source, gold, orbs in team_gold_sources:
        team_sources_at.setdefault(t, []).append((source, gold, orbs))

    for t, worth, *obj in stats:
        s = p.stats.add()
        s.time_stamp_s = t
        s.net_worth = worth

        if obj:
            s.boss_damage = obj[0]

        for source, gold, orbs in sources_at.get(t, ()):
            gs = s.gold_sources.add()
            gs.source = source
            gs.gold = gold
            gs.gold_orbs = orbs

        for source, gold, orbs in team_sources_at.get(t, ()):
            gs = s.gold_sources.add()
            gs.source = source
            gs.gold = gold
            gs.gold_orbs = orbs

        for mate in mates:
            ms = mate.stats.add()
            ms.time_stamp_s = t
            ms.net_worth = worth

            for source, gold, orbs in team_sources_at.get(t, ()):
                gs = ms.gold_sources.add()
                gs.source = source
                gs.gold = gold
                gs.gold_orbs = orbs

        es = enemy.stats.add()
        es.time_stamp_s = t
        es.net_worth = enemy_worth if enemy_worth is not None else worth // 2

    for item_id, t in ability_items:
        it = p.items.add()
        it.item_id = item_id
        it.game_time_s = t

    for item_id, t, sold, flags, *imbued in item_events:
        it = p.items.add()
        it.item_id = item_id
        it.game_time_s = t
        it.sold_time_s = sold
        it.flags = flags

        if imbued:
            it.imbued_ability_id = imbued[0]

    for accolade_id, value, threshold in accolades:
        acc = p.accolades.add()
        acc.accolade_id = accolade_id
        acc.accolade_stat_value = value
        acc.accolade_threshold_achieved = threshold

    for pickup, count, permanent, *picked in buffs:
        b = p.power_up_buffs.add()
        b.type = pickup
        b.value = count
        b.is_permanent = permanent

        for time_s, stat in picked[0] if picked else ():
            b.pickup_times_s.append(time_s)

            if stat is not None:
                b.pickup_stat_values.append(stat)

    for ability_id, value, is_enemy in stacks:
        st = (enemy if is_enemy else p).ability_stats.add()
        st.ability_id = ability_id
        st.ability_value = value

    for stat_id, (name, _) in enumerate(custom_stats, start=1):
        reg = info.custom_user_stats.add()
        reg.name = name
        reg.id = stat_id

    for stat_id, (_, value) in enumerate(custom_stats, start=1):
        cs = p.stats[-1].custom_user_stats.add()
        cs.id = stat_id
        cs.value = value

    if shots is not None:
        p.stats[-1].shots_hit, p.stats[-1].shots_missed = shots

    if paths:
        mp = info.match_paths
        mp.interval_s = 1.0
        mp.x_resolution = 100
        mp.y_resolution = 100

        track = mp.paths.add()
        track.player_slot = p.player_slot
        track.x_max = 10000.0
        track.y_max = 10000.0
        track.x_pos.extend(range(10))
        track.y_pos.extend([0] * 10)
        track.health.extend([100] * 10)
        track.combat_type.extend([1] * 4 + [0] * 6)
        track.move_type.extend([0, 4, 4, 3, 0, 7, 8, 7, 6, 0])

    for victim_slot, killer_slot, t in death_log:
        victim = p if victim_slot == 1 else enemy
        d = victim.death_details.add()
        d.game_time_s = t
        d.time_to_kill_s = 2.5
        d.death_duration_s = 20
        d.death_pos.x = 1000.0
        d.death_pos.y = 2000.0
        d.death_pos.z = 0.0

        if killer_slot:
            d.killer_player_slot = killer_slot
            d.killer_pos.x = 1000.0 + 10 * 39.37
            d.killer_pos.y = 2000.0
            d.killer_pos.z = 0.0

    if damage:
        dm = info.damage_matrix
        dm.sample_time_s.extend([300, 600])
        dealers = {}

        for j, entry in enumerate(damage):
            name, values, *rest = entry
            dm.source_details.source_name.append(name)
            dm.source_details.stat_type.append(rest[0] if rest else 0)
            dealer_slot = rest[1] if len(rest) > 1 else 1
            target_slot = rest[2] if len(rest) > 2 else 2

            dealer = dealers.get(dealer_slot)

            if dealer is None:
                dealer = dm.damage_dealers.add()
                dealer.dealer_player_slot = dealer_slot
                dealers[dealer_slot] = dealer

            src = dealer.damage_sources.add()
            src.source_details_index = j
            t = src.damage_to_players.add()
            t.target_player_slot = target_slot
            t.damage.extend(values)

    if objectives:
        o = info.objectives.add()
        o.team = pb.k_ECitadelLobbyTeam_Team0
        o.team_objective_id = pb.k_eCitadelTeamObjective_Tier1_Lane1
        o.destroyed_time_s = 400
        o.first_damage_time_s = 100
        o.player_damage = 1000
        o.creep_damage = 200

        mb = info.mid_boss.add()
        mb.destroyed_time_s = 500
        mb.team_killed = pb.k_ECitadelLobbyTeam_Team1
        mb.team_claimed = pb.k_ECitadelLobbyTeam_Team0

    meta = pb.CMsgMatchMetaData()
    meta.match_id = match_id
    meta.match_details = contents.SerializeToString()

    header = b"replay999.valve.net\x00" + f"/1422450/{match_id}_{salt}.meta.bz2".encode() + b"\x00"
    f = cache_dir / f"entry_{match_id}"
    f.write_bytes(header + bz2.compress(meta.SerializeToString()))

    return f


def run_main(tmp_path, *args, accounts="you = 42", extra=""):
    cfg = tmp_path / "config.toml"
    contents = 'timezone = "America/Chicago"'

    if accounts:
        contents += f"\n[accounts]\n{accounts}\n"

    if extra:
        contents += f"\n{extra}\n"

    cfg.write_text(contents)
    (tmp_path / "cache").mkdir(exist_ok=True)

    base = ["--cache", str(tmp_path / "cache"), "--archive", str(tmp_path / "arc")]
    base += ["--parquet", str(tmp_path / "pq")]
    main([*base, *args], config=cfg)


def split_era_cache(tmp_path):
    """Write one game from each side of the build 6652 queue split.

    Before 6652 match_mode 1 was the ranked queue and ranked_type went
    unrecorded. After it, ranked play moved to match_mode 4 and match_mode 1
    became the unranked queue.
    """
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, start_time=1783000000, stats=[(300, 3000)])
    write_cache_entry(
        cache,
        match_id=101,
        start_time=1784000000,
        won=False,
        ranked_type=extract.RANKED_TYPE_UNRANKED,
        stats=[(300, 4000)],
    )
    write_cache_entry(
        cache,
        match_id=102,
        start_time=1784100000,
        match_mode=pb.k_ECitadelMatchMode_Ranked,
        ranked_type=extract.RANKED_TYPE_RANKED,
        rank_interval=1,
        stats=[(300, 5000)],
    )

    return cache
