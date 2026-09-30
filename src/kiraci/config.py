from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field

TIER_ENV = {
    "strong": "KIRACI_MODEL_STRONG",
    "mid": "KIRACI_MODEL_MID",
    "cheap": "KIRACI_MODEL_CHEAP",
}


@dataclass(frozen=True)
class Config:
    models: dict[str, str] = field(default_factory=dict)  # agent -> tier
    costs: dict[str, int] = field(default_factory=dict)  # agent -> cents per run
    limits: dict[str, int] = field(default_factory=dict)

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
    return Config(
        models=dict(data.get("models", {})),
        costs={k: int(v) for k, v in data.get("cost_cents_per_run", {}).items()},
        limits={k: int(v) for k, v in data.get("limits", {}).items()},
    )
