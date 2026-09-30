"""Test doubles for agent runs. Also used by `orchestrator --dry-run`."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .runner import RunResult


class FakeRunner:
    """Scripted runner: no opencode, no network, no spending.

    outputs maps agent -> list of responses; each response is either a string
    (a successful run with that text) or a ready-made RunResult. When the list
    for an agent is exhausted, `default` is used. `on_run` is an optional
    side-effect hook (agent, prompt, cwd), e.g. so a fake builder can write files.
    """

    def __init__(
        self,
        outputs: dict[str, list] | None = None,
        *,
        fail_agents: tuple[str, ...] = (),
        timeout_agents: tuple[str, ...] = (),
        # The placeholder carries 3 distinct source URLs so dispatched scout
        # tasks pass the research evidence check (§8) by default.
        default: str = ("fake run completed\n\nSources:\n"
                        "- https://example.com/research-a\n"
                        "- https://example.com/research-b\n"
                        "- https://example.com/research-c"),
        on_run: Callable[[str, str, Path], None] | None = None,
    ):
        self.outputs = {k: list(v) for k, v in (outputs or {}).items()}
        self.fail_agents = set(fail_agents)
        self.timeout_agents = set(timeout_agents)
        self.default = default
        self.on_run = on_run
        self.calls: list[dict] = []

    def run(self, agent: str, prompt: str, cwd: Path, timeout_s: int) -> RunResult:
        self.calls.append({"agent": agent, "prompt": prompt, "cwd": cwd,
                           "timeout_s": timeout_s})
        if self.on_run is not None:
            self.on_run(agent, prompt, Path(cwd))
        if agent in self.timeout_agents:
            return RunResult(ok=False, text="", exit_code=None,
                             duration_s=float(timeout_s))
        if agent in self.fail_agents:
            return RunResult(ok=False, text="fake failure", exit_code=1,
                             duration_s=0.1)
        scripted = self.outputs.get(agent)
        if scripted:
            out = scripted.pop(0)
            if isinstance(out, RunResult):
                return out
            return RunResult(ok=True, text=out, exit_code=0, duration_s=0.1)
        return RunResult(ok=True, text=self.default, exit_code=0, duration_s=0.1)

    def calls_for(self, agent: str) -> list[dict]:
        return [c for c in self.calls if c["agent"] == agent]
