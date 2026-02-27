# lec-dance-booker

Automates booking classes on [lec.dance](https://www.lec.dance) via the Momence booking widget using Playwright.

## Setup

**1. Install dependencies**

```bash
# Requires uv (https://astral.sh/uv)
uv sync
uv run playwright install chromium
```

**2. Add credentials**

```bash
cp .env.example .env
# Edit .env with your Momence email and password
```

---

## Usage

### Interactive

```bash
uv run python main.py
```

Prompts you to type a class description, then asks for confirmation before booking.

---

### Single booking

```bash
uv run python main.py "book beginner salsa on Friday evening"
uv run python main.py "salsa improvers monday"
uv run python main.py "bachata thursday evening"
```

The query is parsed for:
- **Class type** — salsa, bachata, merengue, cha cha, kizomba, tango, rumba, samba
- **Level** — beginner / intermediate / advanced (also: intro, improver, level 1/2/3)
- **Day** — monday–sunday, today, tomorrow
- **Time** — morning, afternoon, evening (or am/pm)

All fields are optional — any you omit are treated as "any".

---

### Skip confirmation (`--yes`)

```bash
uv run python main.py "salsa improvers monday evening" --yes
```

Skips the "Book this class? [y/n]" prompt. If multiple classes match, auto-picks the highest-scoring one.

---

### Headless mode (`--headless`)

```bash
uv run python main.py "salsa improvers monday evening" --headless
```

Runs the browser invisibly. Combine with `--yes` for fully unattended operation:

```bash
uv run python main.py "salsa improvers monday evening" --yes --headless
```

---

### Book your weekly schedule (`--schedule`)

Define your regular classes in `schedule.yaml`:

```yaml
monday:
  - "salsa improvers monday evening"
  - "salsa on1 partnerwork monday"

wednesday:
  - "salsa shines wednesday evening"
```

Then book everything scheduled for a given day:

```bash
# Book today's classes
uv run python main.py --schedule

# Book a specific day
uv run python main.py --schedule monday
uv run python main.py --schedule wednesday --headless
```

This logs in once and loads the timetable once, then books each class in sequence.

Exit code is `0` if all classes succeeded, `1` if any failed.

---

## Agent / automation use

The CLI is designed to be called as a tool by an LLM agent or scheduler:

```python
import subprocess

result = subprocess.run(
    ["uv", "run", "python", "main.py", "--schedule", "monday", "--yes", "--headless"],
    cwd="/path/to/lec-dance-booker",
    capture_output=True,
    text=True,
)
success = result.returncode == 0
output  = result.stdout
```

Or as a cron job (books today's classes every day at 8am):

```
0 8 * * * cd /path/to/lec-dance-booker && uv run python main.py --schedule --yes --headless
```

---

## How it works

1. Logs in to `momence.com` first (same browser session)
2. Navigates to `lec.dance/timetable` and waits for the Momence widget to render
3. Scrapes all class cards (title, day, start time)
4. Scores each card against your query using hard filters (day, time window) and soft scoring (class type, level)
5. Navigates directly to the Momence booking URL and clicks **Book Now**
6. Detects "already booked" and treats it as success

---

## Files

| File | Purpose |
|---|---|
| `main.py` | CLI entry point, flag parsing, schedule runner |
| `booker.py` | Playwright automation (login, scrape, book) |
| `parser.py` | Natural language intent parser |
| `schedule.yaml` | Your weekly class schedule |
| `.env` | Credentials (never committed) |
| `.env.example` | Credentials template |
