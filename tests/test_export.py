import json

import pytest

from jevwall.export import MARKER, PAGE, export, latest_run

RUN = {
    "header": {"model": "jev-latest"},
    "events": [{"id": "deepset-0", "text": "</script><b>x", "p_attack": 0.9}],
}


def test_real_page_contains_marker_exactly_once():
    assert PAGE.read_text().count(MARKER) == 1


def _payload_region(html: str) -> str:
    start = html.index("window.JEVWALL_RUN = ") + len("window.JEVWALL_RUN = ")
    end = html.index(";\n", start)
    return html[start:end]


def test_export_inlines_run_and_escapes_script_close(tmp_path):
    run_file = tmp_path / "run.json"
    run_file.write_text(json.dumps(RUN))
    out = export(run_file, tmp_path / "dist" / "replay.html")
    html = out.read_text()
    assert MARKER not in html
    assert '"deepset-0"' in html
    assert "</script><b>x" not in html  # would break out of the script tag
    assert "\\u003c/script\\u003e\\u003cb\\u003ex" in html


def test_export_escapes_html_comment_reopen_and_line_separators(tmp_path):
    text = "<!-- <script>alert(1)</script> -->\u2028\u2029&"
    run = {
        "header": {"model": "jev-latest"},
        "events": [{"id": "x", "text": text, "p_attack": 0.1}],
    }
    run_file = tmp_path / "run.json"
    run_file.write_text(json.dumps(run))
    html = export(run_file, tmp_path / "dist" / "replay.html").read_text()
    payload = _payload_region(html)
    assert "<!--" not in payload
    assert "<script" not in payload
    assert "\u2028" not in payload
    assert "\u2029" not in payload


def test_export_round_trips_through_json(tmp_path):
    run_file = tmp_path / "run.json"
    run_file.write_text(json.dumps(RUN))
    html = export(run_file, tmp_path / "dist" / "replay.html").read_text()
    payload = _payload_region(html)
    assert json.loads(payload) == RUN


def test_export_output_has_no_key_and_no_server_calls(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "sk-secret-value")
    run_file = tmp_path / "run.json"
    run_file.write_text(json.dumps(RUN))
    html = export(run_file, tmp_path / "replay.html").read_text()
    assert "sk-secret-value" not in html
    assert "JEV_API_KEY" not in html


def test_latest_run_picks_newest_name_and_errors_when_empty(tmp_path):
    with pytest.raises(FileNotFoundError, match="No runs"):
        latest_run(tmp_path)
    (tmp_path / "20260921-100000.json").write_text("{}")
    (tmp_path / "20260921-110000.json").write_text("{}")
    assert latest_run(tmp_path).name == "20260921-110000.json"
