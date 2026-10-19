"""USD/VND workspace exchange rate: stored in settings['fx'], editable by the admin, optionally refreshed daily.

Auto-update uses the open access endpoint of ExchangeRate-API (no key; attribution required, caching allowed,
update once per day). It never blocks a request: refresh runs in a background thread with a short timeout and
any failure silently keeps the last stored rate."""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Setting

log = logging.getLogger("app.fx")
KEY = "fx"
ATTRIBUTION = {"text": "Rates By Exchange Rate API", "url": "https://www.exchangerate-api.com"}
MIN_RATE, MAX_RATE = 5_000.0, 100_000.0
_last_attempt = 0.0
_lock = threading.Lock()


def default_fx() -> dict:
    s = get_settings()
    return {"usd_vnd_rate": s.usd_vnd_rate_default, "rate_updated_at": None, "rate_source": "default"}


def get_fx(db: Session) -> dict:
    row = db.get(Setting, KEY)
    fx = {**default_fx(), **(row.value if row else {})}
    fx["auto_update"] = get_settings().fx_auto_update
    fx["attribution"] = ATTRIBUTION if str(fx.get("rate_source", "")).startswith("auto") else None
    return fx


def get_rate(db: Session) -> float:
    return float(get_fx(db)["usd_vnd_rate"])


def valid_rate(rate: float) -> bool:
    return MIN_RATE <= rate <= MAX_RATE


def set_fx(db: Session, rate: float, source: str) -> dict:
    if not valid_rate(rate):
        raise ValueError(f"rate must be between {MIN_RATE:g} and {MAX_RATE:g} VND per USD")
    value = {"usd_vnd_rate": round(float(rate), 2), "rate_updated_at": datetime.now(UTC).isoformat(),
             "rate_source": source}
    row = db.get(Setting, KEY)
    if row is None:
        db.add(Setting(key=KEY, value=value))
    else:
        row.value = value
    db.commit()
    return get_fx(db)


def fetch_rate(url: str, timeout: float = 4.0) -> float:
    r = httpx.get(url, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if data.get("result") != "success":
        raise ValueError("provider error")
    rate = float(data["rates"]["VND"])
    if not valid_rate(rate):
        raise ValueError(f"implausible rate {rate}")
    return rate


def _refresh() -> None:
    from app.db.session import SessionLocal

    try:
        rate = fetch_rate(get_settings().fx_source_url)
        with SessionLocal() as db:
            set_fx(db, rate, "auto: open.er-api.com")
        log.info("fx rate refreshed", extra={"extra": {"usd_vnd": rate}})
    except Exception as e:  # keep the stored rate; never surface to users
        log.warning("fx refresh failed: %s", e)


def maybe_refresh(db: Session) -> None:
    """Start a background refresh when auto-update is on and the stored rate is older than 24 h (tried at most hourly).
    Manual rates (source 'manual') are never overwritten."""
    global _last_attempt
    s = get_settings()
    if not s.fx_auto_update:
        return
    fx = get_fx(db)
    if str(fx.get("rate_source", "")).startswith("manual"):
        return
    updated = fx.get("rate_updated_at")
    if updated and datetime.fromisoformat(updated) > datetime.now(UTC) - timedelta(hours=24):
        return
    with _lock:
        if time.time() - _last_attempt < 3600:
            return
        _last_attempt = time.time()
    threading.Thread(target=_refresh, daemon=True).start()
