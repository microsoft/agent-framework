# Evaluation — Foundry Rubric

This sample evaluates a pre-existing Azure AI Foundry agent against a **rubric evaluator**
authored in the Foundry portal. Rubric evaluators are LLM-as-judge evaluators with custom
scoring dimensions you define for your domain; agent-framework references them by name and
version, mixes them with built-in evaluators, and exposes per-dimension scores you can gate
CI on.

## What this sample demonstrates

- Connecting to a pre-existing Foundry agent (`AgentAdministrationClient.GetAgentAsync`).
- Referencing a pre-existing rubric evaluator via `GeneratedEvaluatorRef(name, version)`.
- Mixing the rubric with built-in evaluators (`Relevance`, `Coherence`) in one
  `FoundryEvals` run.
- Reading per-dimension breakdowns from `EvalScoreResult.Dimensions`.
- Gating CI on a per-dimension threshold via
  `AgentEvaluationResults.AssertDimensionScoreAtLeast(...)`.

## Prerequisites

- .NET 10 SDK or later.
- Azure CLI installed and authenticated (`az login`).
- An Azure AI Foundry project with a deployed model.
- A registered Foundry agent in that project (the agent the rubric was created against).
- A rubric evaluator created in the Foundry portal. Creating rubrics through the portal
  currently requires picking a Foundry agent as the generation context, so this
  prerequisite is implied by having a rubric at all.

> [!IMPORTANT]
> `FOUNDRY_PROJECT_ENDPOINT` **must** be the project-scoped URL
> `https://<resource>.services.ai.azure.com/api/projects/<project>`. A bare Azure OpenAI
> endpoint silently fails eval submission with HTTP 500.

> [!NOTE]
> An **Eval Definition** (a saved bundle of testing_criteria with `"object": "eval"`) is
> not the same as a **Rubric Evaluator** (a standalone evaluator with dimensions, weights,
> and a version). `GeneratedEvaluatorRef` points at the latter.

## Environment variables

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-resource.services.ai.azure.com/api/projects/your-project"
$env:FOUNDRY_MODEL="gpt-4o-mini"
$env:FOUNDRY_AGENT_NAME="your-agent-name"
$env:FOUNDRY_AGENT_VERSION="1"                   # optional; omit for latest
$env:FOUNDRY_RUBRIC_NAME="your-rubric-name"
$env:FOUNDRY_RUBRIC_VERSION="1"                  # optional; omit for latest (CI: pin this)
```

## Run the sample

```powershell
cd dotnet/samples/05-end-to-end/Evaluation
dotnet run --project .\Evaluation_FoundryRubric
```
