# Native declarative customer-support workflow

[`workflow.yaml`](workflow.yaml) defines a multi-turn customer-support flow
using `InvokeAzureAgent`, `ConditionGroup`, `SendActivity`, and Power Fx
expressions. [`main.py`](main.py) hosts the built declarative `Workflow`
directly through `ResponsesHostServer(workflow=..., parse_response=...)`.

The parser uses the explicit `response_input_messages()` migration helper for
the declarative workflow's `list[Message]` start contract. The host restores the
exact scoped MAF checkpoint first; it does not silently unwrap a
`WorkflowAgent`, rebuild outer Responses history as workflow state, or reuse a
downstream service session.

Every request-aware factory call creates fresh agents, Foundry clients,
credentials, and a fresh graph while the stable IDs in `workflow.yaml` preserve
checkpoint compatibility. Start a fresh Responses chain when migrating from
the legacy `.as_agent()` hosting path because old unscoped checkpoints are not
safe across Foundry sandboxes.

Example:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input":"I was double-charged this month","store":true}'
```

> [!IMPORTANT]
> Deploy this sample as a **container**. The `powerfx` dependency requires the
> .NET runtime copied by the provided `Dockerfile`. This PR does not install or
> deploy that runtime during validation.

For Foundry deployment instructions, see the
[parent README](../../README.md#deploying-the-agent-to-foundry).
