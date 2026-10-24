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
| MemorySync | A context provider that recalls and captures user memory around agent runs. | Per-user cross-session memory; instruction-layer recall; automatic fact capture | [agent-framework-memorysync](https://pypi.org/project/agent-framework-memorysync/) | [Open an issue](https://github.com/memorysyncio/memorysync-plugins/issues/new/choose) |

## Middleware

| Name | Brief description | Scenarios | Project | Issues |
| --- | --- | --- | --- | --- |
| ACGS | Function middleware that checks each function call's name and arguments against an ACGS rule set before it runs, and requests tool approval when a rule calls for review. | Block function calls by rule; human review of flagged calls through tool approvals; refuse runs that offer tools the middleware cannot check | [agent-framework-acgs](https://github.com/acgs-ai/agent-framework-acgs) | [Open an issue](https://github.com/acgs-ai/agent-framework-acgs/issues/new) |
| Tracekit | Function middleware that checks each function call against a policy before it runs and records calls and results in a signed, hash-chained log. | Allow or deny function calls by policy; human approval of held calls; offline-verifiable run records | [tracekit-ai](https://github.com/Cygnux-Labs/Tracekit/blob/main/docs/integrations/microsoft-agent-framework.md) | [Open an issue](https://github.com/Cygnux-Labs/Tracekit/issues/new/choose) |
