# Memory with Mem0

This sample registers `Mem0Provider` as an `AIContextProvider` on a Foundry-backed
agent. Mem0 extracts memories from conversation messages and retrieves relevant
memories for later requests, including requests in a new session with the same
scope. It is not a replacement for storing the complete conversation transcript.

## Prerequisites and configuration

- Install the .NET SDK specified in `dotnet/global.json`.
- Create a Foundry project with a deployed chat model and authenticate locally
  with `az login`. The sample uses `DefaultAzureCredential`; the selected identity
  needs permission to use the project and model.
- Have a Mem0 service endpoint and API key. The sample sends conversation data
  to that service; use a dedicated test scope and test data.

Set these environment variables before running:

| Variable | Value |
| --- | --- |
| `FOUNDRY_PROJECT_ENDPOINT` | Your Foundry project URL, ending in `/api/projects/<project-name>`. |
| `FOUNDRY_MODEL` | Your model deployment name. If omitted, the sample uses `gpt-5.4-mini`. |
| `MEM0_ENDPOINT` | The Mem0 service base URL. |
| `MEM0_API_KEY` | The API key for that service. The sample sends it using the `Token` authorization scheme. |

From the repository root, run:

```sh
dotnet run --project dotnet/samples/02-agents/AgentWithMemory/AgentWithMemory_Step02_MemoryUsingMem0
```

**The sample clears existing Mem0 memories for its scope at startup.**
`ClearStoredMemoriesAsync(session)` uses the provider's storage scope, not just
the current in-memory conversation. The sample scope is
`ApplicationId = "getting-started-agents"` and `UserId = "sample-user"`.
Choose a dedicated scope before running; remove the clear call when you want
memories to survive repeated executions.

## How the provider participates in a run

The registration in [Program.cs](./Program.cs) supplies the existing `HttpClient`
to `Mem0Provider` and adds it to `ChatClientAgentOptions.AIContextProviders`.

1. Before model invocation, the provider searches Mem0 using the request text
   and the session's search scope, then adds retrieved memories to the context.
2. After invocation, it sends request and response messages to Mem0 for memory
   extraction using the storage scope.
3. Later invocations can retrieve those memories. The two-second delay in the
   sample gives indexing time; it is not a guarantee that every memory is ready.

By default, `Mem0ProviderOptions.SearchInputMessageFilter` and
`StorageInputRequestMessageFilter` select external request messages;
`StorageInputResponseMessageFilter` includes all response messages. Configure
these options when only a subset of messages should be searched or stored.
For the full options, see [Mem0ProviderOptions](../../../../src/Microsoft.Agents.AI.Mem0/Mem0ProviderOptions.cs).

## Choose the memory scope

`Mem0ProviderScope` can contain application, agent, thread, and user IDs. Supply
at least one scope value. Omitting a dimension allows memories to span that
dimension; for example, omitting `UserId` does not provide per-user separation.

The sample uses a stable application/user pair, so its final new session can
recall earlier memories. Add a distinct `ThreadId` when memories should stay
within one conversation. The `stateInitializer` runs when the provider first
encounters a session without its state, so a generated ID there is per session,
not per model invocation.

In a multi-user application, derive scope IDs from the authenticated caller and
the application's tenant boundary. The shared `sample-user` literal is only for
this demonstration. A caller-supplied user ID is not proof of identity, and
memory scope selection does not replace application authorization.

## Session state and troubleshooting

The sample serializes and restores the agent session, then starts another session
with the same scope. Session serialization preserves provider state; memories
remain in the Mem0 service rather than becoming embedded in the serialized session.

If recall is empty, check the scope values, endpoint/key, and indexing delay.
The provider logs search and storage failures when a logger is configured;
a successful agent response alone does not prove memory persistence succeeded.
Inspect [Mem0Provider](../../../../src/Microsoft.Agents.AI.Mem0/Mem0Provider.cs)
for error-handling behavior. Avoid putting API keys or sensitive memory contents
in logs.
