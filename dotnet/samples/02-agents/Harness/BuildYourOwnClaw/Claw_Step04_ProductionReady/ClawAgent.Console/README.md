# ClawAgent.Console

Interactive local host for the production-ready claw. It uses the shared `ClawAgentFactory` and the Step 03 console experience (`HarnessConsole.RunAgentAsync`) with planning observers and OpenAI Responses display helpers.

## Run

```bash
cd dotnet
dotnet run --project samples/02-agents/Harness/BuildYourOwnClaw/Claw_Step04_ProductionReady/ClawAgent.Console
```

Set `OTEL_EXPORTER_OTLP_ENDPOINT` to send traces/metrics to an OTLP collector (for example a local Aspire dashboard). When it is not set, telemetry is not exported — there is no console exporter, because streaming spans and metrics to stdout would corrupt the interactive UI rendered by `HarnessConsole.RunAgentAsync`.
