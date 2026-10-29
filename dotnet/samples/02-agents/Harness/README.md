# Harness Agent Samples

Samples demonstrating the [Harness AIContextProviders](../../../src/Microsoft.Agents.AI/Harness/) — reusable providers that add planning, task management, and mode tracking to any `ChatClientAgent`.

## Samples

| Sample | Description |
| --- | --- |
| [Harness_Step01_Research](./Harness_Step01_Research/README.md) | Using a ChatClientAgent with TodoProvider and AgentModeProvider for research, showcasing planning mode and todo management |
| [Harness_Step02_Research_WithBackgroundAgents](./Harness_Step02_Research_WithBackgroundAgents/README.md) | Using BackgroundAgentsProvider to delegate stock price lookups to a web-search background agent concurrently |
| [Harness_Step03_DataProcessing](./Harness_Step03_DataProcessing/README.md) | Using FileAccessProvider to give an agent access to CSV data files for reading, analysis, and output generation |
| [Harness_Step05_Loop](./Harness_Step05_Loop/README.md) | Wrapping a HarnessAgent with the LoopAgent decorator to re-invoke it until a configured LoopEvaluator (completion marker, predicate, AI judge, or approval-aware loop) decides to stop |

## Choose the model API before configuring reasoning

`AsHarnessAgent` uses the `IChatClient` you supply. That interface does not select
an HTTP API: the underlying client determines whether requests use Chat Completions
or Responses. Setting `ChatOptions.Reasoning` does not switch between them.

For example, the Aspire Azure OpenAI `AddChatClient(deploymentName)` registration
in [issue #8429](https://github.com/microsoft/agent-framework/issues/8429) sends
Chat Completions requests. If the service rejects reasoning together with function
tools on that API, changing harness instructions will not resolve the rejection.
Use a Responses client supported by your endpoint and SDK, or a reasoning/tool
combination supported by the API you selected.

These samples use a **Foundry project endpoint** and explicitly select Responses.
The client construction in [Harness_Step01_Research](./Harness_Step01_Research/Program.cs)
follows this sequence:

```csharp
// projectClient is an Azure.AI.Projects.AIProjectClient configured for your Foundry project.
IChatClient chatClient = projectClient.GetProjectOpenAIClient()
    .GetResponsesClient()
    .AsIChatClient(deploymentName);
```

`IChatClient` and `AsIChatClient` use the `Microsoft.Extensions.AI` namespace.
See the linked sample for its package references, authentication, and complete setup.
`FOUNDRY_PROJECT_ENDPOINT` is a project endpoint, not an Azure OpenAI resource
endpoint; do not substitute one for the other.

Applications using an `AzureOpenAIClient` registered by Aspire must also verify
that their installed Azure SDK and Aspire versions support Responses for their
resource endpoint. The compatibility problems linked from #8429 are tracked in
[#7484](https://github.com/microsoft/agent-framework/issues/7484),
[Aspire #20175](https://github.com/microsoft/aspire/issues/20175), and
[Azure SDK #60689](https://github.com/Azure/azure-sdk-for-net/issues/60689).
The Foundry project sample above does not establish that those resource-client
paths work with every package version.

## Build your own claw blog series

Samples accompanying the [*Build your own agent harness or claw with Microsoft Agent Framework*](https://devblogs.microsoft.com/agent-framework/build-your-own-claw-and-agent-harness-with-microsoft-agent-framework) blog series, which builds a personal finance assistant step by step.

| Sample | Description |
| --- | --- |
| [Claw_Step01_MeetYourClaw](./BuildYourOwnClaw/Claw_Step01_MeetYourClaw/README.md) | Post 1 — a minimal HarnessAgent with a custom `get_stock_price` tool, web search, and planning |
| [Claw_Step02_WorkingWithData](./BuildYourOwnClaw/Claw_Step02_WorkingWithData/README.md) | Post 2 — file access, approvals, and durable memory (file memory plus optional Foundry memory) |
| [Claw_Step03_ScalingCapabilities](./BuildYourOwnClaw/Claw_Step03_ScalingCapabilities/README.md) | Post 3 — scaling the claw with skills (plus optional Foundry skills), a confined shell, CodeAct, and background agents |
| [Claw_Step04_ProductionReady](./BuildYourOwnClaw/Claw_Step04_ProductionReady/README.md) | Post 4 — production-ready shared claw library with observability, opt-in Purview governance, Foundry hosted deployment, and evals |

## Security Considerations

Several harness providers extend the agent's trust boundary to external systems the developer
configures — see the security notes in the individual sample READMEs (and the XML docs on the
corresponding types) before enabling them in production:
- **`BackgroundAgentsProvider`** — delegates work to developer-supplied agents (see
  [Harness_Step02_Research_WithBackgroundAgents](./Harness_Step02_Research_WithBackgroundAgents/README.md)).
- **`AIJudgeLoopEvaluator`** (used by `LoopAgent`) — sends conversation content to a second, external
  judge chat client (see [Harness_Step05_Loop](./Harness_Step05_Loop/README.md)).
- **`AgentSkillsProvider`** with external skill sources (e.g. `UseMcpSkills`) — loads skill content,
  and potentially scripts, from a remote source (see
  [AgentSkills samples](../AgentSkills/Agent_Step06_McpBasedSkills/README.md)).
- **`SummarizationCompactionStrategy`** — used for in-loop context compaction via
  `HarnessAgentOptions.CompactionStrategy`, calls out to an LLM whose output becomes permanent chat
  history (see [Agent_Step18_CompactionPipeline](../Agents/Agent_Step18_CompactionPipeline/README.md)).

In every case, the capability is opt-in and requires explicit configuration by the developer, who is
responsible for vetting the external service, agent, skill source, or provider before enabling it.
