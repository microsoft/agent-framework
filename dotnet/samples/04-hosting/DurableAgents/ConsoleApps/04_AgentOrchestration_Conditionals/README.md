# Multi-Agent Conditional Orchestration Sample

This sample demonstrates how to use the durable agents extension to create a console app that orchestrates multiple AI agents with conditional logic based on the results of previous agent interactions.

## Key Concepts Demonstrated

- Multi-agent orchestration with conditional branching
- Using agent responses to determine workflow paths
- Activity functions for non-agent operations
- Waiting for orchestration completion using `WaitForInstanceCompletionAsync`

## Environment Setup

See the [README.md](../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

## Running the Sample

With the environment setup, you can run the sample:

```bash
cd dotnet/samples/04-hosting/DurableAgents/ConsoleApps/04_AgentOrchestration_Conditionals
dotnet run --framework net10.0
```

The app will prompt you for email content. You can test both legitimate emails and spam emails:

### Testing with a Legitimate Email

```text
=== Multi-Agent Conditional Orchestration Sample ===
Enter email content:

Hi John, I hope you're doing well. I wanted to follow up on our meeting yesterday about the quarterly report. Could you please send me the updated figures by Friday? Thanks!
```

The orchestration will analyze the email and display the result:

```text
Orchestration started with instance ID: 86313f1d45fb42eeb50b1852626bf3ff
Waiting for completion...

✓ Orchestration completed successfully!

Result: Email sent: Thank you for your email. I'll prepare the updated figures...
```

### Testing with a Spam Email

```text
=== Multi-Agent Conditional Orchestration Sample ===
Enter email content:

URGENT! You've won $1,000,000! Click here now to claim your prize! Limited time offer! Don't miss out!
```

The orchestration will detect it as spam and display:

```text
Orchestration started with instance ID: 86313f1d45fb42eeb50b1852626bf3ff
Waiting for completion...

✓ Orchestration completed successfully!

Result: Email marked as spam: Contains suspicious claims about winning money and urgent action requests...
```

## Scriptable Usage

You can also pipe email content to the app:

```bash
# Test with a legitimate email
echo "Hi John, I hope you're doing well..." | dotnet run

# Test with a spam email
echo "URGENT! You've won $1,000,000! Click here now!" | dotnet run
```

The orchestration will proceed as follows:

1. The SpamDetectionAgent analyzes the email to determine if it's spam
2. Based on the result:
   - If spam: The orchestration calls the `HandleSpamEmail` activity function
   - If not spam: The EmailAssistantAgent drafts a response, then the `SendEmail` activity function is called

## Viewing Orchestration State

You can view the state of the orchestration in the Durable Task Scheduler dashboard:

1. Open your browser and navigate to `http://localhost:8082`
2. In the dashboard, you can see:
   - **Orchestrations**: View the orchestration instance, including its runtime status, input, output, and execution history
   - **Agents**: View the state of both the SpamDetectionAgent and EmailAssistantAgent

The orchestration instance ID is displayed in the console output. You can use this ID to find the specific orchestration in the dashboard and inspect the conditional branching logic, including which path was taken based on the spam detection result.
