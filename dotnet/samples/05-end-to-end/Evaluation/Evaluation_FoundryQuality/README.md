# Evaluation - Foundry Quality

This sample demonstrates agent evaluation using MEAI quality evaluators (Relevance, Coherence) via `FoundryEvals`.

## What this sample demonstrates

- Setting up `ChatConfiguration` for MEAI quality evaluators
- Using `FoundryEvals` with `Relevance` and `Coherence` evaluators
- Pattern 1: Running the agent first, then evaluating pre-existing responses
- Pattern 2: Running and evaluating in a single `agent.EvaluateAsync()` call
- Reading numeric quality scores from evaluation results

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
dotnet run --project .\Evaluation_FoundryQuality
```
