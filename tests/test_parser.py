import intent_parser as parser


def test_parse_full_query():
    r = parser.parse("book beginner salsa on monday evening")
    assert r["class_type"] == "salsa"
    assert r["level"] == "beginner"
    assert r["day"] == "monday"
    assert r["time"] == "evening"


def test_parse_partial_no_level_or_time():
    r = parser.parse("bachata thursday")
    assert r["class_type"] == "bachata"
    assert r["day"] == "thursday"
    assert r["level"] == "any"
    assert r["time"] == "any"


def test_parse_improver_maps_to_advanced():
    r = parser.parse("salsa improvers")
    assert r["level"] == "advanced"


def test_parse_intro_maps_to_beginner():
    r = parser.parse("salsa intro class")
    assert r["level"] == "beginner"


def test_parse_am_maps_to_morning():
    r = parser.parse("salsa class am")
    assert r["time"] == "morning"


def test_parse_pm_maps_to_evening():
    r = parser.parse("salsa class pm")
    assert r["time"] == "evening"


def test_parse_no_match_returns_any():
    r = parser.parse("just book something")
    assert r["class_type"] == "any"
    assert r["level"] == "any"
    assert r["day"] is None
    assert r["time"] == "any"


def test_parse_today(monkeypatch):
    from datetime import date
    monkeypatch.setattr("intent_parser.date",type("date", (), {"today": staticmethod(lambda: date(2026, 3, 2))}))
    r = parser.parse("salsa today")
    assert r["day"] == "monday"  # March 2 2026 is a Monday


def test_parse_tomorrow(monkeypatch):
    from datetime import date
    monkeypatch.setattr("intent_parser.date",type("date", (), {"today": staticmethod(lambda: date(2026, 3, 2))}))
    r = parser.parse("salsa tomorrow")
    assert r["day"] == "tuesday"


def test_describe_full():
    r = parser.parse("beginner salsa monday evening")
    desc = parser.describe(r)
    assert "salsa" in desc
    assert "Monday" in desc
    assert "evening" in desc


def test_describe_any_returns_any_class():
    r = parser.parse("nothing matched")
    assert parser.describe(r) == "any class"


# ---------------------------------------------------------------------------
# name_keywords
# ---------------------------------------------------------------------------

def test_name_keywords_extracted_for_levelless_class():
    r = parser.parse("salsa on1 partnerwork monday")
    assert "on1" in r["name_keywords"]
    assert "partnerwork" in r["name_keywords"]


def test_name_keywords_excludes_class_type():
    r = parser.parse("salsa playground")
    assert "salsa" not in r["name_keywords"]
    assert "playground" in r["name_keywords"]


def test_name_keywords_excludes_day():
    r = parser.parse("salsa playground monday")
    assert "monday" not in r["name_keywords"]


def test_name_keywords_excludes_stop_words():
    r = parser.parse("book a salsa class on monday evening")
    assert "book" not in r["name_keywords"]
    assert "a" not in r["name_keywords"]
    assert "on" not in r["name_keywords"]
    assert "class" not in r["name_keywords"]


def test_name_keywords_lec_ignite():
    r = parser.parse("LEC Ignite Company")
    assert "ignite" in r["name_keywords"]
    assert "company" in r["name_keywords"]


# ---------------------------------------------------------------------------
# Day injection
# ---------------------------------------------------------------------------

def test_day_injection_when_no_day_in_query():
    intent = parser.parse("mens salsa")
    day = "tuesday"
    if day and intent["day"] is None:
        intent["day"] = day
    assert intent["day"] == "tuesday"


def test_day_injection_does_not_override_explicit_day():
    intent = parser.parse("salsa advanced shines tuesday evening")
    day = "monday"
    if day and intent["day"] is None:
        intent["day"] = day
    assert intent["day"] == "tuesday"
