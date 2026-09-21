from jevwall import corpus
from jevwall.corpus import Record, from_deepset, from_jackhhao
from jevwall.judge import MAX_CHARS


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
