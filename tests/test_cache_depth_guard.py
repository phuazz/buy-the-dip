"""The post-subscription cache-depth gate.

Upgrading the Norgate trial (rolling 2-year window) to Platinum (1990→)
leaves the 2-year CSV cache warm; engines must refuse to run rather than
silently produce trial-depth results labelled as full history.
"""

import pandas as pd
import pytest

from scripts.providers import assert_cache_depth


def test_passes_when_depths_match():
    assert_cache_depth(pd.Timestamp("2024-07-03"), pd.Timestamp("2024-07-03"))


def test_passes_when_cache_is_deeper_than_benchmark():
    # e.g. $NDXTR starts 1999 while cached members reach back to 1992.
    assert_cache_depth(pd.Timestamp("1999-03-10"), pd.Timestamp("1992-01-02"))


def test_passes_within_tolerance():
    assert_cache_depth(pd.Timestamp("2024-01-02"), pd.Timestamp("2024-07-03"))


def test_raises_on_stale_trial_cache_after_upgrade():
    with pytest.raises(RuntimeError, match="refresh-cache"):
        assert_cache_depth(pd.Timestamp("1998-01-02"), pd.Timestamp("2024-07-03"))


def test_none_inputs_are_noop():
    assert_cache_depth(None, pd.Timestamp("2024-07-03"))
    assert_cache_depth(pd.Timestamp("1998-01-02"), None)
