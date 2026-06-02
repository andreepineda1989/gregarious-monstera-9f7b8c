#!/usr/bin/env python3
"""
Life OS — Personal AI Agent
Usage:
  python main.py --brief      Morning briefing
  python main.py --checkin    Evening check-in
  python main.py --plan       Weekly planner
  python main.py --track      Habit tracker dashboard
"""

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent


def check_env():
    import os
    if not os.environ.get("GEMINI_API_KEY"):
        print("✗  GEMINI_API_KEY is not set.")
        print("   Set it before running:")
        print("   Windows:  set GEMINI_API_KEY=your-key-here")
        print("   Mac/Linux: export GEMINI_API_KEY=your-key-here")
        sys.exit(1)

    token = BASE_DIR / "token.pickle"
    if not token.exists():
        print("⚠  token.pickle not found in life-os/")
        print("   Place your Google Calendar token.pickle file here.")


def main():
    parser = argparse.ArgumentParser(
        prog="life-os",
        description="Life OS — Personal AI Agent for Andreé",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
commands:
  --brief     🌅 Morning briefing: schedule, top priority, French word of the day
  --checkin   🌙 Evening check-in: log habits, get reflection, reschedule slips
  --plan      📅 Weekly planner: time-blocked plan using Claude + Google Calendar
  --track     📊 Habit tracker: view streaks, weekly progress, manual update
        """,
    )

    parser.add_argument("--brief",   action="store_true", help="Morning briefing")
    parser.add_argument("--checkin", action="store_true", help="Evening check-in")
    parser.add_argument("--plan",    action="store_true", help="Weekly planner")
    parser.add_argument("--track",   action="store_true", help="Habit tracker dashboard")

    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        sys.exit(0)

    # Tracker doesn't need Claude API, so check env only for the others
    if args.brief or args.checkin or args.plan:
        check_env()

    if args.brief:
        from briefing import run_briefing
        run_briefing()

    elif args.checkin:
        from checkin import run_checkin
        run_checkin()

    elif args.plan:
        from planner import run_planner
        run_planner()

    elif args.track:
        from tracker import run_tracker
        run_tracker()


if __name__ == "__main__":
    main()
