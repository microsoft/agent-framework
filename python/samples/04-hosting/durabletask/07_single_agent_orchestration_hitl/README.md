# Single-Agent Orchestration with Human-in-the-Loop (HITL)

This sample demonstrates the human-in-the-loop pattern where a WriterAgent generates content and waits for human approval before publishing. The orchestration handles external events, timeouts, and iterative refinement based on feedback.

## Key Concepts Demonstrated

- Human-in-the-loop workflow with orchestration pausing for external approval/rejection events.
- External event handling using `wait_for_external_event()` to receive human input.
- Timeout management with `when_any()` to race between approval event and timeout.
- Iterative refinement where agent regenerates content based on reviewer feedback.
- Structured outputs using Pydantic models with `options={"response_format": ...}` for type-safe agent responses.
- Activity functions for notifications and publishing as separate side effects.
- Long-running orchestrations maintaining state across multiple interactions.

## Environment Setup

See the [README.md](../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

## Running the Sample

With the environment setup, you can run the sample using the combined approach or separate worker and client processes:

**Option 1: Combined (Recommended for Testing)**

```bash
cd samples/getting_started/durabletask/07_single_agent_orchestration_hitl
python sample.py
```

**Option 2: Separate Processes**

Start the worker in one terminal:

```bash
python worker.py
```

In a new terminal, run the client:

```bash
python client.py
```

The sample runs two test scenarios:

**Test 1: Immediate Approval**
```
Topic: The benefits of cloud computing
[WriterAgent generates content]
[Notification sent: Please review the content]
[Client sends approval]
✓ Content published successfully
```

**Test 2: Rejection with Feedback, Then Approval**
```
Topic: The future of artificial intelligence
[WriterAgent generates initial content]
[Notification sent: Please review the content]
[Client sends rejection with feedback: "Make it more technical..."]
[WriterAgent regenerates content with feedback]
[Notification sent: Please review the revised content]
[Client sends approval]
✓ Revised content published successfully
```

## How It Works

1. **Initial Generation**: WriterAgent creates content based on the topic.
2. **Review Loop** (up to max_review_attempts):
   - Activity notifies user for approval
   - Orchestration waits for approval event OR timeout
   - **If approved**: Publishes content and returns
   - **If rejected**: Incorporates feedback and regenerates
   - **If timeout**: Raises TimeoutError
3. **Completion**: Returns published content or error.

## Viewing Agent State

You can view the state of the WriterAgent and orchestration in the Durable Task Scheduler dashboard:

1. Open your browser and navigate to `http://localhost:8082`
2. In the dashboard, you can view:
   - Orchestration instance status and pending events
   - WriterAgent entity state and conversation threads
   - Activity execution logs
   - External event history
