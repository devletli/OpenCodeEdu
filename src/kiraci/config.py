from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field

TIER_ENV = {
    "strong": "KIRACI_MODEL_STRONG",
    "mid": "KIRACI_MODEL_MID",
    "cheap": "KIRACI_MODEL_CHEAP",
}

REVENUE_DEFAULTS = {
    "payment_fee_percent": 5,
    "payment_fee_fixed_cents": 50,
    "venture_budget_cents": 1500,
    "max_active_ventures": 3,
    "poll_minutes": 15,
    "min_sources_per_research": 3,
    "payment_provider": "lemonsqueezy",
    "payment_store_id": "",
}

SANDBOX_DEFAULTS = {"mode": "required", "bwrap": "bwrap"}

COST_TRUTH_DEFAULTS = {
    "usd_to_eur": 0.92,
    "cost_safety_multiplier_max": 5.0,
    "daily_hard_stop_cents": 120,
    "reconcile_times_utc": ["06:00", "21:45"],
}

BACKUP_DEFAULTS = {"keep_daily": 14, "keep_weekly": 8, "time_utc": "22:30"}

OPS_DEFAULTS = {"heartbeat_stale_minutes": 15, "dashboard_port": 8787}


@dataclass(frozen=True)
class Config:
    models: dict[str, str] = field(default_factory=dict)  # agent -> tier
    costs: dict[str, int] = field(default_factory=dict)  # agent -> cents per run
    limits: dict[str, int] = field(default_factory=dict)
    revenue: dict = field(default_factory=lambda: dict(REVENUE_DEFAULTS))
    sandbox: dict = field(default_factory=lambda: dict(SANDBOX_DEFAULTS))
    cost_truth: dict = field(default_factory=lambda: dict(COST_TRUTH_DEFAULTS))
    backup: dict = field(default_factory=lambda: dict(BACKUP_DEFAULTS))
    ops: dict = field(default_factory=lambda: dict(OPS_DEFAULTS))

    def tier_for(self, agent: str) -> str | None:
        return self.models.get(agent)

    def model_for(self, agent: str) -> str | None:
        """Resolved `provider/model` for an agent, or None if its tier env is missing."""
        tier = self.tier_for(agent)
        if tier is None:
            return None
        return os.environ.get(TIER_ENV.get(tier, "")) or None

    def cost_for(self, agent: str) -> int:
        return int(self.costs.get(agent, 0))

    def revenue_value(self, key: str):
        return self.revenue.get(key, REVENUE_DEFAULTS.get(key))

    def sandbox_value(self, key: str):
        return self.sandbox.get(key, SANDBOX_DEFAULTS.get(key))

    def cost_truth_value(self, key: str):
        return self.cost_truth.get(key, COST_TRUTH_DEFAULTS.get(key))

    def backup_value(self, key: str):
        return self.backup.get(key, BACKUP_DEFAULTS.get(key))

    def ops_value(self, key: str):
        return self.ops.get(key, OPS_DEFAULTS.get(key))

    def missing_tier_envs(self) -> list[str]:
        """Env var names (sorted) whose tier is used by at least one agent but unset."""
        needed = {self.models[a] for a in self.models if self.models[a] in TIER_ENV}
        return sorted(e for t, e in TIER_ENV.items() if t in needed and not os.environ.get(e))


def default_path() -> str:
    return os.environ.get("KIRACI_CONFIG") or "config.toml"


def load_config(path: str | None = None) -> Config:
    path = path or default_path()
    with open(path, "rb") as f:
        data = tomllib.load(f)
    revenue = dict(REVENUE_DEFAULTS)
    for k, v in data.get("revenue", {}).items():
        revenue[k] = v
    return Config(
        models=dict(data.get("models", {})),
        costs={k: int(v) for k, v in data.get("cost_cents_per_run", {}).items()},
        limits={k: int(v) for k, v in data.get("limits", {}).items()},
        revenue=revenue,
        sandbox={**SANDBOX_DEFAULTS, **dict(data.get("sandbox", {}))},
        cost_truth={**COST_TRUTH_DEFAULTS, **dict(data.get("cost_truth", {}))},
        backup={**BACKUP_DEFAULTS, **dict(data.get("backup", {}))},
        ops={**OPS_DEFAULTS, **dict(data.get("ops", {}))},
    )
