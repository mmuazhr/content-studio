import pytest

from pipeline.db import check_transition, IllegalTransition


def test_legal_full_chain_passes():
    chain = [
        "proposed", "pending_script_review", "script_approved",
        "generating", "pending_video_review", "video_approved",
        "posted", "archived",
    ]
    for cur, new in zip(chain, chain[1:]):
        check_transition(cur, new)  # should not raise


def test_pending_script_review_to_rejected_passes():
    check_transition("pending_script_review", "rejected")


def test_pending_script_review_to_backlog_passes():
    check_transition("pending_script_review", "backlog")


def test_proposed_to_generating_raises():
    with pytest.raises(IllegalTransition):
        check_transition("proposed", "generating")


def test_script_approved_to_video_approved_raises():
    with pytest.raises(IllegalTransition):
        check_transition("script_approved", "video_approved")


@pytest.mark.parametrize("cur", [
    "proposed", "pending_script_review", "script_approved", "rejected",
    "backlog", "generating", "pending_video_review", "video_approved",
    "posted", "archived",
])
def test_anything_to_error_passes(cur):
    check_transition(cur, "error")


def test_error_to_pending_script_review_passes():
    check_transition("error", "pending_script_review")


def test_error_to_script_approved_passes():
    check_transition("error", "script_approved")
