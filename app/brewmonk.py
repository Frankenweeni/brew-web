"""myBrewMonk hydrometer sync.

myBrewMonk has no public API, so this logs in to the website with the
credentials saved under Settings > Brew Monk and reads the readings from
the pages, the same way a browser would.
"""
import logging
import os
import re

import requests

from .models import AppSettings, db

BASE_URL = "https://mybrewmonk.eu"
TIMEOUT = 20

log = logging.getLogger(__name__)


class BrewMonkError(Exception):
    pass


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


def probe(out_dir="logs/brewmonk_probe"):
    """Save the logged-in pages to disk so their layout can be inspected."""
    settings = get_settings()
    session = login(settings.brewmonk_username, settings.brewmonk_password)
    os.makedirs(out_dir, exist_ok=True)
    for path in ["/", "/fermentation", "/equipment", "/sessions"]:
        resp = session.get(f"{BASE_URL}{path}", timeout=TIMEOUT)
        name = path.strip("/") or "home"
        with open(os.path.join(out_dir, f"{name}.html"), "w", encoding="utf-8") as fh:
            fh.write(resp.text)
        print(f"{path}: {resp.status_code}, {len(resp.text)} bytes")
