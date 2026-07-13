# Workflow on a Standalone Durable Task Worker

This sample demonstrates running an agent-framework `Workflow` as a durable
orchestration on a **standalone Durable Task worker** — no Azure Functions
required. It is the durabletask counterpart to the Azure Functions workflow
samples (`samples/04-hosting/azure_functions/10_workflow_no_shared_state`).

## Key Concepts Demonstrated

- Hosting a MAF `Workflow` outside Azure Functions via
  `DurableAIAgentWorker.configure_workflow(workflow)`, which auto-registers:
  - a durable **entity** for each agent executor,
  - a durable **activity** for each non-agent executor, and
  - the **workflow orchestrator** (registered as `WORKFLOW_ORCHESTRATOR_NAME`).
- Conditional routing with `add_switch_case_edge_group` (spam vs. legitimate email).
- Mixing AI agents with non-agent executors in one workflow graph.
- Starting the workflow from a client with
  `DurableWorkflowClient.start_workflow(input=...)` and reading its result with
  `await_workflow_output(instance_id)`.

## Environment Setup

See the [README.md](../README.md) in the parent directory for environment setup.

This sample uses Azure AI Foundry credentials:

- `FOUNDRY_PROJECT_ENDPOINT`
- `FOUNDRY_MODEL`

It also needs a Durable Task Scheduler. For local development, start the
emulator (defaults to `http://localhost:8080`):

```bash
docker run -d -p 8080:8080 -p 8082:8082 mcr.microsoft.com/dts/dts-emulator:latest
```

## Running the Sample

Start the worker in one terminal:

```bash
cd samples/04-hosting/durabletask/08_workflow
python worker.py
```

In a second terminal, run the client:

```bash
python client.py
```

The client runs two cases:

- **Legitimate email** → `SpamDetectionAgent` → `EmailAssistantAgent` →
  `email_sender` → `"Email sent: ..."`.
- **Spam email** → `SpamDetectionAgent` → `spam_handler` →
  `"Email marked as spam: ..."`.
