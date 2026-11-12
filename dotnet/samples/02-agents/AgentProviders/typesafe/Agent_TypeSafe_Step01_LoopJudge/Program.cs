// Copyright (c) Microsoft. All rights reserved.

// This sample uses Jev, the TypeSafe System One model, as the judge of a LoopAgent. A Foundry agent writes the
// answer. After each answer, Jev checks every criterion with its own yes or no question, and the loop sends the agent
// the criteria that are still missing, until the answer meets all of them. The judge uses the decision API proposed
// for Microsoft.Extensions.AI: an IDecisionClient and a typed DecisionDefinition.

#pragma warning disable MAAI001 // LoopAgent and DelegateLoopEvaluator are experimental.
#pragma warning disable MEAI001 // The decision API is experimental.

using System.ClientModel;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.TypeSafe;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";
var typeSafeApiKey = Environment.GetEnvironmentVariable("TYPESAFE_API_KEY") ?? throw new InvalidOperationException("TYPESAFE_API_KEY is not set.");

// 1. The criteria, as a typed verdict. Each property is a Binary question, whose answer is the probability that the
// answer meets the criterion, so the judge reports exactly which criteria are missing instead of a single verdict. The
// questions describe what a good answer contains; wording that steers the judge, such as "only say yes if", tends to
// push every answer one way.
DecisionDefinition<Verdict> criteria = DecisionDefinition<Verdict>.Create(builder =>
{
    builder.BinaryProbability(verdict => verdict.BlueSky, "Does `answer` explain why the daytime sky appears blue?");
    builder.BinaryProbability(verdict => verdict.RedSunsets, "Does `answer` explain why sunsets appear red or orange?");
    builder.BinaryProbability(verdict => verdict.PlainLanguage, "Does `answer` use clear language suitable for a general audience?");
});

// A criterion is met when its probability is above this threshold. 0.5 is not calibrated for any task: a higher value
// accepts fewer answers that still miss a criterion, at the cost of more loop runs. Choose it on labeled examples of
// your own answers.
const double CriterionThreshold = 0.5;

// 2. The agent that writes the answers. Its instructions hold back part of the first answer, so the judge has a gap
// to find and the loop runs more than once.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent answerer = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential()).AsAIAgent(
    model: deploymentName,
    name: "Answerer",
    instructions: """
        You answer science questions for a general audience in one short paragraph.
        Your first answer is a single sentence about why the daytime sky is blue. It does not mention sunsets, even
        if the user asks about them.
        When feedback lists missing points, rewrite the whole answer so that it covers them too.
        """);

// 3. The judge. AIJudgeLoopEvaluator asks a chat client for JSON structured output, which a decision model does not
// write, so a DelegateLoopEvaluator asks the decision client the criteria questions instead. The state is the request
// and the latest answer.
using IDecisionClient judge = new JevDecisionClient(new ApiKeyCredential(typeSafeApiKey));
bool accepted = false;
var evaluator = new DelegateLoopEvaluator(async (context, cancellationToken) =>
{
    Console.WriteLine($"\nAnswer {context.Iteration}:\n{context.LastResponse.Text}");
    string request = string.Join("\n", context.InitialMessages.Select(message => message.Text));
    List<string> missing = await JudgeAsync(request, context.LastResponse.Text, cancellationToken);
    accepted = missing.Count == 0;

    // The feedback names the missing criteria, which is the gap analysis that a generative judge would write.
    return accepted
        ? LoopEvaluation.Stop()
        : LoopEvaluation.Continue($"Your answer does not yet: {string.Join("; ", missing)}. Rewrite the whole answer so that it does.");
});

// 4. The loop re-runs the agent until the judge stops it. MaxIterations bounds the cost if the answer never passes.
const int MaxIterations = 3;
const string Request = "Explain why the sky is blue and why sunsets are red.";
AIAgent loop = new LoopAgent(answerer, evaluator, new LoopAgentOptions { MaxIterations = MaxIterations, NonStreamingReturnsLastResponseOnly = true });
AgentResponse response = await loop.RunAsync(Request);

// LoopAgent stops at MaxIterations before it calls the evaluator, so an answer from the last allowed run has not been
// judged yet. Judging it here keeps the final answer from being presented as accepted when it may miss a criterion.
if (!accepted)
{
    Console.WriteLine($"\nAnswer {MaxIterations} (the last run the loop allows):\n{response.Text}");
    accepted = (await JudgeAsync(Request, response.Text, CancellationToken.None)).Count == 0;
}

Console.WriteLine(accepted ? "\nFinal answer:" : "\nFinal answer (some criteria are still missing):");
Console.WriteLine(response.Text);

// Asks the judge whether the answer meets each criterion, prints the probabilities, and returns the missing criteria.
async Task<List<string>> JudgeAsync(string request, string answer, CancellationToken cancellationToken)
{
    DecisionResponse<Verdict> decision = await judge.GetResponseAsync(new JudgedAnswer(request, answer), criteria, cancellationToken: cancellationToken);
    Verdict verdict = decision.Result;

    Console.WriteLine("Judge:");
    List<string> missing = [];
    foreach ((string name, string description, double probability) in new[]
    {
        ("blue_sky", "explain why the daytime sky appears blue", verdict.BlueSky),
        ("red_sunsets", "explain why sunsets appear red or orange", verdict.RedSunsets),
        ("plain_language", "use clear language suitable for a general audience", verdict.PlainLanguage),
    })
    {
        bool met = probability > CriterionThreshold;
        Console.WriteLine($"  {name}: {(met ? "met" : "missing")} (probability {probability:F2})");
        if (!met)
        {
            missing.Add(description);
        }
    }

    return missing;
}

/// <summary>The state the judge reads: the user's request and the answer to judge.</summary>
internal sealed record JudgedAnswer(string Request, string Answer);

/// <summary>The probability that the answer meets each criterion.</summary>
#pragma warning disable CA1812 // Instantiated by the decision definition, which creates the result from the answers.
internal sealed record Verdict(double BlueSky, double RedSunsets, double PlainLanguage);
#pragma warning restore CA1812
