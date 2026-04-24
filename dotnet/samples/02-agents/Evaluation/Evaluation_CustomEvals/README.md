# Evaluation - Custom Evals

This sample demonstrates writing custom domain-specific evaluation functions using `FunctionEvaluator.Create`. Custom evaluators run locally with no cloud evaluator service needed — useful for enforcing business rules, format requirements, or safety guardrails.

## What this sample demonstrates

- Writing custom checks with `FunctionEvaluator.Create` for domain-specific logic
- Checking that a customer support agent doesn't refuse to help
- Verifying responses contain actionable steps (numbered lists or bullet points)
- Enforcing response length constraints
- Combining multiple custom checks into a `LocalEvaluator`

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
dotnet run --project .\Evaluation_CustomEvals
```

## See also

- [Evaluation_SimpleEval](../Evaluation_SimpleEval/) — Simplest evaluation using Foundry quality evaluators (Relevance, Coherence)
- [Evaluation_ExpectedOutputs](../Evaluation_ExpectedOutputs/) — Evaluating against ground-truth expected outputs
- [Evaluation_MixedProviders](../../../05-end-to-end/Evaluation/Evaluation_MixedProviders/) — Combining custom + Foundry evaluators in one call
