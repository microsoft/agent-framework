# Agent Framework hosting samples (bring your own route)

These samples show how to expose an Agent Framework agent or workflow over the OpenAI Responses HTTP
protocol from an ASP.NET Core app that you write, where your app owns the HTTP route, authentication, and
where conversations are stored.

## Two ways to expose an agent over the Responses protocol

Agent Framework gives you two options:

1. **`MapOpenAIResponses` (batteries included).** A single call maps a ready-made `/responses` endpoint that
   handles the protocol, routing, and session storage for you. Pick this when you want a working endpoint
   quickly and the built-in behavior fits. See [AgentWebChat](../../05-end-to-end/AgentWebChat) for a sample
   that uses it.

2. **Call the conversion helpers from your own route (these samples).** You write the ASP.NET Core route and
   call the `OpenAIResponses` helper methods to translate between the Responses HTTP payloads and the agent.
   The framework only does the protocol translation, so you keep full control of routing, authentication,
   and where conversations are stored. Pick this when you need hosting behavior the built-in endpoint does
   not provide.

## Samples

| Sample | What it shows |
|---|---|
| [`local_responses/`](./local_responses) | An agent behind an ASP.NET Core route you write, using the `OpenAIResponses` helper methods plus `AgentSessionStore` for conversation continuity. The simplest sample to start with. |
| [`local_responses_workflow/`](./local_responses_workflow) | A workflow behind an ASP.NET Core route you write, using the `OpenAIResponses` helper methods, `HostedWorkflowState`, an explicit `CheckpointManager`, and a checkpoint cursor your app keeps so a run resumes across turns. |

Each sample is a **client/server pair** split into two projects:

```
local_responses/
├── Server/   # exposes POST /responses using the OpenAIResponses helper methods
└── Client/   # consumes it two ways: a chat client and an agent
```

The `Client` shows the two ways to consume the endpoint from .NET, both against the same server:

- A plain `Microsoft.Extensions.AI.IChatClient` (the lower-level chat-client path).
- A Microsoft Agent Framework `AIAgent` (the higher-level agent path).

## Relationship to `../FoundryHostedAgents/`

The sibling [`../FoundryHostedAgents/`](../FoundryHostedAgents) directory contains samples for agents that
run inside the Foundry Hosted Agents platform, which hosts the agent and exposes the protocol for you. Use
those when you want the Foundry-managed hosting surface; use these when you want to host the agent in your
own ASP.NET Core app.

| Aspect | `af-hosting/` (this directory) | `FoundryHostedAgents/` |
|---|---|---|
| Server stack | An ASP.NET Core app you write plus the hosting protocol helpers | Foundry Hosted Agents runtime |
| Who exposes the route | Your app | The platform |
| When to pick this | You need custom hosting code | You want the Foundry-managed hosting surface |