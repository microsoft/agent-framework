# Evaluation - Workflow Eval

This sample demonstrates evaluating a multi-agent workflow with per-agent breakdown.

## What this sample demonstrates

- Building a two-agent workflow (planner → executor)
- Running the workflow and collecting events
- Using `run.EvaluateAsync()` to evaluate the completed run
- Per-agent sub-results via `results.SubResults`
- Combining `FunctionEvaluator.Create` with `EvalChecks.KeywordCheck`

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
cd dotnet/samples/03-workflows/Evaluation
dotnet run --project .\Evaluation_WorkflowEval
```
