import pytest
from agent_framework import EvalResults, assert_dimension_score_at_least

def test_assert_dimension_score_at_least_no_match():
    """Empty results should trigger failure when require_applicable=True"""
    empty_results = EvalResults(items=[])
    with pytest.raises(AssertionError, match="No scores found"):
        assert_dimension_score_at_least(
            empty_results,
            dimension_id="nonexistent",
            score=0.5,
            require_applicable=True,
        )
