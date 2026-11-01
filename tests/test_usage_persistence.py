"""Usage persistence through to sidebar HTML; temporary DB only, no provider calls."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import dispatcher
import extra_credits
import usage_limits


def test_missing_utilization_does_not_refresh_old_percentage(tmp_path):
    now = 1800000000
    path = str(tmp_path / "dispatch.db")
    with dispatcher.DispatchDB(path) as db:
        # A previously observed 99% is followed by allowed events without a
        # percentage, both within the old window and after its reset.
        for new_reset in (now + 100, now + 18100):
            db.save_limits("claude", [{"rateLimitType": "five_hour", "status": "allowed_warning",
                                      "utilization": .99, "resetsAt": now + 100}])
            db.save_limits("claude", [{"rateLimitType": "five_hour", "status": "allowed",
                                      "resetsAt": new_reset}])
            assert db.limits("claude")[0]["utilization"] is None
            windows = usage_limits.claude_windows(
                {"_dispatcher": usage_limits.load_dispatcher_usage(path)}, None, now)
            assert windows[0]["pct"] is None
            html = extra_credits.awake_html([dict(name="Claude", awake=True, badge="", windows=windows)])
            assert "5ω: άγνωστο" in html and "απομένουν 1%" not in html


def test_explicit_percentage_and_rejection_are_preserved(tmp_path):
    path = str(tmp_path / "dispatch.db")
    with dispatcher.DispatchDB(path) as db:
        for status, utilization in (("allowed", 0.0), ("allowed", .42),
                                    ("allowed_warning", .99), ("rejected", 1.0)):
            db.save_limits("claude", [{"rateLimitType": "five_hour", "status": status,
                                      "utilization": utilization, "resetsAt": 1800000100}])
            assert db.limits("claude")[0]["utilization"] == utilization
