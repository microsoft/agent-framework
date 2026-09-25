# Responses agents: history, storage, and options

The **outer** Responses request decides whether the hosted response is stored. The developer separately selects
where the **inner** agent gets its conversation history:

| Entry point | `inner_history` | Model history |
| --- | --- | --- |
| [main.py](main.py) | `"host"` | The outer Responses transcript; the inner client runs with `store=False`. |
| [service_history.py](service_history.py) | `"service"` | Only new input goes to the model; its private `service_session_id` persists for later turns. |
| [agent_history.py](agent_history.py) | `"agent"` | `InMemoryHistoryProvider` loads from `AgentSession.state`; inner client storage is off. |
| [options.py](options.py) | `"host"` | The hook removes the caller's token limit so the agent default is used. |
| [provider_background.py](provider_background.py) | `"service"` | Opt-in provider background with a private recovery token. |

Run one entry point at a time. The deployment manifest targets `main.py`; select another script to deploy a different
mode. Set `FOUNDRY_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME` in `.env`, then run `python main.py`.
Follow the [parent hosting guide](../../README.md) for local and deployed setup.

## Outer response storage and background

`store=True` makes a response retrievable at `GET /responses/{response.id}` and available for continuation using
`previous_response_id` or a `conversation`. It does **not** choose inner history. With `store=False`, the response
is one-shot: the host writes no MAF session, approval, or conversation state, and it does not request inner service
storage. Application-owned tools and other external services can still have their own side effects. If a custom
agent or external history provider cannot guarantee that boundary, the host rejects the unstored request.

`background=True` requires `store=True` and returns the **outer** `response.id` as the polling handle. Normal agent
background runs inside AgentServer even if the chat client cannot run in the background. Without durable inner
continuation, a process crash can leave such a response unfinished. The optional
[provider_background.py](provider_background.py) opts a storing Responses client into its *separate* background
mode: only this mode persists the provider's private token and polls it until completion/recovery. It is incompatible
with steering. The deployed identity needs Foundry User permission on the project for private provider polling.

[client.py](client.py) shows stored conversation turns, an unstored request, and background polling. It also needs
`FOUNDRY_AGENT_NAME` and Azure CLI authentication. For a local host, a simple multi-turn request is:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input": "Hello", "store": true, "conversation": "my-conversation"}'
```

Send another request with the same `conversation` to continue. When deployed, keep the same Foundry sandbox:
`agent_session_id` is a **platform** session, not the outer `response.id` or the private
`AgentSession.service_session_id`. A `conversation` binds that sandbox; with a bare `previous_response_id`, also
forward the earlier response's `agent_session_id`. Older unscoped hosted MAF state is not migrated; start a new
conversation after upgrading (see the [package state guide](../../../../../packages/foundry_hosting/README.md#state-store)).

## Options and compatibility

Native CreateResponse generation fields become MAF run options (`max_output_tokens` becomes `max_tokens` and
`parallel_tool_calls` becomes `allow_multiple_tool_calls`). Flattened OpenAI `extra_body` values overlay translated
keys **last**. The developer's `prepare_options(request, options)` hook can then remove or replace *caller* options;
removing one exposes the agent's own unchanged `default_options`. In [options.py](options.py),
`max_output_tokens=300` plus `extra_body={"max_tokens": 150}` becomes `max_tokens=150` before the hook removes it;
the model receives the agent's `max_tokens=256` default instead. Platform IDs, storage flags, and private
continuation tokens are never caller model options; the hook cannot add them back.

`history_source="agent_server"` and `history_source="agent"` remain available with a per-host deprecation warning.
For **stored** requests, the latter preserves the former behavior: only new input goes to the agent, and its
developer-owned defaults may choose either a HistoryProvider **or downstream service storage**. It does **not**
silently become `inner_history="agent"`. Prefer the explicit mode in new code. `store=` as a constructor parameter
is a deprecated alias for `response_store=` (the outer storage *backend*, not the caller's `store` flag).
