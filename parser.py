"""
Natural language intent parser.

Extracts class_type, level, day, and time_of_day from free text input.
Example: "book beginner salsa on Friday evening"
         -> {"class_type": "salsa", "level": "beginner", "day": "friday", "time": "evening"}
"""

import re
from datetime import date, timedelta


DAYS_OF_WEEK = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

CLASS_TYPES = ["salsa", "bachata", "merengue", "cha cha", "kizomba", "tango", "rumba", "samba"]

LEVEL_KEYWORDS = {
    "beginner":     ["beginner", "beginners", "intro", "introduction", "starter", "level 1", "lvl 1"],
    "intermediate": ["intermediate", "level 2", "lvl 2"],
    "advanced":     ["advanced", "level 3", "lvl 3", "improver"],
}

TIME_KEYWORDS = {
    "morning":   ["morning", "am"],
    "afternoon": ["afternoon", "midday", "noon", "lunch"],
    "evening":   ["evening", "night", "pm"],
}


def _resolve_day(text: str) -> str | None:
    """Return a lowercase weekday name, or None if not found."""
    today = date.today()

    if "today" in text:
        return today.strftime("%A").lower()
    if "tomorrow" in text:
        return (today + timedelta(days=1)).strftime("%A").lower()

    for day in DAYS_OF_WEEK:
        if day in text:
            return day

    return None


def parse(text: str) -> dict:
    """
    Parse a natural language booking request.

    Returns a dict with keys:
        class_type  str | "any"
        level       str | "any"   ("beginner", "intermediate", "advanced")
        day         str | None    (lowercase weekday name)
        time        str | "any"   ("morning", "afternoon", "evening")
    """
    lowered = text.lower()

    # --- class type ---
    class_type = "any"
    for ct in CLASS_TYPES:
        if ct in lowered:
            class_type = ct
            break

    # --- level ---
    level = "any"
    for level_name, keywords in LEVEL_KEYWORDS.items():
        for kw in keywords:
            if kw in lowered:
                level = level_name
                break
        if level != "any":
            break

    # --- day ---
    day = _resolve_day(lowered)

    # --- time of day ---
    time_of_day = "any"
    for period, keywords in TIME_KEYWORDS.items():
        for kw in keywords:
            if kw in lowered:
                time_of_day = period
                break
        if time_of_day != "any":
            break

    return {
        "class_type": class_type,
        "level":      level,
        "day":        day,
        "time":       time_of_day,
    }


def describe(intent: dict) -> str:
    """Return a human-readable summary of the parsed intent."""
    parts = []
    if intent["class_type"] != "any":
        parts.append(intent["class_type"])
    if intent["level"] != "any":
        parts.append(f"({intent['level']})")
    if intent["day"]:
        parts.append(f"on {intent['day'].capitalize()}")
    if intent["time"] != "any":
        parts.append(f"in the {intent['time']}")
    return " ".join(parts) if parts else "any class"
