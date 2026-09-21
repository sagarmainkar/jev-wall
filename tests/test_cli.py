import pytest

from jevwall.cli import build_parser, effective_limit
from jevwall.corpus import DEFAULT_LIMIT


def parse(*argv):
    return build_parser().parse_args(argv)


def test_run_defaults_to_the_default_limit():
    assert effective_limit(parse("run")) == DEFAULT_LIMIT


def test_run_honours_an_explicit_limit():
    assert effective_limit(parse("run", "--limit", "42")) == 42


def test_full_wins_over_limit():
    assert effective_limit(parse("run", "--full", "--limit", "42")) is None
    assert effective_limit(parse("run", "--limit", "42", "--full")) is None


def test_run_defaults_max_cost_to_fifty_cents():
    assert parse("run").max_cost == 0.50


def test_export_defaults():
    args = parse("export")
    assert args.run is None
    assert args.out == "dist/replay.html"


def test_serve_defaults_to_port_8000():
    assert parse("serve").port == 8000


def test_a_command_is_required():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])
