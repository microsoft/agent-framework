# Steerable Responses agent

This sample hosts a single, slowly streaming [Agent Framework](https://github.com/microsoft/agent-framework)
agent using the Responses protocol. The agent counts down with a remark before each number. A new turn sent to
the same `conversation` while the first is running can steer it: the host stops the older turn, saves its partial
response under its own `response.id`, then lets the newer turn advance the CAS-protected conversation state.
Steering is supported for regular agents, not for workflow agents or provider-native background mode.

[main.py](main.py) sets `inner_history="host"` and
`ResponsesServerOptions(steerable_conversations=True)`. The host enables AgentServer's multi-turn TaskManager
before startup; no agent-side steering code is needed. Both requests use `store=True` so the outer Responses API
can retrieve their result; the inner Foundry client still runs with `store=False`. The outer `response.id` remains
the background polling handle.

Run the agent as described in the [parent guide](../../README.md), then start a long **streamed**
background turn. Keep the SSE connection open while you send the next request; `response.created` supplies
the first polling ID:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input": "Count down from 30, slowly and with commentary.", "store": true, "stream": true, "background": true, "conversation": "my-conversation"}'
```

While it runs, submit the second turn against that **same** conversation:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input": "Actually, count down from 3 instead.", "store": true, "background": true, "conversation": "my-conversation"}'
```

The second request is accepted as queued or in progress. Poll `GET /responses/{response.id}` for each outer
response ID; the older response should complete with partial output, and the newer one should contain its own
countdown. An explicit `conversation` binds the Foundry sandbox and avoids the need to forward the
`x-agent-session-id` response header. If continuing with only `previous_response_id`, forward the prior response's
`agent_session_id` as well to stay in the same sandbox.

[verify_steering.py](verify_steering.py) runs this check against a real model, using a fresh conversation ID and
isolated temporary AgentServer state. It never deletes your existing `~/.agentserver` data. Real model timing
varies; its assertions are intentionally looser than the package's deterministic local steering tests:

```bash
python verify_steering.py --first-target 30 --second-target 3
```

For a Foundry deployment, follow the [parent deployment guide](../../README.md).
