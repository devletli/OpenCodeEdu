# 0004: `config.py` is the single settings module (no new wrapper)

## Context

The roadmap asks for env loading "via a single settings module". All
configuration already funnels through `src/kiraci/config.py`: tier model
chains (`KIRACI_MODEL_*`), `KIRACI_CONFIG` path selection, and every
`[section]` default table. Secrets (`*_KEY`, `*_TOKEN`) are read at point
of use from process env, never stored in config objects.

## Decision

No new settings module. `config.py` stays the single place for env names,
file paths, and defaults; any new knob goes into `config.toml` +
`OPS_DEFAULTS`/`REVENUE_DEFAULTS`/etc. with a code default.

## Consequences

- One import surface for settings; no wrapper cruft.
- Secret env vars remain out of config dumps and logs by construction.
