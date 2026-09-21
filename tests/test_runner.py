import json

import pytest

from jevwall.corpus import Record
from jevwall.judge import JudgeError, Verdict
from jevwall.runner import CostLimitError, estimate_cost, estimate_tokens, run


def rec(i, attack=False, text="hello"):
    return Record(f"deepset-{i}", "deepset", text, attack, False)


class FakeJudge:
    def __init__(self, tokens=1000, fail_on=()):
        self.tokens, self.fail_on, self.seen = tokens, set(fail_on), []

    async def judge(self, text):
        self.seen.append(text)
        if text in self.fail_on:
            raise JudgeError("rate limited")
        return Verdict(
            0.9, "ignore_previous", 0.8, {"ignore_previous": 0.8}, 2.0, 100.0, self.tokens
        )


async def collect(records, judge, **kwargs):
    return [event async for event in run(records, judge, **kwargs)]


def test_estimate_tokens_counts_questions_plus_text():
    assert estimate_tokens("x" * 400) == 1300 + 100


def test_estimate_cost_for_two_thousand_prompts_is_cents():
    assert 0.05 < estimate_cost([rec(i, text="x" * 1600) for i in range(2000)]) < 0.30


async def test_run_yields_one_event_per_record_then_done(tmp_path):
    events = await collect([rec(0, True), rec(1)], FakeJudge(), runs_dir=tmp_path)
    assert {e["id"] for e in events[:-1]} == {"deepset-0", "deepset-1"}
    first = next(e for e in events if e.get("id") == "deepset-0")
    assert first["truth"] is True and first["p_attack"] == 0.9 and first["error"] is None
    assert first["technique_probs"] == {"ignore_previous": 0.8}
    assert events[-1]["type"] == "done" and events[-1]["stopped_early"] is False


async def test_failed_call_becomes_error_event_and_run_continues(tmp_path):
    events = await collect(
        [rec(0, text="bad"), rec(1, text="good")], FakeJudge(fail_on={"bad"}), runs_dir=tmp_path
    )
    bad = next(e for e in events if e.get("id") == "deepset-0")
    assert bad["error"] == "rate limited" and bad["p_attack"] is None
    assert any(e.get("id") == "deepset-1" and e["error"] is None for e in events)


async def test_run_file_has_header_and_events_and_no_key(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "sk-secret-value")
    events = await collect([rec(0)], FakeJudge(), runs_dir=tmp_path)
    raw = (tmp_path / events[-1]["run_file"].split("/")[-1]).read_text()
    data = json.loads(raw)
    assert data["header"]["counts"] == {"deepset": 1}
    assert data["header"]["taxonomy"][0]["id"] == "override"
    assert len(data["events"]) == 1
    assert "sk-secret-value" not in raw


async def test_estimate_over_ceiling_refuses_before_any_call(tmp_path):
    judge = FakeJudge()
    with pytest.raises(CostLimitError, match="max-cost"):
        await collect([rec(i) for i in range(100)], judge, max_cost=0.0001, runs_dir=tmp_path)
    assert judge.seen == []


async def test_running_cost_over_ceiling_stops_early(tmp_path):
    judge = FakeJudge(tokens=10_000_000)  # each call "costs" $0.42
    events = await collect(
        [rec(i) for i in range(50)], judge, max_cost=0.50, concurrency=1, runs_dir=tmp_path
    )
    assert events[-1]["stopped_early"] is True
    assert len(judge.seen) < 50
