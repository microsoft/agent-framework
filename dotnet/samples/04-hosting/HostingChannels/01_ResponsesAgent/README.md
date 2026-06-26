# Responses agent

Exposes an `AIAgent` on the OpenAI Responses-shaped channel from
`Microsoft.Agents.AI.Hosting.Channels.Responses`. The smallest demonstration of
`AddAgentFrameworkHost(agent).AddResponsesChannel()` + `MapAgentFrameworkHost()`.

## What it shows

* One `AgentFrameworkHost` owning a single Responses channel
* `POST /responses` returning a Responses JSON object
* `POST /responses` with `"stream": true` returning a Server-Sent-Events stream
* Session continuity keyed by `ChannelSession.IsolationKey` (here derived from `previous_response_id`)

## Requirements

* `OPENAI_API_KEY` set
* `OPENAI_MODEL` optional; defaults to `gpt-5.4-mini`

## Try it

```bash
cd dotnet/samples/04-hosting/HostingChannels/01_ResponsesAgent
dotnet run
```

```bash
curl -X POST http://localhost:5000/responses \
  -H "Content-Type: application/json" \
  -d '{ "input": "Tell me a short joke." }'

curl -N -X POST http://localhost:5000/responses \
  -H "Content-Type: application/json" \
  -d '{ "input": "Outline a haiku about spring.", "stream": true }'
```