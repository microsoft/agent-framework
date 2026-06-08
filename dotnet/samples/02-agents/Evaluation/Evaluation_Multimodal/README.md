# Evaluation - Multimodal

This sample demonstrates that the evaluation pipeline preserves multimodal content. When conversations include images, `EvalChecks.HasImageContent` can verify they survived into the `EvalItem`.

## What this sample demonstrates

- Building `EvalItem` objects with `UriContent` image content
- Using built-in `EvalChecks.HasImageContent` to detect images in conversations
- Comparing image vs. text-only conversations to show when the check passes/fails
- Evaluating directly with `LocalEvaluator.EvaluateAsync()` (no agent needed)

## Prerequisites

- .NET 10 SDK or later

No Azure credentials or environment variables are required for this sample since it evaluates locally without calling an agent.

## Run the sample

```powershell
cd dotnet/samples/02-agents/Evaluation
dotnet run --project .\Evaluation_Multimodal
```

## See also

- [Evaluation_SimpleEval](../Evaluation_SimpleEval/) — Simplest evaluation with built-in checks and `agent.EvaluateAsync()`
- [Evaluation_FoundryQuality](../../../05-end-to-end/Evaluation/Evaluation_FoundryQuality/) — Cloud-based quality evaluation with Foundry evaluators
- [Evaluation_ConversationSplits](../../../05-end-to-end/Evaluation/Evaluation_ConversationSplits/) — Multi-turn conversation split strategies
