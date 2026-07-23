# Copyright (c) Microsoft. All rights reserved.

import logging
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from agent_framework import (
    Executor,
    Message,
    SkillsProvider,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    handler,
)
from agent_framework.github import GitHubCopilotAgent
from copilot.session import PermissionHandler, PermissionRequestResult
from copilot.session_events import PermissionRequest
from pydantic import BaseModel
from sample_validation.const import WORKER_COMPLETED
from sample_validation.models import (
    ExecutionResult,
    ReplayResult,
    RunResult,
    RunStatus,
    SampleInfo,
    ValidationConfig,
    WorkflowCreationResult,
)
from sample_validation.playbook import (
    Playbook,
    PlaybookStore,
    compute_sample_hash,
    sample_files,
)
from typing_extensions import Never

logger = logging.getLogger(__name__)

# Directory containing file-based skills used by the validation agents.
SKILLS_DIR = Path(__file__).parent / "skills"


class PlaybookScript(BaseModel):
    """Reproducible Python validation script the agent returns so future runs can skip the agent.

    ``script`` is a complete, self-contained Python program that reproduces a successful
    validation without any AI assistance. The harness runs it with the active interpreter from
    the Python root and treats a zero exit code as success.
    """

    script: str
    timeout: int = 120
    env: dict[str, str] = {}


class AgentResponseFormat(BaseModel):
    status: str
    output: str
    error: str
    playbook: PlaybookScript | None = None


@dataclass
class CoordinatorStart:
    samples: list[SampleInfo]


@dataclass
class WorkerFreed:
    worker_id: str


class BatchCompletion:
    pass


AgentInstruction = (
    "You are validating exactly one Python sample.\n"
    "Analyze the sample code and execute it as it is. Based on the execution result, determine "
    "if it runs successfully, fails, or is missing_setup. Use `missing_setup` if the sample reports "
    "missing required environment variables. The environment you're given should contain the necessary "
    "variables. Don't create new environment variables nor modify the sample code, unless an available "
    "skill instructs you to do so for the setup issue you detected. When a skill applies to the problem, "
    "follow its guidance to resolve the setup and then re-run the sample.\n"
    "Feel free to install any required dependencies if needed.\n"
    "The sample can be interactive. If it is interactive, respond to the sample when prompted "
    "based on your analysis of the code. You do not need to consult human on what to respond.\n"
    "Fail fast and do not attempt to fix the sample unless instructed by a skill.\n"
    "When (and only when) the status is `success`, also return a `playbook`: a self-contained "
    "Python script that reproduces this successful validation WITHOUT any AI assistance, so future "
    "runs can replay it deterministically. `playbook.script` is a COMPLETE Python program with "
    "these rules:\n"
    "  - It is run with the SAME Python interpreter, and its WORKING DIRECTORY is the python/ "
    "directory (the repo's Python root, where the shared .env lives). Reference the sample with a "
    'path relative to python/, e.g. "samples/04-hosting/foundry-hosted-agents/responses/01_basic".\n'
    "  - It MUST exit 0 when validation passes and exit non-zero (raise or sys.exit(1)) when it "
    "fails. The harness maps exit code 0 to success and anything else to failure.\n"
    "  - It may import ONLY: the sample's own already-installed dependencies, the Python standard "
    "library, and `httpx`. Do not require any other third-party package.\n"
    "  - It must be non-interactive and deterministic (no prompts, no reliance on you).\n"
    "  - For a normal run-to-completion sample: launch it (e.g. subprocess.run([sys.executable, "
    '"<path>/main.py"], ...) feeding any needed stdin via input=), then assert on the exit code '
    "and/or expected output.\n"
    "  - For a LONG-LIVED SERVER sample (an HTTP server that never returns on its own, e.g. a "
    "hosted agent listening on a port): start it in the BACKGROUND (subprocess.Popen), POLL until "
    "the port accepts connections (bounded readiness loop), send the real HTTP request(s) with "
    "httpx, and assert HTTP 200 plus a non-empty/expected response. When the sample keeps "
    "conversational state, exercise MULTIPLE TURNS (e.g. turn 1 provides a fact like a name, turn 2 "
    "asks it to be recalled) and assert the recall. ALWAYS terminate the server in a finally block "
    "so no process or port is leaked (the harness also force-kills the process group as a backstop).\n"
    "  - If you had to edit any sample file to make it run, BAKE that edit into the script (apply it "
    "in code before running); the harness restores sample files after replay.\n"
    "  - On failure, print the captured server/sample output before exiting non-zero to aid debugging.\n"
    "Also set `playbook.timeout` (whole-run seconds; the harness caps it) and optional "
    "`playbook.env` (extra environment overrides; the CI environment already provides the real "
    "credentials, so usually leave this empty).\n"
    "Return ONLY valid JSON with this schema:\n"
    "{\n"
    '  "status": "success|failure|missing_setup",\n'
    '  "output": "short summary of the result and what you did if the sample was interactive",\n'
    '  "error": "error details or empty string",\n'
    '  "playbook": {"script": "<complete python program>", "timeout": 120, "env": {}}\n'
    "}\n\n"
)


def parse_agent_json(text: str) -> AgentResponseFormat:
    """Parse JSON object from an agent response."""
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return AgentResponseFormat.model_validate_json(stripped)

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in response")

    return AgentResponseFormat.model_validate_json(stripped[start : end + 1])


def status_from_text(value: str) -> RunStatus:
    """Convert a string value to RunStatus with safe fallback."""
    normalized = value.strip().lower()
    for status in RunStatus:
        if status.value == normalized:
            return status
    return RunStatus.FAILURE


def prompt_permission(
    request: PermissionRequest, context: dict[str, str]
) -> PermissionRequestResult:
    """Permission handler that always approves."""
    logger.debug(
        f"[Permission Request: {request.kind}] ({context})Automatically approved for sample validation."
    )
    return PermissionHandler.approve_all(request, context)


class CustomAgentExecutor(Executor):
    """Executor that runs a GitHub Copilot agent and returns its response.

    We need the custom executor to wrap the agent call in a try/except to ensure that any exceptions are caught and
    returned as error responses, otherwise an exception in one agent could crash the entire workflow.
    """

    # Retry in case GitHub Copilot agent encounters transient errors unrelated to the sample execution.
    RETRY_COUNT = 1

    def __init__(
        self,
        agent: GitHubCopilotAgent,
        store: PlaybookStore | None = None,
        python_root: Path | None = None,
    ):
        super().__init__(id=agent.id)
        self.agent = agent
        self._store = store
        self._python_root = python_root
        self._session = agent.create_session()

    @handler
    async def handle_task(
        self, sample: SampleInfo, ctx: WorkflowContext[WorkerFreed | RunResult]
    ) -> None:
        """Execute one sample task and notify collector + coordinator."""
        # Snapshot the sample's pristine content so we can restore the working tree afterwards
        # (the agent, or a baked-in playbook edit, may modify sample files while validating).
        snapshot = self._snapshot_sample(sample)
        current_retry = 0
        while True:
            try:
                response = await self.agent.run(
                    [
                        Message(
                            role="user",
                            contents=[f"Validate the following sample:\n\n{sample.relative_path}"],
                        )
                    ],
                    session=self._session,
                )
                result_payload = parse_agent_json(response.text)
                result = RunResult(
                    sample=sample,
                    status=status_from_text(result_payload.status),
                    output=result_payload.output,
                    error=result_payload.error,
                )
                if result.status == RunStatus.SUCCESS:
                    # Restore the sample to its committed content before hashing so the playbook's
                    # sample_hash matches what a fresh checkout (and future staleness check) sees.
                    self._restore_snapshot(snapshot)
                    self._save_playbook(sample, result_payload)
                break
            except Exception as ex:
                if current_retry < self.RETRY_COUNT:
                    logger.warning(
                        f"Error executing agent {self.agent.id} (attempt {current_retry + 1}/{self.RETRY_COUNT}): {ex}. Retrying..."
                    )
                    try:
                        current_retry += 1
                        await self.agent.stop()
                        await self.agent.start()
                        self._session = self.agent.create_session()  # Reset session for retry
                        continue
                    except Exception as restart_ex:
                        logger.error(
                            f"Error restarting agent {self.agent.id}: {restart_ex}. No more retries."
                        )
                        result = RunResult(
                            sample=sample,
                            status=RunStatus.FAILURE,
                            output="",
                            error=f"Original error: {ex}. Restart error: {restart_ex}",
                        )
                        break

                logger.error(f"Error executing agent {self.agent.id}: {ex}")
                result = RunResult(
                    sample=sample,
                    status=RunStatus.FAILURE,
                    output="",
                    error=str(ex),
                )
                break

        # Always restore the working tree so a run never leaves the repository dirty
        # (on success this is a no-op because we already restored above).
        self._restore_snapshot(snapshot)

        await ctx.send_message(result, target_id="collector")
        await ctx.send_message(WorkerFreed(worker_id=self.id), target_id="coordinator")

        await ctx.add_event(WorkflowEvent(WORKER_COMPLETED, sample))  # type: ignore

    def _snapshot_sample(self, sample: SampleInfo) -> dict[Path, bytes]:
        """Capture the current on-disk bytes of every file that makes up a sample."""
        snapshot: dict[Path, bytes] = {}
        for file in sample_files(sample):
            try:
                snapshot[file] = file.read_bytes()
            except OSError as ex:  # pragma: no cover - defensive
                logger.warning(f"Could not snapshot {file}: {ex}")
        return snapshot

    def _restore_snapshot(self, snapshot: dict[Path, bytes]) -> None:
        """Restore snapshotted files to their pristine bytes if the agent changed them."""
        for file, original in snapshot.items():
            try:
                if file.read_bytes() != original:
                    file.write_bytes(original)
            except OSError as ex:  # pragma: no cover - defensive
                logger.warning(f"Could not restore {file}: {ex}")

    def _save_playbook(self, sample: SampleInfo, payload: AgentResponseFormat) -> None:
        """Persist a cached playbook for a sample the agent validated successfully."""
        if self._store is None or payload.playbook is None:
            return
        spec = payload.playbook
        if not spec.script.strip():
            logger.warning(f"Agent returned no replay script for {sample.relative_path}; skipping playbook.")
            return
        try:
            playbook = Playbook(
                sample=sample.relative_path,
                sample_hash=compute_sample_hash(sample),
                script=spec.script,
                timeout=int(spec.timeout),
                env=dict(spec.env),
            )
            path = self._store.save(playbook)
            logger.info(f"Saved playbook for {sample.relative_path} -> {path}")
        except Exception as ex:  # pragma: no cover - defensive; never fail validation over caching
            logger.warning(f"Could not save playbook for {sample.relative_path}: {ex}")


class BatchCoordinatorExecutor(Executor):
    """Dispatch sample tasks to worker executors in bounded batches."""

    def __init__(self, worker_ids: list[str], max_parallel_workers: int) -> None:
        super().__init__(id="coordinator")
        self._worker_ids = worker_ids
        self._max_parallel_workers = max(1, max_parallel_workers)
        self._pending: deque[SampleInfo] = deque()
        self._inflight: set[str] = set()

    async def _assign_next(
        self, worker_id: str, ctx: WorkflowContext[SampleInfo | BatchCompletion]
    ) -> None:
        if not self._pending:
            # No more samples to assign
            if not self._inflight:
                # All tasks are completed, notify collector and exit
                await ctx.send_message(BatchCompletion(), target_id="collector")
            return

        sample = self._pending.popleft()
        self._inflight.add(worker_id)
        # Messages will get queued in the runner until the next superstep when all workers are freed,
        # thus achieving automatic batching without needing complex synchronization logic
        await ctx.send_message(sample, target_id=worker_id)

    @handler
    async def on_start(
        self,
        start: CoordinatorStart,
        ctx: WorkflowContext[SampleInfo | BatchCompletion],
    ) -> None:
        """Initialize queue and dispatch first wave of tasks."""
        self._pending = deque(start.samples)
        self._inflight.clear()

        for worker_id in self._worker_ids[: self._max_parallel_workers]:
            await self._assign_next(worker_id, ctx)

    @handler
    async def on_worker_freed(
        self, freed: WorkerFreed, ctx: WorkflowContext[SampleInfo | BatchCompletion]
    ) -> None:
        """Dispatch next queued sample when a worker finishes."""
        self._inflight.discard(freed.worker_id)
        await self._assign_next(freed.worker_id, ctx)


class CollectorExecutor(Executor):
    """Collect per-sample results and emit the final execution result."""

    def __init__(self) -> None:
        super().__init__(id="collector")
        self._results: list[RunResult] = []

    @handler
    async def on_all(
        self,
        batch_completion: BatchCompletion,
        ctx: WorkflowContext[Never, ExecutionResult],
    ) -> None:
        """Receive all results at once and emit Workflow Output."""
        await ctx.yield_output(ExecutionResult(results=self._results))

    @handler
    async def on_item(self, item: RunResult, ctx: WorkflowContext) -> None:
        """Record a result and emit output when all expected results arrive."""
        self._results.append(item)


class CreateConcurrentValidationWorkflowExecutor(Executor):
    """Executor that builds a nested concurrent workflow with one agent per sample."""

    def __init__(self, config: ValidationConfig):
        super().__init__(id="create_dynamic_workflow")
        self.config = config
        self._store = (
            PlaybookStore(config.playbooks_dir)
            if config.use_cache and config.playbooks_dir is not None
            else None
        )

    @handler
    async def create(
        self,
        replay: ReplayResult,
        ctx: WorkflowContext[WorkflowCreationResult],
    ) -> None:
        """Create a nested workflow with a coordinator + worker fan-out/fan-in."""
        samples = replay.remaining_samples
        cached_results = replay.cached_results
        sample_count = len(samples)
        print(
            f"\nCreating nested batched workflow for {sample_count} samples "
            f"({len(cached_results)} served from cache)..."
        )

        if sample_count == 0:
            await ctx.send_message(
                WorkflowCreationResult(
                    samples=[], workflow=None, agents=[], cached_results=cached_results
                )
            )
            return

        agents: list[GitHubCopilotAgent] = []
        workers: list[CustomAgentExecutor] = []

        for index, sample in enumerate(samples, start=1):
            agent_id = f"sample_validator_{index}({sample.relative_path})"
            agent = GitHubCopilotAgent(
                id=agent_id,
                name=agent_id,
                instructions=AgentInstruction,
                context_providers=[SkillsProvider.from_paths(skill_paths=str(SKILLS_DIR))],
                default_options={
                    "on_permission_request": prompt_permission,
                    "timeout": self.config.agent_timeout,
                },  # type: ignore
            )
            agents.append(agent)

            workers.append(
                CustomAgentExecutor(agent, store=self._store, python_root=self.config.python_root)
            )

        coordinator = BatchCoordinatorExecutor(
            worker_ids=[worker.id for worker in workers],
            max_parallel_workers=self.config.max_parallel_workers,
        )
        collector = CollectorExecutor()

        nested_builder = WorkflowBuilder(start_executor=coordinator, output_from=[collector])
        nested_builder.add_edge(coordinator, collector)
        for worker in workers:
            nested_builder.add_edge(coordinator, worker)
            nested_builder.add_edge(worker, coordinator)
            nested_builder.add_edge(worker, collector)
        nested_workflow: Workflow = nested_builder.build()

        await ctx.send_message(
            WorkflowCreationResult(
                samples=samples,
                workflow=nested_workflow,
                agents=agents,
                cached_results=cached_results,
            )
        )
