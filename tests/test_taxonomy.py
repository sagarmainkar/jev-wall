from jevwall import taxonomy


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
    assert data[0]["techniques"][0].keys() == {"id", "name", "criteria"}
