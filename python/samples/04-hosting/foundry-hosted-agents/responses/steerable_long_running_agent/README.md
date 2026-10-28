# Long-running Responses agent (steering temporarily unavailable)

**Steering is currently gated.** `ResponsesHostServer` rejects
`ResponsesServerOptions(steerable_conversations=True)` during construction rather than starting a
TaskManager that can retain unbounded futures after rejected steering requests. The upstream fix is
[Azure/azure-sdk-for-python#49233](https://github.com/Azure/azure-sdk-for-python/pull/49233);
steering will be re-enabled only after a patched official `azure-ai-agentserver-core` wheel is released,
the package's minimum dependency and lockfile are updated, and a concurrent overflow test verifies
that rejected turns leave no pending futures. Do not enable steering using a private SDK patch or a
queue-length precheck.

[main.py](main.py) remains **runnable** as a regular non-steerable countdown agent. It uses
`history_source="agent_server"` with a `FoundryChatClient` and returns the caller's **outer** `response.id` for
background polling. Running a second turn concurrently does not steer the first. Start it using the
[parent hosting guide](../../README.md), then send one stored background request. The deployment
manifests keep their existing agent name for identity compatibility, not because steering is enabled:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input": "Count down from 30, slowly and with commentary.", "store": true, "background": true}'
```

Poll `GET /responses/{response.id}` until the response is completed. The agent can also stream text
with `"stream": true`; normal background polling does not require provider-native background mode.

[verify_steering.py](verify_steering.py) currently checks the **fail-fast gate** without Azure
credentials or a deployed host. It does not send steering turns or claim they work:

```bash
python verify_steering.py
```

Restore the end-to-end steering verifier only after the SDK fix is consumed and the queue-overflow
regression passes. Do not claim crash replay for an ordinary background agent: a process crash can
leave a response unfinished without an opted-in private provider continuation.
