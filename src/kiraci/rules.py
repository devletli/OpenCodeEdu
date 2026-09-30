from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Status = Literal["approved", "pending", "rejected"]
Tier = Literal["auto", "yellow", "red", "none"]

BUCKETS = ("infra", "tokens", "experiment", "emergency", "owner")

# EUR 100 genesis budget, in cents. "owner" is the human's profit share, starts at 0.
GENESIS = {"infra": 3000, "tokens": 3000, "experiment": 2500, "emergency": 1500}


@dataclass(frozen=True)
class Policy:
    auto_limit_cents: int = 300           # <= EUR 3: approved automatically
    hard_limit_cents: int = 1000          # > EUR 10: red tier, human approval
    survival_threshold_cents: int = 1000  # total balance < EUR 10 => survival mode
    daily_caps_cents: dict[str, int] = field(default_factory=lambda: {"tokens": 60})
    human_only_buckets: frozenset[str] = frozenset({"emergency", "owner"})
    survival_blocked_buckets: frozenset[str] = frozenset({"experiment"})


DEFAULT_POLICY = Policy()


@dataclass(frozen=True)
class Decision:
    status: Status
    tier: Tier
    reason: str


def decide(
    policy: Policy,
    *,
    bucket: str,
    amount: int,
    bucket_balance: int,
    total_balance: int,
    spent_today: int,
) -> Decision:
    """Decide a spend request. Order matters: hard rejections come first."""
    if amount <= 0:
        return Decision("rejected", "none", "amount must be positive")
    if bucket not in BUCKETS:
        return Decision("rejected", "none", f"unknown bucket: {bucket}")
    if amount > bucket_balance:
        return Decision("rejected", "none", "insufficient balance in bucket")
    if total_balance < policy.survival_threshold_cents and bucket in policy.survival_blocked_buckets:
        return Decision("rejected", "none", "survival mode: this bucket is locked")

    cap = policy.daily_caps_cents.get(bucket)
    if cap is not None and spent_today + amount > cap:
        return Decision("rejected", "none", f"daily cap would be exceeded ({cap} cents)")

    if bucket in policy.human_only_buckets:
        return Decision("pending", "red", "this bucket can only be spent with human approval")
    if amount > policy.hard_limit_cents:
        return Decision("pending", "red", "single-transaction limit exceeded, human approval required")
    if amount > policy.auto_limit_cents:
        return Decision("pending", "yellow", "auto limit exceeded, approval required")
    return Decision("approved", "auto", "within policy")
