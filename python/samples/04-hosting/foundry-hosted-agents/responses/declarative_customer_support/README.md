# What this sample demonstrates

A realistic **multi-turn** [Agent Framework](https://github.com/microsoft/agent-framework) **declarative workflow** — defined entirely in YAML — hosted using the **Responses protocol**. It shows how a declarative workflow that invokes multiple Foundry-hosted agents can run end-to-end on every user turn while reading the prior conversation through `Conversation.messages` (populated automatically by `Workflow.as_agent()`).

> Read more about declarative workflows in the [Agent Framework documentation](https://learn.microsoft.com/en-us/agent-framework/workflows/declarative/?pivots=programming-language-python) and about workflow-as-an-agent in the [Workflow as an Agent documentation](https://learn.microsoft.com/en-us/agent-framework/workflows/as-agents?pivots=programming-language-python).

## How It Works

### The Workflow

[`workflow.yaml`](workflow.yaml) describes a customer-support triage flow:

1. `InvokeAzureAgent: TriageAgent` — looks at the full conversation so far and emits a structured `TriageResponse` (`Category`, `NeedsClarification`, `ClarificationQuestion`, `Reply`).
2. `ConditionGroup` routes on the triage decision:
   - **NeedsClarification** → `SendActivity` asks one focused follow-up question and ends the turn.
   - **Category = "Technical"** → `SendActivity` confirms the handoff, then `InvokeAzureAgent: TechSupportAgent` answers with `autoSend: true` so its reply streams directly to the caller.
   - **Category = "Billing"** → same pattern, routed to `BillingAgent`.
   - **else** → `SendActivity` returns the triage agent's `Reply` directly (good for greetings or general questions).

Each user message re-runs the workflow from the trigger. Because `Workflow.as_agent()` populates `Conversation.messages` with the prior turns of the conversation, every `InvokeAzureAgent` call sees the full history — which is what makes the triage decision and the specialist follow-ups coherent across turns.

### Agent Hosting

[`main.py`](main.py) builds three `Agent` instances on top of a shared `FoundryChatClient` (one per workflow role), registers them with the `WorkflowFactory` so the YAML's `InvokeAzureAgent` actions can resolve them by name, loads the workflow, wraps it with `.as_agent(...)`, and hands the agent to `ResponsesHostServer`, which provisions a REST API endpoint compatible with the OpenAI Responses protocol.

The triage agent is configured with `response_format=TriageResponse` (a Pydantic model) so the workflow can read its structured fields via `Local.Triage.*`. The specialist agents are plain text and use `autoSend: true` to deliver their reply straight to the caller.

## Running the Agent Host

Follow the instructions in the [Running the Agent Host Locally](../../README.md#running-the-agent-host-locally) section of the README in the parent directory to run the agent host.

## Interacting with the agent

> Depending on how you run the agent host, you can invoke the agent using `curl` (`Invoke-WebRequest` in PowerShell) or `azd`. Please refer to the [parent README](../../README.md) for more details. Use this README for sample queries you can send to the agent.

Send a POST request to the server with a JSON body containing an `"input"` field to interact with the agent. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "I have a problem"}'
```

Invoke with `azd`:

```bash
azd ai agent invoke --local "I was double-charged this month"
# → "Connecting you with billing support..."
# → BillingAgent: "I'm sorry about that. Can you share the last 4 digits of the card on file?"
```

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the [Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry) section of the README in the parent directory.

> [!IMPORTANT]
> Deploy this sample as a **container** (not Code/ZIP). Its declarative workflow uses Power Fx, which needs the .NET runtime included in the `Dockerfile`. Choose **Container** in every deploy flow.