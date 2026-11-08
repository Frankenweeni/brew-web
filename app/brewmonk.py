"""myBrewMonk hydrometer sync.

myBrewMonk has no public API, so this logs in to the website with the
credentials saved under Settings > Brew Monk Hydrometer and reads the same
CSV file the website uses to draw its fermentation chart.

Each batch gets one measurement per day from the hydrometer. During the day
that row is updated with the latest reading, so the measurements list stays
readable while still showing the gravity curve day by day.
"""
import base64
import csv
import hashlib
import io
import json
import logging
import re
import time
from datetime import datetime

import requests
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

from .models import AppSettings, Batch, Measurement, db
from .utils import c_to_f

BASE_URL = "https://mybrewmonk.eu"
TIMEOUT = 20
NOTE = "Brew Monk hydrometer (auto)"
# Outside this range the hydrometer is not floating in wort/must/cider
# (for example lying on a desk), so the reading is not logged.
SG_MIN, SG_MAX = 0.980, 1.200

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


def latest_reading(session):
    """Latest reading from the active myBrewMonk fermentation, or None."""
    page = session.get(f"{BASE_URL}/fermentation", timeout=TIMEOUT)
    page.raise_for_status()
    urls = re.findall(r'load_data\("(/fermentation/\d+/data)"', page.text)
    if not urls:
        return None

    resp = session.get(f"{BASE_URL}{urls[0]}", timeout=TIMEOUT)
    resp.raise_for_status()
    rows = list(csv.reader(io.StringIO(resp.text)))
    if len(rows) < 2:
        return None

    names = ["created"] + [json.loads(col).get("name") for col in rows[0][1:]]
    last = dict(zip(names, rows[-1]))

    def number(key):
        try:
            return float(last.get(key))
        except (TypeError, ValueError):
            return None

    created = datetime.fromisoformat(last["created"]).astimezone().replace(tzinfo=None)
    return {
        "time": created,
        "sg": number("SG"),
        "temp_c": number("Temperature"),
        "battery": number("Battery Voltage"),
    }


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


def sync():
    """Fetch the latest reading and log it to the selected batch. Returns a status text."""
    settings = get_settings()
    try:
        session = login(settings.brewmonk_username, decrypt_password(settings.brewmonk_password))
        reading = latest_reading(session)
        if reading is None:
            status = "No active fermentation with readings on myBrewMonk"
        else:
            status = _describe(reading)
            sg = reading["sg"]
            batch = db.session.get(Batch, settings.brewmonk_batch_id) if settings.brewmonk_batch_id else None
            if batch is None:
                status += " (not logged: no batch selected)"
            elif batch.end_date:
                status += " (not logged: batch is finished)"
            elif sg is None or not SG_MIN <= sg <= SG_MAX:
                status += " (not logged: hydrometer doesn't seem to be floating)"
            else:
                _save_measurement(settings.brewmonk_batch_id, reading)
                status += " (logged)"
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
