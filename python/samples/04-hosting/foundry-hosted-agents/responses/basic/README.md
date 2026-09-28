# Responses agents: history, storage, and options

The **outer** Responses request decides whether the hosted response is stored. The developer separately selects
who supplies the agent's model history:

| Entry point | `history_source` | Model history |
| --- | --- | --- |
| [main.py](main.py) | `"agent_server"` | The outer Responses transcript; the inner client runs with `store=False`. |
| [service_history.py](service_history.py) | `"service"` | Only new input goes to the model; its private `service_session_id` persists for later turns. |
| [agent_history.py](agent_history.py) | `"agent"` | This agent opts into `InMemoryHistoryProvider` with `default_options={"store": False}`; another `"agent"` configuration with `store=True` can use service history instead. |
| [options.py](options.py) | `"agent_server"` | The hook removes the caller's token limit so the agent default is used. |
| [provider_background.py](provider_background.py) | `"service"` | `background_source="provider"` opts into provider background with a private recovery token. |

For the same two stored requests—first **"My name is Ada"**, then **"What is my name?"** with the first
response's `previous_response_id`—the modes differ at the *model* boundary. `main.py` replays both
the first user message and the first assistant output before the follow-up. `service_history.py`
sends only the follow-up and privately resumes the service thread returned by the first call.
`agent_history.py` sends the follow-up plus earlier messages loaded from `InMemoryHistoryProvider`
inside the persisted MAF session. With `history_source="agent"`, the agent's storage default determines
whether it uses that provider or downstream service storage; the host does not force either one on
stored requests. In none of these cases is the caller's `response.id` the
downstream service ID.

Run one entry point at a time. The deployment manifest targets `main.py`; select another script to deploy a different
mode. Set `FOUNDRY_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME` in `.env`, then run `python main.py`.
Follow the [parent hosting guide](../../README.md) for local and deployed setup.

## Outer response storage and background

`store=True` makes a response retrievable at `GET /responses/{response.id}` and available for continuation using
`previous_response_id` or a `conversation`. For a local two-turn example, capture the `"id"` returned by the
first request and use it in the second; keep the same Foundry sandbox when deployed:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input": "My name is Ada", "store": true}'
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input": "What is my name?", "store": true, "previous_response_id": "REPLACE_WITH_FIRST_RESPONSE_ID"}'
```

The *same* outer request works with any of the three host entry points above; only the source of
inner model history changes. `store=True` does **not** choose inner history. With `store=False`, the response
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

`history_source="agent_server"` and `history_source="agent"` retain their existing meaning without a
deprecation warning. For **stored** requests, `"agent"` passes only new input to the agent, whose
developer-owned defaults may choose either a HistoryProvider **or downstream service storage**.
`history_source="service"` explicitly requires service-managed history and overrides the agent's
`store` default on stored requests. `store=` as a constructor parameter remains a deprecated alias
for `response_store=` (the outer storage *backend*, not the caller's `store` flag).
