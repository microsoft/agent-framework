# Using reasoning with Anthropic agents

This sample demonstrates how to use extended thinking/reasoning capabilities with Anthropic Claude agents.

## What this sample demonstrates

- Creating an AI agent with Anthropic Claude extended thinking
- Using reasoning capabilities for complex problem solving
- Extracting thinking and response content from agent output
- Managing agent lifecycle

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 8.0 SDK or later
- Anthropic API key configured
- Access to Anthropic Claude models with extended thinking support

**Note**: This sample uses Anthropic Claude models with extended thinking. For more information, see [Anthropic documentation](https://docs.anthropic.com/).

Set the following environment variables:

```powershell
$env:ANTHROPIC_API_KEY="your-anthropic-api-key"  # Replace with your Anthropic API key
$env:ANTHROPIC_MODEL="your-anthropic-model"  # Replace with your Anthropic model
```

## Run the sample

Navigate to the AgentWithAnthropic sample directory and run:

```powershell
cd dotnet\samples\GettingStarted\AgentWithAnthropic
dotnet run --project .\Agent_Anthropic_Step02_Reasoning
```

## Expected behavior

The sample will:

1. Create an agent with Anthropic Claude extended thinking enabled
2. Run the agent with a complex reasoning prompt
3. Display the agent's thinking process
4. Display the agent's final response

