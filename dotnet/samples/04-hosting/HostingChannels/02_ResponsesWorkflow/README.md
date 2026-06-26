# Responses-hosted workflow

Exposes a `Workflow` on the OpenAI Responses-shaped channel. A run hook adapts the channel's parsed
Responses input (a `ChatMessage` list) into the workflow's typed string input before the host invokes the
workflow.

## What it shows

* `AddAgentFrameworkHost(workflow).AddResponsesChannel(o => o.RunHook = ...)`
* The run-hook seam (`IChannelRunHook`) for workflow input preparation
* Host `StatePaths` for per-isolation-key workflow checkpoint location derivation

## Requirements

No model credentials required; the workflow echoes its input.

## Try it

```bash
cd dotnet/samples/04-hosting/HostingChannels/02_ResponsesWorkflow
dotnet run
```

```bash
curl -X POST http://localhost:5000/responses \
  -H "Content-Type: application/json" \
  -d '{ "input": "ping" }'
```