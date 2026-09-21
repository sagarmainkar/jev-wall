"""Push records through a judge concurrently, yield events, record the run, guard the cost."""

import asyncio
import json
import time
from collections import Counter
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from jevwall import taxonomy
from jevwall.corpus import Record
from jevwall.judge import JudgeError, Verdict

PRICE_PER_TOKEN = 0.042 / 1_000_000
QUESTION_TOKENS = 1300
CHARS_PER_TOKEN = 4
MIN_START_GAP = 0.06  # seconds between call starts: 1,000/minute, under Jev's 1,200 limit


class CostLimitError(Exception):
    """The estimated cost of a run is above the ceiling."""


def estimate_tokens(text: str) -> int:
    return QUESTION_TOKENS + len(text) // CHARS_PER_TOKEN


def estimate_cost(records: list[Record]) -> float:
    return sum(estimate_tokens(r.text) for r in records) * PRICE_PER_TOKEN


def make_event(record: Record, verdict: Verdict | None, error: str | None, t: float) -> dict:
    return {
        "id": record.id,
        "source": record.source,
        "text": record.text,
        "truth": record.is_attack,
        "truncated": record.truncated,
        "p_attack": verdict.p_attack if verdict else None,
        "technique": verdict.technique if verdict else None,
        "technique_confidence": verdict.technique_confidence if verdict else None,
        "technique_probs": verdict.technique_probs if verdict else None,
        "severity": verdict.severity if verdict else None,
        "latency_ms": verdict.latency_ms if verdict else None,
        "input_tokens": (verdict.input_tokens or estimate_tokens(record.text)) if verdict else 0,
        "tokens_estimated": bool(verdict) and verdict.input_tokens is None,
        "t": round(t, 3),
        "error": error,
    }


async def run(
    records: list[Record],
    judge,
    *,
    max_cost: float = 0.50,
    concurrency: int = 8,
    runs_dir: Path = Path("runs"),
) -> AsyncIterator[dict]:
    estimate = estimate_cost(records)
    if estimate > max_cost:
        raise CostLimitError(
            f"Estimated cost ${estimate:.4f} is above --max-cost ${max_cost:.2f}. "
            "Lower --limit or raise --max-cost."
        )

    started_at = datetime.now(UTC)
    started = time.perf_counter()
    queue: asyncio.Queue[dict] = asyncio.Queue()
    pending = iter(records)
    state = {"cost": 0.0, "stopped_early": False, "last_start": 0.0}
    start_lock = asyncio.Lock()

    async def worker() -> None:
        for record in pending:
            if state["cost"] > max_cost:
                state["stopped_early"] = True
                return
            async with start_lock:
                wait = state["last_start"] + MIN_START_GAP - time.perf_counter()
                if wait > 0:
                    await asyncio.sleep(wait)
                state["last_start"] = time.perf_counter()
            try:
                verdict, error = await judge.judge(record.text), None
            except JudgeError as exc:
                verdict, error = None, str(exc)
            event = make_event(record, verdict, error, time.perf_counter() - started)
            state["cost"] += event["input_tokens"] * PRICE_PER_TOKEN
            await queue.put(event)

    workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
    events: list[dict] = []
    run_file: Path | None = None
    try:
        while not all(w.done() for w in workers) or not queue.empty():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.05)
            except TimeoutError:
                continue
            events.append(event)
            yield event
        for w in workers:
            w.result()
    finally:
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        if events:
            runs_dir.mkdir(parents=True, exist_ok=True)
            run_file = runs_dir / f"{started_at:%Y%m%d-%H%M%S}.json"
            header = {
                "started": started_at.isoformat(),
                "model": "jev-latest",
                "counts": dict(Counter(e["source"] for e in events)),
                "taxonomy": taxonomy.as_json(),
                "price_per_mtok": 0.042,
            }
            run_file.write_text(json.dumps({"header": header, "events": events}))

    yield {
        "type": "done",
        "run_file": str(run_file) if run_file else None,
        "cost": round(state["cost"], 6),
        "stopped_early": state["stopped_early"],
    }
