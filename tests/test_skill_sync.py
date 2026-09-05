import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / ".agents" / "skills" / "deadlock-matches"
WIKI = REPO / ".agents" / "wiki"
BUNDLED = REPO / "src" / "deadlock_matches" / "agent" / "skills" / "deadlock-matches"

NOT_WINDOWS = pytest.mark.skipif(
    sys.platform == "win32", reason="git checks the symlinks out as plain files on Windows"
)


def _relative_files(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts
    }


def _source_files() -> set[str]:
    skill = _relative_files(SKILL)
    wiki = {f"references/{name}" for name in _relative_files(WIKI)}

    return skill | wiki


def _source_path(name: str) -> Path:
    if name.startswith("references/"):
        return WIKI / name.removeprefix("references/")

    return SKILL / name


def test_bundled_skill_has_the_same_files_as_the_source():
    assert _relative_files(BUNDLED) == _source_files()


@pytest.mark.parametrize("name", sorted(_source_files()))
def test_bundled_skill_file_matches_source(name):
    assert (BUNDLED / name).read_bytes() == _source_path(name).read_bytes()


@NOT_WINDOWS
def test_claude_skill_dir_points_at_the_source():
    link = REPO / ".claude" / "skills" / "deadlock-matches"

    assert link.resolve() == SKILL.resolve()


@NOT_WINDOWS
def test_skill_references_point_at_the_wiki():
    assert (SKILL / "references").resolve() == WIKI.resolve()
