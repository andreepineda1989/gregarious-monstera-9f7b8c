"""
planner.py — Generates a time-blocked weekly plan.
Reads the week's Google Calendar events and asks Claude to produce
a structured plan that fits in all weekly targets.
"""

import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import anthropic

from gcal import get_service, get_events, format_event
from tracker import compute_stats, load_habits

BASE_DIR = Path(__file__).parent
MODEL = "claude-sonnet-4-20250514"

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _week_monday(offset_weeks: int = 0) -> date:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return monday + timedelta(weeks=offset_weeks)


def _group_events_by_day(events: list, monday: date) -> dict:
    """Return {day_name: [events]} for the 7 days starting at monday."""
    by_day: dict[str, list] = {d: [] for d in DAYS}
    for event in events:
        start_raw = event["start"].get("dateTime", event["start"].get("date", ""))
        if "T" in start_raw:
            from gcal import parse_event_dt
            dt = parse_event_dt(start_raw).date()
        else:
            dt = date.fromisoformat(start_raw[:10])

        delta = (dt - monday).days
        if 0 <= delta <= 6:
            by_day[DAYS[delta]].append(event)

    return by_day


def _events_text(by_day: dict) -> str:
    lines = []
    for day in DAYS:
        events = by_day[day]
        lines.append(f"\n{day}:")
        if events:
            for e in events:
                lines.append(f"  • {format_event(e)}")
        else:
            lines.append("  (no events)")
    return "\n".join(lines)


def run_planner() -> None:
    print("\n📅  LIFE OS — Weekly Planner")
    print("=" * 44)

    # ── Load profile + habits ─────────────────────────────────────────────────
    with open(BASE_DIR / "profile.json") as fh:
        profile = json.load(fh)

    habits = load_habits()
    stats = compute_stats(habits.get("daily_log", {}))
    w = stats["weekly"]
    targets = profile["weekly_targets"]

    # ── Which week? ───────────────────────────────────────────────────────────
    print("\nWhich week to plan?")
    print("  [1] This week")
    print("  [2] Next week")
    choice = input("  → ").strip()
    offset = 1 if choice == "2" else 0
    monday = _week_monday(offset)
    sunday = monday + timedelta(days=6)
    print(f"\nPlanning week: {monday.strftime('%d %b')} – {sunday.strftime('%d %b %Y')}")

    # ── Google Calendar ───────────────────────────────────────────────────────
    events_text = "(calendar unavailable)"
    try:
        service = get_service()
        events = get_events(service, monday, sunday)
        by_day = _group_events_by_day(events, monday)
        events_text = _events_text(by_day)
        print(f"✓  {len(events)} events loaded from Google Calendar")
    except Exception as exc:
        print(f"⚠  Calendar: {exc}", file=sys.stderr)

    # ── Context for Claude ────────────────────────────────────────────────────
    remaining_ai = max(0, targets["ai_project_hours"] - (w["ai_project_hours"] if offset == 0 else 0))
    remaining_french = max(0, targets["french_spoken_sessions"] - (w["french_spoken_sessions"] if offset == 0 else 0))
    remaining_gym = max(0, targets["gym_sessions"] - (w["gym_sessions"] if offset == 0 else 0))

    progress_note = ""
    if offset == 0:
        progress_note = f"""
ALREADY COMPLETED THIS WEEK:
  AI project: {w['ai_project_hours']:.1f}h (need {remaining_ai:.1f}h more)
  French spoken: {w['french_spoken_sessions']} sessions ({remaining_french} more needed)
  Gym: {w['gym_sessions']} sessions ({remaining_gym} more needed)
"""

    # ── Claude API ────────────────────────────────────────────────────────────
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("✗  ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    system = [
        {
            "type": "text",
            "text": f"""You are the Life OS weekly planner for Andreé.

PROFILE:
{json.dumps(profile, indent=2)}

Planning rules:
1. NEVER move or remove fixed commitments (Work, Andrea routines, couple time, family time)
2. Protect: Sat 19:00 Finance review, Sun 20:00 Weekly planning
3. French Babbel/Busuu = 06:00 every morning (30 min, non-negotiable)
4. French spoken practice ONLY on: Mon, Tue, Thu, Sat, Sun — 20 min
5. AI deep work: Sat 08:00–10:00 and Sun 08:00–10:00 are peak blocks; use evenings for the rest
6. Gym days: Mon 06:30, Fri 06:30, Sat 10:00, Sun 10:00
7. Do not over-schedule weekday evenings — leave buffer for energy/family

Output format:
- One section per day (Monday through Sunday)
- Each time block on its own line: HH:MM–HH:MM  Activity
- End with a "WEEKLY PRIORITIES" section (top 3 numbered items)
- Plain text, no markdown headers or decorations

Week: {monday.strftime('%d %B')} – {sunday.strftime('%d %B %Y')}""",
            "cache_control": {"type": "ephemeral"},
        }
    ]

    user_msg = f"""EXISTING CALENDAR COMMITMENTS:
{events_text}
{progress_note}
Generate the full weekly plan, filling productive blocks around these commitments.
Ensure {remaining_ai:.1f}h AI project, {remaining_french} French spoken sessions, and {remaining_gym} gym sessions are scheduled."""

    print("\n🤖  Generating weekly plan...\n")
    print("-" * 44)

    full_text = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=2500,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    ) as stream:
        for chunk in stream.text_stream:
            print(chunk, end="", flush=True)
            full_text += chunk

    print("\n" + "-" * 44)

    # ── Save option ───────────────────────────────────────────────────────────
    save = input("\n💾  Save to weekly_plan.md? [y/n]  ").strip().lower()
    if save == "y":
        plan_file = BASE_DIR / "weekly_plan.md"
        with open(plan_file, "w") as fh:
            fh.write(f"# Weekly Plan — {monday.strftime('%d %b')} to {sunday.strftime('%d %b %Y')}\n\n")
            fh.write(full_text)
        print(f"  ✓ Saved to {plan_file}")

    print("\n" + "=" * 44)
