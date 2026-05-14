### Motivation and Context

This PR completes the Magentic end-to-end workflow coverage described in `MagenticE2E_TestPlan.md` and summarized in `MagenticE2E_ImplementationReview.md`.

The Magentic orchestrator has several user-visible branches that are difficult to validate with isolated unit tests: planning and replanning, human plan review, participant routing, stall/reset handling, progress-ledger retry behavior, final-answer termination, checkpoint/resume, and invalid or erroneous workflow inputs. This change adds fully built workflow tests that exercise those behaviors through `MagenticWorkflowBuilder.Build()` and the in-process streaming workflow runtime.

It also fixes production behavior discovered while adding the E2E tests:

- Empty Magentic teams now fail during workflow build instead of producing a workflow that can fail later during execution.
- New top-level messages sent after Magentic termination now surface the orchestrator's terminal-state error as a workflow error, even though the workflow framework accepts queued messages.

### Description

This PR adds a Magentic E2E test suite and supporting implementation updates.

Key changes:

- Added `MagenticOrchestrationTests.cs` with **23 end-to-end tests** that run fully built Magentic workflows through the streaming workflow runtime.
- Covered happy-path completion, participant delegation, multi-round coordination, plan signoff, plan approval/revision flows, multiple revisions, stall-triggered replanning, checkpoint/resume behavior, round/reset limits, progress-ledger retry/reset handling, next-speaker validation, warning/event emission, instruction-message flow, empty-team validation, and post-termination message rejection.
- Added `MagenticE2E_TestPlan.md` documenting the intended E2E coverage across the Magentic orchestrator decision tree.
- Added/updated `MagenticE2E_ImplementationReview.md` documenting the final coverage state and production behavior verified by the suite.
- Updated `MagenticWorkflowBuilder.Build()` to throw `InvalidOperationException` when no participants have been added.
- Updated `MagenticOrchestrator.TakeTurnAsync()` to reject new messages after the Magentic task context is terminated, matching the existing terminal-state protection on plan-review responses.
- Aligned Magentic orchestration behavior with the expected coordination loop: normal participant returns resume progress-ledger coordination instead of replanning.
- Ensured stall handling uses the intended `StallCount > MaxStallCount` semantics and preserves stall context for plan review when replanning after a stall.
- Ensured the orchestrator declares the final-answer output protocol used by fully built workflow execution.

Validation performed:

- `dotnet build tests/Microsoft.Agents.AI.Workflows.UnitTests/Microsoft.Agents.AI.Workflows.UnitTests.csproj -f net10.0`
- `dotnet test --project tests/Microsoft.Agents.AI.Workflows.UnitTests/Microsoft.Agents.AI.Workflows.UnitTests.csproj -f net10.0 --filter-class '*MagenticOrchestrationTests'`
- Parallel validation completed with no review comments or security alerts.

### Contribution Checklist

- [x] The code builds clean without any errors or warnings
- [x] The PR follows the [Contribution Guidelines](https://github.com/microsoft/agent-framework/blob/main/CONTRIBUTING.md)
- [x] All unit tests pass, and I have added new tests where possible
- [ ] **Is this a breaking change?** If yes, add "[BREAKING]" prefix to the title of the PR.
