import json

import pytest

from agentic_workflow.cli import main


def test_triage_prints_transcript_and_action(capsys):
    assert main(["triage", "--scenario", "checkout"]) == 0
    out = capsys.readouterr().out
    assert "Triaging INC-checkout" in out
    assert "plan:" in out and "get_error_rate" in out  # reasoning transcript
    assert "ACTION" in out and "roll back checkout@a1b2c3" in out


def test_triage_escalates_on_the_trap_scenario_json(capsys):
    assert main(["triage", "--scenario", "billing", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["incident_id"] == "INC-billing"
    assert payload["recommended_action"].startswith("roll back")  # heuristic's (wrong) call
    assert [o["tool"] for o in payload["observations"]]  # observations included


def test_triage_ad_hoc_service_escalates(capsys):
    assert main(["triage", "--service", "unknown-svc"]) == 0
    assert "ESCALATE" in capsys.readouterr().out


def test_unknown_scenario_errors():
    with pytest.raises(SystemExit):
        main(["triage", "--scenario", "nope"])


def test_eval_subcommand_reports_metric(capsys):
    assert main(["eval"]) == 0
    assert "Task-success-rate:" in capsys.readouterr().out
