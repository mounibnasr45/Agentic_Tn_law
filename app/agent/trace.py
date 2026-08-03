"""What the agent actually did, captured so the UI can show it.

WHY THIS EXISTS. From outside, a RAG answer is a black box: text goes in, text comes out,
and nothing distinguishes a system that reasoned from one that pasted the first vector hit
into a prompt. This records the decisions that make the difference visible:

  - the query the AGENT wrote, which is not the question the user typed
  - what each retrieval returned, with scores and ranks
  - whether the reflection checkpoint fired, and on which term
  - how much of the iteration budget was consumed

WHY A ContextVar AND NOT A RETURN VALUE. The events originate three layers down — inside
the retrieval tool and inside reflect_and_reground — and threading a collector through
create_react_agent's call signature is not possible: LangGraph owns that call. The same
reasoning that put `retrieved_chunks` in a ContextVar applies here, and so does the same
safety property: ContextVars propagate into asyncio tasks and are isolated per task, so two
concurrent requests cannot bleed traces into each other. A module-level list would be bug 2
wearing a third hat.

STREAMING, AND WHY THE ContextVar STILL WORKS. `/api/ask` reads `trace.steps` only after
the whole run finishes — same content, one round trip, fully assertable in a deterministic
test. `/api/ask/stream` wants each step the instant it happens, which is what `live` below
is for: an optional per-request queue that `add()` also pushes onto. The two consumers coexist
because ChatService runs the agent as a background asyncio.Task for the streaming path — the
ContextVar is set INSIDE that task, so it gets its own copy (contextvars propagate into and
are isolated per asyncio task, the same property that makes bug 2 impossible), and `live`
just gives the surrounding generator a way to observe it as it fills up rather than waiting
for the task to finish.

An earlier version of this file argued against streaming entirely, for reasons that still
apply to the transport, not to this design: EventSource cannot send an Authorization header
(the token would have to go in the URL), so streaming goes over a `fetch()` body instead,
where a normal header works. Free-tier proxies can still buffer a long-lived response — that
risk did not go away, it was accepted.
"""
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
