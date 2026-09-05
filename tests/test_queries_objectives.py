import pytest

from deadlock_matches.queries import objectives


@pytest.mark.parametrize(("share", "minute"), [(247, 13.0), (284, 14.0), (432, 18.0)])
def test_rift_minute_inverts_the_share(share, minute):
    assert objectives.rift_minute(share) == minute


@pytest.mark.parametrize(("bounty", "minute"), [(950, 10.0), (2350, 30.0)])
def test_urn_minute_inverts_the_bounty(bounty, minute):
    assert objectives.urn_minute(bounty) == minute


@pytest.mark.parametrize(
    ("gains", "comeback", "duration_s", "payout"),
    [
        ([247] * 6, 0, 1800, 247),
        ([247, 247, 247, 247, 247, 3000], 0, 1800, 247),
        ([574] * 6, 327, 1800, 574),
        ([247, 247, 247, 100, 200, 300], 0, 1800, None),
        ([364] * 6, 0, 1800, None),
        ([54] * 6, 0, 1800, None),
        ([987] * 6, 0, 900, None),
    ],
    ids=[
        "shared payout",
        "one urn runner in the window",
        "comeback bonus set aside",
        "split window",
        "off formula amount",
        "before the first spawn",
        "past the final whistle",
    ],
)
def test_detect_rift(gains, comeback, duration_s, payout):
    assert objectives.detect_rift(gains, 6, comeback, duration_s) == payout


@pytest.mark.parametrize(
    ("gains", "heroes", "shared", "duration_s", "delivery"),
    [
        ([2350], ["Mirage"], 0, 1800, ("Mirage", 2350)),
        (
            [247, 247, 247, 247, 247, 2597],
            ["A", "B", "C", "D", "E", "Runner"],
            247,
            1800,
            ("Runner", 2350),
        ),
        ([2000, 300], ["Runner", "Ally"], 0, 1800, ("Runner", 2000)),
        ([500], ["Mirage"], 0, 1800, None),
        ([2350], ["Mirage"], 0, 1200, None),
    ],
    ids=[
        "solo runner",
        "shared rift payout set aside",
        "runner over orb sharers",
        "small treasure gain",
        "past the final whistle",
    ],
)
def test_detect_urn(gains, heroes, shared, duration_s, delivery):
    assert objectives.detect_urn(gains, heroes, shared, duration_s) == delivery
