import re

from jevwall import taxonomy

ATLAS_ID = re.compile(r"^AML\.T\d{4}(\.\d{3})?$")


def test_ids_are_unique():
    ids = [t.id for tactic in taxonomy.TACTICS for t in tactic.techniques]
    assert len(ids) == len(set(ids))


def test_choice_criteria_covers_every_technique_plus_none():
    criteria = taxonomy.choice_criteria()
    ids = {t.id for tactic in taxonomy.TACTICS for t in tactic.techniques}
    assert set(criteria) == ids | {taxonomy.NONE_ID}
    assert all(text.strip() for text in criteria.values())


def test_option_count_fits_jev_limit():
    assert 20 <= len(taxonomy.choice_criteria()) <= 255


def test_as_json_round_trips_structure():
    data = taxonomy.as_json()
    assert [d["id"] for d in data] == [t.id for t in taxonomy.TACTICS]
    assert data[0].keys() == {"id", "name", "techniques", "atlas"}
    assert data[0]["techniques"][0].keys() == {"id", "name", "criteria"}


def test_every_tactic_references_at_least_one_atlas_technique():
    for tactic in taxonomy.TACTICS:
        assert tactic.atlas, f"{tactic.id} has no ATLAS reference"
        for atlas_id, name in tactic.atlas.items():
            assert ATLAS_ID.match(atlas_id), f"{tactic.id}: {atlas_id} is not an ATLAS id"
            assert name.strip(), f"{tactic.id}: {atlas_id} has no name"


def test_atlas_version_is_recorded():
    assert taxonomy.ATLAS_VERSION == "5.6.0"


# Jev never sees the ATLAS references: the questions it is asked, and their token cost, are
# exactly what they were before the references existed.
def test_choice_criteria_never_mentions_atlas():
    criteria = taxonomy.choice_criteria()
    assert len(criteria) == 29
    assert not any("AML." in text for text in criteria.values())
    assert not any("AML." in key for key in criteria)
