---
status: proposed
date: 2026-11-09
deciders: ["@eavanvalkenburg"]
---

# Separate Foundry agent and native workflow hosts

## Context and Problem Statement

Foundry agent and native workflow hosting have different construction and state-ownership
contracts. A combined constructor advertises agent history and session settings to workflows,
and makes required workflow parsers appear optional. The
[decision in #10010](https://github.com/microsoft/agent-framework/issues/10010#issuecomment-6744873668)
selects separate hosts for Responses and Invocations.

## Considered Options

- Separate hosts: explicit execution models and required inputs, but more public entry points.
- Typed option groups: one host, but extra imports and configuration layers.
- Flat constructor: fewer entry points, but mode-dependent requirements and invalid combinations.

## Decision Outcome

Keep `ResponsesHostServer` and `InvocationsHostServer` for agents. Add
`ResponsesWorkflowHostServer` and `InvocationsWorkflowHostServer` for native workflows.
Require a request-aware workflow factory and an explicit `parse_input` callback.
Let the Responses workflow host own native execution directly, without a separate adapter object.
Share the Invocations implementation rather than duplicating its engine.
Group each protocol under `_responses_agent`, `_responses_workflow`, and `_responses_shared`,
with the same `_invocations_agent`, `_invocations_workflow`, and `_invocations_shared` layout.
Consolidate cross-protocol requests, options, and agent/workflow source resolution in `_shared`.
Keep scope, storage, and workflow-state ownership in their purpose-named modules.

The release-candidate branch permits a breaking constructor migration without a combined-host shim.
Use `parse_input` consistently for Responses workflow parsers and Invocations agent/workflow parsers.
Rename the Responses request wrapper to `ResponsesRequest`, including factory and option-hook annotations.
These are the naming choices approved for [#10014](https://github.com/microsoft/agent-framework/issues/10014);
the old parser keywords and request-type name have no aliases. Workflow parsers continue to return
`WorkflowTurn` for typed start input or complete validated pending replies.

Include the [#10015](https://github.com/microsoft/agent-framework/issues/10015) source-literal renames:
`agent_server` becomes `host_managed`, history `agent` becomes `agent_managed`, and history `service`
and background `provider` become `inference_service`. Keep the defaults' meaning, history ownership,
supported inference-service background execution, and outer/inner storage behavior unchanged.
`agent_managed` includes developer-owned service storage, not just a history provider.
Include [#10018](https://github.com/microsoft/agent-framework/issues/10018) by removing the constructor
`store=` backend alias and rejecting it before SDK construction, even when its value is `None`.
Keep `response_store=` and per-request wire `store` unchanged. This consolidates the overlapping
#10015/#10018 work from #10187 into the host split rather than replaying it across moved modules.

Keep SDK options, agent approval stores, wire formats, and storage semantics unchanged.
Workflow hosts expose checkpoint storage rather than agent-session or agent history settings.
Agent hosts reject `WorkflowAgent` instances and factory results; workflow hosts reject agent results.
Checkpoint storage is available only on workflow hosts. There is no deprecated wrapper-hosting path.

The narrowly coupled [#7688](https://github.com/microsoft/agent-framework/issues/7688)
construction change rejects built workflow instances, including local one-shot hosting.
Factories must allocate isolated execution resources, not just new wrappers around shared executors.
Reuse the existing identity guard; it does not prove that arbitrary application globals are isolated.
No new concurrency, checkpoint, retry, routing, or external exactly-once guarantee is introduced.

All hosts stay in one package. Responses remains the initial stable-surface target;
Invocations and Toolbox retain their experimental boundary. Other hosting policy changes
remain separate work.
