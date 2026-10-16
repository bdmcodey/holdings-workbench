"""
What each pattern's statements do on their own, said on the Patterns step.

Until 0.39.0 the Patterns step said only how many statements lose a value. A
statement that is held -- "v. 94 no. 1 - v. 101 no. 4 (Jan 1988 - Fall 1995)",
months changing to seasons inside it -- sat folded away under "nothing to
decide", and so did two that convert with something to check. With an uploaded
file the record list said so; with pasted statements there is no Convert step,
and nothing did. Measured on the main corpus pasted: 1 held and 2 to check, all
on folded cards.
"""

from __future__ import annotations

import pytest

from conftest import REPO_ROOT

SWITCH = "v. 94 no. 1 - v. 101 no. 4 (Jan 1988 - Fall 1995)"
GUIDE = "v. 15 (1998 Buyers Guide)"
SUPPLEMENT = "v. 19 no. 2 Suppl. (1998)"
FALL = "v. 8 no. 3-v. 10 no. 2 (1981-Fall 1983)"
CLEAN = "v. 1-10 (1963-1972)"


def _group(client, text):
    data = client.post("/api/detect", json={"statements": [text],
                                            "pasted": True}).get_json()
    (group,) = data["groups"]
    return group


def test_a_held_statement_is_counted_with_its_reason(client):
    group = _group(client, SWITCH)
    assert (group["held"], group["to_check"]) == (1, 0)
    (outcome,) = group["example_outcomes"]
    assert outcome["outcome"] == "held"
    assert outcome["chron_switch"]["where"] == "within"
    assert any("months to seasons" in w for w in outcome["warnings"])


def test_one_statement_can_be_to_check_and_leave_something_out(client):
    group = _group(client, GUIDE)
    assert (group["held"], group["to_check"], group["left_out"]) == (0, 1, 1)
    (outcome,) = group["example_outcomes"]
    assert outcome["outcome"] == "to_check"
    assert outcome["attention"] and outcome["left_out"]


def test_left_out_alone_is_still_counted(client):
    group = _group(client, FALL)
    assert (group["held"], group["to_check"], group["left_out"]) == (0, 0, 1)
    assert group["example_outcomes"][0]["outcome"] == "left_out"


@pytest.mark.parametrize("text", [SUPPLEMENT])
def test_a_supplement_is_not_counted_as_held(client, text):
    # It keeps its own fold and its own pill: it belongs in 867, which is not
    # the same as being held for a decision.
    group = _group(client, text)
    assert group["held"] == 0
    outcome = group["example_outcomes"][0]
    assert outcome["outcome"] == "elsewhere" and outcome["belongs_in"] == "867"


def test_a_clean_statement_counts_nothing(client):
    group = _group(client, CLEAN)
    assert (group["held"], group["to_check"], group["left_out"]) == (0, 0, 0)
    assert group["example_outcomes"][0]["outcome"] == "clean"


def test_outcomes_line_up_with_the_examples_shown(client):
    data = client.post("/api/detect", json={
        "statements": [CLEAN, SWITCH, FALL, GUIDE], "pasted": True}).get_json()
    for group in data["groups"]:
        assert len(group["example_outcomes"]) == group["examples_shown"]


def test_the_page_never_folds_a_held_or_to_check_card():
    page = (REPO_ROOT / "marc_serials" / "templates" / "tool.html").read_text(
        encoding="utf-8")
    # Filed before the folds are, in a group of their own that starts open.
    assert ("else if (needsALook(group) && !needsAnAnswer(group, stored)) "
            "parts.attention.push(entry);") in page
    assert "details.open = patternFolds[key] ?? key === 'attention';" in page
    # Supplements keep their own fold.
    assert "return group.decides !== 'elsewhere' &&" in page
    # Pasted statements show their own outcome, and can be split in place.
    assert "if (sourceMode !== 'paste') return '';" in page
    assert "onclick=\"openPasteSplit(${idx}, ${i})\"" in page
