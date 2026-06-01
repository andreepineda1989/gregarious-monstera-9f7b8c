"""Shared Google Calendar auth and event helpers."""

import pickle
from datetime import datetime, date, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from googleapiclient.discovery import build

BASE_DIR = Path(__file__).parent


def get_service():
    """Return an authenticated Google Calendar service using token.pickle."""
    token_path = BASE_DIR / "token.pickle"

    if not token_path.exists():
        raise FileNotFoundError(
            f"token.pickle not found in {BASE_DIR}. "
            "Run your auth script once to generate it."
        )

    with open(token_path, "rb") as fh:
        creds = pickle.load(fh)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, "wb") as fh:
            pickle.dump(creds, fh)

    return build("calendar", "v3", credentials=creds)


def get_events(service, date_from: date, date_to: date, calendar_id="primary"):
    """Fetch all events between two dates (inclusive), expanded from recurrences."""
    time_min = datetime.combine(date_from, datetime.min.time()).isoformat() + "Z"
    time_max = datetime.combine(date_to, datetime.max.time()).isoformat() + "Z"

    result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return result.get("items", [])


def parse_event_dt(dt_string: str) -> datetime:
    """Parse a Google Calendar datetime string (handles Z and +HH:MM offsets)."""
    if dt_string.endswith("Z"):
        return datetime.fromisoformat(dt_string[:-1] + "+00:00")
    return datetime.fromisoformat(dt_string)


def format_event(event: dict) -> str:
    """Return a single human-readable line for a calendar event."""
    summary = event.get("summary", "Untitled")
    start_raw = event["start"].get("dateTime", event["start"].get("date", ""))
    end_raw = event["end"].get("dateTime", event["end"].get("date", ""))

    if "T" in start_raw:
        start_dt = parse_event_dt(start_raw)
        end_dt = parse_event_dt(end_raw)
        return f"{start_dt.strftime('%H:%M')}–{end_dt.strftime('%H:%M')}  {summary}"
    else:
        return f"All day  {summary}"


def format_events_block(events: list, header: str = "") -> str:
    """Return a multi-line text block of events, optionally with a date header."""
    if not events:
        return f"{header}\n  (no events)" if header else "(no events)"

    lines = ([header] if header else []) + [f"  {format_event(e)}" for e in events]
    return "\n".join(lines)


def create_event(
    service,
    summary: str,
    start: datetime,
    end: datetime,
    description: str = "",
    location: str = "",
    calendar_id: str = "primary",
) -> dict:
    """Create a single (non-recurring) calendar event and return the created object."""
    body = {
        "summary": summary,
        "description": description,
        "location": location,
        "start": {"dateTime": start.isoformat(), "timeZone": "Europe/Luxembourg"},
        "end": {"dateTime": end.isoformat(), "timeZone": "Europe/Luxembourg"},
    }
    return service.events().insert(calendarId=calendar_id, body=body).execute()
