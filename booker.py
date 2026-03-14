"""
Playwright automation for booking a class on lec.dance.

Flow:
  1. Log in to momence.com first (same browser context)
  2. Navigate to lec.dance/timetable
  3. Wait for Momence widget to render
  4. Scrape available class cards
  5. Match against parsed intent
  6. Confirm with user
  7. Navigate to the booking URL and complete it
"""

import re
from dataclasses import dataclass
from datetime import date

from playwright.sync_api import sync_playwright, Page, Locator, TimeoutError as PWTimeout

import intent_parser

TIMETABLE_URL  = "https://www.lec.dance/timetable"
MOMENCE_LOGIN  = "https://momence.com/login"

# How long to wait for the Momence widget to render (ms)
WIDGET_TIMEOUT = 20_000

# Momence widget selectors (verified against live page Feb 2026)
_SEL_CARD  = "[class*='momence-host_schedule-session_list-item']"
_SEL_TITLE = "[class*='momence-host_schedule-session_list-item-title']"
_SEL_DATE  = "[class*='momence-session-starts_at']"   # "Saturday, February 28, 2026"
_SEL_DUR   = "[class*='momence-session-duration']"    # "10:00 AM\n - \n11:00 AM\n60 min"

# Time-of-day hour windows
TIME_WINDOWS = {
    "morning":   (0,  12),
    "afternoon": (12, 17),
    "evening":   (17, 24),
}


@dataclass
class ClassCard:
    name:        str
    day:         str   # lowercase weekday
    time:        str   # start time token e.g. "6:00"
    hour:        int   # 24h hour integer
    booking_url: str   # momence.com/s/... direct booking link

    def display(self) -> str:
        return f"{self.name}  |  {self.day.capitalize()}  {self.time}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_hour(time_str: str) -> int:
    """Extract hour from a time string like '7:30 PM' or '19:30'."""
    time_str = time_str.strip().upper()
    # 12-hour format with AM/PM
    m = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)", time_str)
    if m:
        h = int(m.group(1))
        if m.group(3) == "PM" and h != 12:
            h += 12
        if m.group(3) == "AM" and h == 12:
            h = 0
        return h
    # 24-hour format
    m = re.search(r"(\d{1,2}):(\d{2})", time_str)
    if m:
        return int(m.group(1))
    return -1


def _text(locator: Locator, selector: str, fallback: str = "") -> str:
    try:
        el = locator.locator(selector).first
        return el.inner_text(timeout=1000).strip()
    except Exception:
        return fallback


def _score_match(card: ClassCard, intent: dict) -> int:
    """
    Return a match score (higher = better). 0 means hard-filtered out.
    Filters:  day match, time window, class_type, level.
    """
    score = 1

    # Day filter (hard)
    if intent["day"] and card.day != intent["day"]:
        return 0

    # Time-of-day filter (hard)
    if intent["time"] != "any":
        lo, hi = TIME_WINDOWS[intent["time"]]
        if not (lo <= card.hour < hi):
            return 0

    # Class type (soft score)
    if intent["class_type"] != "any":
        if intent["class_type"].lower() in card.name.lower():
            score += 2

    # Level (soft score)
    if intent["level"] != "any":
        level_synonyms = {
            "beginner":     ["beginner", "intro", "level 1", "lvl 1"],
            "intermediate": ["intermediate", "level 2", "lvl 2"],
            "advanced":     ["advanced", "level 3", "lvl 3", "improver"],
        }
        for kw in level_synonyms.get(intent["level"], []):
            if kw in card.name.lower():
                score += 2
                break

    # Name keyword soft score — helps match classes without a level
    # e.g. "on1", "playground", "ignite" distinguish specific classes
    name_lower = card.name.lower()
    for kw in intent.get("name_keywords", []):
        if kw in name_lower:
            score += 1

    return score


# ---------------------------------------------------------------------------
# Main booking function
# ---------------------------------------------------------------------------

def run(intent: dict, email: str, password: str, *, yes: bool = False, headless: bool = False) -> bool:
    """Run the full booking flow. Returns True on success."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        # ------------------------------------------------------------------
        # Step 1: Log in to Momence first
        # ------------------------------------------------------------------
        for attempt in range(3):
            if _login_momence(page, email, password):
                break
            if attempt < 2:
                print(f"  Retrying login ({attempt + 2}/3)...")
        else:
            browser.close()
            return False

        # ------------------------------------------------------------------
        # Step 2: Load the timetable
        # ------------------------------------------------------------------
        print(f"\nOpening {TIMETABLE_URL} ...")
        page.goto(TIMETABLE_URL, wait_until="domcontentloaded", timeout=30_000)

        print("  Waiting for class schedule to load...")
        timetable_loaded = False
        for attempt in range(3):
            try:
                page.wait_for_selector(_SEL_TITLE, timeout=WIDGET_TIMEOUT)
                timetable_loaded = True
                break
            except PWTimeout:
                if attempt < 2:
                    print(f"  Timetable not ready, retrying ({attempt + 2}/3)...")
                    page.goto(TIMETABLE_URL, wait_until="domcontentloaded", timeout=30_000)
        if not timetable_loaded:
            print("\n✗ Timetable did not load after 3 attempts.")
            print("  Please inspect the page manually and update the selectors in booker.py.")
            browser.close()
            return False

        # Give JS a moment to finish rendering all cards
        page.wait_for_timeout(2000)

        # ------------------------------------------------------------------
        # Step 3: Scrape class cards
        # ------------------------------------------------------------------
        cards = _scrape_classes(page)

        if not cards:
            print("\n✗ No classes found on the timetable page.")
            print("  The Momence widget structure may have changed — check booker.py selectors.")
            browser.close()
            return False

        print(f"  Found {len(cards)} classes on the timetable.\n")

        # ------------------------------------------------------------------
        # Step 3: Match intent
        # ------------------------------------------------------------------
        scored = [(c, _score_match(c, intent)) for c in cards]
        matches = [(c, s) for c, s in scored if s > 0]
        matches.sort(key=lambda x: x[1], reverse=True)

        if not matches:
            print("✗ No classes match your request.\n")
            print("Available classes:")
            for c in cards:
                print(f"  • {c.display()}")
            browser.close()
            return False

        # ------------------------------------------------------------------
        # Step 4: Confirm with user (skipped when yes=True)
        # ------------------------------------------------------------------
        if len(matches) == 1:
            chosen, _ = matches[0]
        elif yes:
            # Auto-pick the top-scoring match
            chosen, _ = matches[0]
            print(f"  Auto-selected best match: {chosen.display()}")
        else:
            print("Multiple matching classes found:\n")
            for i, (c, _) in enumerate(matches, 1):
                print(f"  [{i}] {c.display()}")
            while True:
                raw = input("\nEnter number to book (or 'q' to quit): ").strip()
                if raw.lower() == "q":
                    browser.close()
                    return False
                if raw.isdigit() and 1 <= int(raw) <= len(matches):
                    chosen = matches[int(raw) - 1][0]
                    break
                print("  Invalid choice, try again.")

        print(f"\nFound:  {chosen.display()}")
        if not yes:
            confirm = input("Book this class? [y/n]: ").strip().lower()
            if confirm != "y":
                print("Cancelled.")
                browser.close()
                return False

        # ------------------------------------------------------------------
        # Step 5: Book the chosen class
        # ------------------------------------------------------------------
        ok = _book_class(page, chosen)
        browser.close()
        return ok


def run_schedule(queries: list[str], email: str, password: str, *, day: str | None = None, headless: bool = False) -> dict:
    """
    Book multiple classes in a single browser session (one login, one timetable load).
    Returns a dict mapping each query to True (booked/already booked) or False (failed).
    """
    results = {q: False for q in queries}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        for attempt in range(3):
            if _login_momence(page, email, password):
                break
            if attempt < 2:
                print(f"  Retrying login ({attempt + 2}/3)...")
        else:
            browser.close()
            return results

        print(f"\nOpening {TIMETABLE_URL} ...")
        page.goto(TIMETABLE_URL, wait_until="domcontentloaded", timeout=30_000)
        print("  Waiting for class schedule to load...")
        timetable_loaded = False
        for attempt in range(3):
            try:
                page.wait_for_selector(_SEL_TITLE, timeout=WIDGET_TIMEOUT)
                timetable_loaded = True
                break
            except PWTimeout:
                if attempt < 2:
                    print(f"  Timetable not ready, retrying ({attempt + 2}/3)...")
                    page.goto(TIMETABLE_URL, wait_until="domcontentloaded", timeout=30_000)
        if not timetable_loaded:
            print("\n✗ Timetable did not load after 3 attempts.")
            browser.close()
            return results
        page.wait_for_timeout(2000)

        cards = _scrape_classes(page)
        if not cards:
            print("\n✗ No classes found on the timetable page.")
            browser.close()
            return results
        print(f"  Found {len(cards)} classes.\n")

        for i, query in enumerate(queries):
            print(f"--- {query} ---")
            intent = intent_parser.parse(query)
            if day and intent["day"] is None:
                intent["day"] = day
            scored = [(c, _score_match(c, intent)) for c in cards]
            matches = [(c, s) for c, s in scored if s > 0]
            matches.sort(key=lambda x: x[1], reverse=True)

            if not matches:
                print(f"  ✗ No match found.\n")
                continue

            chosen, _ = matches[0]
            print(f"  Matched: {chosen.display()}")
            results[query] = _book_class(page, chosen)

        browser.close()
    return results


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

def _scrape_raw(page: Page) -> list[dict]:
    """
    Browser I/O only: pull raw text fields + booking URL from each class card.
    Returns plain dicts — no live Playwright objects.
    """
    raw: list[dict] = []
    card_locators = page.locator(_SEL_CARD).filter(
        has=page.locator(_SEL_TITLE)
    ).all()

    for el in card_locators:
        name = _text(el, _SEL_TITLE)
        if not name:
            continue
        try:
            booking_url = el.locator("a").filter(
                has_text=re.compile(r"book now|book", re.I)
            ).first.get_attribute("href", timeout=2000) or ""
        except Exception:
            booking_url = ""
        raw.append({
            "name":        name,
            "date_str":    _text(el, _SEL_DATE),
            "dur_str":     _text(el, _SEL_DUR),
            "booking_url": booking_url,
        })
    return raw


def _build_cards(raw: list[dict]) -> list[ClassCard]:
    """
    Pure function: convert raw scraped dicts into ClassCard objects.
    No browser, no I/O — fully unit-testable.
    """
    cards: list[ClassCard] = []
    for r in raw:
        day = ""
        for d in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
            if d in r["date_str"].lower():
                day = d
                break

        dur_str = r["dur_str"]
        time_str = ""
        hour = -1
        for token in dur_str.replace("\n", " ").split():
            if re.search(r"\d{1,2}:\d{2}", token):
                time_str = token
                hour = _parse_hour(dur_str)
                break

        if r["name"] and day and hour >= 0 and r["booking_url"]:
            cards.append(ClassCard(
                name=r["name"],
                day=day,
                time=time_str,
                hour=hour,
                booking_url=r["booking_url"],
            ))
    return cards


def _scrape_classes(page: Page) -> list[ClassCard]:
    """Convenience wrapper: scrape raw data then build cards."""
    return _build_cards(_scrape_raw(page))


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def _login_momence(page: Page, email: str, password: str) -> bool:
    """Log in to momence.com. Returns True on success."""
    print(f"Logging in to {MOMENCE_LOGIN} ...")
    page.goto(MOMENCE_LOGIN, wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(2000)

    try:
        page.wait_for_selector("input[type='email'], input[name='email']", timeout=10_000)
        page.fill("input[type='email'], input[name='email']", email)
        page.fill("input[type='password'], input[name='password']", password)
        page.locator("button").filter(
            has_text=re.compile(r"log in|sign in|continue|submit", re.I)
        ).first.click()
        # Wait for redirect away from login page, then let the page settle
        page.wait_for_url(re.compile(r"momence\.com(?!/login)"), timeout=15_000)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        print("  Logged in.")
        return True
    except PWTimeout:
        print("\n✗ Login failed or timed out. Check your credentials.")
        return False


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------

_ALREADY_BOOKED  = re.compile(r"already (booked|registered|enrolled|signed up)", re.I)
_SUCCESS_PATTERN = re.compile(r"booking confirmed|you'?re booked|you are booked|see you|success", re.I)
_FAILURE_PATTERN = re.compile(r"class is full|sold out|no spots|payment required|payment needed", re.I)


def _book_class(page: Page, card: ClassCard) -> bool:
    """Navigate to the Momence booking page and confirm the booking. Returns True on success."""
    print(f"\nNavigating to booking page...")
    page.goto(card.booking_url, wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(3000)

    if page.locator("body").filter(has_text=_ALREADY_BOOKED).count() > 0:
        print("\n✓ Already booked for this class.")
        return True

    print("  Looking for confirm button...")
    try:
        confirm_btn = page.locator("button").filter(
            has_text=re.compile(r"confirm|book|reserve|complete|add to cart|checkout", re.I)
        ).first
        confirm_btn.wait_for(timeout=10_000)
        print(f"  Found: '{confirm_btn.inner_text()}'")
        confirm_btn.click()
        page.wait_for_timeout(4000)

        body = page.locator("body")
        if body.filter(has_text=_ALREADY_BOOKED).count() > 0:
            print("\n✓ Already booked for this class.")
            return True
        if body.filter(has_text=_SUCCESS_PATTERN).count() > 0:
            print("\n✓ Booking confirmed!")
            return True
        if body.filter(has_text=_FAILURE_PATTERN).count() > 0:
            print("\n✗ Booking failed — class may be full or payment is required.")
            return False
        print("\n⚠  Could not confirm booking status — assuming success.")
        return True
    except PWTimeout:
        print("\n⚠  Could not find a confirm button on the booking page.")
        print(f"   URL: {page.url}")
        btns = page.locator("button:visible").all()
        print(f"  Visible buttons ({len(btns)}):")
        for b in btns[:10]:
            try:
                print(f"    '{b.inner_text(timeout=500).strip()}'")
            except Exception:
                pass
        return False
