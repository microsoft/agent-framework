# Magentic Orchestration Sample

This sample showcases the Magentic Orchestration Pattern in .NET, setting up a team with three roles:

- **ResearcherAgent** gathers factual background information.
- **CoderAgent** uses `HostedCodeInterpreterTool` for quantitative analysis.
- **MagenticManager** plans the work, tracks progress, and decides who should act next.

## What This Sample Demonstrates

- Building a Magentic workflow with `MagenticWorkflowBuilder`
- Combining standard responses-based agents with a code interpreter-enabled participant
- Streaming orchestration events such as the initial plan, replans, and progress-ledger updates
- Printing the final multi-agent conversation transcript

## Prerequisites

- `FOUNDRY_PROJECT_ENDPOINT` set to your Azure AI Foundry project endpoint
- `FOUNDRY_MODEL` set to your model deployment name (defaults to `gpt-5.4-mini`)
- `az login` completed before running the sample

## Running the Sample

```bash
dotnet run
```

## Expected Output

The sample prints:

1. The original task prompt
2. Streamed updates from the participating agents
3. Magentic plan and progress-ledger events as the workflow coordinates the team
4. The final conversation transcript returned by the workflow

## Related Samples

- [Handoff Orchestration](../Handoff) - another multi-agent orchestration pattern in .NET workflows
- [Python Magentic workflow sample](../../../../../python/samples/03-workflows/orchestrations/magentic.py) - the source scenario that this sample ports
