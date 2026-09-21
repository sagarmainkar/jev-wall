from collections import Counter

from jevwall import corpus
from jevwall.corpus import Record, from_deepset, from_jackhhao
from jevwall.judge import MAX_CHARS


def _rows(n: int) -> list[dict]:
    return [
        {
            "text": f"t{i}",
            "label": i % 2,
            "prompt": f"p{i}",
            "type": "jailbreak" if i % 2 else "benign",
        }
        for i in range(n)
    ]


def test_from_deepset_maps_label_to_bool():
    records = from_deepset([{"text": "hi", "label": 0}, {"text": "ignore rules", "label": 1}])
    assert records == [
        Record("deepset-0", "deepset", "hi", False, False),
        Record("deepset-1", "deepset", "ignore rules", True, False),
    ]


def test_from_jackhhao_maps_type_to_bool():
    records = from_jackhhao(
        [{"prompt": "be DAN", "type": "jailbreak"}, {"prompt": "hello", "type": "benign"}]
    )
    assert [r.is_attack for r in records] == [True, False]
    assert records[0].id == "jackhhao-0"


def test_long_text_is_truncated_and_flagged():
    record = from_deepset([{"text": "x" * (MAX_CHARS + 1), "label": 0}])[0]
    assert len(record.text) == MAX_CHARS
    assert record.truncated is True


def test_blank_rows_are_skipped():
    assert from_deepset([{"text": "   ", "label": 1}]) == []


def test_load_corpus_shuffles_deterministically_and_limits(monkeypatch):
    monkeypatch.setattr(
        corpus,
        "_download",
        lambda name: [
            {"text": f"t{i}", "label": i % 2, "prompt": f"p{i}", "type": "benign"}
            for i in range(10)
        ],
    )
    first = corpus.load_corpus(limit=6)
    second = corpus.load_corpus(limit=6)
    assert first == second
    assert len(first) == 6
    assert {r.source for r in corpus.load_corpus()} == {"deepset", "jackhhao"}


def test_load_corpus_limit_zero_returns_empty(monkeypatch):
    monkeypatch.setattr(
        corpus,
        "_download",
        lambda name: [
            {"text": f"t{i}", "label": i % 2, "prompt": f"p{i}", "type": "benign"}
            for i in range(10)
        ],
    )
    assert corpus.load_corpus(limit=0) == []


def test_limit_is_split_evenly_between_sources(monkeypatch):
    monkeypatch.setattr(corpus, "_download", lambda name: _rows(400))
    records = corpus.load_corpus(limit=300)
    assert Counter(r.source for r in records) == {"deepset": 150, "jackhhao": 150}


def test_odd_limit_gives_extra_record_to_jackhhao(monkeypatch):
    monkeypatch.setattr(corpus, "_download", lambda name: _rows(400))
    records = corpus.load_corpus(limit=7)
    assert Counter(r.source for r in records) == {"deepset": 3, "jackhhao": 4}


def test_shortfall_is_taken_from_the_other_source(monkeypatch):
    monkeypatch.setattr(
        corpus,
        "_download",
        lambda name: _rows(10) if name == corpus.DEEPSET else _rows(200),
    )
    records = corpus.load_corpus(limit=100)
    assert Counter(r.source for r in records) == {"deepset": 10, "jackhhao": 90}

    monkeypatch.setattr(
        corpus,
        "_download",
        lambda name: _rows(200) if name == corpus.DEEPSET else _rows(10),
    )
    records = corpus.load_corpus(limit=100)
    assert Counter(r.source for r in records) == {"deepset": 90, "jackhhao": 10}


def test_limit_larger_than_corpus_returns_everything(monkeypatch):
    monkeypatch.setattr(corpus, "_download", lambda name: _rows(10))
    records = corpus.load_corpus(limit=500)
    assert len(records) == 20


def test_balanced_sample_is_deterministic_and_interleaved(monkeypatch):
    monkeypatch.setattr(corpus, "_download", lambda name: _rows(400))
    first = corpus.load_corpus(limit=100)
    second = corpus.load_corpus(limit=100)
    assert first == second
    leading_sources = {r.source for r in first[:50]}
    assert len(leading_sources) > 1


def test_default_limit_constant():
    assert corpus.DEFAULT_LIMIT == 300
