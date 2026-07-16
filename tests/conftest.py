import pytest
from builders import (
    _write_effective_assets,
    _write_item_history,
    build_abandon_match,
    build_chain_collision_match,
    build_day_match,
    build_double_upgrade_match,
    build_heal_match,
    build_interval_match,
    build_match,
    build_movement_match,
    build_rank_match,
    build_skip_upgrade_match,
    build_sold_match,
    build_souls_match,
    build_upgrade_match,
)

from deadlock_matches import export, schemas


@pytest.fixture
def pq(tmp_path):
    for name, df in export.build_tables([build_match()], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    _write_item_history(tmp_path)

    return tmp_path


@pytest.fixture
def no_history_pq(tmp_path):
    for name, df in export.build_tables([build_match()], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    path = schemas.table_path("item_history", tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    schemas.conform("item_history", []).write_parquet(path)

    return tmp_path


@pytest.fixture
def souls_pq(tmp_path):
    for name, df in export.build_tables([build_souls_match()], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    return tmp_path


@pytest.fixture
def heal_pq(tmp_path):
    for name, df in export.build_tables([build_heal_match()], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    _write_item_history(tmp_path)

    return tmp_path


@pytest.fixture
def sold_pq(tmp_path):
    for name, df in export.build_tables([build_sold_match()], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    _write_item_history(tmp_path)

    return tmp_path


@pytest.fixture
def rebuy_pq(tmp_path):
    infos = [build_sold_match(rebuy=True)]

    for name, df in export.build_tables(infos, exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    _write_item_history(tmp_path)

    return tmp_path


@pytest.fixture
def effective_pq(tmp_path):
    for name, df in export.build_tables([build_upgrade_match()], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    _write_effective_assets(tmp_path)

    return tmp_path


@pytest.fixture
def double_upgrade_pq(tmp_path):
    infos = [build_double_upgrade_match()]

    for name, df in export.build_tables(infos, exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    _write_effective_assets(tmp_path)

    return tmp_path


@pytest.fixture
def skip_upgrade_pq(tmp_path):
    infos = [build_skip_upgrade_match()]

    for name, df in export.build_tables(infos, exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    _write_effective_assets(tmp_path)

    return tmp_path


@pytest.fixture
def chain_collision_pq(tmp_path):
    infos = [build_chain_collision_match()]

    for name, df in export.build_tables(infos, exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    _write_effective_assets(tmp_path)

    return tmp_path


@pytest.fixture
def interval_pq(tmp_path):
    for name, df in export.build_tables([build_interval_match()], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    _write_item_history(tmp_path)

    return tmp_path


@pytest.fixture
def rank_pq(tmp_path):
    for name, df in export.build_tables([build_rank_match()], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    return tmp_path


@pytest.fixture
def two_interval_pq(tmp_path):
    infos = [build_interval_match(), build_interval_match(match_id=501)]

    for name, df in export.build_tables(infos, exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    _write_item_history(tmp_path)

    return tmp_path


@pytest.fixture
def movement_pq(tmp_path):
    out = tmp_path / "with-movement"
    out.mkdir()

    for name, df in export.build_tables([build_movement_match()]).items():
        df.write_parquet(out / f"{name}.parquet")

    return out


@pytest.fixture
def record_pq(tmp_path):
    infos = [
        build_day_match(1, 0, won=True),
        build_day_match(2, 0, won=False),
        build_day_match(3, 0, won=False),
        build_day_match(4, 1, won=True),
        build_day_match(5, 1, won=True),
    ]

    for name, df in export.build_tables(infos).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    _write_item_history(tmp_path)

    return tmp_path


@pytest.fixture
def abandon_pq(tmp_path):
    infos = [
        build_day_match(1, 0, won=True),
        build_abandon_match(2, leaver="ally", abandon_s=300, won=False),
        build_abandon_match(3, leaver="enemy", abandon_s=100, won=True),
        build_abandon_match(4, leaver="you", abandon_s=1000, won=False),
        build_abandon_match(5, leaver="enemy", abandon_s=60, won=True, not_scored=True),
    ]

    for name, df in export.build_tables(infos, exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    return tmp_path
