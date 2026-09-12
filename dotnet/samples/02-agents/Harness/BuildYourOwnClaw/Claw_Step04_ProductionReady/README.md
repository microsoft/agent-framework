# Production-ready claw (Post 4) — .NET

Post 4 restructures the Step 03 claw into a shared agent library plus three thin hosts.

## Projects

- [`ClawAgent`](./ClawAgent/README.md) — shared factory that builds the full Step 03 HarnessAgent, adds a stable OpenTelemetry source name, and enables Purview only when `PURVIEW_CLIENT_APP_ID` is set.
- [`ClawAgent.Console`](./ClawAgent.Console/README.md) — local interactive console host with console and OTLP OpenTelemetry exporters.
- [`ClawAgent.Hosted`](./ClawAgent.Hosted/README.md) — ASP.NET Responses host for Foundry Hosted Agent deployment. Observability is wired automatically by the hosting runtime; file access and shell are disabled on the container.
- [`ClawAgent.Evals`](./ClawAgent.Evals/README.md) — local finance checks and optional Foundry quality evals.

## Common configuration

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com/api/projects/your-project"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.4" # optional
export TOOLBOX_MCP_SERVER_URL="https://.../mcp?api-version=v1" # optional Foundry skills
export PURVIEW_CLIENT_APP_ID="<app-id>" # optional Purview governance
```

OpenTelemetry uses source and meter name `BuildYourOwnClaw.ProductionReady.Claw`. Hosts choose exporters.
