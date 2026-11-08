"""Data for the home page's "what's happening now" overview and the batch list grouping."""
from datetime import datetime, timedelta

from . import brewmonk
from .models import Batch, CalendarEvent

TYPE_ICONS = {"Mead": "🍯", "Wine": "🍷", "Beer": "🍺", "Hard Cider": "🍎"}


def is_in_progress(batch, today=None):
    today = today or datetime.now().date()
    return batch.end_date is None or batch.end_date.date() > today


def _batch_summary(batch, today, settings):
    measurements = sorted((m for m in batch.measurements if m.date), key=lambda m: m.date)
    with_gravity = [m for m in measurements if m.gravity is not None]
    last_gravity = with_gravity[-1] if with_gravity else None
    last_log = next((m for m in reversed(measurements)
                     if m.notes and m.notes != brewmonk.NOTE), None)

    og = batch.initial_gravity
    sg = last_gravity.gravity if last_gravity else None

    linked = settings.brewmonk_batch_id == batch.id
    live = None
    if linked:
        readings = brewmonk.load_batch_readings(batch.id)
        live = readings[-1] if readings else None

    return {
        "batch": batch,
        "icon": TYPE_ICONS.get(batch.alcohol_type, "📦"),
        "type": batch.alcohol_type or "Other",
        "day": (today - batch.start_date.date()).days + 1 if batch.start_date else None,
        "sg": sg,
        "sg_date": last_gravity.date if last_gravity else None,
        "abv": max(0.0, (og - sg) * 131.25) if og and sg else None,
        "last_log": last_log,
        "hydrometer_linked": linked,
        "live": live,
    }


def status():
    now = datetime.now()
    today = now.date()
    settings = brewmonk.get_settings()

    batches = Batch.query.order_by(Batch.start_date.desc()).all()
    active = [_batch_summary(b, today, settings) for b in batches if is_in_progress(b, today)]

    upcoming = (CalendarEvent.query
                .filter(CalendarEvent.start >= today, CalendarEvent.start <= today + timedelta(days=14))
                .order_by(CalendarEvent.start)
                .all())

    finished = [b for b in batches
                if not is_in_progress(b, today) and b.end_date >= now - timedelta(days=30)]
    finished.sort(key=lambda b: b.end_date, reverse=True)

    return {
        "today": today,
        "active": active,
        "upcoming": upcoming,
        "finished": finished[:5],
        "hydrometer_status": settings.brewmonk_last_status,
        "hydrometer_sync": settings.brewmonk_last_sync,
    }
