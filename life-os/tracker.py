"""
tracker.py — Reads and updates habits.json.
Streaks and weekly totals are always computed from raw daily_log
to avoid double-counting or drift.
"""

import json
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
HABITS_FILE = BASE_DIR / "habits.json"

# Days when gym and spoken French are scheduled
GYM_DAYS = {"Monday", "Friday", "Saturday", "Sunday"}
SPOKEN_DAYS = {"Monday", "Tuesday", "Thursday", "Saturday", "Sunday"}


# ─── I/O ────────────────────────────────────────────────────────────────────


def load_habits() -> dict:
    if not HABITS_FILE.exists():
        return {"last_updated": date.today().isoformat(), "daily_log": {}}
    with open(HABITS_FILE) as fh:
        return json.load(fh)


def save_habits(habits: dict) -> None:
    habits["last_updated"] = date.today().isoformat()
    with open(HABITS_FILE, "w") as fh:
        json.dump(habits, fh, indent=2)


# ─── Log entry ──────────────────────────────────────────────────────────────


def log_today(habits: dict, entry: dict) -> dict:
    """Merge entry into today's daily_log (overwrites same-day fields)."""
    today = date.today().isoformat()
    daily_log = habits.setdefault("daily_log", {})
    existing = daily_log.get(today, {})
    existing.update(entry)
    existing["date"] = today
    daily_log[today] = existing
    return habits


# ─── Stats computation ───────────────────────────────────────────────────────


def compute_stats(daily_log: dict) -> dict:
    """
    Compute streaks and current-week totals from raw daily_log.
    Returns dict with keys: streaks, weekly.
    """
    today = date.today()

    # ── Streaks ──────────────────────────────────────────────────────────────
    def streak_for(key: str, scheduled_days: set | None = None) -> int:
        """
        Count consecutive completed days ending today.
        If scheduled_days is given, only count days that are in the schedule
        (non-scheduled days are 'neutral' — they don't break the streak).
        """
        count = 0
        for i in range(365):
            d = today - timedelta(days=i)
            day_name = d.strftime("%A")
            d_str = d.isoformat()
            entry = daily_log.get(d_str, {})

            if scheduled_days and day_name not in scheduled_days:
                continue  # skip non-scheduled days

            if entry.get(key):
                count += 1
            else:
                break
        return count

    # French daily — every day
    french_daily_streak = streak_for("french_daily")

    # Gym — only on scheduled days
    gym_streak = streak_for("gym", GYM_DAYS)

    # Steps 10k — every day
    steps_streak = streak_for("steps_10k")

    # AI project — every day (we want daily momentum)
    ai_streak = streak_for("ai_project_any")

    # ── Weekly totals (Mon–Sun of current week) ───────────────────────────────
    monday = today - timedelta(days=today.weekday())
    ai_hours = 0.0
    spoken_sessions = 0
    gym_sessions = 0

    for i in range(7):
        d = (monday + timedelta(days=i)).isoformat()
        e = daily_log.get(d, {})
        ai_hours += e.get("ai_project_hours", 0.0)
        if e.get("french_spoken"):
            spoken_sessions += 1
        if e.get("gym"):
            gym_sessions += 1

    return {
        "streaks": {
            "french_daily": french_daily_streak,
            "gym": gym_streak,
            "steps_10k": steps_streak,
            "ai_project": ai_streak,
        },
        "weekly": {
            "week_start": monday.isoformat(),
            "ai_project_hours": round(ai_hours, 2),
            "french_spoken_sessions": spoken_sessions,
            "gym_sessions": gym_sessions,
        },
    }


# ─── Dashboard ───────────────────────────────────────────────────────────────


def _bar(current: float, target: float, width: int = 12) -> str:
    filled = int(min(current / target, 1.0) * width) if target else 0
    return "[" + "█" * filled + "░" * (width - filled) + "]"


def _flame(n: int) -> str:
    return "🔥" * min(n, 7) + (f" ×{n}" if n > 7 else "")


def run_tracker() -> None:
    habits = load_habits()
    daily_log = habits.get("daily_log", {})
    stats = compute_stats(daily_log)
    streaks = stats["streaks"]
    weekly = stats["weekly"]
    today = date.today()

    print("\n📊  LIFE OS — Habit Tracker")
    print("=" * 44)
    print(f"Today: {today.strftime('%A, %d %B %Y')}\n")

    # ── Streaks ──────────────────────────────────────────────────────────────
    print("🔥  STREAKS")
    print(f"  French daily   {_flame(streaks['french_daily'])} {streaks['french_daily']} days")
    print(f"  Gym            {_flame(streaks['gym'])} {streaks['gym']} sessions streak")
    print(f"  Steps (10k)    {_flame(streaks['steps_10k'])} {streaks['steps_10k']} days")
    print(f"  AI project     {_flame(streaks['ai_project'])} {streaks['ai_project']} days")

    # ── Weekly progress ───────────────────────────────────────────────────────
    print("\n📈  THIS WEEK")
    print(
        f"  AI Project    {_bar(weekly['ai_project_hours'], 7)} "
        f"{weekly['ai_project_hours']:.1f}h / 7h"
    )
    print(
        f"  French spoken {_bar(weekly['french_spoken_sessions'], 5)} "
        f"{weekly['french_spoken_sessions']} / 5 sessions"
    )
    print(
        f"  Gym           {_bar(weekly['gym_sessions'], 4)} "
        f"{weekly['gym_sessions']} / 4 sessions"
    )

    # ── Last 7 days ───────────────────────────────────────────────────────────
    print("\n📅  LAST 7 DAYS")
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        d_str = d.isoformat()
        entry = daily_log.get(d_str, {})
        label = "Today    " if i == 0 else d.strftime("%a %d/%m ")

        if entry:
            icons = []
            if entry.get("french_daily"):
                icons.append("🇫🇷")
            if entry.get("french_spoken"):
                icons.append("💬")
            if entry.get("gym"):
                icons.append("🏋️")
            if entry.get("steps_10k"):
                icons.append("👟")
            h = entry.get("ai_project_hours", 0)
            if h > 0:
                icons.append(f"🤖{h:.1f}h")
            if entry.get("notes"):
                icons.append("📝")
            print(f"  {label}  {''.join(icons) if icons else '—'}")
        else:
            print(f"  {label}  (no log)")

    print("\n" + "=" * 44)

    # ── Manual override ───────────────────────────────────────────────────────
    choice = input("\nManually update today's entry? [y/n]  ").strip().lower()
    if choice != "y":
        return

    today_str = today.isoformat()
    current = daily_log.get(today_str, {})

    def _ask(prompt: str, current_val) -> str:
        display = "y" if current_val is True else ("n" if current_val is False else str(current_val or ""))
        return input(f"  {prompt} (current: {display}) → ").strip()

    print()
    entry: dict = {}

    v = _ask("French daily study done? [y/n]", current.get("french_daily"))
    if v in ("y", "n"):
        entry["french_daily"] = v == "y"

    today_name = today.strftime("%A")
    if today_name in SPOKEN_DAYS:
        v = _ask("Spoken French practice done? [y/n]", current.get("french_spoken"))
        if v in ("y", "n"):
            entry["french_spoken"] = v == "y"

    if today_name in GYM_DAYS:
        v = _ask("Gym session done? [y/n]", current.get("gym"))
        if v in ("y", "n"):
            entry["gym"] = v == "y"

    v = _ask("AI project hours today?", current.get("ai_project_hours", 0))
    if v:
        try:
            h = float(v)
            entry["ai_project_hours"] = h
            entry["ai_project_any"] = h > 0
        except ValueError:
            pass

    v = _ask("Steps today?", current.get("steps", ""))
    if v.isdigit():
        steps = int(v)
        entry["steps"] = steps
        entry["steps_10k"] = steps >= 10000

    if entry:
        habits = log_today(habits, entry)
        save_habits(habits)
        print("\n  ✓ Saved.")
    else:
        print("\n  No changes.")
