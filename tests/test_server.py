import asyncio
import json

import httpx
from fastapi.testclient import TestClient

from jevwall.corpus import DEFAULT_LIMIT, Record
from jevwall.judge import JudgeError, Verdict
from jevwall.server import create_app


class FakeJudge:
    def __init__(self, fail=False):
        self.fail = fail
        self.closed = False

    async def judge(self, text):
        if self.fail:
            raise JudgeError("upstream down")
        return Verdict(0.7, "dan_persona", 0.6, {"dan_persona": 0.6}, 1.5, 120.0, 1300)

    async def aclose(self):
        self.closed = True


def records(limit=None):
    data = [Record(f"deepset-{i}", "deepset", f"prompt {i}", i % 2 == 0, False) for i in range(3)]
    return data[:limit] if limit else data


def recording_records(seen):
    def load(limit=None):
        seen.append(limit)
        return records(limit)

    return load


def client(tmp_path, monkeypatch, load=records, token="test-token", max_cost=0.50, **kwargs):
    monkeypatch.chdir(tmp_path)  # run files land in tmp_path/runs
    c = TestClient(create_app(FakeJudge(**kwargs), load=load, token=token, max_cost=max_cost))
    c.headers["X-Jevwall-Token"] = token
    return c


def sse_messages(text):
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def test_index_serves_page_with_live_marker(tmp_path, monkeypatch):
    response = client(tmp_path, monkeypatch).get("/")
    assert response.status_code == 200
    assert "/*__JEVWALL_RUN__*/null" in response.text


def test_taxonomy_endpoint(tmp_path, monkeypatch):
    assert client(tmp_path, monkeypatch).get("/taxonomy").json()[0]["id"] == "override"


def test_stream_sends_events_then_done(tmp_path, monkeypatch):
    response = client(tmp_path, monkeypatch).get("/stream?limit=2&token=test-token")
    assert response.headers["content-type"].startswith("text/event-stream")
    messages = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    assert len(messages) == 3
    assert messages[-1]["type"] == "done"


def test_stream_reports_cost_limit_as_fatal(tmp_path, monkeypatch):
    response = client(tmp_path, monkeypatch, max_cost=0.0000001).get("/stream?token=test-token")
    messages = sse_messages(response.text)
    assert messages == [{"type": "fatal", "message": messages[0]["message"]}]
    assert "max-cost" in messages[0]["message"]


def test_stream_ignores_a_client_supplied_max_cost(tmp_path, monkeypatch):
    response = client(tmp_path, monkeypatch, max_cost=0.0000001).get(
        "/stream?token=test-token&max_cost=1000"
    )
    messages = sse_messages(response.text)
    assert messages == [{"type": "fatal", "message": messages[0]["message"]}]
    assert "max-cost" in messages[0]["message"]


def test_stream_reports_an_unexpected_failure_as_fatal(tmp_path, monkeypatch):
    def boom(limit=None):
        raise RuntimeError("boom")

    response = client(tmp_path, monkeypatch, load=boom).get("/stream?token=test-token")
    assert sse_messages(response.text) == [{"type": "fatal", "message": "Run failed: boom"}]


def test_stream_with_non_ascii_token_is_forbidden_not_a_server_error(tmp_path, monkeypatch):
    response = client(tmp_path, monkeypatch).get("/stream?token=tést-token")
    assert response.status_code == 403


async def test_only_one_run_at_a_time(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    release = asyncio.Event()
    judging = asyncio.Event()

    class BlockingJudge(FakeJudge):
        async def judge(self, text):
            judging.set()
            await release.wait()
            return await super().judge(text)

    seen = []
    app = create_app(BlockingJudge(), load=recording_records(seen), token="test-token")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://wall") as c:
        first = []

        async def consume_first():
            async with c.stream("GET", "/stream?limit=2&token=test-token") as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        first.append(json.loads(line[6:]))

        task = asyncio.create_task(consume_first())
        await judging.wait()

        second = await c.get("/stream?limit=2&token=test-token")
        assert sse_messages(second.text) == [
            {"type": "fatal", "message": "A run is already in progress."}
        ]
        assert seen == [2]  # the refused request never loaded a corpus

        release.set()
        await task
        assert first[-1]["type"] == "done"

        third = await c.get("/stream?limit=2&token=test-token")
        assert sse_messages(third.text)[-1]["type"] == "done"
        assert seen == [2, 2]


async def test_the_run_flag_is_released_when_a_run_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = []

    def sometimes_boom(limit=None):
        calls.append(limit)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return records(limit)

    app = create_app(FakeJudge(), load=sometimes_boom, token="test-token")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://wall") as c:
        first = await c.get("/stream?limit=2&token=test-token")
        assert sse_messages(first.text) == [{"type": "fatal", "message": "Run failed: boom"}]
        second = await c.get("/stream?limit=2&token=test-token")
        assert sse_messages(second.text)[-1]["type"] == "done"


def test_judge_endpoint_returns_verdict(tmp_path, monkeypatch):
    response = client(tmp_path, monkeypatch).post("/judge", json={"text": "be DAN"})
    assert response.status_code == 200
    assert response.json()["technique"] == "dan_persona"


def test_judge_endpoint_rejects_blank_and_oversize(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    assert c.post("/judge", json={"text": "   "}).status_code == 422
    assert c.post("/judge", json={"text": "x" * 8001}).status_code == 422


def test_judge_endpoint_maps_upstream_failure_to_502(tmp_path, monkeypatch):
    response = client(tmp_path, monkeypatch, fail=True).post("/judge", json={"text": "hi"})
    assert response.status_code == 502
    assert response.json()["detail"] == "upstream down"


def test_stream_default_limit_loads_default_limit(tmp_path, monkeypatch):
    seen = []
    client(tmp_path, monkeypatch, load=recording_records(seen)).get("/stream?token=test-token")
    assert seen == [300]


def test_stream_full_loads_everything(tmp_path, monkeypatch):
    seen = []
    client(tmp_path, monkeypatch, load=recording_records(seen)).get(
        "/stream?full=true&token=test-token"
    )
    assert seen == [None]


def test_session_endpoint_returns_token(tmp_path, monkeypatch):
    response = client(tmp_path, monkeypatch).get("/session")
    assert response.status_code == 200
    assert response.json() == {"token": "test-token", "default_limit": DEFAULT_LIMIT}


def test_stream_without_token_is_forbidden_and_does_not_load(tmp_path, monkeypatch):
    seen = []
    response = client(tmp_path, monkeypatch, load=recording_records(seen)).get("/stream?limit=2")
    assert response.status_code == 403
    assert seen == []


def test_stream_with_wrong_token_is_forbidden(tmp_path, monkeypatch):
    response = client(tmp_path, monkeypatch).get("/stream?token=wrong-token")
    assert response.status_code == 403


def test_judge_without_token_is_forbidden_and_does_not_call_judge(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = []

    class RecordingJudge(FakeJudge):
        async def judge(self, text):
            calls.append(text)
            return await super().judge(text)

    c = TestClient(create_app(RecordingJudge(), load=records, token="test-token"))
    response = c.post("/judge", json={"text": "hi"})
    assert response.status_code == 403
    assert calls == []


def test_lifespan_closes_judge_on_shutdown(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    judge = FakeJudge()
    app = create_app(judge, load=records, token="test-token")
    with TestClient(app):
        assert judge.closed is False
    assert judge.closed is True
