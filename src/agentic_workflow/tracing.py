"""Pluggable tracing so every triage run is observable.

The `Agent` emits one **trace** per incident and one **span** per step — the planner's
decision, then each tool call — capturing inputs, outputs, and latency.

The default `NullTracer` is a no-op, so CI (and anyone who just wants the agent) needs no
observability backend. To see runs in a dashboard, pass a tracer whose `trace()`/`span()`
context managers match this shape — notably
[`llm-observatory`](https://github.com/himanshutamboli/llm-observatory)'s
`Tracer(DBWriter(...))`, which plugs in unchanged (see `observed.py`).

`RecordingTracer` is an in-memory implementation used by the tests and the dep-free demo.
"""

from dataclasses import dataclass, field
from typing import Protocol


class Span(Protocol):
    def set_output(self, text: str) -> None: ...
    def set_usage(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        model: str | None = None,
        cost_usd: float | None = None,
    ) -> None: ...


class Trace(Protocol):
    def span(self, name: str, kind: str = "function", input: str | None = None): ...


class Tracer(Protocol):
    def trace(
        self,
        name: str,
        session_id: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
    ): ...


# --- No-op default (CI-safe: zero dependencies) ---------------------------------------------


class _NullSpan:
    def __enter__(self) -> "_NullSpan":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def set_output(self, text: str) -> None: ...
    def set_usage(self, *args, **kwargs) -> None: ...


class _NullTrace:
    def __enter__(self) -> "_NullTrace":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def span(self, name: str, kind: str = "function", input: str | None = None) -> _NullSpan:
        return _NullSpan()


class NullTracer:
    """Traces nothing; the default so the agent runs without an observability backend."""

    def trace(self, name: str, session_id=None, model=None, prompt_version=None) -> _NullTrace:
        return _NullTrace()


# --- In-memory recorder (tests + dep-free demo) ---------------------------------------------


@dataclass
class RecordedSpan:
    name: str
    kind: str
    input: str | None = None
    output: str | None = None

    def __enter__(self) -> "RecordedSpan":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def set_output(self, text: str) -> None:
        self.output = text

    def set_usage(self, *args, **kwargs) -> None: ...


@dataclass
class RecordedTrace:
    name: str
    session_id: str | None = None
    model: str | None = None
    spans: list[RecordedSpan] = field(default_factory=list)

    def __enter__(self) -> "RecordedTrace":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def span(self, name: str, kind: str = "function", input: str | None = None) -> RecordedSpan:
        s = RecordedSpan(name=name, kind=kind, input=input)
        self.spans.append(s)
        return s


class RecordingTracer:
    """Keeps every trace in memory for assertions and offline demos."""

    def __init__(self) -> None:
        self.traces: list[RecordedTrace] = []

    def trace(self, name: str, session_id=None, model=None, prompt_version=None) -> RecordedTrace:
        t = RecordedTrace(name=name, session_id=session_id, model=model)
        self.traces.append(t)
        return t
