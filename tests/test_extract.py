import bz2

import pytest

from deadlock_matches import extract
from deadlock_matches.extract import pb


def build_meta_bytes(match_id=12345, account_id=42, kills=5):
    contents = pb.CMsgMatchMetaDataContents()
    info = contents.match_info
    info.match_id = match_id
    info.duration_s = 1800

    p = info.players.add()
    p.account_id = account_id
    p.kills = kills

    meta = pb.CMsgMatchMetaData()
    meta.version = 1
    meta.match_id = match_id
    meta.match_details = contents.SerializeToString()

    return meta.SerializeToString()


def write_cache_file(tmp_path, match_id=12345, salt=678, raw=None):
    raw = raw if raw is not None else build_meta_bytes(match_id)
    header = b"replay999.valve.net\x00" + f"/1422450/{match_id}_{salt}.meta.bz2".encode() + b"\x00"

    f = tmp_path / "fakecache"
    f.write_bytes(header + bz2.compress(raw))

    return f


def test_parse_cache_file_extracts_ids(tmp_path):
    f = write_cache_file(tmp_path, match_id=99, salt=777)

    parsed = extract.parse_cache_file(f)

    assert parsed.match_id == 99
    assert parsed.replay_salt == 777
    assert parsed.url == "replay999.valve.net/1422450/99_777.meta.bz2"
    assert parsed.raw == build_meta_bytes(99)


def test_decode_returns_matchinfo(tmp_path):
    raw = build_meta_bytes(match_id=555, account_id=1001, kills=12)

    info = extract.decode(raw)

    assert info.match_id == 555
    assert info.duration_s == 1800
    assert len(info.players) == 1
    assert info.players[0].account_id == 1001
    assert info.players[0].kills == 12


def test_load_end_to_end(tmp_path):
    f = write_cache_file(tmp_path, match_id=321)

    info = extract.load(f)

    assert info.match_id == 321


def test_parse_rejects_non_meta_file(tmp_path):
    f = tmp_path / "junk"
    f.write_bytes(b"avatars.steamstatic.com\x00not a meta")

    with pytest.raises(ValueError, match="not a deadlock meta"):
        extract.parse_cache_file(f)


def test_parse_rejects_missing_bzip(tmp_path):
    f = tmp_path / "nobz"
    f.write_bytes(b"replay1.valve.net\x00/1422450/1_2.meta.bz2\x00no body here")

    with pytest.raises(ValueError, match="no bzip2 body"):
        extract.parse_cache_file(f)


def test_iter_meta_files_finds_written(tmp_path):
    shard = tmp_path / "ab"
    shard.mkdir()
    write_cache_file(shard, match_id=7)
    (tmp_path / "cd").mkdir()
    (tmp_path / "cd" / "avatar").write_bytes(b"avatars.steamstatic.com\x00junk")

    found = list(extract.iter_meta_files(tmp_path))

    assert len(found) == 1
    assert found[0].parent.name == "ab"


def test_default_cache_picks_first_existing(tmp_path):
    missing = tmp_path / "native"
    flatpak = tmp_path / "flatpak"
    flatpak.mkdir()

    assert extract.default_cache((missing, flatpak)) == flatpak


def test_default_cache_prefers_earlier_candidate(tmp_path):
    native = tmp_path / "native"
    flatpak = tmp_path / "flatpak"
    native.mkdir()
    flatpak.mkdir()

    assert extract.default_cache((native, flatpak)) == native


def test_default_cache_falls_back_when_none_exist(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"

    assert extract.default_cache((a, b)) == a


def test_archive_copies_new_entries(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_file(cache, match_id=100, salt=1)
    arc = tmp_path / "arc"

    assert extract.archive(cache, arc) == 1
    assert (arc / "100_1.bin").exists()
    assert extract.archive(cache, arc) == 0


def test_archived_file_still_parses(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_file(cache, match_id=55, salt=9)
    arc = tmp_path / "arc"

    extract.archive(cache, arc)

    info = extract.load(arc / "55_9.bin")

    assert info.match_id == 55


def test_iter_matches_survives_cache_eviction(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    old = write_cache_file(cache, match_id=1, salt=1)
    arc = tmp_path / "arc"

    extract.archive(cache, arc)
    old.unlink()
    write_cache_file(cache, match_id=2, salt=2)

    found = [p.name for p in extract.iter_matches(cache, arc)]

    assert found == ["2_2.bin", "1_1.bin"]


def test_iter_matches_orders_numerically(tmp_path):
    cache = tmp_path / "cache"
    for shard, mid in (("aa", 9), ("bb", 100)):
        d = cache / shard
        d.mkdir(parents=True)
        write_cache_file(d, match_id=mid, salt=1)
    arc = tmp_path / "arc"

    found = [p.name for p in extract.iter_matches(cache, arc)]

    assert found == ["100_1.bin", "9_1.bin"]


def inject_party(player, party):
    raw = player.SerializeToString() + bytes([0x80, 0x01, party])
    player.Clear()
    player.MergeFromString(raw)


def test_player_party_recovered_from_unknown_field():
    info = pb.CMsgMatchMetaDataContents().match_info
    p = info.players.add()
    p.account_id = 42
    p.kills = 5
    inject_party(p, 3)

    assert extract.player_party(p) == 3
    assert p.account_id == 42


def test_player_party_zero_means_solo():
    info = pb.CMsgMatchMetaDataContents().match_info
    p = info.players.add()
    p.account_id = 42
    inject_party(p, 0)

    assert extract.player_party(p) == 0


def test_player_party_none_when_field_absent():
    info = pb.CMsgMatchMetaDataContents().match_info
    p = info.players.add()
    p.account_id = 42
    p.kills = 5

    assert extract.player_party(p) is None


def test_player_party_survives_archive_round_trip(tmp_path):
    contents = pb.CMsgMatchMetaDataContents()
    info = contents.match_info
    info.match_id = 77
    p = info.players.add()
    p.account_id = 42
    inject_party(p, 2)

    meta = pb.CMsgMatchMetaData()
    meta.version = 1
    meta.match_id = 77
    meta.match_details = contents.SerializeToString()

    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_file(cache, match_id=77, salt=1, raw=meta.SerializeToString())
    arc = tmp_path / "arc"

    extract.archive(cache, arc)

    loaded = extract.load(arc / "77_1.bin")

    assert extract.player_party(loaded.players[0]) == 2


def build_custom_stats_info():
    info = pb.CMsgMatchMetaDataContents().match_info
    info.match_id = 100

    for name, stat_id in [("Parry Success", 3), ("Enemy Hero Accuracy##Shots", 5)]:
        reg = info.custom_user_stats.add()
        reg.name = name
        reg.id = stat_id

    p = info.players.add()
    p.account_id = 42

    for t, values in [(180, {3: 1, 5: 200}), (360, {3: 2, 5: 900, 8: 7})]:
        s = p.stats.add()
        s.time_stamp_s = t

        for stat_id, value in values.items():
            cs = s.custom_user_stats.add()
            cs.id = stat_id
            cs.value = value

    return info


def test_custom_stats_resolves_names_and_splits_groups():
    resolved = extract.custom_stats(build_custom_stats_info())

    assert set(resolved[42]) == {
        (180, None, "Parry Success", 1),
        (180, "Enemy Hero Accuracy", "Shots", 200),
        (360, None, "Parry Success", 2),
        (360, "Enemy Hero Accuracy", "Shots", 900),
    }


def test_custom_stats_player_without_data():
    info = build_custom_stats_info()
    b = info.players.add()
    b.account_id = 43

    assert extract.custom_stats(info)[43] == []


def write_steam_tree(tmp_path, deadlock=(42, 43), other=(), vdf=None):
    root = tmp_path / "Steam"
    (root / "appcache/httpcache").mkdir(parents=True)

    for account_id in deadlock:
        (root / f"userdata/{account_id}/1422450").mkdir(parents=True)

    for account_id in other:
        (root / f"userdata/{account_id}").mkdir(parents=True)

    if vdf is not None:
        (root / "config").mkdir(exist_ok=True)
        (root / "config/loginusers.vdf").write_text(vdf)

    return root / "appcache/httpcache"


def vdf_block(steam32, login, persona, timestamp):
    return (
        f'\t"{steam32 + extract.STEAM64_BASE}"\n\t{{\n'
        f'\t\t"AccountName"\t\t"{login}"\n'
        f'\t\t"PersonaName"\t\t"{persona}"\n'
        f'\t\t"Timestamp"\t\t"{timestamp}"\n'
        "\t}\n"
    )


def test_steam_accounts(tmp_path):
    vdf = '"users"\n{\n' + vdf_block(42, "mainlogin", "Main Guy", 200) + "}\n"
    cache = write_steam_tree(tmp_path, deadlock=(42, 43), vdf=vdf)

    found = extract.steam_accounts(cache)

    assert [a.account_id for a in found] == [42, 43]
    assert found[0].login == "mainlogin"
    assert found[0].persona == "Main Guy"
    assert found[0].last_login == 200
    assert found[1].login is None
    assert found[1].persona is None
    assert found[1].last_login == 0


def test_steam_accounts_skips_unrelated_folders(tmp_path):
    cache = write_steam_tree(tmp_path, deadlock=(42, 0), other=(99, "anonymous"))

    found = extract.steam_accounts(cache)

    assert [a.account_id for a in found] == [42]


def test_steam_accounts_sorts_newest_login_first(tmp_path):
    vdf = (
        '"users"\n{\n'
        + vdf_block(42, "older", "older", 100)
        + vdf_block(43, "newer", "newer", 300)
        + "}\n"
    )
    cache = write_steam_tree(tmp_path, deadlock=(42, 43, 44), vdf=vdf)

    found = extract.steam_accounts(cache)

    assert [a.account_id for a in found] == [43, 42, 44]


def test_steam_accounts_without_userdata(tmp_path):
    root = tmp_path / "Steam"
    cache = root / "appcache/httpcache"
    cache.mkdir(parents=True)

    assert extract.steam_accounts(cache) == []


def test_steam_accounts_without_loginusers(tmp_path):
    cache = write_steam_tree(tmp_path, deadlock=(42,))

    found = extract.steam_accounts(cache)

    assert found[0].login is None


def _write_steam_inf(root, version):
    inf = root / "steamapps/common/Deadlock/game/citadel/steam.inf"
    inf.parent.mkdir(parents=True, exist_ok=True)
    inf.write_text(f"ClientVersion={version}\nServerVersion={version}\nappID=1422450\n")

    return inf


def test_installed_client_version_reads_steam_inf(tmp_path):
    cache = tmp_path / "appcache/httpcache"
    _write_steam_inf(tmp_path, 6635)

    assert extract.installed_client_version(cache) == 6635


def test_installed_client_version_checks_library_folders(tmp_path):
    cache = tmp_path / "appcache/httpcache"
    library = tmp_path / "second-drive"
    _write_steam_inf(library, 7000)
    vdf = tmp_path / "steamapps/libraryfolders.vdf"
    vdf.parent.mkdir(parents=True, exist_ok=True)
    vdf.write_text(f'"libraryfolders"\n{{\n\t"1"\n\t{{\n\t\t"path"\t\t"{library}"\n\t}}\n}}\n')

    assert extract.installed_client_version(cache) == 7000


def test_installed_client_version_none_without_an_install(tmp_path):
    assert extract.installed_client_version(tmp_path / "appcache/httpcache") is None
