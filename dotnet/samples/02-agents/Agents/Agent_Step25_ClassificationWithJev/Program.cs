// Copyright (c) Microsoft. All rights reserved.

// Classification with Jev — Give an agent a fast, calibrated classifier as a tool
//
// Jev, the TypeSafe System One model, does not write text: it answers typed questions
// (choice, score, noul) about a state and returns calibrated probabilities. This sample gives
// a support agent a Jev tool built with JevAIToolBuilder. The agent's model decides which
// questions to ask, Jev answers them, and the model writes the routing decision, sending
// uncertain tickets to a human. The second part answers the same tool with another client.

using System.ClientModel;
using System.Globalization;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.TypeSafe;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";
var typeSafeApiKey = Environment.GetEnvironmentVariable("TYPESAFE_API_KEY") ?? throw new InvalidOperationException("TYPESAFE_API_KEY is not set.");

// <create_jev_tool>
// The tool's arguments are a Jev request (the state plus typed questions) and its result is the Jev response.
AIFunction jev = new JevAIToolBuilder(new ApiKeyCredential(typeSafeApiKey)).Build();
// </create_jev_tool>

const string Instructions = """
    You triage customer support tickets. For every ticket, call ask_system_one once with the ticket text as the
    state and these questions:
    - "department": a choice between billing (payments, invoices, refunds), technical (bugs, outages, integrations),
      and sales (pricing, upgrades, new accounts).
    - "urgent": a noul asking whether the customer needs help urgently.
    - "frustration": a score with the rubric calm, annoyed, and angry.
    Then reply in one line with the department, whether it is urgent, and the frustration level. When the department
    confidence is below 0.6, say the ticket needs human review instead of naming a department.
    """;

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
var projectClient = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential());
AIAgent agent = projectClient.AsAIAgent(model: deploymentName, instructions: Instructions, name: "TicketTriage", tools: [jev]);

string[] tickets =
[
    "I've been trying to connect my Stripe account for 3 days and the integration keeps failing. I'm losing sales. Please help ASAP.",
    "Hi, could you send me a copy of last month's invoice when you get a chance? Thanks!",
    "I'd like to talk to someone about my account.",
];

foreach (string ticket in tickets)
{
    await TriageAsync(agent, ticket);
}

// <use_client>
// The same tool can be answered by another client. UseClient takes the client's operation and two mappers: one from
// the JevRequest that the model writes to the client's request, and one from the client's response to a JevResult.
// The tool resolves the client from the agent's services, in a new scope on every call, and checks the mapped result
// against the request before the model sees it.
AIFunction localJev = new JevAIToolBuilder()
    .UseClient<KeywordClassifier, ClassificationRequest, ClassificationResponse>(
        (classifier, request, cancellationToken) => classifier.ClassifyAsync(request, cancellationToken),
        inputMapper: ToClassificationRequest,
        outputMapper: ToJevResult)
    .Build();

using ServiceProvider services = new ServiceCollection()
    .AddSingleton<KeywordClassifier>()
    .BuildServiceProvider();
AIAgent localAgent = projectClient.AsAIAgent(
    model: deploymentName,
    instructions: Instructions,
    name: "LocalTicketTriage",
    tools: [localJev],
    services: services);
// </use_client>

Console.WriteLine("The same tool, answered by a local keyword classifier:");
Console.WriteLine();
await TriageAsync(localAgent, tickets[1]);

static async Task TriageAsync(AIAgent agent, string ticket)
{
    AgentResponse response = await agent.RunAsync(ticket);

    Console.WriteLine($"Ticket: {ticket}");
    foreach (FunctionResultContent result in response.Messages.SelectMany(static m => m.Contents).OfType<FunctionResultContent>())
    {
        Console.WriteLine($"Tool result: {result.Result}");
    }

    Console.WriteLine($"Agent: {response.Text}");
    Console.WriteLine();
}

// <mappers>
// Converts each Jev question into a classifier task. The options carry the words the classifier matches.
static ClassificationRequest ToClassificationRequest(JevRequest request) =>
    new(
        request.State.ToString(),
        [.. request.Questions.Select(question => question.Value switch
        {
            JevChoiceQuestion choice => new ClassificationTask(
                question.Key,
                ClassificationKind.PickOne,
                [.. choice.Criteria.Select(criterion => new ClassificationOption(criterion.Key, $"{criterion.Key} {criterion.Value}"))]),
            JevScoreQuestion score => new ClassificationTask(
                question.Key,
                ClassificationKind.Rate,
                [.. score.Criteria.Select((level, index) => new ClassificationOption(index.ToString(CultureInfo.InvariantCulture), level.ToString()))]),
            JevNoulQuestion noul => new ClassificationTask(
                question.Key,
                ClassificationKind.YesNo,
                [new ClassificationOption("yes", $"{noul.Instructions} {noul.Criteria?.True}"), new ClassificationOption("no", $"{noul.Criteria?.False}")]),
            _ => throw new NotSupportedException($"Question '{question.Key}' has an unknown type."),
        })]);

// Converts each classifier result back into the Jev answer of the same kind.
static JevResult ToJevResult(ClassificationResponse response) => new()
{
    Model = "local-keyword-classifier",
    Answers = response.Results.ToDictionary(result => result.Key, result => ToJevResponse(result.Value)),
    Usage = new JevUsage { InputTokens = 0, OutputTokens = 0 },
};

static JevResponse ToJevResponse(ClassificationResult result)
{
    ScoredOption best = result.Options.MaxBy(option => option.Probability)!;
    Dictionary<string, double> probabilities = result.Options.ToDictionary(option => option.Key, option => option.Probability);
    return result.Kind switch
    {
        ClassificationKind.PickOne => new JevChoiceResponse { Choice = best.Key, Confidence = best.Probability, Probabilities = probabilities },
        ClassificationKind.Rate => new JevScoreResponse
        {
            // Like Jev, the score is the expected value over the rubric, so it can fall between levels.
            Score = result.Options.Sum(option => int.Parse(option.Key, CultureInfo.InvariantCulture) * option.Probability),
            Confidence = best.Probability,
            Legend = result.Options.ToDictionary(option => option.Key, option => (JevEntry)option.Description),
            Probabilities = probabilities,
        },
        _ => new JevNoulResponse { Noul = probabilities["yes"] },
    };
}
// </mappers>
