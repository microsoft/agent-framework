# Evaluation - Conversation Splits

This sample demonstrates multi-turn conversation evaluation with different split strategies.

## What this sample demonstrates

- **LastTurn** (default): Evaluates whether the last response was good given all prior context
- **Full**: Evaluates whether the entire conversation trajectory served the original request
- **PerTurnItems**: Splits a conversation into one `EvalItem` per user turn for independent evaluation
- Building multi-turn conversations with `FunctionCallContent` and `FunctionResultContent`
- Using `ConversationSplitters.LastTurn` and `ConversationSplitters.Full`
- Using `EvalItem.PerTurnItems()` to decompose a conversation

## Prerequisites

- .NET 10 SDK or later
- Azure CLI installed and authenticated (`az login`)

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"
```

## Run the sample

```powershell
cd dotnet/samples/05-end-to-end/Evaluation
dotnet run --project .\Evaluation_ConversationSplits
```