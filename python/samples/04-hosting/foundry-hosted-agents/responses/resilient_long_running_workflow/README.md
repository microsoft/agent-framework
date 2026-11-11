# Resilient native Responses workflow

This sample runs a typed countdown as a native workflow and opts into the
AgentServer resilient task subsystem. Each acknowledged MAF checkpoint is paired
with the exact caller-visible Responses output and usage produced from it.
Recovery therefore resumes the same outer `response.id` from that pair rather
than selecting an unrelated latest checkpoint.

The sample intentionally uses no model or Azure credential. Send:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input":"{\"target\":5,\"label\":\"demo\"}","stream":true,"store":true,"background":true}'
```

Poll `GET /responses/<id>` or reconnect with
`GET /responses/<id>?stream=true`. A process crash can replay work after the
last acknowledged checkpoint. The host prevents duplicate emitted output and
usage for recovered checkpoints, but it does **not** promise exactly-once
external tool side effects; make such operations idempotent.

Locally, AgentServer stores Responses envelopes, event replay, scoped bindings,
and workflow checkpoints under `${AGENTSERVER_STATE_ROOT:-~/.agentserver}`.
Do not delete shared state as part of a sample or test. Use an isolated
`AGENTSERVER_STATE_ROOT` when experimenting with crashes.

The Foundry sandbox, the Responses continuation, and the MAF checkpoint remain
separate identities. Existing legacy unscoped workflow sessions are not read;
start a fresh response chain when migrating from `agent=workflow.as_agent()`.

For Foundry deployment instructions, see the
[parent README](../../README.md#deploying-the-agent-to-foundry).
