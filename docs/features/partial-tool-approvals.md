# Collecting partial tool approvals

`ChatClientAgentOptions.EnablePartialApprovalResponses` opts a native agent into collecting decisions across runs. The default remains unchanged: an unanswered request is rejected on the next run.

```csharp
var agent = new ChatClientAgent(chatClient, new ChatClientAgentOptions
{
    EnablePartialApprovalResponses = true,
    ChatOptions = new ChatOptions { Tools = [protectedTool] },
});
```

The option requires approval-response binding. Keep it enabled when reconstructing the agent after a restart. Use a durable session store and serialize runs for each session.

For a batch with requests A and B:

1. Answer A using its original `ToolApprovalRequestContent.CreateResponse(...)`.
2. The run saves A's answer in the session and returns B with its original request ID, call ID, name and arguments. It does not invoke the model or execute A yet. An omitted answer is neither approval nor denial.
3. Save the session with `SerializeSessionAsync`. After constructing another agent, restore it with `DeserializeSessionAsync`.
4. Answer B. The complete batch is rebound to the original server-recorded calls and resumed. Explicit denials produce the normal rejected result; approved native calls produce their actual results.
5. Save the session again. Replayed answers cannot execute the completed batch again.

The first recorded decision wins, including an explicit decline. A conflicting later answer does not change a saved decision. Unknown request IDs never authorize execution. Results supplied for already completed frontend calls are retained while native siblings await decisions. Normal tool-result validation and trust rules still apply; this option is not an authorization boundary for frontend results.

Internally, `_pendingApprovalRequests` retains the batch's execution authorizations until successful completion. `_collectedApprovalDecisions` records decisions and completed sibling results. A recorded answer means **decided, awaiting batch completion**, not **executed**. Unanswered requests remain actionable. Consumers inspecting native state must distinguish those states, including when history is persisted per service call and a collection-only run never reaches that service. For service-managed and per-service history, `_collectedApprovalInput` durably queues ordinary external input from collection-only runs until it can be sent to the model. This includes text accompanying a decision. The queue is removed only after the resumed batch succeeds; the existing conversation ID is preserved on waiting responses. Client-managed end-of-run history continues to persist ordinary input through its normal history provider.

History may contain repeated waiting notifications for the same original request; these are not new tool occurrences.

This is a sequential-session durability policy, not an atomic transaction across external tool effects and session storage. A host must save collection-only runs and prevent concurrent updates to the same session. Existing failure/retry semantics after a tool executes but before storage succeeds are unchanged. Applications needing crash-safe side effects must make those effects idempotent. Disabling the option while a batch is pending reverts to the default rejection policy.

## Regression reproduction

From the `dotnet` directory, with the SDK and packages declared by the repository:

```sh
dotnet test --project tests/Microsoft.Agents.AI.UnitTests -f net10.0 \
  --filter-class '*Approval*'
```

`ChatClientAgent_PartialApprovalsTests` uses deterministic model responses and original IDs `call-a` / `ficc_call-a`, `call-b` / `ficc_call-b`, plus an optional frontend sibling. It covers streaming and non-streaming execution, both history-persistence modes, partial approve/decline, no-answer runs, fresh-agent serialization/reload, late approve/decline, duplicate and conflicting answers, rebinding tampered call identity/arguments, canonical persisted results, and no repeated successful executions after reload.

The behavior was originally reproduced on Microsoft.Agents.AI 1.26.0 with Microsoft.Extensions.AI 10.10.0 and Abstractions 10.10.1. MEAI source commit `02107c65bab30aad9e35b5133ed643eaa77bccd8` requires complete approval batches. The existing native default policy is intentional ([PR #9152](https://github.com/microsoft/agent-framework/pull/9152)); this option collects a complete batch before invoking that machinery.

This native regression coverage does not certify AG-UI host conversion, import extraction, Intelligence persistence, browser behavior or real-provider compatibility. Those layers must expose saved decisions and remaining requests truthfully and be validated with the configured host. No AG-UI host changes are included here.
