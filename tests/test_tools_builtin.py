from agentic_workflow.mock_ops import MockOps
from agentic_workflow.tools_builtin import build_registry


def _reg():
    return build_registry(MockOps())


def test_registry_has_expected_tools():
    names = set(_reg().names())
    assert names == {
        "get_recent_deploys",
        "get_error_rate",
        "get_service_metrics",
        "search_logs",
        "lookup_runbook",
        "rollback_deploy",
    }


def test_error_rate_flags_elevated():
    result = _reg().get("get_error_rate").run(service="checkout")
    assert result.data["elevated"] is True
    assert result.data["error_rate"] == 0.082


def test_recent_deploys_and_log_search():
    reg = _reg()
    deploys = reg.get("get_recent_deploys").run(service="checkout").data["deploys"]
    assert deploys[0]["id"] == "checkout@a1b2c3"

    matches = (
        reg.get("search_logs").run(service="checkout", pattern="PaymentGateway").data["matches"]
    )
    assert len(matches) == 2 and all("PaymentGateway" in m for m in matches)


def test_runbook_lookup():
    steps = _reg().get("lookup_runbook").run(symptom="elevated 5xx after deploy").data["steps"]
    assert any("Roll back" in s for s in steps)
    assert _reg().get("lookup_runbook").run(symptom="cosmic rays").data["steps"] == []


def test_rollback_is_side_effecting():
    ops = MockOps()
    reg = build_registry(ops)
    result = reg.get("rollback_deploy").run(service="checkout", deploy_id="checkout@a1b2c3")
    assert "rolled back" in result.summary
    assert ops.state("checkout").rolled_back == ["checkout@a1b2c3"]


def test_unknown_service_is_graceful():
    result = _reg().get("get_error_rate").run(service="ghost")
    assert result.data["elevated"] is False
