# Client (Hosting Responses Agent)

Client half of the [Hosting Responses Agent](../README.md) sample.

Runs the same three-turn conversation twice against the server's `POST /responses` route, once per
consumption path:

- **CC** — a plain `Microsoft.Extensions.AI.IChatClient` from `ResponsesClient.AsIChatClient(model)`.
  Continuity is threaded by hand: each response's `ChatResponse.ConversationId` (a `resp_` id) is passed
  back as the next turn's `ChatOptions.ConversationId`, which the SDK sends as `previous_response_id`.
- **MAF** — a Microsoft Agent Framework `AIAgent` from `ResponsesClient.AsAIAgent(...)`. A single
  `AgentSession` threads the rotating response-id chain automatically.

The third turn asks about the first turn, so a correct answer proves multi-turn session continuity.

```bash
dotnet run
```

Defaults to `http://localhost:5000`; override with `RESPONSES_SERVER_URL`. Start the server first.
