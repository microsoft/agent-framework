# Evaluation - Mixed Providers

This sample demonstrates mixing local and cloud evaluators in a single evaluation run.

## What this sample demonstrates

- **Local-only evaluation**: Fast, API-free checks for inner-loop development
- **Cloud-only evaluation**: Full Foundry evaluators for comprehensive quality assessment
- **Mixed evaluation**: Local + Foundry evaluators in a single `EvaluateAsync()` call
- Using `EvalChecks.KeywordCheck` and `EvalChecks.ToolCalledCheck` for local checks
- Using `FoundryEvals` for cloud-based relevance and coherence evaluation
- Combining both in one call returns one `AgentEvaluationResults` per provider

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
dotnet run --project .\Evaluation_MixedProviders
```