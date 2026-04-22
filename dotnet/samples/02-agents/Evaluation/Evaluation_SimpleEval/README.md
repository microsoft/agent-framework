# Evaluation - Simple Eval

The simplest agent evaluation: create a Foundry agent, run it against test questions, and use Foundry quality evaluators (Relevance, Coherence) to score the responses.

## What this sample demonstrates

- Creating an agent with `AIProjectClient.AsAIAgent()`
- Using `FoundryEvals` with Relevance and Coherence quality evaluators
- Running evaluation with `agent.EvaluateAsync()` — runs the agent and evaluates in one call

## Prerequisites

- .NET 10 SDK or later
- Azure CLI installed and authenticated (`az login`)
- A deployed model in your Azure AI Foundry project

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"
```

## Run the sample

```powershell
cd dotnet/samples/02-agents/Evaluation
dotnet run --project .\Evaluation_SimpleEval
```

## See also

- [Evaluation_CustomEvals](../Evaluation_CustomEvals/) — Writing custom domain-specific evaluation checks
- [Evaluation_ExpectedOutputs](../Evaluation_ExpectedOutputs/) — Evaluating against ground-truth expected outputs
- [Evaluation_MixedProviders](../../../05-end-to-end/Evaluation/Evaluation_MixedProviders/) — Combining local + Foundry evaluators in one call
