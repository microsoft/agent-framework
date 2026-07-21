# Copyright (c) Microsoft. All rights reserved.

"""Executor that replays cached playbooks before falling back to the agent."""

import asyncio
import logging

from agent_framework import Executor, WorkflowContext, handler

from sample_validation.models import (
    DiscoveryResult,
    ReplayResult,
    RunResult,
    RunStatus,
    SampleInfo,
    ValidationConfig,
)
from sample_validation.playbook import PlaybookStore, replay_playbook

logger = logging.getLogger(__name__)


class ReplayCachedPlaybooksExecutor(Executor):
    """Replay cached playbooks and split samples into cached vs. agent-bound.

    For every discovered sample we look for a playbook whose recorded hash still
    matches the sample's current content. Matching playbooks are replayed
    deterministically (no LLM). Samples that pass are returned as cached
    results; samples without a valid playbook, or whose replay fails, are passed
    on for agent-driven validation (which will refresh the playbook).
    """

    def __init__(self, config: ValidationConfig) -> None:
        super().__init__(id="replay_cached_playbooks")
        self.config = config
        self._store = PlaybookStore(config.playbooks_dir) if config.playbooks_dir else None

    @handler
    async def replay(self, discovery: DiscoveryResult, ctx: WorkflowContext[ReplayResult]) -> None:
        """Attempt cached replay for each sample, then forward the remainder."""
        samples = discovery.samples

        if not self.config.use_cache or self._store is None or not samples:
            await ctx.send_message(ReplayResult(remaining_samples=samples, cached_results=[]))
            return

        store = self._store
        candidates: list[tuple[SampleInfo, object]] = []
        remaining: list[SampleInfo] = []

        for sample in samples:
            playbook = store.is_valid_for(sample)
            if playbook is None:
                remaining.append(sample)
            else:
                candidates.append((sample, playbook))

        print(
            f"\nCache check: {len(candidates)} sample(s) have a valid playbook, "
            f"{len(remaining)} need the agent."
        )

        cached_results: list[RunResult] = []
        if candidates:
            semaphore = asyncio.Semaphore(max(1, self.config.max_parallel_workers))

            async def _run(sample: SampleInfo, playbook: object) -> tuple[SampleInfo, RunResult]:
                async with semaphore:
                    result = await replay_playbook(playbook, self.config.python_root)  # type: ignore[arg-type]
                return sample, result

            for coro in asyncio.as_completed([_run(s, pb) for s, pb in candidates]):
                sample, result = await coro
                if result.status == RunStatus.SUCCESS:
                    cached_results.append(result)
                    print(f"[cache hit] {sample.relative_path}")
                else:
                    # Replay failed: hand the sample to the agent to re-validate and refresh the playbook.
                    logger.info(f"Cached replay failed for {sample.relative_path}: {result.error}")
                    print(f"[cache miss] {sample.relative_path} (replay failed, will use agent)")
                    remaining.append(sample)

        await ctx.send_message(ReplayResult(remaining_samples=remaining, cached_results=cached_results))
