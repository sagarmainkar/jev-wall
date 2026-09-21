import asyncio
import contextlib
import json

import pytest

from jevwall.corpus import Record
from jevwall.judge import JudgeError, Verdict
from jevwall.runner import CostLimitError, estimate_cost, estimate_tokens, make_event, run


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


class SlowFakeJudge:
    """A FakeJudge that actually yields control, so worker tasks interleave."""

    def __init__(self, tokens=1000, delay=0.01):
        self.tokens, self.delay, self.seen = tokens, delay, []

    async def judge(self, text):
        self.seen.append(text)
        await asyncio.sleep(self.delay)
        return Verdict(
            0.9, "ignore_previous", 0.8, {"ignore_previous": 0.8}, 2.0, 100.0, self.tokens
        )


async def collect(records, judge, **kwargs):
    return [event async for event in run(records, judge, **kwargs)]


def test_estimate_tokens_counts_questions_plus_text():
    assert estimate_tokens("x" * 400) == 1300 + 100


def test_estimate_cost_for_two_thousand_prompts_is_cents():
    assert 0.05 < estimate_cost([rec(i, text="x" * 1600) for i in range(2000)]) < 0.30


def test_make_event_keeps_only_the_top_five_technique_probabilities():
    probs = {f"t{i}": round(i / 100, 6) for i in range(10)}  # t9 highest, t0 lowest
    verdict = Verdict(0.9, "t9", 0.09, probs, 2.0, 100.0, 1000)
    event = make_event(rec(0), verdict, None, 1.0)
    assert list(event["technique_probs"]) == ["t9", "t8", "t7", "t6", "t5"]
    assert event["technique_probs"]["t9"] == 0.09


def test_make_event_rounds_technique_probabilities_to_four_decimals():
    verdict = Verdict(0.9, "a", 0.5, {"a": 0.123456789, "b": 0.5}, 2.0, 100.0, 1000)
    assert make_event(rec(0), verdict, None, 1.0)["technique_probs"] == {"b": 0.5, "a": 0.1235}


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


async def test_early_disconnect_still_writes_every_completed_verdict(tmp_path, monkeypatch):
    monkeypatch.setattr("jevwall.runner.MIN_START_GAP", 0.0)
    concurrency = 4
    judge = SlowFakeJudge(delay=0.01)
    received = []
    async with contextlib.aclosing(
        run([rec(i) for i in range(20)], judge, concurrency=concurrency, runs_dir=tmp_path)
    ) as stream:
        async for event in stream:
            received.append(event)
            if len(received) == 2:
                # Let the other workers race ahead and finish more calls than the
                # consumer has seen before disconnecting - this is what exposes finding
                # 2 (completed verdicts sitting in the queue, never yielded, must still
                # be drained into the run file on disconnect).
                await asyncio.sleep(0.3)
                break

    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    saved_ids = {e["id"] for e in data["events"]}
    received_ids = {e["id"] for e in received}
    assert received_ids <= saved_ids
    assert len(data["events"]) >= 2

    # At the moment of disconnect, at most `concurrency` calls can be mid-flight
    # (already dispatched to the judge, not yet returned); those are cancelled before
    # completing and their verdicts are necessarily lost. Every other completed call
    # must have been saved, whether it was already yielded to the consumer or was still
    # sitting in the queue.
    assert len(judge.seen) - concurrency <= len(data["events"]) <= len(judge.seen)


async def test_cancelled_consumer_still_writes_run_file(tmp_path, monkeypatch):
    monkeypatch.setattr("jevwall.runner.MIN_START_GAP", 0.0)
    judge = SlowFakeJudge(delay=0.05)
    received = []

    async def consume():
        async for event in run(
            [rec(i) for i in range(10)], judge, concurrency=2, runs_dir=tmp_path
        ):
            received.append(event)

    task = asyncio.create_task(consume())
    while not received:
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert "header" in data
    assert len(data["events"]) >= 1
