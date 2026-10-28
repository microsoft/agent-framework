# Community projects for Agent Framework Python

This page lists published, community-maintained projects that integrate with
the Agent Framework Python SDK. Entries are reviewed against the
[community project catalog criteria](../../.github/skills/community-projects/SKILL.md).

> [!IMPORTANT]
> The projects on this page are created and maintained outside the Microsoft
> Agent Framework team. Microsoft doesn't own, test, or support these projects.
> Listing a project doesn't imply Microsoft endorsement or confirm compatibility
> with any Agent Framework version. For compatibility information, support, and
> issue handling, contact the project maintainer through the project's
> repository and issue tracker.
> For security concerns, follow the maintainer's security reporting guidance.

## Tools

| Name | Brief description | Scenarios | Project | Issues |
| --- | --- | --- | --- | --- |
| Engram | Durable memory tools with optional middleware for Agent Framework agents. | Explicit cross-session memory recall and persistence; automatic recall and capture | [agent-framework-engram](https://github.com/lumetra-io/engram-agent-framework) | [Open an issue](https://github.com/lumetra-io/engram-agent-framework/issues/new/choose) |

## Context providers

| Name | Brief description | Scenarios | Project | Issues |
| --- | --- | --- | --- | --- |
| Membase | A context provider that recalls a user's Membase memory before agent runs, with function tools to search and save memories. | Per-user cross-session memory; time-boxed instruction-layer recall; explicit memory search and save tools | [agent-framework-membase](https://github.com/unibaseio/membase/tree/main/integrations/agent-framework) | [Open an issue](https://github.com/unibaseio/membase/issues/new) |
| MemorySync | A context provider that recalls and captures user memory around agent runs. | Per-user cross-session memory; instruction-layer recall; automatic fact capture | [agent-framework-memorysync](https://pypi.org/project/agent-framework-memorysync/) | [Open an issue](https://github.com/memorysyncio/memorysync-plugins/issues/new/choose) |
| OpenViking | A context database that gives agents searchable context across runs (40K+ GitHub stars). | Pre-run context retrieval; conversation and tool-call capture; explicit memory extraction | [OpenViking integration](https://github.com/volcengine/OpenViking/tree/main/integrations/frameworks/microsoft-agent-framework) | [Open an issue](https://github.com/volcengine/OpenViking/issues/new/choose) |

## Middleware

| Name | Brief description | Scenarios | Project | Issues |
| --- | --- | --- | --- | --- |
| ACGS | Function middleware that checks each function call's name and arguments against an ACGS rule set before it runs, and requests tool approval when a rule calls for review. | Block function calls by rule; human review of flagged calls through tool approvals; refuse runs that offer tools the middleware cannot check | [agent-framework-acgs](https://github.com/acgs-ai/agent-framework-acgs) | [Open an issue](https://github.com/acgs-ai/agent-framework-acgs/issues/new) |
| BotsRated | Function middleware that checks the payTo of an x402 payment tool call against the payTo addresses BotsRated observed for that seller, and stops the call before it runs when that payTo was not observed. | Block payments to a payTo the seller was not observed using; let the model check a payment option with a function tool | [agent-framework-botsrated](https://github.com/botsrated/botsrated/tree/main/integrations/microsoft-agent-framework) | [Open an issue](https://github.com/botsrated/botsrated/issues/new) |
| Tracekit | Function middleware that checks each function call against a policy before it runs and records calls and results in a signed, hash-chained log. | Allow or deny function calls by policy; human approval of held calls; offline-verifiable run records | [tracekit-ai](https://github.com/Cygnux-Labs/Tracekit/blob/main/docs/integrations/microsoft-agent-framework.md) | [Open an issue](https://github.com/Cygnux-Labs/Tracekit/issues/new/choose) |
