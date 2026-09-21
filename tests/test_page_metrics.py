"""Run the page's own metric functions under node, so the maths on screen is tested.

The functions are lifted verbatim out of `index.html` between the `// <metrics>` sentinels,
given a tiny stdin/stdout harness, and executed. Nothing about the page is re-implemented here.
"""

import json
import shutil
import subprocess

import pytest

from jevwall.export import PAGE

OPEN = "// <metrics>"
CLOSE = "// </metrics>"

HARNESS = """
const cases = JSON.parse(require("fs").readFileSync(0, "utf8"));
const out = cases.map((c) => {
  if (c.fn === "confusion") return confusion(c.events, c.threshold);
  if (c.fn === "roc") return roc(c.events);
  if (c.fn === "reliability") return reliability(c.events, c.bins === undefined ? 10 : c.bins);
  if (c.fn === "percentile") return percentile(c.values, c.p);
  throw new Error("unknown fn " + c.fn);
});
process.stdout.write(JSON.stringify(out));
"""

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def metrics_source() -> str:
    html = PAGE.read_text(encoding="utf-8")
    assert html.count(OPEN) == 1 and html.count(CLOSE) == 1
    return html[html.index(OPEN) + len(OPEN) : html.index(CLOSE)]


def evaluate(cases: list[dict]) -> list:
    result = subprocess.run(
        [shutil.which("node"), "-e", metrics_source() + HARNESS],
        input=json.dumps(cases),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def one(case: dict):
    return evaluate([case])[0]


def ev(p: float, truth: bool) -> dict:
    return {"p_attack": p, "truth": truth}


def mann_whitney_auc(events: list[dict]) -> float | None:
    """AUC as the probability a random attack outranks a random benign; ties count 0.5."""
    pos = [e["p_attack"] for e in events if e["truth"]]
    neg = [e["p_attack"] for e in events if not e["truth"]]
    if not pos or not neg:
        return None
    wins = sum(1.0 if a > b else 0.5 if a == b else 0.0 for a in pos for b in neg)
    return wins / (len(pos) * len(neg))


PERFECT = [ev(0.9, True), ev(0.8, True), ev(0.2, False), ev(0.1, False)]
INVERTED = [ev(0.1, True), ev(0.2, True), ev(0.8, False), ev(0.9, False)]
TIED = [ev(0.5, True), ev(0.5, True), ev(0.5, False), ev(0.5, False)]
MIXED = [ev(0.9, True), ev(0.6, True), ev(0.6, False), ev(0.4, True), ev(0.1, False)]


@pytest.mark.parametrize(
    ("events", "expected"),
    [(PERFECT, 1.0), (INVERTED, 0.0), (TIED, 0.5), (MIXED, mann_whitney_auc(MIXED))],
)
def test_roc_auc_matches_mann_whitney(events, expected):
    assert one({"fn": "roc", "events": events})["auc"] == pytest.approx(expected)


def test_roc_points_run_from_origin_to_corner():
    points = one({"fn": "roc", "events": MIXED})["points"]
    assert points[0] == {"fpr": 0, "tpr": 0}
    assert points[-1] == {"fpr": 1, "tpr": 1}


def test_roc_with_one_class_only_has_no_points_and_no_auc():
    result = one({"fn": "roc", "events": [ev(0.9, True), ev(0.1, True)]})
    assert result["points"] == []
    assert result["auc"] is None


def test_confusion_counts_and_rates():
    events = [ev(0.9, True), ev(0.8, False), ev(0.2, True), ev(0.1, False)]
    result = one({"fn": "confusion", "events": events, "threshold": 0.5})
    assert (result["tp"], result["fp"], result["tn"], result["fn"]) == (1, 1, 1, 1)
    assert result["precision"] == pytest.approx(0.5)
    assert result["recall"] == pytest.approx(0.5)
    assert result["accuracy"] == pytest.approx(0.5)


def test_confusion_precision_is_null_when_nothing_is_flagged():
    events = [ev(0.2, True), ev(0.1, False)]
    result = one({"fn": "confusion", "events": events, "threshold": 0.5})
    assert (result["tp"], result["fp"], result["tn"], result["fn"]) == (0, 0, 1, 1)
    assert result["precision"] is None
    assert result["recall"] == pytest.approx(0.0)
    assert result["accuracy"] == pytest.approx(0.5)


def test_reliability_bins_and_ece_on_a_hand_computed_case():
    # Two bins are used: [0.1, 0.3) -> bin 1 and [0.8, 1.0] -> bins 8 and 9.
    events = [ev(0.1, False), ev(0.1, True), ev(0.8, True), ev(0.9, True)]
    result = one({"fn": "reliability", "events": events})
    assert result["bins"] == [
        {"predicted": pytest.approx(0.1), "observed": pytest.approx(0.5), "n": 2},
        {"predicted": pytest.approx(0.8), "observed": pytest.approx(1.0), "n": 1},
        {"predicted": pytest.approx(0.9), "observed": pytest.approx(1.0), "n": 1},
    ]
    # (2/4)*|0.5-0.1| + (1/4)*|1-0.8| + (1/4)*|1-0.9| = 0.2 + 0.05 + 0.025
    assert result["ece"] == pytest.approx(0.275)


def test_reliability_of_nothing_has_no_ece():
    result = one({"fn": "reliability", "events": []})
    assert result["bins"] == []
    assert result["ece"] is None


def test_percentile_of_nothing_is_null():
    assert one({"fn": "percentile", "values": [], "p": 50}) is None


def test_percentile_on_one_to_ten():
    values = list(range(1, 11))
    assert one({"fn": "percentile", "values": values, "p": 50}) == 6
    assert one({"fn": "percentile", "values": values, "p": 95}) == 10
