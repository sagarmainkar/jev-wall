import json

import pytest

from jevwall.export import MARKER, PAGE, export, latest_run

RUN = {
    "header": {"model": "jev-latest"},
    "events": [{"id": "deepset-0", "text": "</script><b>x", "p_attack": 0.9}],
}


def test_real_page_contains_marker_exactly_once():
    assert PAGE.read_text().count(MARKER) == 1


def test_export_inlines_run_and_escapes_script_close(tmp_path):
    run_file = tmp_path / "run.json"
    run_file.write_text(json.dumps(RUN))
    out = export(run_file, tmp_path / "dist" / "replay.html")
    html = out.read_text()
    assert MARKER not in html
    assert '"deepset-0"' in html
    assert "</script><b>x" not in html  # would break out of the script tag
    assert "<\\/script><b>x" in html


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
