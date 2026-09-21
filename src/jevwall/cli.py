"""Command line: serve the live wall, do a headless run, or export a replay."""

import argparse
import asyncio
import sys
from pathlib import Path

from jevwall.corpus import DEFAULT_LIMIT, CorpusError, load_corpus
from jevwall.export import export, latest_run
from jevwall.judge import JudgeError, make_judge
from jevwall.runner import CostLimitError, run


def _serve(args: argparse.Namespace) -> None:
    import uvicorn

    from jevwall.server import create_app

    print(f"Jev Wall: http://127.0.0.1:{args.port}")
    uvicorn.run(create_app(make_judge()), host="127.0.0.1", port=args.port, log_level="warning")


async def _run(args: argparse.Namespace) -> None:
    records = load_corpus(None if args.full else args.limit)
    print(f"{len(records)} prompts")
    judge = make_judge()
    done = errors = 0
    try:
        async for event in run(records, judge, max_cost=args.max_cost):
            if event.get("type") == "done":
                print(
                    f"\nrun file: {event['run_file']}  cost: ${event['cost']:.4f}"
                    f"{'  (stopped early at cost ceiling)' if event['stopped_early'] else ''}"
                )
                continue
            done += 1
            errors += event["error"] is not None
            print(f"\r{done}/{len(records)}  errors: {errors}", end="", flush=True)
    finally:
        await judge.aclose()


def _export(args: argparse.Namespace) -> None:
    out = export(Path(args.run) if args.run else latest_run(), Path(args.out))
    print(f"replay written: {out}  ({out.stat().st_size / 1024:.0f} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(prog="jevwall")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="start the live wall")
    serve.add_argument("--port", type=int, default=8000)
    runp = sub.add_parser("run", help="headless run that records a run file")
    runp.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    runp.add_argument("--full", action="store_true", help="run the whole corpus")
    runp.add_argument("--max-cost", type=float, default=0.50)
    exp = sub.add_parser("export", help="write a self-contained replay page")
    exp.add_argument("--run", default=None, help="run file (default: newest in runs/)")
    exp.add_argument("--out", default="dist/replay.html")
    args = parser.parse_args()
    try:
        if args.command == "serve":
            _serve(args)
        elif args.command == "run":
            asyncio.run(_run(args))
        else:
            _export(args)
    except (JudgeError, CorpusError, CostLimitError, FileNotFoundError) as error:
        sys.exit(f"error: {error}")
