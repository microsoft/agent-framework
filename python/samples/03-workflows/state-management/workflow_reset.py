# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass

from agent_framework import Executor, Workflow, WorkflowBuilder, WorkflowContext, handler
from typing_extensions import Never, override

"""
Sample: Reusing a Workflow across independent jobs with reset_for_new_run().

Build a small moderation pipeline that silently accumulates stats as messages
flow through it and emits a summary only when the caller asks for one. Drive
the same workflow instance across multiple independent jobs and show that
``Workflow.reset_for_new_run()`` clears all per-executor state without
rebuilding the graph.

Two custom executors share the work, each with its own per-job state and its
own ``reset()`` override:

- ``FlaggedKeywordCounter`` is the start executor. It accepts message strings
  to inspect (silently updating local stats, sending nothing downstream) and
  ``ReportRequest`` markers that cause it to forward a ``StatsSnapshot``.
- ``StatsReporter`` formats the snapshot, increments its own emitted-reports
  counter, and yields the summary as the workflow output.

A run with a string produces no output, just a state update. A run with a
``ReportRequest`` produces exactly one summary. Job boundaries are entirely
controlled by the caller via ``reset_for_new_run()``, which calls ``reset()``
on every executor in the graph.

Purpose:
Show how to:
- Hold per-job aggregate state on a custom Executor subclass.
- Override ``Executor.reset()`` on every executor that owns per-run state, so
  it is cleared automatically when the workflow is reset.
- Call ``Workflow.reset_for_new_run()`` between independent jobs so a single
  workflow instance can serve a stream of unrelated batches without leaking
  state.

Prerequisites:
- No external services or credentials required; this sample runs entirely in-process.
- Familiarity with WorkflowBuilder and Executor subclasses.
"""


@dataclass
class ReportRequest:
    """Marker input that asks the workflow to emit a summary of stats so far."""


@dataclass
class StatsSnapshot:
    """Snapshot the counter forwards to the reporter when a report is requested."""

    messages_seen: int
    flagged_messages: int
    flagged_keywords: list[str]


class FlaggedKeywordCounter(Executor):
    """Executor that silently accumulates per-job stats; emits on demand.

    Holds three instance attributes that build up across the runs that make up a
    single job:

    - ``_messages_seen``: how many messages have been inspected.
    - ``_flagged_messages``: how many of those messages contained any flagged keyword.
    - ``_flagged_keywords``: the set of distinct keywords actually observed.

    Two handlers dispatch by input type:

    - ``inspect`` accepts a string, updates the counters, and sends nothing.
    - ``emit_report`` accepts a ``ReportRequest`` and forwards a current
      ``StatsSnapshot`` to the downstream reporter.

    Without overriding ``reset()`` this state would leak into the next job when the
    workflow is reused via ``Workflow.reset_for_new_run()``. The override below
    clears these attributes so each fresh job starts empty.
    """

    FLAGGED_KEYWORDS = frozenset({"spam", "scam", "phishing"})

    def __init__(self, id: str) -> None:
        super().__init__(id=id)
        self._messages_seen: int = 0
        self._flagged_messages: int = 0
        self._flagged_keywords: set[str] = set()

    @handler
    async def inspect(self, message: str, ctx: WorkflowContext[StatsSnapshot]) -> None:
        """Inspect ``message`` and update local stats. Sends nothing downstream."""
        self._messages_seen += 1
        hits = {kw for kw in self.FLAGGED_KEYWORDS if kw in message.lower()}
        if hits:
            self._flagged_messages += 1
            self._flagged_keywords.update(hits)

    @handler
    async def emit_report(self, _: ReportRequest, ctx: WorkflowContext[StatsSnapshot]) -> None:
        """Forward the current stats snapshot to the reporter on request."""
        await ctx.send_message(
            StatsSnapshot(
                messages_seen=self._messages_seen,
                flagged_messages=self._flagged_messages,
                flagged_keywords=sorted(self._flagged_keywords),
            )
        )

    @override
    async def reset(self) -> None:
        """Clear per-job aggregate state when the workflow is reset.

        ``Workflow.reset_for_new_run()`` calls ``reset()`` on every executor in the
        graph; overriding it here is what makes a reused workflow safe to drive with
        a brand-new job.
        """
        self._messages_seen = 0
        self._flagged_messages = 0
        self._flagged_keywords.clear()


class StatsReporter(Executor):
    """Terminal executor that formats a snapshot and yields it as workflow output.

    Holds a single instance attribute, ``_reports_emitted``, that tracks how many
    summaries this reporter has produced on this workflow instance, and clears
    it on reset so a reset workflow behaves identically to a freshly built one.
    """

    def __init__(self, id: str) -> None:
        super().__init__(id=id)
        self._reports_emitted: int = 0

    @handler
    async def report(self, snapshot: StatsSnapshot, ctx: WorkflowContext[Never, str]) -> None:
        self._reports_emitted += 1
        summary = (
            f"messages={snapshot.messages_seen}, "
            f"flagged={snapshot.flagged_messages}, "
            f"keywords={snapshot.flagged_keywords or 'none'}, "
            f"reports_emitted={self._reports_emitted}"
        )
        await ctx.yield_output(summary)

    @override
    async def reset(self) -> None:
        """Clear the emitted-reports counter when the workflow is reset."""
        self._reports_emitted = 0


async def _process(workflow: Workflow, messages: list[str]) -> None:
    """Send each message through the workflow; no output is produced."""
    for message in messages:
        await workflow.run(message)


async def _request_report(workflow: Workflow) -> str:
    """Ask the workflow for a summary of the stats accumulated so far."""
    events = await workflow.run(ReportRequest())
    outputs = events.get_outputs()
    return outputs[0] if outputs else ""


async def main() -> None:
    """Build the moderation workflow once, then run it across three independent jobs."""

    # 1. Build the moderation pipeline once. The same workflow instance will be
    #    reused for every job; that's the whole point of this sample.
    counter = FlaggedKeywordCounter(id="counter")
    reporter = StatsReporter(id="reporter")
    workflow = WorkflowBuilder(start_executor=counter, output_from=[reporter]).add_edge(counter, reporter).build()

    # 2. First job -- inspect three messages, then request a report. Note this
    #    batch happens to be three messages, but any size works.
    await _process(workflow, ["hello there", "free phishing kit", "lunch plans?"])
    print(f"Batch A summary: {await _request_report(workflow)}")

    # 3. Second job WITHOUT reset. State from batch A leaks in: the counter's
    #    tallies and the reporter's emitted-reports counter both keep
    #    accumulating even though batch B is conceptually a separate job.
    await _process(workflow, ["weekly status update", "team offsite agenda", "quarterly review"])
    print(f"Batch B summary (no reset): {await _request_report(workflow)}")

    # 4. Now reset between jobs and process the same batch B again. The summary
    #    reflects only batch B and every per-run counter starts fresh, because
    #    reset_for_new_run() calls reset() on every executor in the graph:
    #    - FlaggedKeywordCounter clears its message / flag / keyword tallies.
    #    - StatsReporter clears its emitted-reports counter.
    await workflow.reset_for_new_run()
    await _process(workflow, ["weekly status update", "team offsite agenda", "quarterly review"])
    print(f"Batch B summary (after reset): {await _request_report(workflow)}")

    # 5. Reset again before a final unrelated job. A reset workflow is
    #    indistinguishable from a freshly built one for state purposes, but
    #    cheaper because the graph and executor objects are reused.
    await workflow.reset_for_new_run()
    await _process(workflow, ["spam offer #1", "scam alert", "phishing attempt"])
    print(f"Batch C summary (after reset): {await _request_report(workflow)}")

    """
    Sample Output:

    Batch A summary: messages=3, flagged=1, keywords=['phishing'], reports_emitted=1
    Batch B summary (no reset): messages=6, flagged=1, keywords=['phishing'], reports_emitted=2
    Batch B summary (after reset): messages=3, flagged=0, keywords=none, reports_emitted=1
    Batch C summary (after reset): messages=3, flagged=3, keywords=['phishing', 'scam', 'spam'], reports_emitted=1
    """


if __name__ == "__main__":
    asyncio.run(main())
