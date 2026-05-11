# Evaluation - Workflow Expected Outputs

This sample demonstrates evaluating a multi-agent workflow's final answer
against a golden expected output using Foundry's reference-based **Similarity**
evaluator.

## What this sample demonstrates

- Building a small researcher → editor workflow
- Running the workflow and obtaining a `Run`
- Calling `run.EvaluateAsync(evaluator, expectedOutput: ...)` to attach a
  ground-truth answer to the overall workflow item
- Using `FoundryEvals.Similarity`, which requires a `ground_truth` value
  per item

The `expectedOutput` value is stamped onto the overall `EvalItem.ExpectedOutput`
and is surfaced to Foundry as `ground_truth` in the JSONL payload sent to the
Evals API.

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
dotnet run --project .\Evaluation_WorkflowExpectedOutputs
```
