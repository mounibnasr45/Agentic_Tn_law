"""Records what the agent actually did during a run — each search, each
reflection pass — so the trace panel can show it live or after the fact."""
import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Literal

StepKind = Literal["retrieval", "reflection", "answer"]


@dataclass(frozen=True, slots=True)
class TraceStep:
    kind: StepKind
    # Human-readable, French, shown as the step's heading in the UI.
    label: str
    # The query the agent actually issued. None for steps that are not a search.
    query: str | None = None
    # (article_number, score, rank) per hit — enough to show a ranked list with scores.
    results: tuple[tuple[str | None, float, int], ...] = ()
    # Free-form annotation: the undefined term reflection caught, or why it did nothing.
    detail: str | None = None


@dataclass(slots=True)
class AgentTrace:
    steps: list[TraceStep] = field(default_factory=list)
    # Tool calls issued vs the hard cap in graph.py. Shows the budget is real.
    iterations_used: int = 0
    max_iterations: int = 0
    regrounded: bool = False
    # Set only by stream_answer() (app/services/chat_service.py). When present, every step
    # is pushed here too, the moment it happens, so a consumer can hand it to the client
    # without waiting for the run to finish. None on the plain /api/ask path — same trace,
    # no live audience, nothing to push to.
    live: "asyncio.Queue[TraceStep] | None" = None

    def add(self, step: TraceStep) -> None:
        self.steps.append(step)
        if self.live is not None:
            self.live.put_nowait(step)


# Set by chat_service before the run, read after it. Never a module global.
current_trace: ContextVar[AgentTrace | None] = ContextVar("current_trace", default=None)


def record(step: TraceStep) -> None:
    """Append a step if a trace is being collected.

    Silently does nothing when there is no active trace — the CLI, the eval harness and the
    unit tests all call the retrieval tool outside a request, and tracing must never be the
    thing that makes them fail.
    """
    trace = current_trace.get()
    if trace is not None:
        trace.add(step)
