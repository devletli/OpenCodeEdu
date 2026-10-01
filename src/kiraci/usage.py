"""Cost truth: spend is measured, not guessed.

The provider's reported usage is reconciled against the ledger at
[cost_truth].reconcile_times_utc; the difference is booked as a real expense
or credit and drives a cost multiplier applied to every paid run estimate and
a hard daily stop for paid runs. All deterministic code, no LLM.

OpenRouter adapter VERIFIED against the current documentation
(https://openrouter.ai/docs/api-reference/limits, fetched 2026-10-01):
GET https://openrouter.ai/api/v1/key returns data.usage (credits used, all
time) and data.usage_daily (credits used in the current UTC day), in USD.
"""

from __future__ import annotations

import json
import math
import os
import urllib.request
from datetime import datetime, timedelta
from typing import Protocol

OPENROUTER_KEY_ENDPOINT = "https://openrouter.ai/api/v1/key"
USAGE_TIMEOUT_S = 10

DEFAULT_MULTIPLIER_NO_PROBE = 2.0
MULTIPLIER_ALERT_RATIO = 2.0
CALIBRATION_WINDOW_DAYS = 7


class UsageProbe(Protocol):
    def cumulative_spend_cents(self) -> int | None: ...  # provider-reported, EUR cents

    def daily_spend_cents(self) -> int | None: ...  # provider-reported, current UTC day


class HttpClient(Protocol):
    def get_json(self, url: str, headers: dict[str, str]) -> dict | None: ...


class UrllibClient:
    def get_json(self, url: str, headers: dict[str, str]) -> dict | None:
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=USAGE_TIMEOUT_S) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (OSError, ValueError):
            return None


class OpenRouterProbe:
    """Reads the key from env OPENROUTER_API_KEY (never given to agents)."""

    def __init__(self, *, api_key: str, usd_to_eur: float = 0.92,
                 client: HttpClient | None = None):
        self.api_key = api_key
        self.usd_to_eur = usd_to_eur
        self.client = client or UrllibClient()

    def _usd(self, field: str) -> float | None:
        payload = self.client.get_json(
            OPENROUTER_KEY_ENDPOINT, {"Authorization": f"Bearer {self.api_key}"})
        if not isinstance(payload, dict):
            return None
        data = payload.get("data")
        if not isinstance(data, dict):
            return None
        try:
            return float(data[field])
        except (TypeError, KeyError, ValueError):
            return None

    def cumulative_spend_cents(self) -> int | None:
        usd = self._usd("usage")
        return None if usd is None else round(usd * self.usd_to_eur * 100)

    def daily_spend_cents(self) -> int | None:
        usd = self._usd("usage_daily")
        return None if usd is None else round(usd * self.usd_to_eur * 100)


def get_probe(config) -> UsageProbe | None:
    """The provider probe, or None without a key (runner then uses 2.0x)."""
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        return None
    return OpenRouterProbe(
        api_key=key, usd_to_eur=float(config.cost_truth_value("usd_to_eur")))


def ensure_probe_task(store) -> None:
    """Exactly one human task asking for OPENROUTER_API_KEY in .env."""
    store.add_human_task(
        kind="secret_provisioning",
        title="Add OPENROUTER_API_KEY to .env",
        instructions=(
            "The system cannot reconcile real provider spend against the ledger "
            "without a provider usage key. Create a DEDICATED OpenRouter API key "
            "with a provider-side spending limit, add it as OPENROUTER_API_KEY=... "
            "to the .env file next to the service, and mark this task done. "
            "Never send the key through chat."),
        dedupe_key="env-usage-probe",
        created_by="orchestrator",
    )


def paid_estimate_cents(store, config, agent: str) -> int:
    """Estimate charged to the tokens bucket: ceil(config_cost * multiplier).

    Without a working probe the multiplier is conservatively 2.0.
    """
    cost = config.cost_for(agent)
    if cost <= 0:
        return 0
    if get_probe(config) is None:
        mult = DEFAULT_MULTIPLIER_NO_PROBE
    else:
        try:
            mult = float(store.kv_get("cost_multiplier") or 1.0)
        except (TypeError, ValueError):
            mult = 1.0
        mult = max(1.0, mult)
    return math.ceil(cost * mult)


def _reconcile_ref(store, now: datetime) -> str:
    day = now.strftime("%Y-%m-%d")
    n = 1
    for r in store.conn.execute(
        "SELECT ref FROM ledger WHERE ref LIKE ?", (f"reconcile:{day}:%",)
    ):
        try:
            n = max(n, int(str(r["ref"]).rsplit(":", 1)[1]) + 1)
        except (IndexError, ValueError):
            n += 1
    return f"reconcile:{day}:{n}"


def booked_since_cents(store, since_iso: str | None) -> int:
    """Token estimates charged since `since_iso`, excluding reconciliation
    entries themselves (those ARE the correction, not an estimate)."""
    excl = "AND (ref IS NULL OR ref NOT LIKE 'reconcile:%')"
    if since_iso:
        row = store.conn.execute(
            f"""SELECT COALESCE(SUM(-delta_cents),0) s FROM ledger
               WHERE bucket='tokens' AND kind IN ('expense','refund')
               AND ts > ? {excl}""", (since_iso,)).fetchone()
    else:
        row = store.conn.execute(
            f"""SELECT COALESCE(SUM(-delta_cents),0) s FROM ledger
               WHERE bucket='tokens' AND kind IN ('expense','refund') {excl}"""
        ).fetchone()
    return int(row["s"])


def reconcile(store, ledger, config, probe, now: datetime) -> dict:
    """One reconciliation round. actual - booked is booked into the ledger."""
    if probe is None:
        ensure_probe_task(store)
        return {"status": "no-probe", "multiplier": DEFAULT_MULTIPLIER_NO_PROBE}
    actual_total = probe.cumulative_spend_cents()
    if actual_total is None:
        return {"status": "probe-unreadable"}
    baseline = store.kv_get("usage_baseline")
    since = store.kv_get("usage_reconcile_ts")
    try:
        baseline_cents = int(baseline) if baseline else 0
    except ValueError:
        baseline_cents = 0
    actual = actual_total - baseline_cents
    booked = booked_since_cents(store, since)
    delta = booked - actual  # >0: over-booked (credit), <0: under-booked (expense)
    booked_ref = None
    if delta != 0:
        ref = _reconcile_ref(store, now)
        res = ledger.record_reconciliation("tokens", delta, ref,
                                           note="provider usage reconciliation")
        if res.get("status") in ("recorded", "duplicate"):
            booked_ref = ref
    store.kv_set("usage_baseline", str(actual_total))
    store.kv_set("usage_reconcile_ts", now.isoformat())
    mult = _update_multiplier(store, config, actual=actual, booked=booked, now=now)
    return {"status": "reconciled", "actual": actual, "booked": booked,
            "delta": delta, "ref": booked_ref, "multiplier": mult}


def _clamp_multiplier(ratio: float, config) -> float:
    lo, hi = 1.0, float(config.cost_truth_value("cost_safety_multiplier_max"))
    return min(hi, max(lo, ratio))


def _update_multiplier(store, config, *, actual: int, booked: int,
                       now: datetime) -> float | None:
    """7-day rolling actual/booked, clamped to [1.0, max]; stored in kv.

    Returns the new multiplier when a calibration round completed.
    """
    agg_actual = float(store.kv_get("calib_actual") or 0) + actual
    agg_booked = float(store.kv_get("calib_booked") or 0) + booked
    since_raw = store.kv_get("calib_since")
    try:
        since = datetime.fromisoformat(since_raw) if since_raw else None
    except ValueError:
        since = None
    if since is None:
        since = now
    if (now - since).days < CALIBRATION_WINDOW_DAYS:
        store.kv_set("calib_actual", str(agg_actual))
        store.kv_set("calib_booked", str(agg_booked))
        store.kv_set("calib_since", since.isoformat())
        return None
    if agg_booked <= 0:
        ratio, mult = 0.0, 1.0
    else:
        ratio = agg_actual / agg_booked
        mult = _clamp_multiplier(ratio, config)
    store.kv_set("cost_multiplier", str(mult))
    if ratio > MULTIPLIER_ALERT_RATIO:
        from .notify import send_info
        send_info(
            f"Real provider spend ran at {ratio:.1f}x the booked estimate over "
            f"the last {CALIBRATION_WINDOW_DAYS} days; cost multiplier set to "
            f"{mult:.2f}.", store)
    store.kv_set("calib_actual", "0")
    store.kv_set("calib_booked", "0")
    store.kv_set("calib_since", now.isoformat())
    return mult


def paid_paused(store, now: datetime) -> bool:
    """True while the hard daily stop is in effect."""
    until = store.kv_get("paid_paused_until")
    if not until:
        return False
    try:
        return datetime.fromisoformat(until) > now
    except ValueError:
        return False


def check_hard_stop(store, config, probe, now: datetime) -> str | None:
    """Pause paid runs when provider-reported spend today exceeds the cap."""
    if probe is None:
        return None
    daily = probe.daily_spend_cents()
    if daily is None:
        return None
    cap = int(config.cost_truth_value("daily_hard_stop_cents"))
    if daily <= cap or paid_paused(store, now):
        return None
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0,
                                            microsecond=0)
    store.kv_set("paid_paused_until", nxt.isoformat())
    return f"hard stop: {daily}c today > {cap}c cap, paid runs paused until 00:05 UTC"