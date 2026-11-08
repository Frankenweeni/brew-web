"""myBrewMonk hydrometer sync.

myBrewMonk has no public API, so this logs in to the website with the
credentials saved under Settings > Brew Monk Hydrometer and reads the same
CSV file the website uses to draw its fermentation chart.

The hydrometer is linked to a batch from the batch page. While linked:
- every reading since the link is kept for that batch's chart
  (instance/brewmonk/batch_<id>.json), and
- the batch gets one measurement per day, updated with the latest reading,
  so the measurements list stays readable.
Finishing the batch (setting an end date) unlinks the hydrometer.
"""
import base64
import csv
import hashlib
import io
import json
import logging
import os
import re
import tempfile
import time
from datetime import datetime, timedelta

import requests
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

from .models import AppSettings, Batch, Measurement, db
from .utils import c_to_f

BASE_URL = "https://mybrewmonk.eu"
TIMEOUT = 20
NOTE = "Brew Monk hydrometer (auto)"
DATA_DIR = os.path.join("instance", "brewmonk")
LOW_BATTERY_V = 3.4  # myBrewMonk shows its battery warning at or below this
# Outside this range the hydrometer is not floating in wort/must/cider
# (for example lying on a desk), so the reading is ignored.
SG_MIN, SG_MAX = 0.980, 1.200
MAX_CHART_POINTS = 1500

log = logging.getLogger(__name__)


class BrewMonkError(Exception):
    pass


# --- Password storage -------------------------------------------------------

def _fernet():
    secret = current_app.config["SECRET_KEY"]
    key = hashlib.sha256(f"brewmonk-password:{secret}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_password(password):
    return _fernet().encrypt(password.encode()).decode()


def decrypt_password(stored):
    if not stored:
        return None
    try:
        return _fernet().decrypt(stored.encode()).decode()
    except InvalidToken:
        # Saved before encryption was added; encrypt it now
        settings = get_settings()
        settings.brewmonk_password = encrypt_password(stored)
        db.session.commit()
        return stored


# --- myBrewMonk access ------------------------------------------------------

def get_settings():
    settings = AppSettings.query.first()
    if settings is None:
        settings = AppSettings()
        db.session.add(settings)
        db.session.commit()
    return settings


def login(username, password):
    """Return a requests session logged in to myBrewMonk."""
    if not username or not password:
        raise BrewMonkError("No myBrewMonk username or password saved")

    session = requests.Session()
    session.headers["User-Agent"] = "BrewWeb"
    page = session.get(f"{BASE_URL}/login", timeout=TIMEOUT)
    page.raise_for_status()

    data = {"username": username, "password": password, "remember_me": "on"}
    hidden = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', page.text)
    if hidden:
        data["csrfmiddlewaretoken"] = hidden.group(1)
    headers = {"Referer": f"{BASE_URL}/login"}
    if session.cookies.get("csrftoken"):
        headers["X-CSRFToken"] = session.cookies.get("csrftoken")

    resp = session.post(f"{BASE_URL}/login", data=data, headers=headers, timeout=TIMEOUT)
    resp.raise_for_status()
    if "/login" in resp.url or 'id="id_password"' in resp.text:
        raise BrewMonkError("myBrewMonk login failed, check username and password")
    return session


def fetch_readings(session):
    """All readings of the active myBrewMonk fermentation, oldest first."""
    page = session.get(f"{BASE_URL}/fermentation", timeout=TIMEOUT)
    page.raise_for_status()
    urls = re.findall(r'load_data\("(/fermentation/\d+/data)"', page.text)
    if not urls:
        return []

    resp = session.get(f"{BASE_URL}{urls[0]}", timeout=TIMEOUT)
    resp.raise_for_status()
    rows = list(csv.reader(io.StringIO(resp.text)))
    if len(rows) < 2:
        return []

    names = ["created"] + [json.loads(col).get("name") for col in rows[0][1:]]
    readings = []
    for row in rows[1:]:
        values = dict(zip(names, row))

        def number(key):
            try:
                return float(values.get(key))
            except (TypeError, ValueError):
                return None

        try:
            created = datetime.fromisoformat(values["created"]).astimezone().replace(tzinfo=None)
        except (KeyError, ValueError):
            continue
        readings.append({
            "time": created,
            "sg": number("SG"),
            "temp_c": number("Temperature"),
            "battery": number("Battery Voltage"),
        })
    readings.sort(key=lambda r: r["time"])
    return readings


def is_floating(reading):
    return reading["sg"] is not None and SG_MIN <= reading["sg"] <= SG_MAX


# --- Per-batch reading history ------------------------------------------------

def _batch_file(batch_id):
    return os.path.join(DATA_DIR, f"batch_{batch_id}.json")


def load_batch_readings(batch_id):
    try:
        with open(_batch_file(batch_id), encoding="utf-8") as fh:
            raw = json.load(fh)
    except (FileNotFoundError, ValueError):
        return []
    return [{"time": datetime.fromisoformat(r["t"]), "sg": r.get("sg"),
             "temp_c": r.get("c"), "battery": r.get("v")} for r in raw]


def _store_batch_readings(batch_id, new_readings):
    merged = {r["time"]: r for r in load_batch_readings(batch_id)}
    for r in new_readings:
        merged[r["time"]] = r
    raw = [{"t": r["time"].isoformat(), "sg": r["sg"], "c": r["temp_c"], "v": r["battery"]}
           for r in sorted(merged.values(), key=lambda r: r["time"])]
    os.makedirs(DATA_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=DATA_DIR, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(raw, fh)
    os.replace(tmp, _batch_file(batch_id))


# --- Sync -------------------------------------------------------------------

def _describe(reading):
    parts = []
    if reading["sg"] is not None:
        parts.append(f"SG {reading['sg']:.3f}")
    if reading["temp_c"] is not None:
        parts.append(f"{reading['temp_c']:.1f} °C")
    if reading["battery"] is not None:
        parts.append(f"battery {reading['battery']:.2f} V")
    return ", ".join(parts) + f" at {reading['time']:%Y-%m-%d %H:%M}"


def _save_measurement(batch_id, reading):
    day_start = reading["time"].replace(hour=0, minute=0, second=0, microsecond=0)
    row = (Measurement.query
           .filter(Measurement.batch_id == batch_id,
                   Measurement.notes == NOTE,
                   Measurement.date >= day_start)
           .order_by(Measurement.date.desc())
           .first())
    if row is None:
        row = Measurement(batch_id=batch_id, notes=NOTE)
        db.session.add(row)
    row.date = reading["time"]
    row.gravity = round(reading["sg"], 3)
    # Brew Web stores temperatures in °F
    row.temperature = round(c_to_f(reading["temp_c"]), 1) if reading["temp_c"] is not None else None


def unlink(settings):
    settings.brewmonk_batch_id = None
    settings.brewmonk_linked_at = None


def sync():
    """Fetch readings and log them to the linked batch. Returns a status text."""
    settings = get_settings()
    try:
        session = login(settings.brewmonk_username, decrypt_password(settings.brewmonk_password))
        readings = fetch_readings(session)
        if not readings:
            status = "No active fermentation with readings on myBrewMonk"
        else:
            latest = readings[-1]
            status = _describe(latest)
            batch = db.session.get(Batch, settings.brewmonk_batch_id) if settings.brewmonk_batch_id else None
            if batch is None:
                status += " (not logged: not linked to a batch)"
            elif batch.end_date:
                unlink(settings)
                status += f" (not logged: {batch.name} is finished, hydrometer unlinked)"
            else:
                since = settings.brewmonk_linked_at or datetime.min
                usable = [r for r in readings if r["time"] >= since and is_floating(r)]
                _store_batch_readings(batch.id, usable)
                if usable and usable[-1] is latest:
                    _save_measurement(batch.id, latest)
                    status += f" (logged to {batch.name})"
                else:
                    status += " (not logged: hydrometer doesn't seem to be floating)"
    except BrewMonkError as e:
        status = str(e)
    except requests.RequestException:
        log.exception("myBrewMonk request failed")
        status = "Could not reach myBrewMonk"

    settings.brewmonk_last_sync = datetime.now()
    settings.brewmonk_last_status = status[:255]
    db.session.commit()
    return status


def sync_forever(interval_seconds=900):
    while True:
        try:
            print(sync(), flush=True)
        except Exception:
            log.exception("Brew Monk sync failed")
            db.session.rollback()
        finally:
            db.session.remove()
        time.sleep(interval_seconds)


# --- Batch page card ----------------------------------------------------------

def card(batch):
    """Everything the batch page's hydrometer card shows."""
    settings = get_settings()
    linked = settings.brewmonk_batch_id == batch.id
    elsewhere = None
    if settings.brewmonk_batch_id and not linked:
        other = db.session.get(Batch, settings.brewmonk_batch_id)
        elsewhere = other.name if other else None

    readings = load_batch_readings(batch.id)
    latest = readings[-1] if readings else None
    og = batch.initial_gravity or (readings[0]["sg"] if readings else None)

    stats = {"sg": None, "temp_c": None, "battery": None, "battery_low": False,
             "time": None, "abv": None, "attenuation": None, "change_24h": None}
    if latest:
        sg = latest["sg"]
        stats.update(sg=sg, temp_c=latest["temp_c"], battery=latest["battery"], time=latest["time"])
        stats["battery_low"] = latest["battery"] is not None and latest["battery"] <= LOW_BATTERY_V
        if og and sg is not None:
            stats["abv"] = max(0.0, (og - sg) * 131.25)
            if og > 1:
                stats["attenuation"] = max(0.0, (og - sg) / (og - 1) * 100)
        # Gravity change per day, from the reading closest to 24 hours earlier
        older = [r for r in readings if r["time"] <= latest["time"] - timedelta(hours=20)]
        if older and sg is not None:
            ref = min(older, key=lambda r: abs((latest["time"] - r["time"]) - timedelta(hours=24)))
            days = (latest["time"] - ref["time"]).total_seconds() / 86400
            if days > 0 and ref["sg"] is not None:
                stats["change_24h"] = (sg - ref["sg"]) * 1000 / days

    step = max(1, len(readings) // MAX_CHART_POINTS)
    chart = {
        "readings": [{"x": int(r["time"].timestamp() * 1000), "sg": r["sg"], "c": r["temp_c"]}
                     for r in readings[::step]],
        "manual": [{"x": int(m.date.timestamp() * 1000), "sg": m.gravity}
                   for m in batch.measurements
                   if m.notes != NOTE and m.gravity is not None and m.date is not None],
    }

    return {
        "configured": bool(settings.brewmonk_username and settings.brewmonk_password),
        "linked": linked,
        "linked_at": settings.brewmonk_linked_at if linked else None,
        "elsewhere": elsewhere,
        "stats": stats,
        "chart": chart,
    }
