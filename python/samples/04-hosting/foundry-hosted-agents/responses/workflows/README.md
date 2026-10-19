# Native Responses workflows

This sample hosts built Agent Framework workflows directly with
`ResponsesHostServer(workflow=..., parse_response=...)`; it does not wrap them
with `.as_agent()`.

- [`main.py`](main.py) parses a typed `SloganRequest`, builds fresh agents,
  clients, credentials, executors, and a graph for every hosted request, and
  keeps stable workflow/executor IDs so a later turn can restore its exact
  checkpoint.
- [`approval.py`](approval.py) pauses on an approval request and resumes only
  after the caller answers the complete pending reply batch. Its "publish"
  operation is deliberately simulated and makes no external change.

The Foundry sandbox (`agent_session_id`) is the trusted user-isolation boundary.
Responses `response.id`/`previous_response_id` select caller-visible turns
inside that sandbox. The MAF checkpoint ID is private workflow state and is
bound to the exact outer response; none of these IDs is a downstream model
`service_session_id`.

Use a request-aware factory for multi-turn workflows or pauses. A built
`Workflow` instance is single-use and is not cloned. Every factory invocation
must create fresh mutable resources, while workflow names and executor IDs
remain stable. `store=False` is one-shot and cannot expose a resumable pause.

Run locally from this directory with the current workspace:

```bash
uv run --no-sync python main.py
# or:
uv run --no-sync python approval.py
```

Example typed request:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input":"{\"topic\":\"an affordable electric SUV\",\"style\":\"retro\"}","store":true}'
```

An approval response uses the `id` of each returned
`mcp_approval_request`. Reusing an old, forged, duplicate, partial, cross-user,
or cross-sandbox reply is rejected.

For Foundry deployment instructions, see the
[parent README](../../README.md#deploying-the-agent-to-foundry).
