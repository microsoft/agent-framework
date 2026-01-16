# Multi-Agent Orchestration with Conditionals

This sample demonstrates conditional orchestration logic with two agents that analyze incoming emails and route execution based on spam detection results.

## Key Concepts Demonstrated

- Multi-agent orchestration with two specialized agents (SpamDetectionAgent and EmailAssistantAgent).
- Conditional branching with different execution paths based on spam detection results.
- Structured outputs using Pydantic models with `options={"response_format": ...}` for type-safe agent responses.
- Activity functions for side effects (spam handling and email sending).
- Decision-based routing where orchestration logic branches on agent output.

## Environment Setup

See the [README.md](../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

## Running the Sample

With the environment setup, you can run the sample using the combined approach or separate worker and client processes:

**Option 1: Combined (Recommended for Testing)**

```bash
cd samples/getting_started/durabletask/06_multi_agent_orchestration_conditionals
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

The sample runs two test cases:

**Test 1: Legitimate Email**
```
Email ID: email-001
Email Content: Hello! I wanted to reach out about our upcoming project meeting...

🔍 SpamDetectionAgent: Analyzing email...
✓ Not spam - routing to EmailAssistantAgent

📧 EmailAssistantAgent: Drafting response...
✓ Email sent: [Professional response drafted by EmailAssistantAgent]
```

**Test 2: Spam Email**
```
Email ID: email-002
Email Content: URGENT! You've won $1,000,000! Click here now...

🔍 SpamDetectionAgent: Analyzing email...
⚠️ Spam detected: [Reason from SpamDetectionAgent]
✓ Email marked as spam and handled
```

## How It Works

1. **Input Validation**: Orchestration validates email payload using Pydantic models.
2. **Spam Detection**: SpamDetectionAgent analyzes email content.
3. **Conditional Routing**:
   - If spam: Calls `handle_spam_email` activity
   - If legitimate: Runs EmailAssistantAgent and calls `send_email` activity
4. **Result**: Returns confirmation message from the appropriate activity.

## Viewing Agent State

You can view the state of both agents and orchestration in the Durable Task Scheduler dashboard:

1. Open your browser and navigate to `http://localhost:8082`
2. In the dashboard, you can view:
   - Orchestration instance status and history
   - SpamDetectionAgent and EmailAssistantAgent entity states
   - Activity execution logs
   - Decision branch paths taken
