# Microsoft Agent Framework Workflows Orchestrations

Orchestrations are pre-built workflow patterns that allow developers to quickly create complex workflows by simply plugging in their own AI agents.

## Why Multi-Agent?

Traditional single-agent systems are limited in their ability to handle complex, multi-faceted tasks. By orchestrating multiple agents, each with specialized skills or roles, we can create systems that are more robust, adaptive, and capable of solving real-world problems collaboratively.

## Supported Orchestrations

| Pattern                       | Description                                                                                                                                                                         | Typical Use Case                                                      |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| [Concurrent](./concurrent.md) | Broadcasts a task to all agents, collects results independently.                                                                                                                    | Parallel analysis, independent subtasks, ensemble decision making.    |
| [Sequential](./sequential.md) | Passes the result from one agent to the next in a defined order.                                                                                                                    | Step-by-step workflows, pipelines, multi-stage processing.            |
| [Handoff](./handoff.md)       | Dynamically passes control between agents based on context or rules.                                                                                                                | Dynamic workflows, escalation, fallback, or expert handoff scenarios. |
| [Magentic](./magentic.md)     | Inspired by [MagenticOne](https://www.microsoft.com/en-us/research/articles/magentic-one-a-generalist-multi-agent-system-for-solving-complex-tasks/). | Complex, generalist multi-agent collaboration.                        |

## Next Steps

Explore the individual orchestration patterns to understand their unique features and how to use them effectively in your applications.
