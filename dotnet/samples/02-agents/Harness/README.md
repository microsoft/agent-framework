# Harness Agent Samples

Samples demonstrating the [Harness AIContextProviders](../../../src/Microsoft.Agents.AI/Harness/) — reusable providers that add planning, task management, and mode tracking to any `ChatClientAgent`.

## Samples

| Sample | Description |
| --- | --- |
| [Harness_Step01_Research](./Harness_Step01_Research/README.md) | Using a ChatClientAgent with TodoProvider and AgentModeProvider for research, showcasing planning mode and todo management |
| [Harness_Step02_Research_WithBackgroundAgents](./Harness_Step02_Research_WithBackgroundAgents/README.md) | Using BackgroundAgentsProvider to delegate stock price lookups to a web-search background agent concurrently |
| [Harness_Step03_DataProcessing](./Harness_Step03_DataProcessing/README.md) | Using FileAccessProvider to give an agent access to CSV data files for reading, analysis, and output generation |
| [Harness_Step05_Loop](./Harness_Step05_Loop/README.md) | Wrapping a HarnessAgent with the LoopAgent decorator to re-invoke it until a configured LoopEvaluator (completion marker, predicate, AI judge, or approval-aware loop) decides to stop |

## Build your own claw blog series

Samples accompanying the [*Build your own agent harness or claw with Microsoft Agent Framework*](https://devblogs.microsoft.com/agent-framework/build-your-own-claw-and-agent-harness-with-microsoft-agent-framework) blog series, which builds a personal finance assistant step by step.

| Sample | Description |
| --- | --- |
| [Claw_Step01_MeetYourClaw](./BuildYourOwnClaw/Claw_Step01_MeetYourClaw/README.md) | Post 1 — a minimal HarnessAgent with a custom `get_stock_price` tool, web search, and planning |
| [Claw_Step02_WorkingWithData](./BuildYourOwnClaw/Claw_Step02_WorkingWithData/README.md) | Post 2 — file access, approvals, and durable memory (file memory plus optional Foundry memory) |
