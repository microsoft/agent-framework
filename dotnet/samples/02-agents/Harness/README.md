# Harness Agent Samples

Samples demonstrating the [Harness AIContextProviders](../../../src/Microsoft.Agents.AI/Harness/) — reusable providers that add planning, task management, and mode tracking to any `ChatClientAgent`.

## Samples

| Sample | Description |
| --- | --- |
| [Harness_Step01_Research](./Harness_Step01_Research/README.md) | Using a ChatClientAgent with TodoProvider and AgentModeProvider for research, showcasing planning mode and todo management |
| [Harness_Step02_Research_WithBackgroundAgents](./Harness_Step02_Research_WithBackgroundAgents/README.md) | Using BackgroundAgentsProvider to delegate stock price lookups to a web-search background agent concurrently |
| [Harness_Step03_DataProcessing](./Harness_Step03_DataProcessing/README.md) | Using FileAccessProvider to give an agent access to CSV data files for reading, analysis, and output generation |

## Related samples

| Sample | What it adds |
| --- | --- |
| [SquadWithDTS](../SquadWithDTS/README.md) | Shows how to wrap **GitHub Copilot Squad** as a first-class MAF `AIAgent` and compose it with a DTS-backed durable workflow. Compare `HarnessAgent.ToolApproval` (session-scoped) with Squad's charter-bounded `OnPermissionRequest` governance pattern. |
