"""
checkin.py — Evening check-in.
Logs what got done, updates habits.json, asks Claude for a reflection
and rescheduling suggestions for anything missed.
"""

import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import anthropic

from gcal import get_service, get_events, format_events_block, create_event
from tracker import (
    GYM_DAYS,
    SPOKEN_DAYS,
    compute_stats,
    load_habits,
    log_today,
    save_habits,
)

BASE_DIR = Path(__file__).parent
MODEL = "claude-sonnet-4-20250514"


def _ask_yn(prompt: str) -> bool:
    return input(f"  {prompt} [y/n]  ").strip().lower() == "y"


def _ask_float(prompt: str, default: float = 0.0) -> float:
    raw = input(f"  {prompt} (e.g. 1.5, default 0)  ").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _ask_int(prompt: str) -> int | None:
    raw = input(f"  {prompt} (press Enter to skip)  ").strip()
    return int(raw) if raw.isdigit() else None


def run_checkin() -> None:
    now = datetime.now()
    today = date.today()
    today_str = today.isoformat()
    day_name = today.strftime("%A")

    print(f"\n🌙  LIFE OS — Evening Check-in")
    print("=" * 44)
    print(f"📅  {now.strftime('%A, %d %B %Y')}  —  {now.strftime('%H:%M')}\n")

    # ── Load data ─────────────────────────────────────────────────────────────
    with open(BASE_DIR / "profile.json") as fh:
        profile = json.load(fh)

    habits = load_habits()
    daily_log = habits.get("daily_log", {})

    # ── Today's calendar ──────────────────────────────────────────────────────
    events_block = ""
    gcal_service = None
    try:
        gcal_service = get_service()
        events = get_events(gcal_service, today, today)
        events_block = format_events_block(events)
    except Exception as exc:
        print(f"⚠  Calendar: {exc}", file=sys.stderr)

    # ── Interactive questions ─────────────────────────────────────────────────
    print("Answer each question — press Enter to skip:\n")
    entry: dict = {}
    missed: list[str] = []

    # French daily (every day)
    done = _ask_yn("🇫🇷  French Babbel/Busuu today?")
    entry["french_daily"] = done
    if not done:
        missed.append("French daily study (Babbel/Busuu)")

    # French spoken (scheduled days only)
    if day_name in SPOKEN_DAYS:
        done = _ask_yn("💬  Spoken French with Claude (20 min)?")
        entry["french_spoken"] = done
        if not done:
            missed.append("Spoken French practice (20 min)")

    # Gym (scheduled days only)
    if day_name in GYM_DAYS:
        done = _ask_yn("🏋️  Gym session done?")
        entry["gym"] = done
        if not done:
            missed.append("Gym session")

    # Steps
    steps = _ask_int("👟  Steps today? (number)")
    if steps is not None:
        entry["steps"] = steps
        entry["steps_10k"] = steps >= 10000
        label = "✅ 10k reached!" if steps >= 10000 else f"📊 {steps:,} — {10000 - steps:,} to go"
        print(f"     {label}")

    # AI project
    ai_hours = _ask_float("🤖  AI project hours today?")
    entry["ai_project_hours"] = ai_hours
    entry["ai_project_any"] = ai_hours > 0
    if ai_hours == 0:
        missed.append("AI project work")
    else:
        print(f"     ✅  {ai_hours:.1f}h logged")

    # Finance review (Saturdays)
    if day_name == "Saturday":
        done = _ask_yn("💰  Finance review done?")
        entry["finance_review"] = done
        if not done:
            missed.append("Finance review")

    # Weekly planning (Sundays)
    if day_name == "Sunday":
        done = _ask_yn("📋  Weekly planning session done?")
        entry["weekly_planning"] = done
        if not done:
            missed.append("Weekly planning")

    # Notes / wins
    notes = input("\n  📝  Any wins or notes? (Enter to skip)  ").strip()
    if notes:
        entry["notes"] = notes

    # ── Save ──────────────────────────────────────────────────────────────────
    habits = log_today(habits, entry)
    save_habits(habits)
    print("\n  ✓ Habits saved.\n")

    # ── Stats for Claude ──────────────────────────────────────────────────────
    updated_log = habits["daily_log"]
    stats = compute_stats(updated_log)
    s = stats["streaks"]
    w = stats["weekly"]
    targets = profile["weekly_targets"]

    # ── Claude reflection ─────────────────────────────────────────────────────
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("✗  ANTHROPIC_API_KEY not set.", file=sys.stderr)
        return

    client = anthropic.Anthropic(api_key=api_key)

    system = [
        {
            "type": "text",
            "text": f"""You are Life OS, a personal accountability coach for Andreé.

PROFILE:
{json.dumps(profile, indent=2)}

Today is {now.strftime('%A, %d %B %Y')}. Be honest, warm, and concise.""",
            "cache_control": {"type": "ephemeral"},
        }
    ]

    ai_gap = max(0, targets["ai_project_hours"] - w["ai_project_hours"])
    french_gap = max(0, targets["french_spoken_sessions"] - w["french_spoken_sessions"])
    gym_gap = max(0, targets["gym_sessions"] - w["gym_sessions"])

    user_msg = f"""Evening check-in summary:

TODAY:
{json.dumps({k: v for k, v in entry.items() if k != 'date'}, indent=2)}

CALENDAR TODAY:
{events_block or '(unavailable)'}

WEEKLY PROGRESS:
  AI project: {w['ai_project_hours']:.1f}h / {targets['ai_project_hours']}h  (gap: {ai_gap:.1f}h)
  French spoken: {w['french_spoken_sessions']} / {targets['french_spoken_sessions']} sessions  (gap: {french_gap})
  Gym: {w['gym_sessions']} / {targets['gym_sessions']} sessions  (gap: {gym_gap})

STREAKS:
  French daily: {s['french_daily']} days | Gym: {s['gym']} | Steps 10k: {s['steps_10k']} | AI: {s['ai_project']} days

MISSED TODAY: {', '.join(missed) if missed else 'Nothing — perfect day!'}

Give me:
1. REFLECTION — 2 sentences on today's performance (honest, no fluff)
2. CATCH-UP — if anything was missed this week, one specific suggestion with day and time to make it up (skip if on track)
3. WIN — one small thing to celebrate or carry into tomorrow

Under 150 words total."""

    print("🤖  Reflection:\n")
    with client.messages.stream(
        model=MODEL,
        max_tokens=400,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    ) as stream:
        for chunk in stream.text_stream:
            print(chunk, end="", flush=True)

    print("\n\n" + "=" * 44)

    # ── Offer to reschedule missed items in Google Calendar ───────────────────
    if missed and gcal_service:
        reschedule = input("\n📅  Add a catch-up block to Google Calendar? [y/n]  ").strip().lower()
        if reschedule == "y":
            _schedule_catchup(gcal_service, missed, today)


def _schedule_catchup(service, missed: list[str], today: date) -> None:
    """Suggest and optionally create a catch-up block for tomorrow."""
    tomorrow = today + timedelta(days=1)
    tomorrow_name = tomorrow.strftime("%A")

    print(f"\n  Scheduling catch-up for {tomorrow.strftime('%A %d/%m')}:")

    # Simple time slot: 07:00 – 07:30 for short items, 21:00–22:00 for longer
    short_items = [m for m in missed if "French" in m]
    long_items = [m for m in missed if "AI project" in m or "Gym" in m]

    created = []

    if short_items:
        start = datetime.combine(tomorrow, datetime.strptime("07:00", "%H:%M").time())
        end = start + timedelta(minutes=30)
        summary = "Catch-up: " + ", ".join(short_items)
        try:
            create_event(service, summary, start, end, description="Catch-up block from Life OS")
            created.append(summary)
        except Exception as exc:
            print(f"  ⚠  Could not create event: {exc}", file=sys.stderr)

    if long_items:
        start = datetime.combine(tomorrow, datetime.strptime("21:00", "%H:%M").time())
        end = start + timedelta(hours=1)
        summary = "Catch-up: " + ", ".join(long_items)
        try:
            create_event(service, summary, start, end, description="Catch-up block from Life OS")
            created.append(summary)
        except Exception as exc:
            print(f"  ⚠  Could not create event: {exc}", file=sys.stderr)

    for title in created:
        print(f"  ✓  Created: '{title}'")
