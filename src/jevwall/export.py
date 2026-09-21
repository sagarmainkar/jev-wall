"""Inline a recorded run into the page to make a self-contained, key-free replay file."""

import json
from pathlib import Path

MARKER = "/*__JEVWALL_RUN__*/null"
PAGE = Path(__file__).parent / "web" / "index.html"


def latest_run(runs_dir: Path = Path("runs")) -> Path:
    runs = sorted(runs_dir.glob("*.json"))
    if not runs:
        raise FileNotFoundError(
            f"No runs found in {runs_dir}/. Do a run first: jevwall run --limit 50"
        )
    return runs[-1]


def export(run_file: Path, out: Path = Path("dist/replay.html"), page: Path = PAGE) -> Path:
    run = json.loads(run_file.read_text(encoding="utf-8"))
    payload = (
        json.dumps(run, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )
    html = page.read_text(encoding="utf-8")
    if html.count(MARKER) != 1:
        raise ValueError(f"{page} must contain the marker {MARKER} exactly once.")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html.replace(MARKER, payload), encoding="utf-8")
    return out
