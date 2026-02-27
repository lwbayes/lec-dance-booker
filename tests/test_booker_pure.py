"""
Unit tests for the pure functions in booker.py.
No browser, no network — runs instantly.
"""
import pytest
from booker import _parse_hour, _score_match, _build_cards, ClassCard


# ---------------------------------------------------------------------------
# _parse_hour
# ---------------------------------------------------------------------------

def test_parse_hour_am():
    assert _parse_hour("10:00 AM") == 10


def test_parse_hour_pm():
    assert _parse_hour("7:30 PM") == 19


def test_parse_hour_noon_pm():
    assert _parse_hour("12:00 PM") == 12


def test_parse_hour_midnight_am():
    assert _parse_hour("12:00 AM") == 0


def test_parse_hour_24h():
    assert _parse_hour("18:30") == 18


def test_parse_hour_from_dur_string():
    # Real format returned by the Momence widget
    assert _parse_hour("6:00 PM\n - \n7:00 PM\n60 min") == 18


def test_parse_hour_no_match():
    assert _parse_hour("no time here") == -1


# ---------------------------------------------------------------------------
# _score_match
# ---------------------------------------------------------------------------

def _card(name="Salsa", day="monday", hour=18):
    return ClassCard(name=name, day=day, time="6:00", hour=hour, booking_url="https://example.com")


def _intent(class_type="any", level="any", day=None, time="any", name_keywords=None):
    return {"class_type": class_type, "level": level, "day": day, "time": time,
            "name_keywords": name_keywords or []}


def test_score_match_day_hard_filter_rejects():
    assert _score_match(_card(day="monday"), _intent(day="tuesday")) == 0


def test_score_match_day_passes_when_matches():
    assert _score_match(_card(day="monday"), _intent(day="monday")) > 0


def test_score_match_day_passes_when_none():
    assert _score_match(_card(day="monday"), _intent(day=None)) > 0


def test_score_match_time_morning_rejects_evening():
    assert _score_match(_card(hour=18), _intent(time="morning")) == 0


def test_score_match_time_evening_accepts_6pm():
    assert _score_match(_card(hour=18), _intent(time="evening")) > 0


def test_score_match_time_afternoon_boundary():
    assert _score_match(_card(hour=12), _intent(time="afternoon")) > 0
    assert _score_match(_card(hour=11), _intent(time="afternoon")) == 0


def test_score_match_class_type_soft_adds_score():
    base = _score_match(_card("Salsa Partnerwork"), _intent())
    with_type = _score_match(_card("Salsa Partnerwork"), _intent(class_type="salsa"))
    assert with_type > base


def test_score_match_class_type_mismatch_no_penalty():
    # Soft filter — wrong type doesn't hard-reject, just no bonus
    score = _score_match(_card("Bachata Shines"), _intent(class_type="salsa"))
    assert score > 0


def test_score_match_level_improver_soft():
    base = _score_match(_card("Salsa - Improvers"), _intent())
    with_level = _score_match(_card("Salsa - Improvers"), _intent(level="advanced"))
    assert with_level > base


def test_score_match_no_filters_returns_one():
    assert _score_match(_card(), _intent()) == 1


def test_score_match_name_keyword_boosts_specific_class():
    on1     = _card("Salsa On1 Partnerwork",        day="monday", hour=19)
    improv  = _card("Salsa Partnerwork - Improvers", day="monday", hour=18)
    intent  = _intent(class_type="salsa", day="monday", name_keywords=["on1", "partnerwork"])
    assert _score_match(on1, intent) > _score_match(improv, intent)


def test_score_match_name_keyword_lec_ignite():
    ignite  = _card("LEC Ignite Company Training", day="thursday", hour=19)
    bachata = _card("Bachata Shines",               day="thursday", hour=18)
    intent  = _intent(day="thursday", name_keywords=["lec", "ignite", "company"])
    assert _score_match(ignite, intent) > _score_match(bachata, intent)


def test_score_match_name_keywords_empty_no_change():
    score_without = _score_match(_card("Salsa"), _intent())
    score_with    = _score_match(_card("Salsa"), _intent(name_keywords=[]))
    assert score_without == score_with


# ---------------------------------------------------------------------------
# _build_cards
# ---------------------------------------------------------------------------

def _raw(name="Salsa", date_str="Monday, March 2, 2026",
         dur_str="6:00 PM\n - \n7:00 PM\n60 min",
         booking_url="https://momence.com/s/123"):
    return {"name": name, "date_str": date_str, "dur_str": dur_str, "booking_url": booking_url}


def test_build_cards_happy_path():
    cards = _build_cards([_raw()])
    assert len(cards) == 1
    c = cards[0]
    assert c.name == "Salsa"
    assert c.day == "monday"
    assert c.hour == 18
    assert c.booking_url == "https://momence.com/s/123"


def test_build_cards_saturday():
    cards = _build_cards([_raw(date_str="Saturday, February 28, 2026")])
    assert cards[0].day == "saturday"


def test_build_cards_morning_class():
    cards = _build_cards([_raw(dur_str="10:00 AM\n - \n11:00 AM\n60 min")])
    assert cards[0].hour == 10


def test_build_cards_skips_missing_day():
    raw = _raw(date_str="March 2, 2026")  # no weekday name
    assert _build_cards([raw]) == []


def test_build_cards_skips_missing_booking_url():
    raw = _raw(booking_url="")
    assert _build_cards([raw]) == []


def test_build_cards_skips_unparseable_time():
    raw = _raw(dur_str="no time here")
    assert _build_cards([raw]) == []


def test_build_cards_multiple():
    raws = [
        _raw("Salsa Improvers", "Monday, March 2, 2026", "6:00 PM\n - \n7:00 PM\n60 min", "https://momence.com/s/1"),
        _raw("Bachata Shines",  "Thursday, March 5, 2026", "6:00 PM\n - \n7:00 PM\n60 min", "https://momence.com/s/2"),
    ]
    cards = _build_cards(raws)
    assert len(cards) == 2
    assert cards[0].day == "monday"
    assert cards[1].day == "thursday"
