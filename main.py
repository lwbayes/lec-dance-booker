"""
lec.dance class booker — CLI entry point.

Usage:
    python main.py "book beginner salsa on Friday evening"
    python main.py          # prompts for input interactively

Agent flags:
    --yes              Skip all confirmation prompts (auto-confirm)
    --headless         Run browser without opening a visible window
    --schedule [day]   Book all classes from schedule.yaml for a given day
                       (defaults to today if no day is given)
"""

import sys
import os
from datetime import date
from dotenv import load_dotenv
import yaml

import parser as intent_parser
import booker

SCHEDULE_FILE = os.path.join(os.path.dirname(__file__), "schedule.yaml")


def main() -> None:
    load_dotenv()

    email = os.getenv("LEC_EMAIL")
    password = os.getenv("LEC_PASSWORD")

    if not email or not password:
        print(
            "✗  Credentials not found.\n"
            "   Copy .env.example to .env and fill in your email and password."
        )
        sys.exit(1)

    args = sys.argv[1:]
    yes      = "--yes"      in args
    headless = "--headless" in args
    args     = [a for a in args if a not in ("--yes", "--headless")]

    # --schedule [day]
    if "--schedule" in args:
        idx = args.index("--schedule")
        args.pop(idx)
        # Optional day argument immediately after the flag
        if idx < len(args) and not args[idx].startswith("--"):
            day = args.pop(idx).lower()
        else:
            day = date.today().strftime("%A").lower()

        _run_schedule(day, email, password, headless=headless)
        return

    # Single booking
    if args:
        text = " ".join(args)
    else:
        text = input("What class would you like to book?\n> ").strip()

    if not text:
        print("✗  No input provided.")
        sys.exit(1)

    intent = intent_parser.parse(text)
    summary = intent_parser.describe(intent)
    print(f"\nLooking for: {summary}")
    print(f"  class_type : {intent['class_type']}")
    print(f"  level      : {intent['level']}")
    print(f"  day        : {intent['day'] or 'any'}")
    print(f"  time       : {intent['time']}")

    ok = booker.run(intent, email, password, yes=yes, headless=headless)
    sys.exit(0 if ok else 1)


def _run_schedule(day: str, email: str, password: str, headless: bool) -> None:
    try:
        with open(SCHEDULE_FILE, encoding="utf-8") as f:
            schedule = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"✗  schedule.yaml not found. Create it next to main.py.")
        sys.exit(1)

    queries = schedule.get(day, [])
    if not queries:
        print(f"No classes scheduled for {day.capitalize()}.")
        sys.exit(0)

    print(f"Booking {len(queries)} class(es) for {day.capitalize()}:")
    for q in queries:
        print(f"  • {q}")
    print()

    results = booker.run_schedule(queries, email, password, headless=headless)

    print("\n--- Results ---")
    all_ok = True
    for query, ok in results.items():
        status = "OK" if ok else "FAILED"
        print(f"  [{status}] {query}")
        if not ok:
            all_ok = False

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
