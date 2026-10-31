# Jev as the judge of a loop

This sample uses `JevChatClient` from `Microsoft.Agents.AI.TypeSafe` as the judge of a `LoopAgent`. A Foundry agent
writes the answer, and Jev, the TypeSafe System One model, decides whether the answer is complete.

A generative judge writes a verdict and a gap analysis. Jev writes no text, so the sample asks it one `JevNoulQuestion`
per criterion instead. Each answer is the probability, from 0 to 1, that the answer meets that criterion, so the judge
reports exactly which criteria are missing:

```text
Judge:
  blue_sky: met (probability 0.99)
  red_sunsets: missing (probability 0.02)
  plain_language: met (probability 0.92)
```

The loop turns the missing criteria into the feedback for the next run, and stops when every criterion is met or after
three runs. The agent's instructions hold back part of the first answer on purpose, so the loop visibly runs twice.

`LoopAgent` checks `MaxIterations` before it calls the evaluator, so when the loop reaches its limit, the answer of the
last run has not been judged. The sample judges that answer after the loop and labels the final answer when some
criteria are still missing, instead of presenting it as accepted.

## Why a delegate evaluator

`AIJudgeLoopEvaluator` asks its chat client for a `JudgeVerdict` as JSON structured output, which Jev cannot write;
`JevChatClient` rejects the JSON response format with a `NotSupportedException`. The sample wraps the judge in a
`DelegateLoopEvaluator` instead:

```csharp
var evaluator = new DelegateLoopEvaluator(async (context, cancellationToken) =>
{
    List<string> missing = await JudgeAsync(context.InitialMessages, context.LastResponse.Text, cancellationToken);
    accepted = missing.Count == 0;
    return accepted
        ? LoopEvaluation.Stop()
        : LoopEvaluation.Continue($"Your answer does not yet: {string.Join("; ", missing)}. ...");
});
```

`JudgeAsync` sends Jev the original request and the answer as a conversation, with
`new ChatOptions().WithJevQuestions(questions)`, and returns the criteria whose Noul is at or below
`CriterionThreshold`.

Jev reads the original request and the latest answer as a conversation, and each question refers to "the assistant's
latest response". The same pattern works with a `JevScoreQuestion` for a graded rubric, or a `JevChoiceQuestion` to
classify what kind of revision is needed.

## Writing criteria for a judge

- **Choose the threshold on your own data.** The sample treats a criterion as met when its probability is above
  `CriterionThreshold`, which is 0.5. That value is not calibrated for any task. The threshold trades two errors
  against each other: a higher value accepts fewer answers that still miss a criterion, and costs more loop runs, while
  a lower value stops sooner and lets more incomplete answers through. Pick it from labeled examples of the answers your
  agent writes, based on which error costs you more.
- **Describe the criterion, do not steer the judge.** Ask what a good answer contains, as the sample does ("Does the
  assistant's latest response explain why sunsets appear red?"). Directional wording such as "only say yes if" or
  "lean towards yes" tends to push every answer the same way instead of making the judge more accurate. When a
  criterion is hard to judge, a neutral description of what is being judged helps more than stronger wording.
- **Ask about the response, not the topic.** When the conversation contains harmful or sensitive content, a question
  such as "Is this safe?" can be read as a question about that content rather than about the answer. A correct
  refusal could then look like a missing criterion, and the loop would keep revising an answer that was already right.
  Ask how the response handles the request, for example "Does the assistant's latest response decline to give
  dangerous instructions?", and check such criteria on labeled examples, including refusals, before relying on them.

## Prerequisites

- .NET 10 SDK or later
- A Microsoft Foundry project with a deployed chat model
- Azure CLI installed and authenticated (`az login`)
- A TypeSafe API key

Set the environment variables:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:FOUNDRY_MODEL="gpt-5.4-mini"   # Optional, defaults to gpt-5.4-mini
$env:TYPESAFE_API_KEY="your-typesafe-api-key"
```

## Running the sample

```powershell
dotnet run
```

The sample prints each answer with the judge's probabilities, then the final answer, labeled when some criteria are
still missing. The wording of the answers and the exact probabilities vary between runs.
