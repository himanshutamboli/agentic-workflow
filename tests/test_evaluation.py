from agentic_workflow.domain import TriageResult
from agentic_workflow.evaluation import classify, render_markdown, run_eval, scenarios


def test_classify_maps_result_to_outcome():
    assert classify(TriageResult("i", "h", "roll back checkout@a1b2c3", 0.7)) == "rollback"
    assert classify(TriageResult("i", "h", "escalate to on-call", 0.0, escalate=True)) == "escalate"


def test_heuristic_eval_scores_known_scenarios():
    report = run_eval()  # HeuristicPlanner
    by_id = {r.scenario.id: r for r in report.rows}

    # clean rollback cases: right call, right deploy
    assert by_id["checkout"].success and by_id["api-gateway"].success
    # escalate cases the heuristic handles
    assert by_id["search"].success and by_id["auth"].success and by_id["ghost"].success
    # the trap: heuristic wrongly rolls back an innocent deploy → a false rollback
    assert not by_id["billing"].success
    assert by_id["billing"].got == "rollback"

    assert report.false_rollbacks == 1
    assert report.task_success_rate == 5 / 6


def test_render_markdown_reports_headline_metric():
    md = render_markdown(run_eval())
    assert "Task-success-rate:" in md
    assert len(scenarios()) == 6
    assert md.count("✅") + md.count("❌") == len(scenarios())
