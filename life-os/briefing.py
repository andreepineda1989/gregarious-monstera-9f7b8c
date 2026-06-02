"""
briefing.py — Daily morning briefing.
Pulls today's calendar, habit stats, and asks Gemini for a focused briefing
including schedule summary, top priority, and a French word of the day.
"""

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import google.generativeai as genai

from gcal import get_service, get_events, format_events_block
from tracker import load_habits, compute_stats

BASE_DIR = Path(__file__).parent
MODEL = "gemini-1.5-flash"


def run_briefing() -> None:
    now = datetime.now()
    today = date.today()

    print(f"\n🌅  LIFE OS — Morning Briefing")
    print("=" * 44)
    print(f"📅  {now.strftime('%A, %d %B %Y')}  —  {now.strftime('%H:%M')}\n")

    # ── Profile ───────────────────────────────────────────────────────────────
    with open(BASE_DIR / "profile.json") as fh:
        profile = json.load(fh)

    # ── Google Calendar ───────────────────────────────────────────────────────
    events_block = "Calendar unavailable."
    try:
        service = get_service()
        events = get_events(service, today, today)
        events_block = format_events_block(events, header=f"{today.strftime('%A %d/%m')}:")
        print(f"✓  {len(events)} events loaded from Google Calendar")
    except Exception as exc:
        print(f"⚠  Calendar: {exc}", file=sys.stderr)

    # ── Habit stats ───────────────────────────────────────────────────────────
    habits = load_habits()
    stats = compute_stats(habits.get("daily_log", {}))
    s = stats["streaks"]
    w = stats["weekly"]
    targets = profile["weekly_targets"]

    habit_context = f"""\
Streaks: French daily {s['french_daily']}d | Gym {s['gym']} sessions | Steps 10k {s['steps_10k']}d | AI project {s['ai_project']}d

This week: AI {w['ai_project_hours']:.1f}h / {targets['ai_project_hours']}h target | \
French spoken {w['french_spoken_sessions']} / {targets['french_spoken_sessions']} sessions | \
Gym {w['gym_sessions']} / {targets['gym_sessions']} sessions"""

    # ── Gemini API ────────────────────────────────────────────────────────────
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("✗  GEMINI_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    genai.configure(api_key=api_key)

    system_prompt = f"""You are Life OS, a personal AI briefing assistant for Andreé.

PROFILE:
{json.dumps(profile, indent=2)}

Be direct, warm, and energising. Use plain text (no markdown headers). Today is {now.strftime('%A, %d %B %Y')}."""

    user_msg = f"""Generate my morning briefing. Keep it under 280 words.

TODAY'S CALENDAR:
{events_block}

HABIT STATUS:
{habit_context}

Include exactly these four sections, labelled clearly:
1. SCHEDULE — 3–5 bullet points of today's key time blocks (skip trivial ones)
2. TOP PRIORITY — one sentence: the single most important thing I must do today
3. MOT DU JOUR — one French word or expression relevant to daily life in Luxembourg, with pronunciation, meaning, and a short example sentence
4. MOMENTUM — one sentence connecting today's effort to the bigger goal (permanent residency, AI business, or debt freedom)"""

    print()
    model = genai.GenerativeModel(
        model_name=MODEL,
        system_instruction=system_prompt,
    )

    response = model.generate_content(user_msg, stream=True)
    for chunk in response:
        if chunk.text:
            print(chunk.text, end="", flush=True)

    print("\n\n" + "=" * 44)
