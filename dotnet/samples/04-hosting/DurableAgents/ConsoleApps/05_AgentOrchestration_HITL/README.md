# Human-in-the-Loop Orchestration Sample

This sample demonstrates how to use the durable agents extension to create a console app that implements a human-in-the-loop workflow using durable orchestration, including interactive approval prompts.

## Key Concepts Demonstrated

- Human-in-the-loop workflows with durable orchestration
- External event handling for human approval/rejection
- Timeout handling for approval requests
- Iterative content refinement based on human feedback

## Environment Setup

See the [README.md](../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

## Running the Sample

With the environment setup, you can run the sample:

```bash
cd dotnet/samples/04-hosting/DurableAgents/ConsoleApps/05_AgentOrchestration_HITL
dotnet run --framework net10.0
```

The app will prompt you for input:

```text
=== Human-in-the-Loop Orchestration Sample ===
Enter topic for content generation:

The Future of Artificial Intelligence

Max review attempts (default: 3):
3
Approval timeout in hours (default: 72):
72
```

The orchestration will generate content and prompt you for approval:

```text
Orchestration started with instance ID: 86313f1d45fb42eeb50b1852626bf3ff

=== NOTIFICATION: Content Ready for Review ===
Title: The Future of Artificial Intelligence

Content:
[Generated content appears here]

Please review the content above and provide your approval.

Content is ready for review. Check the logs above for details.
Approve? (y/n): n
Feedback (optional): Please add more details about the ethical implications.
```

The orchestration will incorporate your feedback and regenerate the content. Once approved, it will publish and complete.

## Viewing Orchestration State

You can view the state of the orchestration in the Durable Task Scheduler dashboard:

1. Open your browser and navigate to `http://localhost:8082`
2. In the dashboard, you can see:
   - **Orchestrations**: View the orchestration instance, including its runtime status, custom status (which shows approval state), input, output, and execution history
   - **Agents**: View the state of the WriterAgent, including conversation history

The orchestration instance ID is displayed in the console output. You can use this ID to find the specific orchestration in the dashboard and inspect:

- The custom status field, which shows the current state of the approval workflow
- When the orchestration is waiting for external events
- The iteration count and feedback history
- The final published content
