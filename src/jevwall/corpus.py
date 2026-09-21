"""Load the two labelled prompt datasets into one record shape."""

import random
from collections.abc import Iterable
from dataclasses import dataclass

from jevwall.judge import MAX_CHARS

DEEPSET = "deepset/prompt-injections"
JACKHHAO = "jackhhao/jailbreak-classification"

DEFAULT_LIMIT = 300


class CorpusError(Exception):
    """A dataset could not be downloaded."""


@dataclass(frozen=True)
class Record:
    id: str
    source: str
    text: str
    is_attack: bool
    truncated: bool


def _records(source: str, pairs: Iterable[tuple[str, bool]]) -> list[Record]:
    records = []
    for index, (text, is_attack) in enumerate(pairs):
        text = (text or "").strip()
        if not text:
            continue
        records.append(
            Record(
                f"{source}-{index}",
                source,
                text[:MAX_CHARS],
                is_attack,
                len(text) > MAX_CHARS,
            )
        )
    return records


def from_deepset(rows: Iterable[dict]) -> list[Record]:
    return _records("deepset", ((row["text"], row["label"] == 1) for row in rows))


def from_jackhhao(rows: Iterable[dict]) -> list[Record]:
    return _records("jackhhao", ((row["prompt"], row["type"] == "jailbreak") for row in rows))


def _download(name: str) -> list[dict]:
    from datasets import load_dataset

    try:
        splits = load_dataset(name)
    except Exception as error:  # noqa: BLE001 - any download failure stops the run with one message
        raise CorpusError(f"Could not download dataset {name}: {error}") from error
    return [row for split in splits.values() for row in split]


def _split_share(deepset_total: int, jackhhao_total: int, limit: int) -> tuple[int, int]:
    """Split `limit` between the two sources, backfilling from whichever has more."""
    deepset_take = min(limit // 2, deepset_total)
    jackhhao_take = min(limit - deepset_take, jackhhao_total)
    shortfall = limit - deepset_take - jackhhao_take
    if shortfall > 0:
        deepset_take = min(deepset_take + shortfall, deepset_total)
    return deepset_take, jackhhao_take


def _balanced_sample(
    deepset_records: list[Record], jackhhao_records: list[Record], limit: int, seed: int
) -> list[Record]:
    deepset_take, jackhhao_take = _split_share(len(deepset_records), len(jackhhao_records), limit)
    deepset_shuffled = random.Random(seed).sample(deepset_records, len(deepset_records))
    jackhhao_shuffled = random.Random(seed).sample(jackhhao_records, len(jackhhao_records))
    sample = deepset_shuffled[:deepset_take] + jackhhao_shuffled[:jackhhao_take]
    random.Random(seed).shuffle(sample)
    return sample


def load_corpus(limit: int | None = None, seed: int = 7) -> list[Record]:
    deepset_records = from_deepset(_download(DEEPSET))
    jackhhao_records = from_jackhhao(_download(JACKHHAO))
    if limit is None:
        records = deepset_records + jackhhao_records
        random.Random(seed).shuffle(records)
        return records
    limit = max(0, limit)
    return _balanced_sample(deepset_records, jackhhao_records, limit, seed)
