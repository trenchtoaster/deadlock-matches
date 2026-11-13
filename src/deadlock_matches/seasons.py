"""Names the Ranked seasons and the rank intervals their games carry."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from deadlock_matches import api

SEASON_PATH = "v1/assets/ranked-seasons"

CURRENT = "current"

EVERY = "all"

PRE_SEASON_WORDS = ("pre", "pre-season", "preseason", "0")

SUBRANK_POINTS = 1_000


@dataclass(frozen=True)
class Season:
    """One Ranked season with the rank intervals and the point rules of its games.

    - number 0 is the Pre-Season, the ranked play before build 6652 that
      carries no rank interval and no Rank Points
    - top_subrank_points is the width of subrank VI, wider than the
      1,000 points of subranks I to V
    """

    number: int
    name: str
    intervals: tuple[int, ...] = ()
    start_timestamp: int | None = None
    end_timestamp: int | None = None
    base_point_grant: int = 300
    top_subrank_points: int = 2_000

    @property
    def tier_points(self) -> int:
        """Count the points one whole tier spans."""
        return 5 * SUBRANK_POINTS + self.top_subrank_points


PRE_SEASON = Season(0, "Pre-Season")

SHIPPED = (
    Season(1, "Beta Season 1", (1,), 1_785_430_800, 1_793_908_800, 300, 2_000),
    Season(2, "Beta Season 2", (2,), 1_793_908_800, 1_804_802_400, 350, 1_500),
)


def _number(table: dict[str, Any], position: int) -> int:
    """Read the season number from the class name or fall back to the list position.

    Args:
        table: One season of the API payload.
        position: Where the season sits in the payload, counted from 1.
    """
    found = re.fullmatch(r"season_(\d+)", str(table.get("class_name", "")))

    return int(found.group(1)) if found else position


def _season(table: dict[str, Any], position: int) -> Season:
    """Build one season from its API table.

    Args:
        table: One season of the API payload.
        position: Where the season sits in the payload, counted from 1.
    """
    number = _number(table, position)
    spans = [i for i in table.get("intervals") or [] if isinstance(i, dict)]
    intervals = tuple(i["interval"] for i in spans if isinstance(i.get("interval"), int))
    starts = [i["start_timestamp"] for i in spans if isinstance(i.get("start_timestamp"), int)]
    ends = [i["end_timestamp"] for i in spans if isinstance(i.get("end_timestamp"), int)]
    name = table.get("name")
    grant = table.get("base_win_loss_point_grant")
    top = SHIPPED[0].top_subrank_points

    for info in table.get("rank_info") or []:
        widths = info.get("sub_rank_xp") if isinstance(info, dict) else None

        if isinstance(widths, list) and widths and isinstance(widths[-1], int):
            top = widths[-1]

    return Season(
        number=number,
        name=name if isinstance(name, str) and name else f"Season {number}",
        intervals=intervals,
        start_timestamp=min(starts) if starts else None,
        end_timestamp=max(ends) if ends else None,
        base_point_grant=grant if isinstance(grant, int) and grant > 0 else 300,
        top_subrank_points=top,
    )


def known() -> tuple[Season, ...]:
    """List the Ranked seasons oldest first, from the API or the copy shipped here."""
    try:
        payload = api.get_json(SEASON_PATH, max_age=api.DAY)

    except OSError:
        return SHIPPED

    if not isinstance(payload, list):
        return SHIPPED

    tables = [s for s in payload if isinstance(s, dict)]
    normal = [s for s in tables if s.get("ranked_type") == "normal"] or tables
    found = [_season(table, position) for position, table in enumerate(normal, start=1)]
    usable = [s for s in found if s.intervals]

    if not usable:
        return SHIPPED

    return tuple(sorted(usable, key=lambda s: s.number))


def current(now: float | None = None) -> Season | None:
    """Pick the season running now, or the newest one that has started.

    Args:
        now: The moment to judge by as a Unix timestamp, the clock when left out.
    """
    moment = time.time() if now is None else now
    seasons = known()
    started = [s for s in seasons if s.start_timestamp is None or s.start_timestamp <= moment]

    if started:
        return started[-1]

    return seasons[0] if seasons else None


def _short_name(name: str) -> str:
    """Reduce a season name to the form a flag is typed in, like beta1.

    Args:
        name: A season name or a typed --season value.
    """
    return re.sub(r"season|[^a-z0-9]", "", name.lower())


def pick(text: str | None) -> Season | None:
    """Turn a --season value into a season, with None standing for every season.

    Args:
        text: current, all, pre, a season number, or a name like beta1.
    """
    word = (text or CURRENT).strip().lower()

    if word == CURRENT:
        return current()

    if word == EVERY:
        return None

    if word in PRE_SEASON_WORDS:
        return PRE_SEASON

    seasons = known()
    wanted = int(word) if word.isdigit() else None
    short = _short_name(word)

    for season in seasons:
        if season.number == wanted or _short_name(season.name) == short:
            return season

    numbers = ", ".join(str(s.number) for s in seasons)
    msg = f"Unknown season {text!r}, use current, all, pre, or one of: {numbers}"
    raise ValueError(msg)


def of_interval(interval: int | None) -> Season | None:
    """Find the season one rank interval belongs to.

    Args:
        interval: The rank_interval of a match.
    """
    for season in known():
        if interval in season.intervals:
            return season

    return None
