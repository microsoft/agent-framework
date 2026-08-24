# Client (Hosting Responses Workflow)

Client half of the [Hosting Responses Workflow](../README.md) sample.

Runs the same two-turn conversation twice against the server's `POST /responses` route, once per consumption
path:

- **CC** — a plain `Microsoft.Extensions.AI.IChatClient` from `ResponsesClient.AsIChatClient(model)`.
- **MAF** — a Microsoft Agent Framework `AIAgent` + `AgentSession` from `ResponsesClient.AsAIAgent(...)`.

Both send a JSON brief on the first turn and a refinement on the second, following the rotating
`previous_response_id` chain (the CC path threads it by hand via `ChatOptions.ConversationId`; the MAF path
lets `AgentSession` do it). The follow-up only makes sense if the workflow resumed the first turn's
checkpoint, so it proves checkpoint continuity.

```bash
dotnet run
```

Defaults to `http://localhost:5001`; override with `RESPONSES_SERVER_URL`. Start the server first.