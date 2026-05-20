# Evaluation - Expected Outputs

This sample demonstrates evaluating agent responses against expected outputs using built-in checks.

## What this sample demonstrates

- Using `EvalChecks.ContainsExpected` for ground-truth comparison
- Using `EvalChecks.NonEmpty` for basic response validation
- Passing `expectedOutput` to `agent.EvaluateAsync()` so checks can access ground truth

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
cd dotnet/samples/02-agents/Evaluation
dotnet run --project .\Evaluation_ExpectedOutputs
```

## See also

- [Evaluation_SimpleEval](../Evaluation_SimpleEval/) — Simplest evaluation with built-in and custom checks
- [Evaluation_FoundryQuality](../../../05-end-to-end/Evaluation/Evaluation_FoundryQuality/) — Cloud-based quality evaluation with Foundry evaluators
