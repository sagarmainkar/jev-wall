"""Load the two labelled prompt datasets into one record shape."""

import random
from collections.abc import Iterable
from dataclasses import dataclass

from jevwall.judge import MAX_CHARS

DEEPSET = "deepset/prompt-injections"
JACKHHAO = "jackhhao/jailbreak-classification"


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


def load_corpus(limit: int | None = None, seed: int = 7) -> list[Record]:
    records = from_deepset(_download(DEEPSET)) + from_jackhhao(_download(JACKHHAO))
    random.Random(seed).shuffle(records)
    return records[:limit] if limit else records
