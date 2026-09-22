// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates the DecisionLoopEvaluator: a LoopEvaluator that asks a decision-oriented model, through the
// provider-neutral IDecisionClient, for the probability that the original request has been fully addressed, instead of
// asking a generative chat model for a verdict plus prose. TypeSafe's Jev (System One) is the decision model, reached
// through the Microsoft.Agents.AI.TypeSafe provider package; the core framework has no dependency on it.
//
//   1. Decision-only loop — Jev judges completion after every iteration; the loop stops once the model-reported
//      probability reaches the completion threshold (DecisionLoopEvaluator). Because this agent answers one
//      sub-question per turn, the demo supplies a StateFactory that sends Jev every response so far instead of the
//      default latest-response-only projection.
//   2. Cheap-then-strong cascade — Jev runs first; while it says "incomplete" the expensive AI judge is skipped and
//      the agent runs again; once Jev says "complete" the AI judge verifies (and can still send the loop back with
//      a gap analysis). This uses existing LoopAgent ordering semantics: the first evaluator that asks to continue
//      wins, and the loop stops only when every evaluator stops (DecisionLoopEvaluator + AIJudgeLoopEvaluator).
//   3. Direct decisions — one IDecisionClient call with a mixed batch of binary, choice, and score questions, to
//      show the three primitives outside of a loop.
//
// The agent is deliberately instructed to answer only one sub-question per response so that the loop visibly needs
// several iterations to fully address a multi-part request.

#pragma warning disable MAAI001 // Suppress experimental API warnings for Agents AI experiments.

using System.ClientModel;
using System.Text.Json;
using Harness_Step06_DecisionLoop;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.TypeSafe;
using Microsoft.Extensions.AI;
using OpenAI;

// Primary agent + generative judge: OpenAI, or any OpenAI-compatible chat-completions endpoint (for example Bitdeer
// with zai-org/GLM-5.3-Flash) when OPENAI_COMPATIBLE_ENDPOINT is set.
// The key is tied to the endpoint: a compatible endpoint uses only OPENAI_COMPATIBLE_API_KEY, and OpenAI uses only
// OPENAI_API_KEY, so a credential for one service is never sent to the other.
var chatEndpoint = Environment.GetEnvironmentVariable("OPENAI_COMPATIBLE_ENDPOINT");
var chatApiKey = chatEndpoint is null
    ? Environment.GetEnvironmentVariable("OPENAI_API_KEY") ?? throw new InvalidOperationException("OPENAI_API_KEY is not set (or set OPENAI_COMPATIBLE_ENDPOINT and OPENAI_COMPATIBLE_API_KEY).")
    : Environment.GetEnvironmentVariable("OPENAI_COMPATIBLE_API_KEY") ?? throw new InvalidOperationException("OPENAI_COMPATIBLE_ENDPOINT is set but OPENAI_COMPATIBLE_API_KEY is not.");
var chatModel = Environment.GetEnvironmentVariable("OPENAI_COMPATIBLE_MODEL")
    ?? Environment.GetEnvironmentVariable("OPENAI_CHAT_MODEL_NAME")
    ?? "gpt-5.4-mini";

// Decision model: TypeSafe System One (Jev). TYPESAFE_API_KEY is required; TYPESAFE_MODEL optionally pins a version.
var typeSafeApiKey = Environment.GetEnvironmentVariable("TYPESAFE_API_KEY") ?? throw new InvalidOperationException("TYPESAFE_API_KEY is not set.");
var typeSafeModel = Environment.GetEnvironmentVariable("TYPESAFE_MODEL") ?? TypeSafeDecisionClientOptions.DefaultModelId;

// The HarnessAgent pre-configures function invocation, per-service-call chat history persistence, and
// context-window compaction. These bounds size the in-loop compaction window.
const int MaxContextWindowTokens = 400_000;
const int MaxOutputTokens = 16_000;

var openAIClient = chatEndpoint is null
    ? new OpenAIClient(chatApiKey)
    : new OpenAIClient(new ApiKeyCredential(chatApiKey), new OpenAIClientOptions { Endpoint = new Uri(chatEndpoint) });
IChatClient CreateChatClient() => openAIClient.GetChatClient(chatModel).AsIChatClient();

// The provider client implements IDecisionClient. It is wrapped in a small delegating client (defined at the bottom)
// that prints every binary answer, so the loop's decisions are visible on the console.
using var jev = new ConsoleObservingDecisionClient(new TypeSafeDecisionClient(typeSafeApiKey, new() { ModelId = typeSafeModel }));
Console.WriteLine($"Primary model: {chatModel} ({chatEndpoint ?? "OpenAI"}) · Decision model: {typeSafeModel} (TypeSafe System One)");

const string Task = "Explain why the sky is blue, why sunsets are red, and why clouds are white.";

await DecisionOnlyLoopAsync();
await CascadeLoopAsync();
await DirectDecisionsAsync();

// Pattern 1: Jev alone decides whether the request has been fully addressed.
async Task DecisionOnlyLoopAsync()
{
    Console.WriteLine("\n=== 1. Decision-only loop — Jev judges completion over all responses so far (threshold 0.90, max 5) ===");

    AIAgent loopAgent = new LoopAgent(
        CreateAnswerer(),
        new DecisionLoopEvaluator(
            jev,
            new DecisionLoopEvaluatorOptions
            {
                // A false stop returns an incomplete answer while a false continue only costs one more iteration,
                // so the threshold is deliberately high. It is application policy, not a property of the model.
                CompletionThreshold = 0.90,

                // The default projection judges only the latest response (like AIJudgeLoopEvaluator). This agent
                // spreads its answer across turns, so judge the accumulated responses instead. The factory keeps its
                // per-run list on the LoopContext, which is what keeps the evaluator itself stateless and shareable.
                StateFactory = CreateCumulativeState,
            }),
        new LoopAgentOptions { MaxIterations = 5 });

    AgentResponse response = await StreamLoopAsync(loopAgent, Task);
    Console.WriteLine($"\nFinal response:\n{response.Text}");
}

// Pattern 2: Jev first, strong generative judge only when Jev believes the work is complete.
async Task CascadeLoopAsync()
{
    Console.WriteLine("\n=== 2. Cheap-then-strong cascade — Jev, then AI judge verifies (max 6) ===");

    int judgeCalls = 0;
    var strongJudge = new AIJudgeLoopEvaluator(CreateChatClient());
    var countingJudge = new DelegateLoopEvaluator(async (context, cancellationToken) =>
    {
        judgeCalls++;
        Console.WriteLine("  [AI judge] Jev believes the work is complete; verifying with the generative judge...");
        LoopEvaluation verdict = await strongJudge.EvaluateAsync(context, cancellationToken);
        Console.WriteLine(verdict.ShouldReinvoke ? "  [AI judge] Not complete — sending gap analysis back to the agent." : "  [AI judge] Confirmed complete.");
        return verdict;
    });

    AIAgent loopAgent = new LoopAgent(
        CreateAnswerer(),
        [
            // Order matters: Jev goes first. When it says "incomplete" the loop continues immediately and the AI judge
            // is never consulted. When it says "complete" it returns Stop, which only means "no continuation requested",
            // so the AI judge runs next. A transient Jev failure (rate limit, overload, outage) defers to the AI judge;
            // a permanent one (rejected key, invalid request) still surfaces, because hiding it would only cost money.
            new DecisionLoopEvaluator(
                jev,
                new DecisionLoopEvaluatorOptions
                {
                    CompletionThreshold = 0.90,
                    TransientFailureBehavior = DecisionLoopFailureBehavior.DeferToNextEvaluator,
                }),
            countingJudge,
        ],
        new LoopAgentOptions { MaxIterations = 6 });

    AgentResponse response = await StreamLoopAsync(loopAgent, Task);
    Console.WriteLine($"\nFinal response:\n{response.Text}");
    Console.WriteLine($"\nGenerative judge calls: {judgeCalls} (a plain AI-judge loop would have called it after every iteration).");
}

// Pattern 3: the three decision primitives in one batched call, outside of any loop.
async Task DirectDecisionsAsync()
{
    Console.WriteLine("\n=== 3. Direct decisions — one call, three primitives ===");

    JsonElement state = JsonSerializer.SerializeToElement(new
    {
        ticket = "My flight was cancelled and nobody told me. I'm really frustrated. Can I get a refund?",
        policy = "Cancelled flights are eligible for a full refund.",
    });

    var request = new DecisionRequest(
        state,
        [
            new BinaryDecisionQuestion("refund_requested", "Does the customer request a refund?"),
            new ChoiceDecisionQuestion("request_type", "What is the customer's main request?",
            [
                new("refund", "The customer wants money returned."),
                new("rebooking", "The customer wants another flight."),
                new("information", "The customer only wants information."),
            ]),
            new ScoreDecisionQuestion("frustration", "How frustrated does the customer appear?",
            [
                new("Calm and neutral."),
                new("Concerned but civil."),
                new("Very angry or using strong language."),
            ]),
        ]);

    DecisionResponse response = await jev.GetResponseAsync(request);

    var refund = (BinaryDecisionAnswer)response.Answers["refund_requested"];
    var requestType = (ChoiceDecisionAnswer)response.Answers["request_type"];
    var frustration = (ScoreDecisionAnswer)response.Answers["frustration"];

    Console.WriteLine($"  model: {response.ModelId}, input tokens: {response.Usage?.InputTokenCount}");
    Console.WriteLine($"  refund_requested: P(true) = {refund.TrueProbability:F3}");
    Console.WriteLine($"  request_type:     {requestType.SelectedChoice} (confidence {requestType.Confidence:F2}) — " +
        string.Join(", ", requestType.Probabilities.Select(p => $"{p.Key} {p.Value:F2}")));
    Console.WriteLine($"  frustration:      score {frustration.Score:F2} on 0..2 (confidence {frustration.Confidence:F2}) — " +
        string.Join(", ", frustration.Probabilities.OrderBy(p => p.Key).Select(p => $"level {p.Key} {p.Value:F2}")));
}

// Builds the state Jev judges in pattern 1: the original request plus every response produced so far in this run.
// Per-run state lives in LoopContext.AdditionalProperties (owned by the run), never on the evaluator. Whatever the
// factory returns is sent to the decision provider, so keep it to what the question needs.
static JsonElement CreateCumulativeState(LoopContext context)
{
    const string ResponsesKey = "Harness_Step06_DecisionLoop.ResponsesSoFar";
    if (context.AdditionalProperties.TryGetValue(ResponsesKey, out object? existing) && existing is List<string> responses)
    {
        responses.Add(context.LastResponse.Text);
    }
    else
    {
        responses = [context.LastResponse.Text];
        context.AdditionalProperties[ResponsesKey] = responses;
    }

    return JsonSerializer.SerializeToElement(new
    {
        originalRequest = context.InitialMessages.Select(m => new { role = m.Role.Value, text = m.Text }),
        responsesSoFar = responses,
        iteration = context.Iteration,
    });
}

// Creates a lean HarnessAgent that answers one sub-question per turn so the loop has visible work to do.
AIAgent CreateAnswerer() =>
    CreateChatClient().AsHarnessAgent(new HarnessAgentOptions
    {
        Name = "answerer",
        MaxContextWindowTokens = MaxContextWindowTokens,
        MaxOutputTokens = MaxOutputTokens,
        DisableAgentModeProvider = true,
        DisableTodoProvider = true,
        DisableFileMemory = true,
        DisableWebSearch = true,
        ChatOptions = new ChatOptions
        {
            Instructions =
                """
                You are a helpful science explainer. The user may ask several questions at once. Answer exactly ONE
                of the not-yet-answered questions per response, in two or three sentences, and then stop. When you
                are asked to continue, answer the next unanswered question. Never answer more than one per response.
                """,
            MaxOutputTokens = MaxOutputTokens,
        },
    });

// Streams a loop run to the console, marking each new inner run with a "--- run N ---" header so you can see when
// the LoopAgent re-invokes the inner agent. Each message is prefixed with "User:" or "Agent:" based on its role, so
// the loop's on-behalf-of feedback (User) is visually distinct from the agent's responses (Agent).
static async Task<AgentResponse> StreamLoopAsync(AIAgent loopAgent, string input)
{
    string? currentResponseId = null;
    ChatRole? currentRole = null;
    var runCount = 0;
    var updates = new List<AgentResponseUpdate>();

    await foreach (var update in loopAgent.RunStreamingAsync(input))
    {
        if (update.ResponseId is { } responseId && responseId != currentResponseId)
        {
            currentResponseId = responseId;
            currentRole = null;
            Console.WriteLine($"\n--- run {++runCount} ---");
        }

        if (update.Role is { } role && role != currentRole)
        {
            currentRole = role;
            var prefix = role == ChatRole.User ? "User" : role == ChatRole.Assistant ? "Agent" : role.Value;
            Console.Write($"\n{prefix}: ");
        }

        Console.Write(update.Text);
        updates.Add(update);
    }

    Console.WriteLine();
    return updates.ToAgentResponse();
}
