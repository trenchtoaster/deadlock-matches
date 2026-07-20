import email.message
import email.utils
import gzip
import json
import os
import time
import urllib.error
import urllib.request

import pytest

from deadlock_matches import api


def _http_error(code, retry_after=None):
    headers = email.message.Message()

    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)

    return urllib.error.HTTPError("http://x", code, "err", headers, None)


class _Response:
    def __init__(self, body: bytes):
        self._body = body

    def read(self, *args):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_urlopen(payload, calls):
    def opener(req, timeout=None):
        calls.append(req)

        return _Response(json.dumps(payload).encode())

    return opener


def test_get_json_caches_the_download(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(api, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen({"rank": 1}, calls))

    data = api.get_json("v1/leaderboard/Asia")

    assert data == {"rank": 1}
    assert len(calls) == 1
    assert api.cache_path("v1/leaderboard/Asia").exists()


def test_get_json_reads_cache_without_redownloading(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(api, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen({"rank": 1}, calls))

    first = api.get_json("v1/leaderboard/Asia")
    second = api.get_json("v1/leaderboard/Asia")

    assert first == second
    assert len(calls) == 1


def test_get_json_use_cache_false_redownloads(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(api, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen({"rank": 1}, calls))

    api.get_json("v1/assets/heroes", use_cache=False)
    api.get_json("v1/assets/heroes", use_cache=False)

    assert len(calls) == 2
    assert not api.cache_path("v1/assets/heroes").exists()


def test_cache_filename_flattens_path_and_query(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen([], []))

    api.get_json("v1/analytics/item-stats?hero_id=52&comb=2")

    assert (tmp_path / "v1_analytics_item-stats_hero_id=52_comb=2.json").exists()


def test_get_json_max_age_serves_fresh_cache(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(api, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen({"rank": 1}, calls))

    api.get_json("v1/leaderboard/Asia", max_age=api.DAY)
    api.get_json("v1/leaderboard/Asia", max_age=api.DAY)

    assert len(calls) == 1


def test_get_json_max_age_refetches_expired_cache(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(api, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen({"rank": 1}, calls))

    api.get_json("v1/leaderboard/Asia", max_age=api.DAY)

    stale = time.time() - api.DAY - 60
    os.utime(api.cache_path("v1/leaderboard/Asia"), (stale, stale))

    api.get_json("v1/leaderboard/Asia", max_age=api.DAY)

    assert len(calls) == 2


def test_get_json_serves_expired_cache_when_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen({"rank": 1}, []))

    api.get_json("v1/leaderboard/Asia", max_age=api.DAY)

    stale = time.time() - api.DAY - 60
    os.utime(api.cache_path("v1/leaderboard/Asia"), (stale, stale))

    def offline(req, timeout=None):
        raise OSError("no network")

    monkeypatch.setattr(urllib.request, "urlopen", offline)

    assert api.get_json("v1/leaderboard/Asia", max_age=api.DAY) == {"rank": 1}


def test_get_json_offline_without_cache_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "CACHE_DIR", tmp_path)

    def offline(req, timeout=None):
        raise OSError("no network")

    monkeypatch.setattr(urllib.request, "urlopen", offline)

    with pytest.raises(OSError, match="no network"):
        api.get_json("v1/leaderboard/Asia")


def test_get_json_429_without_cache_raises_rate_limited(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "CACHE_DIR", tmp_path)

    def limited(req, timeout=None):
        raise _http_error(429, 7)

    monkeypatch.setattr(urllib.request, "urlopen", limited)

    with pytest.raises(api.RateLimited) as exc:
        api.get_json("v1/matches/900/salts", use_cache=False)

    assert exc.value.retry_after == 7.0


def test_get_json_429_serves_stale_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen({"rank": 1}, []))

    api.get_json("v1/leaderboard/Asia", max_age=api.DAY)

    stale = time.time() - api.DAY - 60
    os.utime(api.cache_path("v1/leaderboard/Asia"), (stale, stale))

    def limited(req, timeout=None):
        raise _http_error(429, 7)

    monkeypatch.setattr(urllib.request, "urlopen", limited)

    assert api.get_json("v1/leaderboard/Asia", max_age=api.DAY) == {"rank": 1}


def test_get_bytes_429_raises_rate_limited(monkeypatch):
    def limited(req, timeout=None):
        raise _http_error(429)

    monkeypatch.setattr(urllib.request, "urlopen", limited)

    with pytest.raises(api.RateLimited) as exc:
        api.get_bytes("http://x")

    assert exc.value.retry_after == 60.0


@pytest.mark.parametrize("header", ["-5", "nan", "inf", "soon"])
def test_retry_after_rejects_malformed_waits(monkeypatch, header):
    def limited(req, timeout=None):
        raise _http_error(429, header)

    monkeypatch.setattr(urllib.request, "urlopen", limited)

    with pytest.raises(api.RateLimited) as exc:
        api.get_bytes("http://x")

    assert exc.value.retry_after == 60.0


def test_retry_after_reads_http_dates(monkeypatch):
    when = email.utils.formatdate(time.time() + 120, usegmt=True)

    def limited(req, timeout=None):
        raise _http_error(429, when)

    monkeypatch.setattr(urllib.request, "urlopen", limited)

    with pytest.raises(api.RateLimited) as exc:
        api.get_bytes("http://x")

    assert 0 <= exc.value.retry_after <= 120


def test_get_bytes_other_http_errors_return_none(monkeypatch):
    def gone(req, timeout=None):
        raise _http_error(404)

    monkeypatch.setattr(urllib.request, "urlopen", gone)

    assert api.get_bytes("http://x") is None


def test_get_json_permanent_stores_in_data_dir(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(api, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(api, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen({"match_info": {}}, calls))

    api.get_json("v1/matches/900/metadata", permanent=True)

    assert api.data_path("v1/matches/900/metadata").exists()
    assert not api.cache_path("v1/matches/900/metadata").exists()

    stale = time.time() - 100 * api.DAY
    os.utime(api.data_path("v1/matches/900/metadata"), (stale, stale))

    api.get_json("v1/matches/900/metadata", permanent=True)

    assert len(calls) == 1


def test_first_request_purges_stale_cache_json_only(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(api, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(api, "_pruned", False)
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen({"rank": 1}, []))

    (tmp_path / "cache").mkdir()
    (tmp_path / "data").mkdir()
    stale = time.time() - api.PRUNE_AGE - 60

    old = tmp_path / "cache" / "v1_leaderboard_Europe.json"
    old.write_text("{}", encoding="utf-8")
    os.utime(old, (stale, stale))

    fresh = tmp_path / "cache" / "v1_leaderboard_Asia.json"
    fresh.write_text("{}", encoding="utf-8")

    foreign = tmp_path / "cache" / "notes.txt"
    foreign.write_text("keep", encoding="utf-8")
    os.utime(foreign, (stale, stale))

    foreign_json = tmp_path / "cache" / "notes.json"
    foreign_json.write_text("{}", encoding="utf-8")
    os.utime(foreign_json, (stale, stale))

    permanent = tmp_path / "data" / "v1_assets_heroes_client_version=1.json.gz"
    permanent.write_bytes(gzip.compress(b"[]"))
    os.utime(permanent, (stale, stale))

    api.get_json("v1/assets/heroes", use_cache=False)

    assert not old.exists()
    assert fresh.exists()
    assert foreign.exists()
    assert foreign_json.exists()
    assert permanent.exists()


def test_get_json_permanent_bodies_are_gzipped(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(api, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen([{"id": 7}], []))

    api.get_json("v1/assets/heroes?client_version=100", permanent=True)

    stored = api.data_path("v1/assets/heroes?client_version=100")

    assert stored.suffix == ".gz"
    assert json.loads(gzip.decompress(stored.read_bytes())) == [{"id": 7}]
    assert api.get_json("v1/assets/heroes?client_version=100", permanent=True) == [{"id": 7}]


def test_get_json_permanent_migrates_old_cache_file(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(api, "DATA_DIR", tmp_path / "data")

    def offline(req, timeout=None):
        raise OSError("no network")

    monkeypatch.setattr(urllib.request, "urlopen", offline)

    old = api.cache_path("v1/matches/900/metadata")
    old.parent.mkdir(parents=True)
    old.write_text('{"match_info": {}}', encoding="utf-8")

    data = api.get_json("v1/matches/900/metadata", permanent=True)

    assert data == {"match_info": {}}
    assert api.data_path("v1/matches/900/metadata").exists()
    assert not old.exists()


def test_request_targets_api_with_user_agent(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(api, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen({}, calls))

    api.get_json("v1/leaderboard/Europe")

    req = calls[0]

    assert req.full_url == f"{api.BASE}/v1/leaderboard/Europe"
    assert req.get_header("User-agent") == "deadlock-matches/1.0"
